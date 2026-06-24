"""Collect SystemConditions from DB state.

Bridges the NLM's DB state and the display selector. Reads mode, kill
switch, networks, exhausted networks, blocklisted networks.
"""
import subprocess

from mjolnir.db.repositories import RepositoryBundle
from mjolnir.ui.epd.selector import SystemConditions


def _interfaces_up() -> bool:
    """Check if wlan0 (or configured interface) exists and is up."""
    try:
        result = subprocess.run(
            ["ip", "link", "show", "wlan0"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return result.returncode == 0 and "state UP" in result.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        # In CI/tests, ip may not exist or wlan0 won't — treat as not-up
        # so tests don't depend on host networking. Override in tests.
        return False


def collect_conditions(bundle: RepositoryBundle,
                        kill_switch_event_set: bool,
                        interfaces_up_override: bool | None = None) -> SystemConditions:
    """Build SystemConditions from current DB + runtime state.

    `interfaces_up_override` lets callers force the interface state
    (used in tests where `ip` isn't available).
    """
    global_mode = bundle.system_state.get_global_mode()
    kill_switch_engaged = (bundle.system_state.is_kill_switch_engaged()
                            or kill_switch_event_set)

    networks = bundle.networks.list_eligible_for_processing()
    networks_visible = len(networks) > 0

    exhausted = [(n.ssid, n.exhausted_reason or "unknown")
                 for n in networks if n.exhausted]
    # Also include exhausted networks that are scope_state=enabled but done
    cursor = bundle.networks.conn.execute(
        "SELECT ssid, exhausted_reason FROM networks WHERE exhausted = 1"
    )
    exhausted = [(row["ssid"], row["exhausted_reason"] or "unknown")
                 for row in cursor.fetchall()]

    cursor = bundle.networks.conn.execute(
        "SELECT COUNT(*) FROM networks WHERE scope_state = 'blocklisted'"
    )
    blocklisted_nearby = cursor.fetchone()[0] > 0

    interfaces_up = interfaces_up_override if interfaces_up_override is not None else _interfaces_up()

    return SystemConditions(
        starting_up=False,  # caller sets this explicitly during boot
        shutting_down=False,  # caller sets this during shutdown
        fatal_error=None,  # caller sets this if a fatal error occurred
        kill_switch_engaged=kill_switch_engaged,
        interfaces_up=interfaces_up,
        networks_visible=networks_visible,
        known_networks_visible=networks_visible,  # simplification: any network counts
        connecting=False,  # caller sets during connection phases
        internet_up=True,  # caller sets after connectivity check
        tailscale_up=True,  # caller sets after tailscale check (sub-project #1)
        active_work=networks_visible and not kill_switch_engaged,
        global_mode=global_mode,
        blocklisted_nearby=blocklisted_nearby,
        exhausted_in_range=exhausted,
        view_only_networks_in_range=len(networks) if global_mode == "view_only" else 0,
    )
