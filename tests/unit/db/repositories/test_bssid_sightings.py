import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.bssids import BssidsRepository
from mjolnir.db.repositories.bssid_sightings import BssidSightingsRepository


@pytest.fixture
def repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    networks = NetworksRepository(conn)
    bssids = BssidsRepository(conn)
    sightings = BssidSightingsRepository(conn)
    return networks, bssids, sightings


def test_record_sighting(repos):
    networks, bssids, sightings = repos
    net = networks.create(ssid="X")
    b = bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01")
    sighting_id = sightings.record(b.id, signal_dbm=-42, channel=6)
    assert sighting_id is not None


def test_list_for_bssid_ordered_by_seen_at_desc(repos):
    networks, bssids, sightings = repos
    net = networks.create(ssid="X")
    b = bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01")
    sightings.record(b.id, signal_dbm=-50, channel=6, when="2026-06-23T10:00:00Z")
    sightings.record(b.id, signal_dbm=-42, channel=6, when="2026-06-23T11:00:00Z")
    sightings.record(b.id, signal_dbm=-55, channel=6, when="2026-06-23T09:00:00Z")

    result = sightings.list_for_bssid(b.id, limit=10)
    assert len(result) == 3
    assert result[0].seen_at == "2026-06-23T11:00:00Z"
    assert result[1].seen_at == "2026-06-23T10:00:00Z"
    assert result[2].seen_at == "2026-06-23T09:00:00Z"


def test_count_for_bssid(repos):
    networks, bssids, sightings = repos
    net = networks.create(ssid="X")
    b = bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01")
    sightings.record(b.id)
    sightings.record(b.id)
    sightings.record(b.id)
    assert sightings.count_for_bssid(b.id) == 3
