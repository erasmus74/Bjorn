"""Tests for the NLM main loop. Uses stub stages + the real DB layer."""
import pytest
import multiprocessing as mp

from mjolnir.nlm.in_process_executor import InProcessExecutor
from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry
from mjolnir.config import BjornConfig, DbConfig, NlmConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


# Spec (docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md §Memory)
# documents 256 MB as the test-fixture floor: the forked subprocess inherits
# the parent's VM (~60 MB) before the stage even runs, plus sqlite3 + WAL
# cache. The production default (128 MB) is too tight for tests.
_TEST_MEM_LIMIT_MB = 256


class CountingStage(Stage):
    """Records each invocation via class-level counter."""
    name = "counting_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE
    operates_in_view_only = True

    invocations = 0

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        CountingStage.invocations += 1
        return StageResult(status="succeeded", outputs={"count": str(CountingStage.invocations)})


@pytest.fixture
def manager(tmp_path, monkeypatch):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    bundle.networks.create(ssid="TestNet")
    conn.close()

    reg = StageRegistry()
    reg.register(CountingStage)
    CountingStage.invocations = 0

    # Patch the runner module to use our test registry
    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path),
        nlm=NlmConfig(stage_memory_limit_mb=_TEST_MEM_LIMIT_MB),
    )

    __ks = mp.Event()
    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=__ks,
        executor=InProcessExecutor(db_path=tmp_path / "x.db", registry=reg, kill_switch_event=__ks),
    )
    return mgr


def test_manager_constructs(manager):
    assert manager.registry is not None
    assert manager.scope_checker is not None
    assert manager.gate_evaluator is not None


def test_find_eligible_work_returns_pending_work(manager):
    """In view_only mode with a network present and a view-only stage,
    find_eligible_work returns at least one (network, stage) pair."""
    work = manager.find_eligible_work()
    assert len(work) >= 1
    stage_names = {s.name for _, s in work}
    assert "counting_test_stage" in stage_names


def test_find_eligible_work_empty_when_no_networks(tmp_path, monkeypatch):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()

    reg = StageRegistry()
    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path),
        nlm=NlmConfig(stage_memory_limit_mb=_TEST_MEM_LIMIT_MB),
    )
    __ks = mp.Event()
    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=__ks,
        executor=InProcessExecutor(db_path=tmp_path / "x.db", registry=reg, kill_switch_event=__ks),
    )
    work = mgr.find_eligible_work()
    assert work == []


def test_find_eligible_work_filters_blocklisted(manager):
    # Blocklist the existing network
    factory = ConnectionFactory(db_path=manager.db_path)
    conn = factory.connect()
    bundle = bundle_for(conn)
    net = bundle.networks.list_eligible_for_processing()[0]
    bundle.networks.update_scope_state(net.id, "blocklisted", reason="test", by="op")
    conn.close()

    work = manager.find_eligible_work()
    assert work == []


def test_run_once_executes_eligible_work(manager):
    """Single pass of the main loop: find work, execute one stage.

    Subprocess isolation means the parent cannot observe the stage's
    class-level counter (fork is copy-on-write). Instead, verify via the
    DB side-effects: stage_outputs written + stage_states marked succeeded.
    """
    executed = manager.run_once()
    assert executed == 1

    factory = ConnectionFactory(db_path=manager.db_path)
    conn = factory.connect()
    try:
        bundle = bundle_for(conn)
        # The CountingStage writes {"count": "<n>"} to stage_outputs.
        outputs = bundle.stage_outputs.list_for_stage(
            network_id=1, stage_name="counting_test_stage"
        )
        assert "count" in outputs
        # And the stage's run-state should be "succeeded".
        state = bundle.stage_states.get_or_create(
            network_id=1, stage_name="counting_test_stage"
        )
        assert state.status == "succeeded"
    finally:
        conn.close()


def test_run_once_with_no_work_does_nothing(manager):
    """If no eligible work, run_once completes without invoking stages."""
    factory = ConnectionFactory(db_path=manager.db_path)
    conn = factory.connect()
    bundle = bundle_for(conn)
    net = bundle.networks.list_eligible_for_processing()[0]
    bundle.networks.update_scope_state(net.id, "blocklisted", reason="test", by="op")
    conn.close()

    executed = manager.run_once()
    assert executed == 0

    # Verify no outputs were written for the stage.
    factory = ConnectionFactory(db_path=manager.db_path)
    conn = factory.connect()
    try:
        bundle = bundle_for(conn)
        outputs = bundle.stage_outputs.list_for_stage(
            network_id=1, stage_name="counting_test_stage"
        )
        assert outputs == {}
    finally:
        conn.close()


def test_kill_switch_prevents_new_work(manager):
    manager.kill_switch_event.set()
    work = manager.find_eligible_work()
    assert work == []
