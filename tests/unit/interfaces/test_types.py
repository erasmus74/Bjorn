from datetime import datetime, timezone
from mjolnir.interfaces.types import BssidObservation, ScanResult


def test_bssidobservation_basic_fields():
    obs = BssidObservation(
        bssid="AA:BB:CC:DD:EE:01",
        ssid="TestNet",
        signal_dbm=-42,
        channel=6,
        security_type="WPA2",
        first_seen="2026-06-23T10:00:00Z",
        last_seen="2026-06-23T10:00:00Z",
    )
    assert obs.bssid == "AA:BB:CC:DD:EE:01"
    assert obs.signal_dbm == -42
    assert obs.security_type == "WPA2"


def test_scanresult_contains_observations():
    obs1 = BssidObservation(
        bssid="AA:BB:CC:DD:EE:01", ssid="X", signal_dbm=-42, channel=6,
        security_type="WPA2",
        first_seen="2026-06-23T10:00:00Z", last_seen="2026-06-23T10:00:00Z",
    )
    obs2 = BssidObservation(
        bssid="AA:BB:CC:DD:EE:02", ssid="X", signal_dbm=-55, channel=6,
        security_type="WPA2",
        first_seen="2026-06-23T10:00:00Z", last_seen="2026-06-23T10:00:00Z",
    )
    result = ScanResult(observations=[obs1, obs2], scanned_at="2026-06-23T10:00:00Z")
    assert len(result.observations) == 2
    assert result.observations[0].bssid == "AA:BB:CC:DD:EE:01"


def test_bssidobservation_security_type_allows_none():
    obs = BssidObservation(
        bssid="AA:BB:CC:DD:EE:01", ssid="X", signal_dbm=-42, channel=6,
        security_type=None,
        first_seen="2026-06-23T10:00:00Z", last_seen="2026-06-23T10:00:00Z",
    )
    assert obs.security_type is None
