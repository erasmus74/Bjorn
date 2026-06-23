"""Data types shared across interface implementations."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BssidObservation:
    """One row from a WiFi scan: a single AP sighting."""
    bssid: str
    ssid: str
    signal_dbm: int
    channel: int
    security_type: str | None  # 'WPA2', 'WPA3', 'WEP', 'open', None if unknown
    first_seen: str  # ISO-8601
    last_seen: str   # ISO-8601


@dataclass(frozen=True)
class ScanResult:
    """The output of a single WiFi scan call."""
    observations: list[BssidObservation]
    scanned_at: str  # ISO-8601
