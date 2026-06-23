import pytest

from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry


def make_stage(name: str, operates_in_view_only: bool = False):
    # Use default-arg capture so the closure variable is visible inside the
    # class body (Python class bodies don't see enclosing function locals
    # directly when there's an assignment to the same name at class scope).
    def _make(vio=operates_in_view_only):
        class _S(Stage):
            resources = ResourceProfile()
            checkpoint_policy = CheckpointPolicy.RESTART_SAFE
            operates_in_view_only = vio

            def can_run(self, ctx):
                return True

            def run(self, ctx, checkpoint):
                return StageResult(status="succeeded")

        _S.name = name
        _S.description = f"test stage {name}"
        return _S

    return _make()


def test_register_stores_class_by_name():
    reg = StageRegistry()
    s = make_stage("alpha")
    reg.register(s)
    assert reg.get("alpha") is s


def test_register_returns_class_for_decorator_use():
    reg = StageRegistry()
    s = make_stage("beta")
    returned = reg.register(s)
    assert returned is s


def test_get_missing_returns_none():
    reg = StageRegistry()
    assert reg.get("nope") is None


def test_all_stages_returns_list():
    reg = StageRegistry()
    reg.register(make_stage("a"))
    reg.register(make_stage("b"))
    names = sorted(s.name for s in reg.all_stages())
    assert names == ["a", "b"]


def test_register_duplicate_name_overwrites():
    reg = StageRegistry()
    reg.register(make_stage("dup"))
    reg.register(make_stage("dup"))
    assert len(reg.all_stages()) == 1


def test_all_stages_empty_when_no_registrations():
    reg = StageRegistry()
    assert reg.all_stages() == []


def test_stages_eligible_for_view_only():
    reg = StageRegistry()
    reg.register(make_stage("passive", operates_in_view_only=True))
    reg.register(make_stage("active_only", operates_in_view_only=False))
    eligible = reg.stages_eligible_for_mode("view_only")
    names = {s.name for s in eligible}
    assert names == {"passive"}


def test_stages_eligible_for_active_returns_all():
    reg = StageRegistry()
    reg.register(make_stage("a"))
    reg.register(make_stage("b"))
    assert len(reg.stages_eligible_for_mode("active")) == 2


def test_stages_eligible_for_invalid_mode_raises():
    reg = StageRegistry()
    with pytest.raises(ValueError):
        reg.stages_eligible_for_mode("weird")
