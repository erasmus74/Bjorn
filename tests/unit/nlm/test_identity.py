import pytest
from mjolnir.nlm.identity import IdentityResolver, Resolution


@pytest.fixture
def resolver():
    return IdentityResolver()


def test_resolve_with_no_existing_networks_creates_new(resolver):
    """No prior networks with this SSID → must create a new one."""
    res = resolver.resolve(ssid="X", observed_bssids={"AA:BB:CC:DD:EE:01"},
                            existing_networks=[])
    assert res.action == "create_new"
    assert res.target_network_id is None


def test_resolve_with_overlapping_bssid_merges(resolver):
    """SSID matches an existing network AND BSSID sets overlap → extend it."""
    existing = [
        {"id": 1, "ssid": "X", "bssids": {"AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"}},
    ]
    res = resolver.resolve(ssid="X",
                            observed_bssids={"AA:BB:CC:DD:EE:02", "AA:BB:CC:DD:EE:03"},
                            existing_networks=existing)
    assert res.action == "extend"
    assert res.target_network_id == 1


def test_resolve_with_no_overlap_creates_new_disambiguator(resolver):
    """SSID matches but BSSID sets disjoint → new network with bumped disambiguator."""
    existing = [
        {"id": 1, "ssid": "X", "bssids": {"AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"}},
    ]
    res = resolver.resolve(ssid="X",
                            observed_bssids={"FF:FF:FF:FF:FF:01", "FF:FF:FF:FF:FF:02"},
                            existing_networks=existing)
    assert res.action == "create_new"
    assert res.target_network_id is None


def test_resolve_picks_max_overlap_when_multiple_match(resolver):
    """If multiple existing networks share the SSID, pick the one with most overlaps."""
    existing = [
        {"id": 1, "ssid": "X", "bssids": {"AA:BB:CC:DD:EE:01"}},
        {"id": 2, "ssid": "X", "bssids": {"AA:BB:CC:DD:EE:02", "AA:BB:CC:DD:EE:03", "AA:BB:CC:DD:EE:04"}},
    ]
    res = resolver.resolve(ssid="X",
                            observed_bssids={"AA:BB:CC:DD:EE:03", "AA:BB:CC:DD:EE:04", "AA:BB:CC:DD:EE:05"},
                            existing_networks=existing)
    assert res.action == "extend"
    assert res.target_network_id == 2


def test_resolve_with_empty_observed_bssids_creates_new(resolver):
    """No observed BSSIDs is degenerate; create_new to be safe."""
    res = resolver.resolve(ssid="X", observed_bssids=set(),
                            existing_networks=[])
    assert res.action == "create_new"


def test_resolve_ignores_networks_with_different_ssid(resolver):
    """Different SSIDs never merge, even with BSSID overlap (which would be unusual)."""
    existing = [
        {"id": 1, "ssid": "Y", "bssids": {"AA:BB:CC:DD:EE:01"}},
    ]
    res = resolver.resolve(ssid="X",
                            observed_bssids={"AA:BB:CC:DD:EE:01"},
                            existing_networks=existing)
    assert res.action == "create_new"
