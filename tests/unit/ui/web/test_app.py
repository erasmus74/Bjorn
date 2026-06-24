"""Tests for the Flask app factory."""
import pytest

from mjolnir.ui.web.app import create_app
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner


@pytest.fixture
def app(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg)


def test_create_app_returns_flask_app(app):
    from flask import Flask
    assert isinstance(app, Flask)


def test_app_has_db_path_attribute(app):
    assert app.config["MJOLNIR_DB_PATH"] is not None


def test_app_test_client_returns_404_for_unknown_route(app):
    client = app.test_client()
    response = client.get("/nonexistent")
    assert response.status_code == 404


def test_app_dashboard_route_returns_200(app):
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"mjolnir" in response.data.lower() or b"Mjolnir" in response.data
