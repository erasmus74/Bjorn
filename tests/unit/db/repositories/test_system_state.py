import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories.system_state import SystemStateRepository


@pytest.fixture
def repo(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    return SystemStateRepository(conn)


def test_get_existing_key(repo):
    assert repo.get("global_mode") == "view_only"


def test_get_missing_key_returns_none(repo):
    assert repo.get("nonexistent") is None


def test_set_new_key(repo):
    repo.set("custom_key", "custom_value")
    assert repo.get("custom_key") == "custom_value"


def test_set_updates_existing_key(repo):
    repo.set("global_mode", "active")
    assert repo.get("global_mode") == "active"


def test_get_global_mode_default(repo):
    assert repo.get_global_mode() == "view_only"


def test_set_global_mode(repo):
    repo.set_global_mode("active")
    assert repo.get_global_mode() == "active"


def test_set_global_mode_invalid_raises_value_error(repo):
    with pytest.raises(ValueError, match="invalid global mode"):
        repo.set_global_mode("bogus")


def test_engage_kill_switch_sets_timestamp(repo):
    repo.engage_kill_switch()
    val = repo.get("kill_switch_engaged")
    assert val != ""
    assert val.endswith("Z")


def test_release_kill_switch(repo):
    repo.engage_kill_switch()
    repo.release_kill_switch()
    assert repo.get("kill_switch_engaged") == ""


def test_is_kill_switch_engaged(repo):
    assert repo.is_kill_switch_engaged() is False
    repo.engage_kill_switch()
    assert repo.is_kill_switch_engaged() is True
