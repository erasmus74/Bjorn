# tests/unit/db/test_migrations.py
from pathlib import Path
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner, CURRENT_SCHEMA_VERSION


def test_fresh_db_seeds_system_state_defaults(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    runner = MigrationRunner(conn)
    runner.initialize_fresh_db()

    cursor = conn.execute(
        "SELECT key, value FROM system_state WHERE key IN (?, ?, ?)",
        ("global_mode", "kill_switch_engaged", "schema_version"),
    )
    rows = {row["key"]: row["value"] for row in cursor.fetchall()}
    assert rows["global_mode"] == "view_only"
    assert rows["kill_switch_engaged"] == ""
    assert rows["schema_version"] == str(CURRENT_SCHEMA_VERSION)


def test_initialize_fresh_db_is_idempotent(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    runner = MigrationRunner(conn)
    runner.initialize_fresh_db()
    runner.initialize_fresh_db()

    cursor = conn.execute("SELECT COUNT(*) FROM system_state WHERE key = 'global_mode'")
    assert cursor.fetchone()[0] == 1


def test_run_pending_migrations_noop_on_current(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    runner = MigrationRunner(conn)
    runner.initialize_fresh_db()

    applied = runner.run_pending_migrations()
    assert applied == []


def test_schema_version_after_init(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    runner = MigrationRunner(conn)
    runner.initialize_fresh_db()
    assert runner.get_schema_version() == CURRENT_SCHEMA_VERSION
