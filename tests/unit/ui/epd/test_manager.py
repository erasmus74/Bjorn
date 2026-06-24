"""Tests for the DisplayManager."""
import pytest
from mjolnir.ui.epd.driver import FakeEPDDriver
from mjolnir.ui.epd.manager import DisplayManager
from mjolnir.ui.epd.selector import SystemConditions
from mjolnir.ui.epd.states import DisplayState


def _conds(**overrides) -> SystemConditions:
    base = dict(
        starting_up=False, shutting_down=False, fatal_error=None,
        kill_switch_engaged=False, interfaces_up=True, networks_visible=True,
        known_networks_visible=True, connecting=False, internet_up=True,
        tailscale_up=True, active_work=True, global_mode="active",
        blocklisted_nearby=False, exhausted_in_range=[],
        view_only_networks_in_range=0,
    )
    base.update(overrides)
    return SystemConditions(**base)


@pytest.fixture
def manager():
    driver = FakeEPDDriver(width=122, height=250)
    driver.init()
    return DisplayManager(driver=driver), driver


def test_manager_initial_display(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True))
    assert "display" in driver.calls
    assert driver.last_image is not None


def test_manager_skips_refresh_when_state_unchanged(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True))
    calls_before = len(driver.calls)
    mgr.update(_conds(active_work=True))  # same state
    assert len(driver.calls) == calls_before  # no new display call


def test_manager_refreshes_on_state_transition(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True))  # ACTIVE_WORKING
    calls_before = len(driver.calls)
    mgr.update(_conds(active_work=False, kill_switch_engaged=True))  # KILL_SWITCH_ENGAGED
    assert len(driver.calls) > calls_before  # new display call


def test_manager_refreshes_on_overlay_change(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True, blocklisted_nearby=False))
    calls_before = len(driver.calls)
    mgr.update(_conds(active_work=True, blocklisted_nearby=True))  # overlay added
    assert len(driver.calls) > calls_before


def test_manager_clears_on_shutdown(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True))
    mgr.shutdown()
    assert "clear" in driver.calls
    assert "sleep" in driver.calls


def test_manager_tracks_current_state(manager):
    mgr, _ = manager
    mgr.update(_conds(kill_switch_engaged=True))
    assert mgr.current_state == DisplayState.KILL_SWITCH_ENGAGED
