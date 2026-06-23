# tests/unit/db/test_connection.py
import sqlite3
from pathlib import Path
from mjolnir.db.connection import ConnectionFactory


def test_connect_returns_sqlite_connection(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_apply_schema_creates_all_tables(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = {row[0] for row in cursor.fetchall()}

    expected = {
        "networks", "bssids", "bssid_sightings", "hosts", "services",
        "credentials", "vulnerabilities", "stage_states", "stage_outputs",
        "action_log", "system_state", "operator_notes", "wifi_captures",
        "file_loot", "sessions", "payloads", "listeners", "exploit_attempts",
        "privesc_attempts", "wordlists", "bt_devices", "tunnels",
        "preferred_ssids",
    }
    assert expected <= table_names


def test_apply_schema_is_idempotent(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    factory.apply_schema(conn)  # should not raise

    cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    assert cursor.fetchone()[0] >= 22


def test_pragmas_applied(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()

    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
