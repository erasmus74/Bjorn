"""Tests for StageExecutor. We use a real subprocess but with stub stages
registered in a test-only registry to verify the executor protocol."""

import pytest

pytestmark = pytest.mark.subprocess
import time
import pytest
import multiprocessing as mp

from mjolnir.nlm.executor import StageExecutor, ExecutionResult
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner


# RLIMIT_AS bounds the child's entire virtual address space — including
# the CPython interpreter, shared libs, and the sqlite3 mmap'd WAL —
# not just stage-allocated heap. A forked child inherits the parent's
# VM state, which on this stack measures ~60 MB before the stage even
# runs. 50 MB (the spec's nominal value) is below that floor and any
# mmap/brk in the child fails with what SQLite surfaces as "disk I/O
# error". 256 MB is the smallest power-of-two that consistently works
# in this environment while still exercising the setrlimit code path.
_TEST_MEM_LIMIT_MB = 256


class SucceedImmediatelyStage(Stage):
    name = "succeed_immediately_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        return StageResult(status="succeeded", outputs={"marker": "yes"})


class SlowStage(Stage):
    name = "slow_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        for _ in range(100):
            if checkpoint.is_cancelled():
                return StageResult(status="failed", error="killed_by_operator")
            time.sleep(0.05)
        return StageResult(status="succeeded")


@pytest.fixture
def executor_with_db(tmp_path, monkeypatch):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    from mjolnir.db.repositories import bundle_for
    bundle = bundle_for(conn)
    net = bundle.networks.create(ssid="TestNet")
    network_id = net.id
    conn.close()

    reg = StageRegistry()
    reg.register(SucceedImmediatelyStage)
    reg.register(SlowStage)

    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    executor = StageExecutor(
        db_path=tmp_path / "x.db",
        mem_limit_mb=_TEST_MEM_LIMIT_MB,
        kill_switch_event=mp.Event(),
    )
    return executor, network_id


def test_executor_returns_success_on_clean_run(executor_with_db):
    executor, network_id = executor_with_db
    result = executor.execute(
        stage_name="succeed_immediately_test_stage",
        network_id=network_id,
        timeout_seconds=10,
    )
    assert isinstance(result, ExecutionResult)
    assert result.status == "succeeded"
    assert result.outputs == {"marker": "yes"}
    assert result.error is None


def test_executor_returns_failed_on_cancellation(executor_with_db):
    executor, network_id = executor_with_db
    import threading
    def trigger():
        time.sleep(0.2)
        executor.kill_switch_event.set()
    threading.Thread(target=trigger, daemon=True).start()

    result = executor.execute(
        stage_name="slow_test_stage",
        network_id=network_id,
        timeout_seconds=10,
    )
    # Cancellation path: child either returns killed_by_operator OR is
    # terminated by parent. Either way, status is failed.
    assert result.status == "failed"


def test_executor_returns_failed_on_timeout(executor_with_db):
    executor, network_id = executor_with_db
    result = executor.execute(
        stage_name="slow_test_stage",
        network_id=network_id,
        timeout_seconds=1,
    )
    assert result.status == "failed"
    assert "timeout" in (result.error or "").lower()


def test_executor_returns_error_on_unknown_stage(executor_with_db):
    executor, network_id = executor_with_db
    result = executor.execute(
        stage_name="nonexistent_stage",
        network_id=network_id,
        timeout_seconds=5,
    )
    assert result.status == "failed"
    assert "not found" in (result.error or "").lower()
