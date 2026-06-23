import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.stage_outputs import StageOutputsRepository


@pytest.fixture
def repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return NetworksRepository(conn), StageOutputsRepository(conn)


def test_set_new_key(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    outputs.set(net.id, "passive_scan", "discovered_hosts_count", "0")
    result = outputs.get(net.id, "passive_scan", "discovered_hosts_count")
    assert result == "0"


def test_set_overwrites_existing(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    outputs.set(net.id, "passive_scan", "counter", "1")
    outputs.set(net.id, "passive_scan", "counter", "2")
    assert outputs.get(net.id, "passive_scan", "counter") == "2"


def test_get_missing_returns_none(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    assert outputs.get(net.id, "passive_scan", "nope") is None


def test_list_for_stage(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    outputs.set(net.id, "passive_scan", "k1", "v1")
    outputs.set(net.id, "passive_scan", "k2", "v2")
    outputs.set(net.id, "wifi_crack", "k3", "v3")

    result = outputs.list_for_stage(net.id, "passive_scan")
    assert dict(result) == {"k1": "v1", "k2": "v2"}


def test_set_many_atomic(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    outputs.set_many(net.id, "passive_scan", {"a": "1", "b": "2", "c": "3"})
    result = outputs.list_for_stage(net.id, "passive_scan")
    assert result == {"a": "1", "b": "2", "c": "3"}
