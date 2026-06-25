"""PassiveScanStage: periodic WiFi beacon observation."""
from dataclasses import replace
from typing import ClassVar

from mjolnir.interfaces.types import BssidObservation
from mjolnir.nlm.identity import IdentityResolver
from mjolnir.stages.base import (
    Checkpoint,
    CheckpointPolicy,
    InterfaceType,
    NetworkContext,
    ResourceProfile,
    Stage,
    StageResult,
)


def _normalize_obs(obs: BssidObservation) -> BssidObservation:
    """Normalize BSSID to lowercase so the UNIQUE(bssid) constraint works
    regardless of whether the source parser already lowercased it or not.
    SSID is preserved as-is (it is case-sensitive by spec)."""
    return replace(obs, bssid=obs.bssid.lower())


class PassiveScanStage(Stage):
    name: ClassVar[str] = "passive_scan"
    description: ClassVar[str] = "Periodic WiFi beacon observation via iw scan"
    resources: ClassVar[ResourceProfile] = ResourceProfile(
        interfaces=[InterfaceType.WIFI],
        is_rf_transmitting=False,
        cpu_weight="light",
        est_duration_seconds=5,
    )
    checkpoint_policy: ClassVar[CheckpointPolicy] = CheckpointPolicy.RESTART_SAFE
    operates_in_view_only: ClassVar[bool] = True
    # Passive scanning *discovers* networks; it runs unattached (no
    # specific network) and creates network rows as it observes beacons.
    is_discovery: ClassVar[bool] = True

    def __init__(self):
        self._resolver = IdentityResolver()

    def can_run(self, ctx: NetworkContext) -> bool:
        return True

    def run(self, ctx: NetworkContext, checkpoint: Checkpoint) -> StageResult:
        scan_result = ctx.interfaces.wifi.scan()

        if checkpoint.is_cancelled():
            return StageResult(status="failed", error="killed_before_processing")

        observations_by_ssid: dict[str, list] = {}
        for obs in scan_result.observations:
            normalized = _normalize_obs(obs)
            observations_by_ssid.setdefault(normalized.ssid, []).append(normalized)

        networks_seen = 0
        for ssid, obs_list in observations_by_ssid.items():
            if checkpoint.is_cancelled():
                return StageResult(status="failed", error="killed_mid_processing")

            existing_networks = self._existing_networks_for_ssid(ctx, ssid)
            observed_bssids = {obs.bssid for obs in obs_list}
            resolution = self._resolver.resolve(ssid, observed_bssids, existing_networks)

            if resolution.action == "extend":
                network_id = resolution.target_network_id
                ctx.db.networks.update_last_seen(network_id, scan_result.scanned_at)
            else:
                new_net = ctx.db.networks.create(
                    ssid=ssid,
                    security_type=obs_list[0].security_type,
                    first_seen=scan_result.scanned_at,
                )
                network_id = new_net.id
                ctx.db.networks.update_last_seen(network_id, scan_result.scanned_at)

            networks_seen += 1

            for obs in obs_list:
                if checkpoint.is_cancelled():
                    return StageResult(status="failed", error="killed_mid_write")
                bssid_row = ctx.db.bssids.upsert(
                    network_id=network_id,
                    bssid=obs.bssid,
                    security_type=obs.security_type,
                    channel=obs.channel,
                    signal_dbm=obs.signal_dbm,
                )
                ctx.db.bssid_sightings.record(
                    bssid_row.id,
                    signal_dbm=obs.signal_dbm,
                    channel=obs.channel,
                    when=scan_result.scanned_at,
                )

        return StageResult(
            status="succeeded",
            outputs={
                "observations_count": str(len(scan_result.observations)),
                "networks_seen_count": str(networks_seen),
            },
        )

    def _existing_networks_for_ssid(self, ctx: NetworkContext, ssid: str) -> list[dict]:
        networks = ctx.db.networks.find_by_ssid(ssid)
        result = []
        for net in networks:
            bssids_for_net = ctx.db.bssids.list_for_network(net.id)
            result.append({
                "id": net.id,
                "ssid": net.ssid,
                "bssids": {b.bssid for b in bssids_for_net},
            })
        return result
