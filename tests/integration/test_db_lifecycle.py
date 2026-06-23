# tests/integration/test_db_lifecycle.py
"""End-to-end DB lifecycle: connect -> apply_schema -> seed -> write -> read -> reopen."""
from pathlib import Path

from mjolnir.audit.logger import AuditLogger, ScopeBasis
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import CURRENT_SCHEMA_VERSION, MigrationRunner
from mjolnir.db.repositories import bundle_for


def _make_config(data_dir: Path) -> BjornConfig:
    return BjornConfig(
        paths=PathsConfig(data_dir=data_dir, log_dir=data_dir / "logs"),
        db=DbConfig(data_dir=data_dir),
    )


def test_full_lifecycle(tmp_path: Path):
    cfg = _make_config(tmp_path)

    # --- first boot ---
    factory = ConnectionFactory(db_path=cfg.db.path)
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()

    bundle = bundle_for(conn)
    assert bundle.system_state.get_global_mode() == "view_only"
    assert bundle.system_state.is_kill_switch_engaged() is False

    bundle.system_state.set_global_mode("active")

    net = bundle.networks.create(ssid="MyHomeNetwork", security_type="WPA2")
    bundle.networks.update_scope_state(net.id, "blocklisted",
                                        reason="my home", by="operator")

    audit = AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)
    audit.log_mode_transition("view_only", "active",
                              scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE)

    conn.close()

    # --- "reboot" — reopen the DB ---
    conn = factory.connect()
    bundle = bundle_for(conn)

    assert bundle.system_state.get_global_mode() == "active"

    networks = bundle.networks.find_by_ssid("MyHomeNetwork")
    assert len(networks) == 1
    assert networks[0].scope_state == "blocklisted"
    assert networks[0].blocklist_reason == "my home"

    rows = bundle.action_log.list_recent(limit=10)
    assert any(r.action_type == "mode_transition" for r in rows)

    conn.close()


def test_migration_version_tracks_current(tmp_path: Path):
    cfg = _make_config(tmp_path)
    factory = ConnectionFactory(db_path=cfg.db.path)
    conn = factory.connect()
    factory.apply_schema(conn)
    runner = MigrationRunner(conn)
    runner.initialize_fresh_db()
    assert runner.get_schema_version() == CURRENT_SCHEMA_VERSION
    assert runner.run_pending_migrations() == []
    conn.close()


def test_main_initialize_is_idempotent(tmp_path: Path):
    """Calling initialize() twice should not raise."""
    from mjolnir.main import initialize
    cfg = _make_config(tmp_path)
    initialize(cfg)
    initialize(cfg)
