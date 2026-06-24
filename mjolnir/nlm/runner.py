"""Subprocess entry point for stage execution.

Called by multiprocessing.Process in executor.py. Sets RLIMIT_AS for
memory isolation, constructs NetworkContext, runs the stage, sends
result back via pipe.
"""
import resource
import threading
from pathlib import Path
from typing import Any

from mjolnir.audit.logger import AuditLogger
from mjolnir.config import BjornConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.interfaces.manager import InterfaceManager
from mjolnir.stages.base import Checkpoint, NetworkContext
from mjolnir.stages.registry import registry


def _watch_pipe_for_cancel(pipe: Any, checkpoint: Checkpoint) -> None:
    """Daemon thread that polls the parent end of the pipe for cancel
    messages and propagates them to the Checkpoint token.

    The parent sends `{"cmd": "cancel"}` when the kill switch engages.
    Stages polling `checkpoint.is_cancelled()` see the cancellation and
    can exit cleanly, preserving any work-in-progress checkpoints.

    Returns when:
      - A cancel message is received (after setting the checkpoint).
      - The pipe is closed (EOFError / OSError) — parent went away.
      - Any unexpected error occurs — never crash the watcher.
    """
    while True:
        try:
            if not pipe.poll(0.1):
                continue
            msg = pipe.recv()
        except (EOFError, OSError):
            # Pipe closed by parent — nothing more to read.
            return
        except Exception:
            # Transient error (e.g. unpickling) — keep watching.
            continue

        if isinstance(msg, dict) and msg.get("cmd") == "cancel":
            checkpoint.cancel(reason="kill_switch")
            return


def run_stage_in_subprocess(
    stage_name: str,
    network_id: int,
    db_path: str,
    config_dict: dict[str, Any],
    mem_limit_mb: int,
    pipe: Any,
) -> None:
    """Entry point called in the child process.

    `pipe` is the child end of a multiprocessing.Pipe. We send:
      {"type": "result", "status": ..., "outputs": ..., "error": ...}
    or:
      {"type": "error", "error": "<message>"}
    """
    mem_bytes = mem_limit_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

    stage_cls = registry.get(stage_name)
    if stage_cls is None:
        pipe.send({"type": "error", "error": f"stage not found: {stage_name}"})
        return

    try:
        factory = ConnectionFactory(db_path=Path(db_path))
        conn = factory.connect()
        MigrationRunner(conn).initialize_fresh_db()
        bundle = bundle_for(conn)

        network = bundle.networks.get_by_id(network_id)
        if network is None:
            pipe.send({"type": "error", "error": f"network not found: {network_id}"})
            return

        audit = AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)
        interfaces = InterfaceManager()
        checkpoint = Checkpoint()
        ctx = NetworkContext(
            network=network,
            db=bundle,
            config=BjornConfig(),
            interfaces=interfaces,
            audit=audit,
            workdir=Path(db_path).parent / "stages" / str(network_id) / stage_name,
            checkpoint=checkpoint,
        )

        # Spawn a daemon thread that watches the pipe for cancel messages
        # from the parent. When received, sets checkpoint so stage.run()
        # can exit cooperatively at its next checkpoint poll.
        threading.Thread(
            target=_watch_pipe_for_cancel,
            args=(pipe, checkpoint),
            daemon=True,
        ).start()

        stage = stage_cls()
        result = stage.run(ctx, checkpoint)

        pipe.send({
            "type": "result",
            "status": result.status,
            "error": result.error,
            "outputs": result.outputs,
        })
    except Exception as e:
        pipe.send({"type": "error", "error": f"{type(e).__name__}: {e}"})
