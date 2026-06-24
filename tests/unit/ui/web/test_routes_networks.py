# tests/unit/ui/web/test_routes_networks.py
"""Tests for the networks inventory + detail routes."""
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
    n1 = bundle.networks.create(ssid="HomeWiFi", security_type="WPA2")
    n2 = bundle.networks.create(ssid="CoffeeShop", security_type="open")
    bundle.bssids.upsert(network_id=n1.id, bssid="aa:bb:cc:dd:ee:01", signal_dbm=-42)
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client(), (n1.id, n2.id)


def test_networks_inventory_returns_200(client):
    c, _ = client
    response = c.get("/networks")
    assert response.status_code == 200


def test_networks_inventory_lists_seed_networks(client):
    c, _ = client
    response = c.get("/networks")
    assert b"HomeWiFi" in response.data
    assert b"CoffeeShop" in response.data


def test_network_detail_returns_200_for_existing_network(client):
    c, (n1_id, _) = client
    response = c.get(f"/networks/{n1_id}")
    assert response.status_code == 200
    assert b"HomeWiFi" in response.data


def test_network_detail_shows_bssids(client):
    c, (n1_id, _) = client
    response = c.get(f"/networks/{n1_id}")
    assert b"aa:bb:cc:dd:ee:01" in response.data


def test_network_detail_returns_404_for_missing_network(client):
    c, _ = client
    response = c.get("/networks/99999")
    assert response.status_code == 404
