"""Verifies that kill-switch activation propagates through the pipe to the
child's Checkpoint object, allowing cooperative cancellation."""
import time
import multiprocessing as mp
import pytest

from mjolnir.nlm.executor import StageExecutor
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner


class CooperativeCancelStage(Stage):
    """Polls checkpoint in a loop, exits cleanly when cancelled."""
    name = "cooperative_cancel_test_stage"
    description = "test"
    resources = ResourceProfile(est_duration_seconds=30)
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        for _ in range(600):  # up to 30 seconds
            if checkpoint.is_cancelled():
                return StageResult(status="failed", error="killed_by_operator_cooperative")
            time.sleep(0.05)
        return StageResult(status="succeeded")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    from mjolnir.db.repositories import bundle_for
    bundle = bundle_for(conn)
    net = bundle.networks.create(ssid="X")
    network_id = net.id
    conn.close()

    reg = StageRegistry()
    reg.register(CooperativeCancelStage)
    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    executor = StageExecutor(
        db_path=tmp_path / "x.db",
        mem_limit_mb=256,
        kill_switch_event=mp.Event(),
    )
    return executor, network_id


def test_cooperative_cancel_propagates_to_child(setup):
    """Kill switch set after 0.3s; child should exit cooperatively within 1s."""
    executor, network_id = setup

    import threading
    def trigger():
        time.sleep(0.3)
        executor.kill_switch_event.set()
    threading.Thread(target=trigger, daemon=True).start()

    result = executor.execute(
        stage_name="cooperative_cancel_test_stage",
        network_id=network_id,
        timeout_seconds=10,
    )

    assert result.status == "failed"
    assert "cooperative" in (result.error or "").lower(), (
        f"expected cooperative cancel, got: {result.error}"
    )
