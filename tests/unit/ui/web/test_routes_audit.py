# tests/unit/ui/web/test_routes_audit.py
"""Tests for the audit log route."""
import pytest

from mjolnir.ui.web.app import create_app
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.audit.logger import AuditLogger, ScopeBasis


@pytest.fixture
def client(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    audit = AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)
    audit.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE,
        action_type="passive_scan.started",
        outcome="started",
    )
    audit.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE,
        action_type="passive_scan.succeeded",
        outcome="completed",
        details={"observations_count": "3"},
    )
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client()


def test_audit_get_returns_200(client):
    response = client.get("/audit")
    assert response.status_code == 200


def test_audit_shows_logged_actions(client):
    response = client.get("/audit")
    assert b"passive_scan.started" in response.data
    assert b"passive_scan.succeeded" in response.data


def test_audit_shows_scope_basis(client):
    response = client.get("/audit")
    assert b"operator-confirmed-active-mode" in response.data
