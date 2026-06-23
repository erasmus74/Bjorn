import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.bssids import BssidsRepository


@pytest.fixture
def repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return (
        NetworksRepository(conn),
        BssidsRepository(conn),
    )


def test_upsert_new_bssid_assigns_id(repos):
    networks, bssids = repos
    net = networks.create(ssid="X")
    bssid = bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01",
                          security_type="WPA2", channel=6, signal_dbm=-42)
    assert bssid.id is not None
    assert bssid.network_id == net.id
    assert bssid.last_signal_dbm == -42


def test_upsert_existing_bssid_updates_signal(repos):
    networks, bssids = repos
    net = networks.create(ssid="X")
    bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01", signal_dbm=-50)
    bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01", signal_dbm=-42)
    fetched = bssids.get_by_bssid("AA:BB:CC:DD:EE:01")
    assert fetched.last_signal_dbm == -42


def test_upsert_existing_bssid_does_not_change_network(repos):
    """If BSSID already exists, network_id stays fixed (ESS identity rule)."""
    networks, bssids = repos
    n1 = networks.create(ssid="X")
    n2 = networks.create(ssid="Y")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:01")
    bssids.upsert(network_id=n2.id, bssid="AA:BB:CC:DD:EE:01")
    fetched = bssids.get_by_bssid("AA:BB:CC:DD:EE:01")
    assert fetched.network_id == n1.id


def test_get_by_bssid_missing_returns_none(repos):
    _, bssids = repos
    assert bssids.get_by_bssid("FF:FF:FF:FF:FF:FF") is None


def test_list_for_network(repos):
    networks, bssids = repos
    n1 = networks.create(ssid="X")
    n2 = networks.create(ssid="Y")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:01")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:02")
    bssids.upsert(network_id=n2.id, bssid="AA:BB:CC:DD:EE:03")

    result = bssids.list_for_network(n1.id)
    assert len(result) == 2


def test_find_by_bssid_set_returns_matches(repos):
    """Used by the ESS union-find logic to detect overlap."""
    networks, bssids = repos
    n1 = networks.create(ssid="X")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:01")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:02")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:03")

    result = bssids.find_by_bssid_set({"AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02", "FF:FF:FF:FF:FF:FF"})
    assert len(result) == 2
