"""ESS identity resolver: BSSID-overlap union-find.

When the device sees SSID X with BSSID set S, decide which existing
networks row to attach to (extend) or whether to create a new one.

Rule: any existing network with same SSID AND non-empty BSSID set
intersection gets considered. Pick the one with maximum intersection
size. If no overlap exists, create a new network with bumped disambiguator.
"""
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Resolution:
    action: Literal["create_new", "extend"]
    target_network_id: int | None


class IdentityResolver:
    """Pure-logic resolver. No DB access — callers pass in the existing networks."""

    def resolve(
        self,
        ssid: str,
        observed_bssids: set[str],
        existing_networks: list[dict[str, Any]],
    ) -> Resolution:
        if not observed_bssids:
            return Resolution(action="create_new", target_network_id=None)

        candidates: list[tuple[int, int]] = []
        for net in existing_networks:
            if net["ssid"] != ssid:
                continue
            overlap = len(observed_bssids & net["bssids"])
            if overlap > 0:
                candidates.append((net["id"], overlap))

        if not candidates:
            return Resolution(action="create_new", target_network_id=None)

        candidates.sort(key=lambda x: (-x[1], x[0]))
        target_id = candidates[0][0]
        return Resolution(action="extend", target_network_id=target_id)
