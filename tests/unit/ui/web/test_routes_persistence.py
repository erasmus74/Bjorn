# tests/unit/ui/web/test_routes_persistence.py
"""Tests for the two-tier persistence authorization handler."""
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
    net = bundle.networks.create(ssid="TargetNet", security_type="WPA2")
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client(), net.id


def test_persistence_grant_requires_typed_ssid_confirmation(client):
    c, net_id = client
    response = c.post(f"/networks/{net_id}/persistence", data={
        "action": "grant",
        "confirm_ssid": "WrongNet",
    })
    assert response.status_code == 400


def test_persistence_grant_with_correct_ssid_authorizes(client, tmp_path):
    c, net_id = client
    response = c.post(f"/networks/{net_id}/persistence", data={
        "action": "grant",
        "confirm_ssid": "TargetNet",
    })
    assert response.status_code in (200, 302)

    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    net = bundle.networks.get_by_id(net_id)
    assert net.persistence_authorized == 1
    assert net.persistence_authorized_by == "operator"
    conn.close()


def test_persistence_revoke_clears_authorization(client, tmp_path):
    c, net_id = client
    c.post(f"/networks/{net_id}/persistence", data={
        "action": "grant", "confirm_ssid": "TargetNet",
    })
    c.post(f"/networks/{net_id}/persistence", data={"action": "revoke"})

    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    net = bundle.networks.get_by_id(net_id)
    assert net.persistence_authorized == 0
    conn.close()


def test_persistence_grant_writes_audit_log(client, tmp_path):
    c, net_id = client
    c.post(f"/networks/{net_id}/persistence", data={
        "action": "grant", "confirm_ssid": "TargetNet",
    })
    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    rows = bundle.action_log.list_for_network(net_id, limit=10)
    assert any("persistence" in r.action_type.lower() for r in rows)
    conn.close()
