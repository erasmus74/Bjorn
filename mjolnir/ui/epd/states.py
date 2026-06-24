"""Display states for the e-Paper UI.

14 primary states with a strict priority order (highest first), plus one
overlay banner (BLOCKLIST_NEARBY) that can appear on top of any primary
state. See spec § E-Paper display.
"""
from enum import IntEnum


class DisplayState(IntEnum):
    """Priority-ordered display states. Lower number = higher priority."""
    SHUTTING_DOWN = 1
    STARTING_UP = 2
    FATAL_ERROR = 3
    KILL_SWITCH_ENGAGED = 4
    NO_INTERFACES_UP = 5
    NO_NETWORKS_VISIBLE = 6
    NO_KNOWN_NETWORKS = 7
    CONNECTING = 8
    NO_INTERNET = 9
    TAILSCALE_DOWN = 10
    ACTIVE_IDLE = 11
    VIEW_ONLY_PASSIVE = 12
    ACTIVE_WORKING = 13
    # Note: BLOCKLIST_NEARBY is handled separately as an overlay, not a primary state
