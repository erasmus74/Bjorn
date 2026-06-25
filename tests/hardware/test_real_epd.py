"""Hardware-marked tests for the real e-Paper display.

Run with: pytest -m hardware
Requires:
- Real Pi Zero 2W with Waveshare 2.13" e-Paper HAT (V2 or V4) attached
- resources/waveshare_epd/ library importable
- SPI enabled on the Pi
"""
import time

import pytest

from mjolnir.ui.epd.driver import RealEPDDriver
from mjolnir.ui.epd.manager import DisplayManager
from mjolnir.ui.epd.selector import SystemConditions
from mjolnir.ui.epd.states import DisplayState, render_state


pytestmark = pytest.mark.hardware


def test_real_epd_initializes():
    """Sanity check: the EPD driver inits without error."""
    driver = RealEPDDriver()
    driver.init()
    driver.clear()
    driver.sleep()


def test_real_epd_renders_all_states():
    """Render every display state to the real EPD. Visual check on hardware."""
    driver = RealEPDDriver()
    driver.init()

    conditions = SystemConditions(
        starting_up=False, shutting_down=False, fatal_error="test error for visual check",
        kill_switch_engaged=False, interfaces_up=True, networks_visible=True,
        known_networks_visible=True, connecting=False, internet_up=True,
        tailscale_up=True, active_work=True, global_mode="active",
        blocklisted_nearby=False, exhausted_in_range=[("TestNet", "all_stages_succeeded")],
        view_only_networks_in_range=0,
    )

    for state in DisplayState:
        img = render_state(state, conditions)
        driver.display(img)
        time.sleep(2)  # let each render be visible

    driver.sleep()


def test_real_epd_display_manager_shutdown_clears():
    """DisplayManager.shutdown() clears the screen."""
    driver = RealEPDDriver()
    driver.init()
    mgr = DisplayManager(driver=driver)
    mgr.shutdown()
