"""InProcessExecutor: runs stages in the calling process — no fork.

For tests and environments where subprocess isolation isn't needed.
Production uses StageExecutor (subprocess-per-stage with RLIMIT_AS
memory caps). The NLM accepts either via the `executor` parameter.

Why this exists: the subprocess executor uses fork() (Linux default
for multiprocessing), and forking from a multi-threaded test process
can deadlock (ADR 0001). The InProcessExecutor eliminates fork() from
the NLM test suite entirely while still exercising real stage logic
against a real DB — it's a test double for the execution strategy,
not for the stage itself.
"""
import threading
import time
from pathlib import Path
from typing import Any

from mjolnir.audit.logger import AuditLogger
from mjolnir.config import BjornConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.interfaces.manager import InterfaceManager
from mjolnir.nlm.executor import ExecutionResult
from mjolnir.stages.base import Checkpoint, NetworkContext
from mjolnir.stages.registry import StageRegistry


class InProcessExecutor:
    """Runs stages in the calling process. Same interface as StageExecutor."""

    def __init__(
        self,
        db_path: Path,
        registry: StageRegistry,
        kill_switch_event: Any,
    ):
        self.db_path = Path(db_path)
        self.registry = registry
        self.kill_switch_event = kill_switch_event

    def execute(
        self,
        stage_name: str,
        network_id: int | None,
        timeout_seconds: int,
    ) -> ExecutionResult:
        stage_cls = self.registry.get(stage_name)
        if stage_cls is None:
            return ExecutionResult(status="failed", error=f"stage not found: {stage_name}")

        try:
            factory = ConnectionFactory(db_path=self.db_path)
            conn = factory.connect()
            try:
                MigrationRunner(conn).initialize_fresh_db()
                bundle = bundle_for(conn)

                # network_id is None for discovery stages, which run
                # unattached and create network rows as side-effects.
                network = None
                if network_id is not None:
                    network = bundle.networks.get_by_id(network_id)
                    if network is None:
                        return ExecutionResult(
                            status="failed", error=f"network not found: {network_id}"
                        )

                audit = AuditLogger(
                    action_log=bundle.action_log,
                    system_state=bundle.system_state,
                )
                interfaces = InterfaceManager()
                checkpoint = Checkpoint()

                ctx = NetworkContext(
                    network=network,
                    db=bundle,
                    config=BjornConfig(),
                    interfaces=interfaces,
                    audit=audit,
                    workdir=self.db_path.parent / "stages" / str(network_id or "_discovery") / stage_name,
                    checkpoint=checkpoint,
                )

                # Cancellation: poll the kill-switch event in a daemon thread
                # and cancel the checkpoint when it fires. Same cooperative
                # semantics as the subprocess executor's pipe-watcher.
                #
                # The watcher MUST terminate when the stage finishes, not only
                # when cancelled — otherwise it leaks a live thread per run,
                # leaving the process multi-threaded. That defeats this
                # executor's entire purpose (ADR 0001: forking from a
                # multi-threaded process can deadlock the child) and breaks
                # any fork()-based test that runs afterward.
                watcher: threading.Thread | None = None
                watcher_stop = threading.Event()
                if self.kill_switch_event is not None:
                    def watch_kill_switch():
                        while not watcher_stop.is_set() and not checkpoint.is_cancelled():
                            if self.kill_switch_event.is_set():
                                checkpoint.cancel(reason="kill_switch")
                                return
                            watcher_stop.wait(0.05)

                    watcher = threading.Thread(target=watch_kill_switch, daemon=True)
                    watcher.start()

                try:
                    stage = stage_cls()
                    result = stage.run(ctx, checkpoint)
                finally:
                    # Signal the watcher to exit and wait for it, so this
                    # method returns with no lingering threads.
                    watcher_stop.set()
                    if watcher is not None:
                        watcher.join(timeout=1.0)

                return ExecutionResult(
                    status=result.status,
                    error=result.error,
                    outputs=result.outputs,
                )
            finally:
                conn.close()
        except Exception as e:
            return ExecutionResult(
                status="failed", error=f"{type(e).__name__}: {e}"
            )
