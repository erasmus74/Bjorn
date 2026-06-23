"""AuditLogger: facade over ActionLogRepository for offensive-action logging.

Stages call this; they cannot bypass it because the NLM's run_stage_safely
wrapper (Plan 2) calls log_offensive_action() automatically.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mjolnir.db.repositories.action_log import ActionLogRepository
from mjolnir.db.repositories.system_state import SystemStateRepository


class ScopeBasis(Enum):
    """Closed vocabulary for the scope_basis column. See spec § Audit log."""
    OPERATOR_CONFIRMED_ACTIVE_MODE = "operator-confirmed-active-mode"
    OPERATOR_AUTHORIZED_NETWORK = "operator-authorized-network"
    OPERATOR_AUTHORIZED_HOST_PERSISTENCE = "operator-authorized-host-persistence"
    KILLED_BY_OPERATOR = "killed-by-operator"
    MODE_VIOLATION_ABORTED = "mode-violation-aborted"
    BLOCKLIST_VIOLATION_ABORTED = "blocklist-violation-aborted"


@dataclass
class AuditLogger:
    action_log: ActionLogRepository
    system_state: SystemStateRepository

    def log_offensive_action(
        self,
        scope_basis: ScopeBasis,
        action_type: str,
        outcome: str,
        stage_name: str | None = None,
        target_network_id: int | None = None,
        target_bssid: str | None = None,
        target_host_id: int | None = None,
        target_service_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write one audit row capturing global_mode at the moment of action."""
        global_mode = self.system_state.get_global_mode()
        basis_str = scope_basis.value
        if target_network_id is not None and scope_basis == ScopeBasis.OPERATOR_AUTHORIZED_NETWORK:
            basis_str = f"{basis_str}-N{target_network_id}"
        if target_host_id is not None and scope_basis == ScopeBasis.OPERATOR_AUTHORIZED_HOST_PERSISTENCE:
            basis_str = f"{basis_str}-H{target_host_id}"

        self.action_log.insert(
            global_mode=global_mode,
            scope_basis=basis_str,
            action_type=action_type,
            outcome=outcome,
            stage_name=stage_name,
            target_network_id=target_network_id,
            target_bssid=target_bssid,
            target_host_id=target_host_id,
            target_service_id=target_service_id,
            details=details,
        )

    def log_mode_transition(self, from_mode: str, to_mode: str,
                            scope_basis: ScopeBasis) -> None:
        self.action_log.insert(
            global_mode=to_mode,
            scope_basis=scope_basis.value,
            action_type="mode_transition",
            outcome="completed",
            details={"from": from_mode, "to": to_mode},
        )
