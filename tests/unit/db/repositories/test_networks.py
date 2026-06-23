import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository, Network


@pytest.fixture
def repo(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return NetworksRepository(conn)


def test_create_assigns_id_and_default_disambiguator(repo):
    net = repo.create(ssid="HomeWiFi", security_type="WPA2")
    assert net.id is not None
    assert net.ssid == "HomeWiFi"
    assert net.disambiguator == 1
    assert net.scope_state == "enabled"
    assert net.exhausted == 0
    assert net.persistence_authorized == 0


def test_create_two_networks_same_ssid_increments_disambiguator(repo):
    n1 = repo.create(ssid="linksys")
    n2 = repo.create(ssid="linksys")
    assert n1.disambiguator == 1
    assert n2.disambiguator == 2


def test_get_by_id_returns_network(repo):
    created = repo.create(ssid="X")
    fetched = repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.ssid == "X"


def test_get_by_id_missing_returns_none(repo):
    assert repo.get_by_id(99999) is None


def test_find_by_ssid_returns_all_disambiguators(repo):
    repo.create(ssid="attwifi")
    repo.create(ssid="attwifi")
    repo.create(ssid="other")
    matches = repo.find_by_ssid("attwifi")
    assert len(matches) == 2


def test_update_scope_state(repo):
    net = repo.create(ssid="X")
    repo.update_scope_state(net.id, "blocklisted", reason="my home", by="operator")
    fetched = repo.get_by_id(net.id)
    assert fetched.scope_state == "blocklisted"
    assert fetched.blocklist_reason == "my home"
    assert fetched.scope_changed_by == "operator"


def test_update_scope_state_invalid_value(repo):
    net = repo.create(ssid="X")
    with pytest.raises(Exception):
        repo.update_scope_state(net.id, "weird-state")


def test_mark_exhausted(repo):
    net = repo.create(ssid="X")
    repo.mark_exhausted(net.id, "all_stages_succeeded")
    fetched = repo.get_by_id(net.id)
    assert fetched.exhausted == 1
    assert fetched.exhausted_reason == "all_stages_succeeded"


def test_list_enabled_non_exhausted(repo):
    enabled = repo.create(ssid="enabled")
    exhausted = repo.create(ssid="done")
    blocked = repo.create(ssid="blocked")
    repo.mark_exhausted(exhausted.id, "all_stages_succeeded")
    repo.update_scope_state(blocked.id, "blocklisted", reason="x", by="op")

    eligible = repo.list_eligible_for_processing()
    eligible_ids = {n.id for n in eligible}
    assert enabled.id in eligible_ids
    assert exhausted.id not in eligible_ids
    assert blocked.id not in eligible_ids


def test_update_last_seen(repo):
    net = repo.create(ssid="X")
    when = "2026-06-23T13:42:00Z"
    repo.update_last_seen(net.id, when)
    fetched = repo.get_by_id(net.id)
    assert fetched.last_seen == when


def test_set_current_stage(repo):
    net = repo.create(ssid="X")
    repo.set_current_stage(net.id, "wifi_crack")
    fetched = repo.get_by_id(net.id)
    assert fetched.current_stage == "wifi_crack"


def test_authorize_persistence(repo):
    net = repo.create(ssid="X")
    repo.authorize_persistence(net.id, by="operator")
    fetched = repo.get_by_id(net.id)
    assert fetched.persistence_authorized == 1
    assert fetched.persistence_authorized_by == "operator"
    assert fetched.persistence_authorized_at is not None


def test_revoke_persistence_authorization(repo):
    net = repo.create(ssid="X")
    repo.authorize_persistence(net.id, by="op")
    repo.revoke_persistence_authorization(net.id)
    fetched = repo.get_by_id(net.id)
    assert fetched.persistence_authorized == 0


def test_create_retries_on_disambiguator_collision(repo):
    """First _next_disambiguator returns a stale value that collides with a
    pre-inserted row; retry uses the real value and succeeds."""
    # Pre-insert a network with disambiguator=1 to create the collision target
    repo.conn.execute(
        "INSERT INTO networks (ssid, disambiguator, first_seen) VALUES (?, ?, ?)",
        ("RaceTest", 1, "2026-01-01T00:00:00Z"),
    )

    # Stale _next_disambiguator returns 1 first (simulating concurrent insert
    # already took that slot), then falls through to real implementation
    real_method = repo._next_disambiguator
    call_count = {"n": 0}

    def stale_then_real(ssid):
        if call_count["n"] == 0:
            call_count["n"] += 1
            return 1  # stale — collides with the pre-inserted row
        return real_method(ssid)

    repo._next_disambiguator = stale_then_real

    net = repo.create(ssid="RaceTest")
    assert net is not None
    assert net.disambiguator == 2  # the real MAX+1 after retry
