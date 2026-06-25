"""Tests for the v1 -> v2 migration script."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "v1_sample"


@pytest.fixture
def migrated_db(tmp_path):
    """Run the migration script against fixture v1 data, return the v2 DB path."""
    db_path = tmp_path / "mjolnir.db"
    # Initialize the v2 DB first
    factory = ConnectionFactory(db_path=db_path)
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()

    # Run the migration script
    result = subprocess.run(
        [sys.executable, "scripts/migrate_v1_to_v2.py",
         "--v1-dir", str(FIXTURE_DIR),
         "--db", str(db_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"migration failed: {result.stderr}"
    return db_path


def test_migration_creates_hosts_from_netkb(migrated_db, tmp_path):
    conn = ConnectionFactory(db_path=migrated_db).connect()
    bundle = bundle_for(conn)
    cursor = conn.execute("SELECT mac, ip, hostname FROM hosts ORDER BY mac")
    hosts = cursor.fetchall()
    macs = {h["mac"] for h in hosts}
    assert "aa:bb:cc:dd:ee:01" in macs
    assert "aa:bb:cc:dd:ee:02" in macs
    # Dead host (Alive=0) — we still migrate it but could skip; either is defensible.
    conn.close()


def test_migration_parses_multiple_ips(migrated_db):
    """v1 stores multiple IPs in one cell; migration should pick one (first)."""
    conn = ConnectionFactory(db_path=migrated_db).connect()
    cursor = conn.execute(
        "SELECT ip FROM hosts WHERE mac = 'aa:bb:cc:dd:ee:02'"
    )
    row = cursor.fetchone()
    assert row is not None
    # First IP from the comma-separated list
    assert row["ip"] == "192.168.1.20"
    conn.close()


def test_migration_parses_ports_into_services(migrated_db):
    """v1 stores ports as comma-separated list in one cell; migration creates one service row per port."""
    conn = ConnectionFactory(db_path=migrated_db).connect()
    cursor = conn.execute(
        "SELECT port FROM services WHERE host_id IN (SELECT id FROM hosts WHERE mac = 'aa:bb:cc:dd:ee:01') ORDER BY port"
    )
    ports = [r["port"] for r in cursor.fetchall()]
    assert ports == [22, 80, 443]
    conn.close()


def test_migration_imports_cracked_credentials(migrated_db):
    conn = ConnectionFactory(db_path=migrated_db).connect()
    cursor = conn.execute(
        "SELECT cred_type, username, secret FROM credentials WHERE cred_type = 'ssh_password'"
    )
    creds = cursor.fetchall()
    assert len(creds) == 2  # two rows in ssh.csv fixture
    usernames = {c["username"] for c in creds}
    assert "root" in usernames
    assert "admin" in usernames
    conn.close()


def test_migration_applies_mac_blacklist(migrated_db):
    """v1 mac_scan_blacklist should become a blocklisted network entry."""
    conn = ConnectionFactory(db_path=migrated_db).connect()
    cursor = conn.execute(
        "SELECT scope_state FROM networks WHERE scope_state = 'blocklisted'"
    )
    rows = cursor.fetchall()
    assert len(rows) >= 1
    conn.close()


def test_migration_is_idempotent(migrated_db):
    """Running migration twice should not duplicate rows."""
    # Run again
    result = subprocess.run(
        [sys.executable, "scripts/migrate_v1_to_v2.py",
         "--v1-dir", str(FIXTURE_DIR),
         "--db", str(migrated_db)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0

    conn = ConnectionFactory(db_path=migrated_db).connect()
    # Host count should not have doubled
    cursor = conn.execute("SELECT COUNT(*) FROM hosts")
    host_count = cursor.fetchone()[0]
    cursor = conn.execute("SELECT COUNT(*) FROM credentials WHERE cred_type = 'ssh_password'")
    cred_count = cursor.fetchone()[0]
    assert host_count == 3  # same as first run
    assert cred_count == 2
    conn.close()


def test_migration_dry_run_does_not_write(tmp_path):
    """--dry-run should report what would migrate without touching the DB."""
    db_path = tmp_path / "mjolnir.db"
    factory = ConnectionFactory(db_path=db_path)
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()

    result = subprocess.run(
        [sys.executable, "scripts/migrate_v1_to_v2.py",
         "--v1-dir", str(FIXTURE_DIR),
         "--db", str(db_path),
         "--dry-run"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0

    conn = ConnectionFactory(db_path=db_path).connect()
    cursor = conn.execute("SELECT COUNT(*) FROM hosts")
    assert cursor.fetchone()[0] == 0  # nothing written
    conn.close()


def test_migration_handles_missing_v1_dir(tmp_path):
    """If v1 dir doesn't exist, migration exits cleanly with non-zero."""
    db_path = tmp_path / "mjolnir.db"
    factory = ConnectionFactory(db_path=db_path)
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()

    result = subprocess.run(
        [sys.executable, "scripts/migrate_v1_to_v2.py",
         "--v1-dir", str(tmp_path / "nonexistent"),
         "--db", str(db_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()
