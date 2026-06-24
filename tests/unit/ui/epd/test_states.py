"""Tests for the state renderers. Verify each produces a valid 122x250 image
with expected text content (where checkable)."""
import pytest
from PIL import Image

from mjolnir.ui.epd.states import (
    DisplayState,
    render_state,
    RENDER_WIDTH,
    RENDER_HEIGHT,
)
from mjolnir.ui.epd.selector import SystemConditions


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


def test_render_constants():
    assert RENDER_WIDTH == 122
    assert RENDER_HEIGHT == 250


def test_render_shutting_down():
    img = render_state(DisplayState.SHUTTING_DOWN, _conds(shutting_down=True))
    assert img.size == (122, 250)


def test_render_starting_up():
    img = render_state(DisplayState.STARTING_UP, _conds(starting_up=True))
    assert img.size == (122, 250)


def test_render_fatal_error_includes_message():
    img = render_state(DisplayState.FATAL_ERROR, _conds(fatal_error="disk full"))
    assert img.size == (122, 250)
    # The error message should be somewhere in the image (we can't easily OCR,
    # but we can verify the image isn't blank by checking pixel variance)
    pixels = list(img.getdata())
    assert len(set(pixels)) > 1, "image should not be blank"


def test_render_kill_switch_engaged():
    img = render_state(DisplayState.KILL_SWITCH_ENGAGED, _conds(kill_switch_engaged=True))
    assert img.size == (122, 250)


def test_render_no_interfaces_up():
    img = render_state(DisplayState.NO_INTERFACES_UP, _conds(interfaces_up=False))
    assert img.size == (122, 250)


def test_render_no_networks_visible():
    img = render_state(DisplayState.NO_NETWORKS_VISIBLE,
                       _conds(active_work=False, networks_visible=False, global_mode="active"))
    assert img.size == (122, 250)


def test_render_no_known_networks():
    img = render_state(DisplayState.NO_KNOWN_NETWORKS,
                        _conds(known_networks_visible=False, active_work=False, global_mode="active"))
    assert img.size == (122, 250)


def test_render_connecting():
    img = render_state(DisplayState.CONNECTING, _conds(connecting=True, active_work=False))
    assert img.size == (122, 250)


def test_render_no_internet():
    img = render_state(DisplayState.NO_INTERNET, _conds(internet_up=False, active_work=False))
    assert img.size == (122, 250)


def test_render_tailscale_down():
    img = render_state(DisplayState.TAILSCALE_DOWN,
                        _conds(internet_up=True, tailscale_up=False, active_work=False))
    assert img.size == (122, 250)


def test_render_active_idle():
    img = render_state(DisplayState.ACTIVE_IDLE,
                        _conds(active_work=False, global_mode="active",
                               exhausted_in_range=[("NetA", "all_stages_succeeded")]))
    assert img.size == (122, 250)


def test_render_view_only_passive():
    img = render_state(DisplayState.VIEW_ONLY_PASSIVE,
                        _conds(active_work=False, global_mode="view_only",
                               view_only_networks_in_range=5))
    assert img.size == (122, 250)


def test_render_active_working():
    img = render_state(DisplayState.ACTIVE_WORKING, _conds(active_work=True))
    assert img.size == (122, 250)


def test_render_with_blocklist_overlay():
    """Overlay should add a banner without changing base image dimensions."""
    img = render_state(DisplayState.ACTIVE_WORKING,
                        _conds(active_work=True, blocklisted_nearby=True),
                        overlay=True)
    assert img.size == (122, 250)


def test_every_state_renders_without_crash():
    """Smoke test: every DisplayState value can be rendered."""
    for state in DisplayState:
        img = render_state(state, _conds())
        assert img.size == (122, 250)
