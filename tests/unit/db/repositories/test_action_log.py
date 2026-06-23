import json
import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.action_log import ActionLogRepository
from mjolnir.db.repositories.networks import NetworksRepository


@pytest.fixture
def repos(tmp_path):
    """Return (ActionLogRepository, NetworksRepository) sharing one connection.

    Networks are seeded first when a test references target_network_id, because
    action_log has FK constraints on networks(id).
    """
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return ActionLogRepository(conn), NetworksRepository(conn)


def test_insert_assigns_id(repos):
    repo, _ = repos
    entry = repo.insert(
        global_mode="active",
        scope_basis="operator-confirmed-active-mode",
        action_type="passive_scan.started",
        outcome="started",
    )
    assert entry.id is not None
    assert entry.timestamp is not None


def test_insert_with_full_fields(repos):
    repo, networks = repos
    net = networks.create(ssid="X")
    repo.insert(
        global_mode="active",
        scope_basis="operator-confirmed-active-mode",
        action_type="ssh_brute.started",
        stage_name="credential_attack",
        target_network_id=net.id,
        target_bssid="AA:BB:CC:DD:EE:FF",
        outcome="started",
        details={"wordlist": "rockyou.txt", "line": 1234},
    )
    fetched = repo.list_recent(limit=1)[0]
    assert fetched.target_network_id == net.id
    assert fetched.stage_name == "credential_attack"
    assert json.loads(fetched.details_json)["wordlist"] == "rockyou.txt"


def test_list_recent_orders_desc(repos):
    repo, _ = repos
    for i in range(5):
        repo.insert(
            global_mode="active",
            scope_basis="x",
            action_type=f"a{i}.started",
            outcome="started",
            when=f"2026-06-23T10:0{i}:00Z",
        )
    result = repo.list_recent(limit=3)
    assert len(result) == 3
    assert result[0].timestamp > result[1].timestamp > result[2].timestamp


def test_list_recent_filter_by_network(repos):
    repo, networks = repos
    n1 = networks.create(ssid="X")
    n2 = networks.create(ssid="Y")
    repo.insert("active", "x", "a.started", target_network_id=n1.id, outcome="started")
    repo.insert("active", "x", "b.started", target_network_id=n2.id, outcome="started")
    result = repo.list_for_network(network_id=n1.id, limit=10)
    assert len(result) == 1
    assert result[0].target_network_id == n1.id


def test_count_total(repos):
    repo, _ = repos
    for _ in range(7):
        repo.insert("active", "x", "a.started", outcome="started")
    assert repo.count_total() == 7
