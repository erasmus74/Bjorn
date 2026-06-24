# tests/unit/ui/web/test_routes_settings.py
"""Tests for the settings route (mode toggle + kill switch)."""
import pytest

from mjolnir.ui.web.app import create_app
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def client(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client()


def test_settings_get_returns_200(client):
    response = client.get("/settings")
    assert response.status_code == 200


def test_settings_shows_current_mode(client):
    response = client.get("/settings")
    assert b"view" in response.data.lower()


def test_toggle_mode_to_active_persists(client, tmp_path):
    response = client.post("/settings/mode", data={"mode": "active"})
    assert response.status_code in (200, 302)

    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    assert bundle.system_state.get_global_mode() == "active"
    conn.close()


def test_toggle_mode_to_invalid_value_rejected(client):
    response = client.post("/settings/mode", data={"mode": "bogus"})
    assert response.status_code == 400


def test_toggle_mode_writes_audit_log(client, tmp_path):
    client.post("/settings/mode", data={"mode": "active"})
    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    rows = bundle.action_log.list_recent(limit=5)
    assert any(r.action_type == "mode_transition" for r in rows)
    conn.close()


def test_engage_kill_switch(client, tmp_path):
    response = client.post("/settings/kill_switch", data={"action": "engage"})
    assert response.status_code in (200, 302)
    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    assert bundle.system_state.is_kill_switch_engaged() is True
    conn.close()


def test_release_kill_switch(client, tmp_path):
    client.post("/settings/kill_switch", data={"action": "engage"})
    client.post("/settings/kill_switch", data={"action": "release"})
    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    assert bundle.system_state.is_kill_switch_engaged() is False
    conn.close()
