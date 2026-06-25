"""Tests for InProcessExecutor thread hygiene.

The InProcessExecutor exists specifically to keep the NLM test process
single-threaded (ADR 0001: forking from a multi-threaded process can
deadlock the child). If its own kill-switch watcher thread leaks past
the stage's completion, the process becomes multi-threaded and a later
fork()-based subprocess test can fail. These tests guard that contract.
"""
import multiprocessing as mp
import threading
import time
from pathlib import Path

from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.nlm.in_process_executor import InProcessExecutor
from mjolnir.stages.base import (
    CheckpointPolicy,
    ResourceProfile,
    Stage,
    StageResult,
)
from mjolnir.stages.registry import StageRegistry


class _SucceedStage(Stage):
    name = "succeed_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE
    operates_in_view_only = True

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        return StageResult(status="succeeded")


def _seed_db(tmp_path: Path) -> Path:
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    network_id = bundle.networks.create(ssid="N").id
    conn.close()
    return network_id


def test_executor_leaks_no_thread_after_success(tmp_path):
    network_id = _seed_db(tmp_path)
    reg = StageRegistry()
    reg.register(_SucceedStage)

    before = threading.active_count()
    executor = InProcessExecutor(
        db_path=tmp_path / "x.db", registry=reg, kill_switch_event=mp.Event()
    )
    result = executor.execute("succeed_stage", network_id, timeout_seconds=30)
    assert result.status == "succeeded"

    # Give any (incorrectly) lingering daemon thread a chance to be counted.
    time.sleep(0.2)
    after = threading.active_count()
    assert after == before, (
        f"watcher thread leaked: {before} -> {after} "
        f"({[t.name for t in threading.enumerate()]})"
    )
