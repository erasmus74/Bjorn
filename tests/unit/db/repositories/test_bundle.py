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
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    bundle = bundle_for(conn)
    bundle.system_state.set("test_key", "test_value")
    fetched = bundle.system_state.get("test_key")
    assert fetched == "test_value"
