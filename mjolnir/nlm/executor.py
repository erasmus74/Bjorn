"""StageExecutor: parent-side wrapper that runs stages in subprocesses.

Spawns a child process via multiprocessing.Process, sends result back
via Pipe, handles timeout and kill-switch cancellation.

The NLM's only path to running stages. Stages cannot bypass audit logging
because the NLM wraps every execute() call with log writes.
"""
import multiprocessing as mp
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from mjolnir.nlm.runner import run_stage_in_subprocess


# Use the "fork" start method explicitly. Stages register themselves into
# mjolnir.stages.registry.registry at module import time, and the NLM may
# mutate that registry during its lifetime (test fixtures do this too).
# fork guarantees the child sees the parent's current registry state.
# forkserver/spawn would re-import modules in a clean helper, losing any
# runtime registrations.
_CTX = mp.get_context("fork")

# Grace periods for cooperative shutdown.
_TERMINATE_GRACE_SECONDS = 2.0
_KILL_GRACE_SECONDS = 1.0


@dataclass
class ExecutionResult:
    status: Literal["succeeded", "failed", "permanently_failed", "partial"]
    error: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)


def _terminate_chain(proc: mp.Process) -> None:
    """SIGTERM, wait, then SIGKILL if still alive. Idempotent."""
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=_TERMINATE_GRACE_SECONDS)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=_KILL_GRACE_SECONDS)


class StageExecutor:
    """Runs stages in isolated subprocesses."""

    def __init__(self, db_path: Path, mem_limit_mb: int, kill_switch_event: Any):
        self.db_path = Path(db_path)
        self.mem_limit_mb = mem_limit_mb
        self.kill_switch_event = kill_switch_event

    def execute(
        self,
        stage_name: str,
        network_id: int,
        timeout_seconds: int,
    ) -> ExecutionResult:
        parent_conn, child_conn = _CTX.Pipe(duplex=False)
        proc = _CTX.Process(
            target=run_stage_in_subprocess,
            args=(
                stage_name,
                network_id,
                str(self.db_path),
                {},
                self.mem_limit_mb,
                child_conn,
            ),
        )
        proc.start()
        child_conn.close()

        # Watcher: signals when the kill switch engages. The cancel
        # message is best-effort — Plan 2a does not yet have a
        # pipe-reading cooperative-cancel thread inside the child, so
        # the parent must also terminate the child to make the kill
        # switch deterministic. Plan 2b will add cooperative cancel
        # propagation; the parent-side terminate remains as the
        # authoritative backstop.
        kill_engaged = {"value": False}

        def watch_kill_switch():
            while proc.is_alive() and not kill_engaged["value"]:
                if self.kill_switch_event.is_set():
                    kill_engaged["value"] = True
                    return
                time.sleep(0.05)

        watcher = threading.Thread(target=watch_kill_switch, daemon=True)
        watcher.start()

        deadline = time.monotonic() + timeout_seconds
        outcome: Literal["result", "timeout", "killed", "no_result"] = "no_result"
        result_msg: dict[str, Any] | None = None

        while True:
            # Child already produced a result message — fastest path out.
            if parent_conn.poll(0.1):
                result_msg = parent_conn.recv()
                outcome = "result"
                break

            # Kill switch tripped — terminate the child for a deterministic
            # cancellation. The cooperative cancel message would have been
            # sent in 2b; here we just SIGTERM/SIGKILL.
            if kill_engaged["value"] and proc.is_alive():
                _terminate_chain(proc)
                outcome = "killed"
                break

            # Hard timeout.
            if proc.is_alive() and time.monotonic() > deadline:
                _terminate_chain(proc)
                outcome = "timeout"
                break

            # Child died without writing to the pipe.
            if not proc.is_alive() and not parent_conn.poll(0):
                result_msg = {"type": "error", "error": f"subprocess_exited_code_{proc.exitcode}"}
                outcome = "result"
                break

        watcher.join(timeout=0.5)

        if outcome == "timeout":
            return ExecutionResult(status="failed", error=f"timeout_after_{timeout_seconds}s")
        if outcome == "killed":
            return ExecutionResult(status="failed", error="killed_by_operator")
        if result_msg is None:
            return ExecutionResult(status="failed", error="no_result_received")

        if result_msg.get("type") == "error":
            return ExecutionResult(status="failed", error=result_msg.get("error", "unknown_error"))

        return ExecutionResult(
            status=result_msg.get("status", "failed"),
            error=result_msg.get("error"),
            outputs=result_msg.get("outputs", {}),
        )
