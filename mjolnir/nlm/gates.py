"""Data-availability gates for stage scheduling.

Each stage has prerequisites expressed as DB queries. The GateEvaluator
runs the relevant query for a given (stage_name, network_id) and returns
whether the stage is runnable now.

Stages not in the registry return GateResult(satisfied=False, reason='unknown_stage')
— fail-closed is safer than fail-open.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from mjolnir.db.repositories import RepositoryBundle

_STALE_THRESHOLD = timedelta(minutes=5)


@dataclass(frozen=True)
class GateResult:
    satisfied: bool
    reason: str


class GateEvaluator:
    """Evaluates stage-specific data-availability gates against current DB state."""

    def __init__(self, bundle: RepositoryBundle):
        self.bundle = bundle

    def evaluate(self, stage_name: str, network_id: int) -> GateResult:
        method = getattr(self, f"_gate_{stage_name}", None)
        if method is None:
            return GateResult(False, f"unknown_stage:{stage_name}")
        return method(network_id)

    def _gate_passive_scan(self, network_id: int) -> GateResult:
        return GateResult(True, "always_runnable")

    def _gate_wifi_probe(self, network_id: int) -> GateResult:
        net = self.bundle.networks.get_by_id(network_id)
        if net is None or net.last_seen is None:
            return GateResult(True, "never_seen_no_stale_check")
        try:
            last = datetime.fromisoformat(net.last_seen.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return GateResult(True, "unparseable_last_seen_no_stale_check")
        now = datetime.now(timezone.utc)
        if now - last > _STALE_THRESHOLD:
            return GateResult(False, f"stale_last_seen:{net.last_seen}")
        return GateResult(True, "recently_seen")

    def _gate_wifi_crack(self, network_id: int) -> GateResult:
        net = self.bundle.networks.get_by_id(network_id)
        if net is None:
            return GateResult(False, "network_not_found")
        if net.security_type == "open":
            return GateResult(False, "open_network_no_crack_needed")
        cursor = self.bundle.action_log.conn.execute(
            "SELECT COUNT(*) FROM credentials WHERE network_id = ? AND cred_type = 'wifi_psk'",
            (network_id,),
        )
        if cursor.fetchone()[0] > 0:
            return GateResult(False, "already_cracked")
        return GateResult(True, "encrypted_no_existing_psk")
