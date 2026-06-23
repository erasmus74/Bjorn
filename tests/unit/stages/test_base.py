import pytest
from mjolnir.stages.base import (
    Stage, StageResult, ResourceProfile, CheckpointPolicy,
    InterfaceType, Checkpoint,
)


def test_stage_result_defaults():
    r = StageResult(status="succeeded")
    assert r.error is None
    assert r.outputs == {}
    assert r.retry_after_seconds is None


def test_resource_profile_defaults():
    rp = ResourceProfile()
    assert rp.interfaces == []
    assert rp.is_rf_transmitting is False
    assert rp.cpu_weight == "light"
    assert rp.est_duration_seconds == 60


def test_checkpoint_is_cancelled_initially_false():
    cp = Checkpoint()
    assert cp.is_cancelled() is False


def test_checkpoint_cancel_flips_to_true():
    cp = Checkpoint()
    cp.cancel(reason="kill switch")
    assert cp.is_cancelled() is True
    assert cp.cancel_reason == "kill switch"


def test_stage_is_abstract():
    with pytest.raises(TypeError):
        Stage()


def test_concrete_stage_subclass_works():
    class FakeStage(Stage):
        name = "fake"
        description = "test fixture"
        resources = ResourceProfile()
        checkpoint_policy = CheckpointPolicy.RESTART_SAFE

        def can_run(self, ctx):
            return True

        def run(self, ctx, checkpoint):
            return StageResult(status="succeeded")

    s = FakeStage()
    assert s.name == "fake"
    assert s.operates_in_view_only is False
    assert s.requires_extra_auth is False


def test_checkpoint_policy_enum_values():
    assert CheckpointPolicy.RESTART_SAFE.value == "restart_safe"
    assert CheckpointPolicy.CHECKPOINTABLE.value == "checkpointable"


def test_interface_type_enum_values():
    assert InterfaceType.WIFI.value == "wifi"
    assert InterfaceType.BLUETOOTH.value == "bluetooth"
    assert InterfaceType.BLE.value == "ble"
