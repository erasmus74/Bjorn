import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.stage_states import StageStatesRepository


@pytest.fixture
def repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return NetworksRepository(conn), StageStatesRepository(conn)


def test_get_or_create_seeds_pending(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.network_id == net.id
    assert state.stage_name == "passive_scan"
    assert state.status == "pending"
    assert state.attempts == 0


def test_get_or_create_is_idempotent(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    s1 = stages.get_or_create(net.id, "passive_scan")
    s2 = stages.get_or_create(net.id, "passive_scan")
    assert s1.network_id == s2.network_id
    assert s1.stage_name == s2.stage_name


def test_mark_running_increments_attempts(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_running(net.id, "passive_scan")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.status == "running"
    assert state.attempts == 1
    stages.mark_running(net.id, "passive_scan")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.attempts == 2


def test_mark_succeeded(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_succeeded(net.id, "passive_scan")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.status == "succeeded"
    assert state.completed_at is not None


def test_mark_failed_with_reason(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_failed(net.id, "passive_scan", reason="radio unavailable")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.status == "failed"
    assert state.failure_reason == "radio unavailable"


def test_mark_permanently_failed(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_permanently_failed(net.id, "wifi_crack", reason="all strategies exhausted")
    state = stages.get_or_create(net.id, "wifi_crack")
    assert state.status == "permanently_failed"


def test_mark_skipped(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_skipped(net.id, "wifi_crack", reason="network is open")
    state = stages.get_or_create(net.id, "wifi_crack")
    assert state.status == "skipped"
    assert state.failure_reason == "network is open"


def test_mark_pending_resets_running(repos):
    """Kill switch path: killed stages return to pending for resume."""
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_running(net.id, "passive_scan")
    stages.mark_pending(net.id, "passive_scan")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.status == "pending"


def test_list_in_state(repos):
    """Used by NLM to find work: WHERE status = 'pending'."""
    networks, stages = repos
    n1 = networks.create(ssid="X")
    n2 = networks.create(ssid="Y")
    n3 = networks.create(ssid="Z")
    stages.mark_running(n1.id, "passive_scan")
    stages.get_or_create(n2.id, "passive_scan")
    stages.get_or_create(n3.id, "passive_scan")

    pending = stages.list_in_state("pending")
    network_ids = {s.network_id for s in pending}
    assert n2.id in network_ids
    assert n3.id in network_ids
    assert n1.id not in network_ids
