"""Subprocess entry point for stage execution.

Called by multiprocessing.Process in executor.py. Sets RLIMIT_AS for
memory isolation, constructs NetworkContext, runs the stage, sends
result back via pipe.
"""
import resource
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
