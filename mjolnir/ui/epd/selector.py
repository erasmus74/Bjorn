"""StateSelector: pure-logic priority-based display state selection.

Given current SystemConditions, returns the highest-priority applicable
DisplayState plus whether the BLOCKLIST_NEARBY overlay should show.
No I/O, no hardware — exhaustively testable.
"""
from dataclasses import dataclass, field

from mjolnir.ui.epd.states import DisplayState


@dataclass(frozen=True)
class SystemConditions:
    """Inputs to the state selector. All fields must be set by the caller."""
    starting_up: bool
    shutting_down: bool
    fatal_error: str | None  # None = no error; string = error message
    kill_switch_engaged: bool
    interfaces_up: bool
    networks_visible: bool
    known_networks_visible: bool
    connecting: bool
    internet_up: bool
    tailscale_up: bool
    active_work: bool  # True if NLM has at least one runnable (network, stage) pair
    global_mode: str  # 'active' or 'view_only'
    blocklisted_nearby: bool
    exhausted_in_range: list[tuple[str, str]]  # [(ssid, reason), ...] for ACTIVE_IDLE display
    view_only_networks_in_range: int


@dataclass(frozen=True)
class Selection:
    state: DisplayState
    blocklist_overlay: bool


class StateSelector:
    """Evaluates conditions against the 14-state priority matrix."""

    def select(self, conditions: SystemConditions) -> tuple[DisplayState, bool]:
        # Priority order: check highest-priority conditions first
        if conditions.shutting_down:
            return self._with_overlay(DisplayState.SHUTTING_DOWN, conditions)

        if conditions.starting_up:
            return self._with_overlay(DisplayState.STARTING_UP, conditions)

        if conditions.fatal_error is not None:
            return self._with_overlay(DisplayState.FATAL_ERROR, conditions)

        if conditions.kill_switch_engaged:
            return self._with_overlay(DisplayState.KILL_SWITCH_ENGAGED, conditions)

        if not conditions.interfaces_up:
            return self._with_overlay(DisplayState.NO_INTERFACES_UP, conditions)

        if not conditions.networks_visible:
            return self._with_overlay(DisplayState.NO_NETWORKS_VISIBLE, conditions)

        if not conditions.known_networks_visible and not conditions.active_work:
            return self._with_overlay(DisplayState.NO_KNOWN_NETWORKS, conditions)

        if conditions.connecting and not conditions.active_work:
            return self._with_overlay(DisplayState.CONNECTING, conditions)

        if not conditions.internet_up and not conditions.active_work:
            return self._with_overlay(DisplayState.NO_INTERNET, conditions)

        if conditions.internet_up and not conditions.tailscale_up and not conditions.active_work:
            return self._with_overlay(DisplayState.TAILSCALE_DOWN, conditions)

        if conditions.active_work:
            return self._with_overlay(DisplayState.ACTIVE_WORKING, conditions)

        # No active work — pick idle state based on mode
        if conditions.global_mode == "active":
            return self._with_overlay(DisplayState.ACTIVE_IDLE, conditions)

        return self._with_overlay(DisplayState.VIEW_ONLY_PASSIVE, conditions)

    def _with_overlay(self, state: DisplayState,
                       conditions: SystemConditions) -> tuple[DisplayState, bool]:
        return state, conditions.blocklisted_nearby
