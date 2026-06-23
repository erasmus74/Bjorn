"""ScopeChecker: enforces mode + blocklist + authorization gates.

Stages call this (via the executor wrapper) before doing any work.
The NLM also consults it during scheduling to skip ineligible work.
"""
from dataclasses import dataclass

from mjolnir.db.repositories.networks import Network


@dataclass(frozen=True)
class ScopeDecision:
    allowed: bool
    reason: str


class ScopeChecker:
    """Pure logic. No I/O. Tests cover every gate."""

    def check(
        self,
        global_mode: str,
        kill_switch_engaged: bool,
        stage_operates_in_view_only: bool,
        stage_requires_extra_auth: bool,
        network: Network,
        host_persistence_authorized: bool | None,
    ) -> ScopeDecision:
        if kill_switch_engaged:
            return ScopeDecision(False, "kill_switch_engaged")

        if global_mode == "view_only" and not stage_operates_in_view_only:
            return ScopeDecision(False, "view_only_mode_blocks_active_stage")

        if network.exhausted:
            return ScopeDecision(False, "network_exhausted")

        if network.scope_state == "blocklisted":
            return ScopeDecision(False, "network_blocklisted")

        if network.scope_state == "disabled":
            return ScopeDecision(False, "network_disabled")

        if stage_requires_extra_auth:
            if not network.persistence_authorized:
                return ScopeDecision(False, "missing network-level persistence authorization")
            if not host_persistence_authorized:
                return ScopeDecision(False, "missing host-level persistence authorization")

        return ScopeDecision(True, "allowed")
