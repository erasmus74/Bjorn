# tests/unit/ui/web/test_routes_blocklist.py
"""Tests for the blocklist management routes."""
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
    bundle = bundle_for(conn)
    blocked = bundle.networks.create(ssid="MyHome", security_type="WPA2")
    bundle.networks.update_scope_state(blocked.id, "blocklisted", reason="my home", by="operator")
    enabled = bundle.networks.create(ssid="Target", security_type="WPA2")
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client(), (blocked.id, enabled.id)


def test_blocklist_get_returns_200(client):
    c, _ = client
    response = c.get("/blocklist")
    assert response.status_code == 200


def test_blocklist_lists_blocklisted_networks(client):
    c, _ = client
    response = c.get("/blocklist")
    assert b"MyHome" in response.data
    assert b"Target" not in response.data


def test_blocklist_add_preemptive_creates_network(client, tmp_path):
    c, _ = client
    response = c.post("/blocklist", data={
        "ssid": "PreemptivelyBlocked",
        "reason": "do not touch",
    })
    assert response.status_code in (200, 302)

    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    matches = bundle.networks.find_by_ssid("PreemptivelyBlocked")
    assert len(matches) == 1
    assert matches[0].scope_state == "blocklisted"
    assert matches[0].blocklist_reason == "do not touch"
    conn.close()


def test_blocklist_unblock_network(client, tmp_path):
    c, (blocked_id, _) = client
    response = c.post(f"/networks/{blocked_id}/scope", data={
        "scope_state": "enabled",
    })
    assert response.status_code in (200, 302)

    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    net = bundle.networks.get_by_id(blocked_id)
    assert net.scope_state == "enabled"
    conn.close()


def test_blocklist_add_requires_ssid(client):
    c, _ = client
    response = c.post("/blocklist", data={"reason": "no ssid"})
    assert response.status_code == 400
