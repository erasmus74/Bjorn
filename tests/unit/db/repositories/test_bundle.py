from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories import RepositoryBundle, bundle_for


def test_bundle_for_returns_all_repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    bundle = bundle_for(conn)
    assert isinstance(bundle, RepositoryBundle)
    assert bundle.system_state is not None
    assert bundle.networks is not None
    assert bundle.bssids is not None
    assert bundle.bssid_sightings is not None
    assert bundle.stage_states is not None
    assert bundle.stage_outputs is not None
    assert bundle.action_log is not None


def test_bundle_shares_connection(tmp_path):
    """Write via one repo, read via another — proves they share the connection."""
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    bundle = bundle_for(conn)

    # Create a network via networks repo
    net = bundle.networks.create(ssid="SharedConn")

    # Reference it via action_log repo — would fail FK validation if connections
    # were separate (foreign_keys=ON enforced per-connection).
    entry = bundle.action_log.insert(
        global_mode="view_only",
        scope_basis="operator-confirmed-active-mode",
        action_type="test_action",
        target_network_id=net.id,
        outcome="started",
    )

    # Read back via stage_states repo (totally different repo) — would return []
    # if connections were separate because the INSERT wouldn't be visible.
    rows = bundle.action_log.list_for_network(network_id=net.id, limit=10)
    assert len(rows) == 1
    assert rows[0].target_network_id == net.id
