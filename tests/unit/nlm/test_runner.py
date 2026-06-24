"""Tests for the subprocess entry point. We don't actually fork — we call
the runner function directly with a fake pipe and verify it does the
right thing."""
import pytest
from mjolnir.nlm.runner import run_stage_in_subprocess
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy


@pytest.fixture(autouse=True)
def _noop_setrlimit(monkeypatch):
    """Default: no-op the setrlimit call so the parent pytest process
    isn't constrained when the runner is invoked directly. Tests that
    need to verify the call (e.g. test_runner_sets_memory_limit) install
    their own patch, which overrides this autouse fixture.
    """
    monkeypatch.setattr(
        "mjolnir.nlm.runner.resource.setrlimit",
        lambda *_args, **_kwargs: None,
    )


class FakeStage(Stage):
    name = "fake_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        return StageResult(status="succeeded", outputs={"hello": "world"})


class FailingStage(Stage):
    name = "failing_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        raise RuntimeError("boom")


class FakePipe:
    """Two-ended pipe for testing."""
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)

    def poll(self):
        return False

    def recv(self):
        return None


def test_runner_executes_stage_and_sends_result(tmp_path):
    """Register a fake stage, call runner, verify result was sent."""
    from mjolnir.stages.registry import StageRegistry
    reg = StageRegistry()
    reg.register(FakeStage)

    pipe = FakePipe()
    import mjolnir.nlm.runner as runner_mod
    original_reg = runner_mod.registry
    runner_mod.registry = reg
    try:
        run_stage_in_subprocess(
            stage_name="fake_test_stage",
            network_id=1,
            db_path=str(tmp_path / "x.db"),
            config_dict={},
            mem_limit_mb=25,
            pipe=pipe,
        )
    finally:
        runner_mod.registry = original_reg

    # The fixture network doesn't exist in a fresh DB; runner should send
    # an error result, but we still expect a single sent message
    assert len(pipe.sent) == 1
    msg = pipe.sent[0]
    assert msg["type"] in ("result", "error")


def test_runner_with_seeded_network_succeeds(tmp_path):
    """End-to-end: seed a real network, run a stage, get the success result."""
    from mjolnir.stages.registry import StageRegistry
    from mjolnir.db.connection import ConnectionFactory
    from mjolnir.db.migrations import MigrationRunner
    from mjolnir.db.repositories import bundle_for

    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    net = bundle.networks.create(ssid="X")
    network_id = net.id
    conn.close()

    reg = StageRegistry()
    reg.register(FakeStage)

    pipe = FakePipe()
    import mjolnir.nlm.runner as runner_mod
    original_reg = runner_mod.registry
    runner_mod.registry = reg
    try:
        run_stage_in_subprocess(
            stage_name="fake_test_stage",
            network_id=network_id,
            db_path=str(tmp_path / "x.db"),
            config_dict={},
            mem_limit_mb=50,
            pipe=pipe,
        )
    finally:
        runner_mod.registry = original_reg

    assert len(pipe.sent) == 1
    result_msg = pipe.sent[0]
    assert result_msg["type"] == "result"
    assert result_msg["status"] == "succeeded"
    assert result_msg["outputs"] == {"hello": "world"}


def test_runner_sends_error_on_stage_exception(tmp_path):
    from mjolnir.stages.registry import StageRegistry
    from mjolnir.db.connection import ConnectionFactory
    from mjolnir.db.migrations import MigrationRunner
    from mjolnir.db.repositories import bundle_for

    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    net = bundle.networks.create(ssid="X")
    network_id = net.id
    conn.close()

    reg = StageRegistry()
    reg.register(FailingStage)

    pipe = FakePipe()
    import mjolnir.nlm.runner as runner_mod
    original_reg = runner_mod.registry
    runner_mod.registry = reg
    try:
        run_stage_in_subprocess(
            stage_name="failing_test_stage",
            network_id=network_id,
            db_path=str(tmp_path / "x.db"),
            config_dict={},
            mem_limit_mb=50,
            pipe=pipe,
        )
    finally:
        runner_mod.registry = original_reg

    assert len(pipe.sent) == 1
    result_msg = pipe.sent[0]
    assert result_msg["type"] == "error"
    assert "boom" in result_msg["error"]


def test_runner_unknown_stage_sends_error(tmp_path):
    pipe = FakePipe()
    run_stage_in_subprocess(
        stage_name="nonexistent",
        network_id=1,
        db_path=str(tmp_path / "x.db"),
        config_dict={},
        mem_limit_mb=25,
        pipe=pipe,
    )
    assert len(pipe.sent) == 1
    assert pipe.sent[0]["type"] == "error"
    assert "not found" in pipe.sent[0]["error"]


def test_runner_sets_memory_limit(tmp_path, monkeypatch):
    """Verify RLIMIT_AS is called in the subprocess entry."""
    import resource
    called = {"limits": None}

    def fake_setrlimit(resource_id, limits):
        called["limits"] = (resource_id, limits)

    monkeypatch.setattr("mjolnir.nlm.runner.resource.setrlimit", fake_setrlimit)

    from mjolnir.stages.registry import StageRegistry
    reg = StageRegistry()
    reg.register(FakeStage)

    pipe = FakePipe()
    import mjolnir.nlm.runner as runner_mod
    original_reg = runner_mod.registry
    runner_mod.registry = reg
    try:
        run_stage_in_subprocess(
            stage_name="fake_test_stage",
            network_id=1,
            db_path=str(tmp_path / "x.db"),
            config_dict={},
            mem_limit_mb=25,
            pipe=pipe,
        )
    finally:
        runner_mod.registry = original_reg

    assert called["limits"] is not None
    assert called["limits"][0] == resource.RLIMIT_AS
    assert called["limits"][1][0] == 25 * 1024 * 1024
