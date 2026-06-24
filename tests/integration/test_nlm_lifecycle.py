# tests/integration/test_nlm_lifecycle.py
"""End-to-end: NLM runs a stub stage in a real subprocess, verifies DB updates."""
import multiprocessing as mp
from pathlib import Path

import pytest

from mjolnir.config import BjornConfig, DbConfig, NlmConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry


# Spec (docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md §Memory)
# documents 256 MB as the test-fixture floor: the forked subprocess inherits
# the parent's VM (~60 MB) before the stage even runs, plus sqlite3 + WAL
# cache. The production default (128 MB) is too tight for tests.
_TEST_MEM_LIMIT_MB = 256


class RecordingStage(Stage):
    """Writes a marker output to stage_outputs so we can verify it ran."""
    name = "recording_integration_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE
    operates_in_view_only = True

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        return StageResult(
            status="succeeded",
            outputs={"ran_in_subprocess": "yes", "network_id": str(ctx.network.id)},
        )


def _make_config(tmp_path: Path) -> BjornConfig:
    return BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path),
        nlm=NlmConfig(stage_memory_limit_mb=_TEST_MEM_LIMIT_MB),
    )


def test_nlm_runs_stage_in_subprocess_and_persists_outputs(tmp_path: Path, monkeypatch):
    # Setup DB with one network
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    net = bundle.networks.create(ssid="IntegrationNet")
    network_id = net.id
    conn.close()

    # Build NLM with our test stage
    reg = StageRegistry()
    reg.register(RecordingStage)

    # Patch the runner module's registry so the subprocess can find the stage
    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    cfg = _make_config(tmp_path)
    kill_switch = mp.Event()
    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=kill_switch,
    )

    executed = mgr.run_once()
    assert executed == 1

    # Verify DB reflects the run
    conn = factory.connect()
    bundle = bundle_for(conn)

    state = bundle.stage_states.get_or_create(network_id, "recording_integration_test_stage")
    assert state.status == "succeeded"
    assert state.attempts == 1

    outputs = bundle.stage_outputs.list_for_stage(network_id, "recording_integration_test_stage")
    assert outputs["ran_in_subprocess"] == "yes"
    assert outputs["network_id"] == str(network_id)

    conn.close()


def test_nlm_mode_change_filters_eligible_stages(tmp_path: Path, monkeypatch):
    """In view_only, only view_only stages are eligible."""
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    bundle.networks.create(ssid="X")
    conn.close()

    class ViewOnlyStage(Stage):
        name = "view_only_test_stage"
        description = "test"
        resources = ResourceProfile()
        checkpoint_policy = CheckpointPolicy.RESTART_SAFE
        operates_in_view_only = True

        def can_run(self, ctx):
            return True

        def run(self, ctx, checkpoint):
            return StageResult(status="succeeded")

    class ActiveOnlyStage(Stage):
        name = "active_only_test_stage"
        description = "test"
        resources = ResourceProfile()
        checkpoint_policy = CheckpointPolicy.RESTART_SAFE
        operates_in_view_only = False

        def can_run(self, ctx):
            return True

        def run(self, ctx, checkpoint):
            return StageResult(status="succeeded")

    reg = StageRegistry()
    reg.register(ViewOnlyStage)
    reg.register(ActiveOnlyStage)

    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    cfg = _make_config(tmp_path)

    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=mp.Event(),
    )

    # Default mode is view_only
    work = mgr.find_eligible_work()
    stage_names = {s.name for _, s in work}
    assert "view_only_test_stage" in stage_names
    assert "active_only_test_stage" not in stage_names

    # Toggle to active
    conn = factory.connect()
    bundle = bundle_for(conn)
    bundle.system_state.set_global_mode("active")
    conn.close()

    work = mgr.find_eligible_work()
    stage_names = {s.name for _, s in work}
    assert "view_only_test_stage" in stage_names
    assert "active_only_test_stage" in stage_names


def test_nlm_kill_switch_blocks_all_work(tmp_path: Path, monkeypatch):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    bundle.networks.create(ssid="X")
    conn.close()

    reg = StageRegistry()

    class AlwaysRunStage(Stage):
        name = "always_run_test_stage"
        description = "test"
        resources = ResourceProfile()
        checkpoint_policy = CheckpointPolicy.RESTART_SAFE
        operates_in_view_only = True

        def can_run(self, ctx):
            return True

        def run(self, ctx, checkpoint):
            return StageResult(status="succeeded")

    reg.register(AlwaysRunStage)

    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    cfg = _make_config(tmp_path)
    kill_switch = mp.Event()
    kill_switch.set()  # engaged

    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=kill_switch,
    )

    assert mgr.find_eligible_work() == []
    assert mgr.run_once() == 0
