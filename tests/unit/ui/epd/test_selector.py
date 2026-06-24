"""Tests for the display state selector — the 14-state priority matrix."""
import pytest
from datetime import datetime, timezone

from mjolnir.ui.epd.selector import StateSelector, SystemConditions
from mjolnir.ui.epd.states import DisplayState


@pytest.fixture
def selector():
    return StateSelector()


def _conds(**overrides) -> SystemConditions:
    """Baseline conditions: a healthy, active, working system."""
    base = dict(
        starting_up=False,
        shutting_down=False,
        fatal_error=None,
        kill_switch_engaged=False,
        interfaces_up=True,
        networks_visible=True,
        known_networks_visible=True,
        connecting=False,
        internet_up=True,
        tailscale_up=True,
        active_work=True,
        global_mode="active",
        blocklisted_nearby=False,
        exhausted_in_range=[],
        view_only_networks_in_range=0,
    )
    base.update(overrides)
    return SystemConditions(**base)


def test_shutting_down_beats_everything(selector):
    state, _ = selector.select(_conds(shutting_down=True, kill_switch_engaged=True,
                                       fatal_error="disk full", starting_up=True))
    assert state == DisplayState.SHUTTING_DOWN


def test_starting_up_beats_everything_except_shutdown(selector):
    state, _ = selector.select(_conds(starting_up=True, kill_switch_engaged=True,
                                       fatal_error="x"))
    assert state == DisplayState.STARTING_UP


def test_fatal_error_beats_lower_priorities(selector):
    state, _ = selector.select(_conds(fatal_error="disk full", kill_switch_engaged=True))
    assert state == DisplayState.FATAL_ERROR


def test_kill_switch_engaged_beats_idle_states(selector):
    state, _ = selector.select(_conds(kill_switch_engaged=True,
                                       interfaces_up=False, networks_visible=False))
    assert state == DisplayState.KILL_SWITCH_ENGAGED


def test_no_interfaces_up(selector):
    state, _ = selector.select(_conds(interfaces_up=False))
    assert state == DisplayState.NO_INTERFACES_UP


def test_no_networks_visible(selector):
    state, _ = selector.select(_conds(networks_visible=False))
    assert state == DisplayState.NO_NETWORKS_VISIBLE


def test_no_known_networks_visible_when_in_active_mode(selector):
    """Active mode but only unknown networks in range → NO_KNOWN_NETWORKS."""
    state, _ = selector.select(_conds(known_networks_visible=False, active_work=False,
                                       global_mode="active"))
    assert state == DisplayState.NO_KNOWN_NETWORKS


def test_connecting(selector):
    state, _ = selector.select(_conds(connecting=True, active_work=False))
    assert state == DisplayState.CONNECTING


def test_no_internet(selector):
    state, _ = selector.select(_conds(internet_up=False, active_work=False))
    assert state == DisplayState.NO_INTERNET


def test_tailscale_down_when_internet_up(selector):
    state, _ = selector.select(_conds(internet_up=True, tailscale_up=False, active_work=False))
    assert state == DisplayState.TAILSCALE_DOWN


def test_active_idle_when_active_mode_no_work(selector):
    state, _ = selector.select(_conds(active_work=False, global_mode="active",
                                       exhausted_in_range=[("NetA", "all_stages_succeeded")]))
    assert state == DisplayState.ACTIVE_IDLE


def test_view_only_passive_when_view_only_mode(selector):
    state, _ = selector.select(_conds(active_work=False, global_mode="view_only",
                                       view_only_networks_in_range=5))
    assert state == DisplayState.VIEW_ONLY_PASSIVE


def test_active_working_when_there_is_work(selector):
    state, _ = selector.select(_conds(active_work=True))
    assert state == DisplayState.ACTIVE_WORKING


def test_blocklist_nearby_is_overlay_not_primary(selector):
    """BLOCKLIST_NEARBY is a banner overlay, not a primary state."""
    state, overlay = selector.select(_conds(active_work=True, blocklisted_nearby=True))
    assert state == DisplayState.ACTIVE_WORKING
    assert overlay is True


def test_blocklist_nearby_overlay_on_idle_states_too(selector):
    state, overlay = selector.select(_conds(active_work=False, global_mode="view_only",
                                             view_only_networks_in_range=3,
                                             blocklisted_nearby=True))
    assert state == DisplayState.VIEW_ONLY_PASSIVE
    assert overlay is True


def test_no_blocklist_overlay_when_flag_false(selector):
    state, overlay = selector.select(_conds(active_work=True, blocklisted_nearby=False))
    assert overlay is False
