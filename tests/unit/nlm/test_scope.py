import pytest
from mjolnir.nlm.scope import ScopeChecker, ScopeDecision
from mjolnir.db.repositories.networks import Network


def _make_net(**overrides) -> Network:
    defaults = dict(
        id=1, ssid="X", disambiguator=1, security_type="WPA2",
        scope_state="enabled", blocklist_reason=None,
        scope_changed_at=None, scope_changed_by=None,
        current_stage=None, exhausted=0, exhausted_reason=None,
        persistence_authorized=0, persistence_authorized_at=None,
        persistence_authorized_by=None, operator_notes_summary=None,
        ess_color_tag=None, first_seen="2026-06-23T00:00:00Z", last_seen=None,
    )
    defaults.update(overrides)
    return Network(**defaults)


def test_view_only_mode_blocks_active_stage():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="view_only",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "view_only" in decision.reason


def test_view_only_mode_allows_view_only_stage():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="view_only",
        kill_switch_engaged=False,
        stage_operates_in_view_only=True,
        stage_requires_extra_auth=False,
        network=_make_net(),
        host_persistence_authorized=None,
    )
    assert decision.allowed is True


def test_kill_switch_blocks_everything():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=True,
        stage_operates_in_view_only=True,
        stage_requires_extra_auth=False,
        network=_make_net(),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "kill_switch" in decision.reason


def test_blocklisted_network_blocks_active_stages():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(scope_state="blocklisted"),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "blocklisted" in decision.reason


def test_disabled_network_blocks_active_stages():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(scope_state="disabled"),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "disabled" in decision.reason


def test_persistence_stage_requires_network_authorization():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=True,
        network=_make_net(persistence_authorized=0),
        host_persistence_authorized=True,
    )
    assert decision.allowed is False
    assert "network-level persistence" in decision.reason


def test_persistence_stage_requires_host_authorization():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=True,
        network=_make_net(persistence_authorized=1),
        host_persistence_authorized=False,
    )
    assert decision.allowed is False
    assert "host-level persistence" in decision.reason


def test_persistence_stage_allowed_when_both_tiers_authorized():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=True,
        network=_make_net(persistence_authorized=1),
        host_persistence_authorized=True,
    )
    assert decision.allowed is True


def test_normal_active_stage_allowed_happy_path():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(scope_state="enabled"),
        host_persistence_authorized=None,
    )
    assert decision.allowed is True


def test_exhausted_network_blocks_all_stages():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(exhausted=1),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "exhausted" in decision.reason
