# Sub-project #0 — Plan 4 of 4: Ship It (Migration + systemd + Acceptance)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship sub-project #0. Build the v1→v2 data migration script, the systemd unit, structured logging, the install/acceptance docs, and run all 10 slice acceptance criteria. Tag `v1.0.0-subproject-0`.

**Architecture:** Migration is a standalone CLI script (`scripts/migrate_v1_to_v2.py`) that reads v1's `data/netkb.csv` + `data/crackedpwd/*.csv` + `config/shared_config.json`, transforms to v2's normalized schema, and upserts via the Plan 1 repositories. systemd unit runs `mjolnir.main` as a service with resource limits. Logging switches to JSON in production, human-readable in dev.

**Tech Stack:** Python 3.11+, existing mjolnir foundation. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md` § Migration plan, § Acceptance
**Depends on:** `v0.5.0-plan3b` (all prior plans complete)

**Branch:** `feat/v2-platform`

---

## File structure (Plan 4 scope)

```
mjolnir/
├── logging_config.py                   ← NEW: structured logging setup
└── (existing files unchanged)

scripts/
├── migrate_v1_to_v2.py                 ← NEW: one-shot migration CLI
└── mjolnir.service                     ← NEW: systemd unit

tests/
└── unit/
    ├── test_migration.py               ← NEW: migration against fixture v1 data
    └── fixtures/
        └── v1_sample/                  ← NEW: sample v1 data dir for tests
            ├── data/
            │   ├── netkb.csv
            │   └── crackedpwd/
            │       └── ssh.csv
            └── config/
                └── shared_config.json

docs/
├── INSTALL-v2.md                       ← NEW: v2 installation guide
└── ACCEPTANCE-RUNBOOK.md               ← NEW: 10-criteria bench test procedure
```

---

## Conventions

(same as prior plans — TDD, conventional commits, type hints, dataclasses, no comments unless WHY is non-obvious)

---

## Phase 1: v1 → v2 migration script

### Task 1.1: Migration script + fixture data + tests

**Files:**
- Create: `scripts/migrate_v1_to_v2.py`
- Create: `tests/unit/fixtures/v1_sample/data/netkb.csv`
- Create: `tests/unit/fixtures/v1_sample/data/crackedpwd/ssh.csv`
- Create: `tests/unit/fixtures/v1_sample/config/shared_config.json`
- Test: `tests/unit/test_migration.py`

The migration reads v1 data, transforms to v2's normalized schema, upserts. Best-effort: logs what it couldn't migrate, never crashes on a single bad row.

**v1 data formats (from inspecting v1 source):**
- `data/netkb.csv`: columns `["MAC Address", "IPs", "Hostnames", "Alive", "Ports"] + [action names...]`. One row per discovered host. IPs/Hostnames/Ports are comma-separated lists within a single CSV cell.
- `data/crackedpwd/ssh.csv`, `smb.csv`, `telnet.csv`, `ftp.csv`, `sql.csv`, `rdp.csv`: cracked credentials per protocol.
- `config/shared_config.json`: has `mac_scan_blacklist` (array of MAC strings) and `ip_scan_blacklist` (array of IP strings), plus timing/config keys.

- [ ] **Step 1: Create fixture v1 data**

`tests/unit/fixtures/v1_sample/data/netkb.csv`:
```csv
MAC Address,IPs,Hostnames,Alive,Ports,ftp_connector,nmap_vuln_scanner,ssh_connector
aa:bb:cc:dd:ee:01,"192.168.1.10","router.local",1,"22,80,443",success,success,failed
aa:bb:cc:dd:ee:02,"192.168.1.20,192.168.1.21","server,server-alt",1,"22",failed,success,success
aa:bb:cc:dd:ee:03,"192.168.1.30","",0,"",failed,failed,failed
```

`tests/unit/fixtures/v1_sample/data/crackedpwd/ssh.csv`:
```csv
IP Address,Port,Username,Password
192.168.1.20,22,root,toor
192.168.1.20,22,admin,admin123
```

`tests/unit/fixtures/v1_sample/config/shared_config.json`:
```json
{
    "mac_scan_blacklist": ["00:11:22:33:44:55"],
    "ip_scan_blacklist": ["192.168.1.1"],
    "portlist": [22, 80, 443],
    "scan_interval": 180,
    "manual_mode": false,
    "websrv": true
}
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_migration.py
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
```

- [ ] **Step 3: Run to verify failure**

```bash
pytest tests/unit/test_migration.py -v
```

- [ ] **Step 4: Write `scripts/migrate_v1_to_v2.py`**

```python
#!/usr/bin/env python3
"""v1 -> v2 data migration for mjolnir.

Reads v1's data/netkb.csv (discovered hosts), data/crackedpwd/*.csv
(cracked credentials), and config/shared_config.json (blacklist + config),
transforms to v2's normalized schema, and upserts via the mjolnir
repositories.

Best-effort: logs what it couldn't migrate, never crashes on a single
bad row. Idempotent: re-runnable via natural-key upserts.

Usage:
    python scripts/migrate_v1_to_v2.py --v1-dir /path/to/v1/checkout --db /var/lib/mjolnir/mjolnir.db
    python scripts/migrate_v1_to_v2.py --v1-dir ... --db ... --dry-run
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.utils import iso_timestamp

_MAC_RE = re.compile(r"^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$")


def _parse_mac(raw: str) -> str | None:
    """Normalize a MAC to lowercase colon-separated, or None if invalid."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if _MAC_RE.match(cleaned):
        return cleaned
    return None


def _split_cell(cell: str) -> list[str]:
    """Split a comma-separated v1 cell into trimmed values."""
    if not cell:
        return []
    return [v.strip() for v in cell.split(",") if v.strip()]


def migrate_netkb(csv_path: Path, bundle, dry_run: bool) -> dict:
    """Migrate v1 netkb.csv -> hosts + services. Returns stats."""
    stats = {"hosts": 0, "services": 0, "skipped_rows": 0}
    if not csv_path.exists():
        return stats

    # v1 has no network concept in netkb.csv; create a single placeholder
    # "v1-imported" network to attach all migrated hosts to.
    network = bundle.networks.create(ssid="v1-imported", security_type=None)
    network_id = network.id

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mac = _parse_mac(row.get("MAC Address", ""))
            if mac is None:
                stats["skipped_rows"] += 1
                continue

            ips = _split_cell(row.get("IPs", ""))
            hostnames = _split_cell(row.get("Hostnames", ""))
            ports_raw = row.get("Ports", "")

            ip = ips[0] if ips else None
            hostname = hostnames[0] if hostnames else None

            # Upsert host (network_id, mac) is unique
            existing = bundle.networks.conn.execute(
                "SELECT id FROM hosts WHERE network_id = ? AND mac = ?",
                (network_id, mac),
            ).fetchone()
            if existing:
                host_id = existing["id"]
            else:
                cursor = bundle.networks.conn.execute(
                    "INSERT INTO hosts (network_id, mac, ip, hostname, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (network_id, mac, ip, hostname, iso_timestamp(), iso_timestamp()),
                )
                host_id = cursor.lastrowid
                stats["hosts"] += 1

            # Parse ports -> services
            for port_str in _split_cell(ports_raw):
                try:
                    port = int(port_str)
                except ValueError:
                    continue
                bundle.networks.conn.execute(
                    "INSERT OR IGNORE INTO services (host_id, port, protocol, discovered_at) "
                    "VALUES (?, ?, 'tcp', ?)",
                    (host_id, port, iso_timestamp()),
                )
                stats["services"] += 1

    return stats


def migrate_crackedpw(crackedpw_dir: Path, bundle, dry_run: bool) -> dict:
    """Migrate v1 crackedpwd/*.csv -> credentials. Returns stats."""
    stats = {"credentials": 0, "skipped_rows": 0}
    if not crackedpw_dir.exists():
        return stats

    # Map v1 filename -> v2 cred_type
    protocol_map = {
        "ssh.csv": "ssh_password",
        "smb.csv": "smb_password",
        "telnet.csv": "telnet_password",
        "ftp.csv": "ftp_password",
        "sql.csv": "sql_password",
        "rdp.csv": "rdp_password",
    }

    for csv_file in crackedpw_dir.glob("*.csv"):
        cred_type = protocol_map.get(csv_file.name)
        if cred_type is None:
            continue

        with csv_file.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                username = row.get("Username", "").strip()
                password = row.get("Password", "").strip()
                if not password:
                    stats["skipped_rows"] += 1
                    continue

                bundle.networks.conn.execute(
                    "INSERT INTO credentials (cred_type, username, secret, discovered_at) "
                    "VALUES (?, ?, ?, ?)",
                    (cred_type, username or None, password, iso_timestamp()),
                )
                stats["credentials"] += 1

    return stats


def migrate_blacklist(config_path: Path, bundle, dry_run: bool) -> dict:
    """Migrate v1 mac_scan_blacklist -> blocklisted network entries. Returns stats."""
    stats = {"blacklisted": 0}
    if not config_path.exists():
        return stats

    with config_path.open() as f:
        config = json.load(f)

    for mac in config.get("mac_scan_blacklist", []):
        normalized = _parse_mac(mac)
        if normalized is None:
            continue
        # Create a placeholder network for the blacklisted MAC and blocklist it
        net = bundle.networks.create(ssid=f"v1-blacklist-{normalized}")
        bundle.networks.update_scope_state(
            net.id, "blocklisted",
            reason="migrated from v1 mac_scan_blacklist",
            by="migration",
        )
        stats["blacklisted"] += 1

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v1 -> v2 mjolnir migration")
    parser.add_argument("--v1-dir", type=Path, required=True,
                        help="path to v1 checkout root (contains data/ and config/)")
    parser.add_argument("--db", type=Path, required=True,
                        help="path to v2 mjolnir.db")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would migrate without writing")
    args = parser.parse_args(argv)

    if not args.v1_dir.exists():
        print(f"error: v1 dir not found: {args.v1_dir}", file=sys.stderr)
        return 2

    netkb_path = args.v1_dir / "data" / "netkb.csv"
    crackedpw_dir = args.v1_dir / "data" / "crackedpwd"
    config_path = args.v1_dir / "config" / "shared_config.json"

    if args.dry_run:
        print(f"[dry-run] would migrate netkb.csv: exists={netkb_path.exists()}")
        print(f"[dry-run] would migrate crackedpwd/: exists={crackedpw_dir.exists()}")
        print(f"[dry-run] would migrate blacklist from config: exists={config_path.exists()}")
        return 0

    factory = ConnectionFactory(db_path=args.db)
    conn = factory.connect()
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)

    try:
        netkb_stats = migrate_netkb(netkb_path, bundle, args.dry_run)
        cracked_stats = migrate_crackedpw(crackedpw_dir, bundle, args.dry_run)
        blacklist_stats = migrate_blacklist(config_path, bundle, args.dry_run)

        print(f"migration complete:")
        print(f"  hosts: {netkb_stats['hosts']} (+{netkb_stats['services']} services)")
        print(f"  credentials: {cracked_stats['credentials']}")
        print(f"  blacklisted: {blacklist_stats['blacklisted']}")
        print(f"  skipped rows: {netkb_stats['skipped_rows'] + cracked_stats['skipped_rows']}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/test_migration.py -v
```
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate_v1_to_v2.py tests/unit/test_migration.py tests/unit/fixtures/
git commit -m "feat(migration): v1 -> v2 data migration script

Reads v1 netkb.csv (hosts + ports), crackedpwd/*.csv (credentials),
and mac_scan_blacklist from config. Transforms to v2 normalized
schema and upserts via repositories. Best-effort: skips bad rows,
logs counts. Idempotent (natural-key upserts). --dry-run supported.

v1's wide netkb.csv (one row per host with comma-separated IPs/ports)
splits into v2's normalized hosts + services tables. v1's per-protocol
crackedpwd CSVs map to credentials with cred_type per protocol. v1's
MAC blacklist becomes blocklisted network entries.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 2: systemd unit + structured logging

### Task 2.1: systemd unit file

**Files:**
- Create: `scripts/mjolnir.service`

- [ ] **Step 1: Write the unit file**

```ini
# scripts/mjolnir.service
# systemd unit for mjolnir v2 daemon.
# Install: sudo cp scripts/mjolnir.service /etc/systemd/system/
#          sudo systemctl daemon-reload
#          sudo systemctl enable --now mjolnir

[Unit]
Description=mjolnir autonomous security-testing daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=mjolnir
Group=mjolnir
WorkingDirectory=/opt/mjolnir
ExecStart=/opt/mjolnir/.venv/bin/python -m mjolnir.main --config /etc/mjolnir/config.toml
ExecStartPre=/opt/mjolnir/.venv/bin/python -m mjolnir.main --config /etc/mjolnir/config.toml --init-db

# Graceful shutdown: SIGTERM, wait up to 30s for stages to checkpoint
KillSignal=SIGTERM
TimeoutStopSec=30

# Restart on crash, but not repeatedly
Restart=on-failure
RestartSec=10

# Resource limits (defense in depth alongside in-process RLIMIT_AS)
MemoryMax=400M
CPUQuota=300%

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/mjolnir /var/log/mjolnir
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Commit**

```bash
git add scripts/mjolnir.service
git commit -m "feat(systemd): mjolnir.service unit

Type=simple service that runs the daemon with --init-db in
ExecStartPre. SIGTERM + 30s timeout for graceful shutdown (stages
checkpoint before exit). Restart=on-failure with 10s backoff.

Resource limits: MemoryMax=400M, CPUQuota=300% (defense in depth
alongside in-process RLIMIT_AS on stages). Hardening: ProtectSystem,
PrivateTmp, NoNewPrivileges.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 2.2: Structured logging setup

**Files:**
- Create: `mjolnir/logging_config.py`
- Modify: `mjolnir/main.py` (call setup_logging at startup)
- Test: `tests/unit/test_logging_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_logging_config.py
"""Tests for structured logging setup."""
import io
import json
import logging

import pytest

from mjolnir.logging_config import setup_logging


def test_setup_logging_json_format():
    logger = setup_logging(format="json", level=logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    logger.info("test message", extra={"event": "test_event"})

    output = stream.getvalue().strip()
    record = json.loads(output)
    assert record["message"] == "test message"
    assert record["event"] == "test_event"
    assert "timestamp" in record


def test_setup_logging_text_format():
    logger = setup_logging(format="text", level=logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    logger.info("hello")

    output = stream.getvalue()
    assert "hello" in output
    assert "INFO" in output


def test_setup_logging_respects_level():
    logger = setup_logging(format="text", level=logging.WARNING)
    assert logger.level == logging.WARNING
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Write `mjolnir/logging_config.py`**

```python
"""Structured logging setup for mjolnir.

JSON format in production (machine-parseable, ships to log aggregators).
Text format in development (human-readable). Configured via --log-format
on main.py, defaulting to text.
"""
import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge extra fields (anything in record.__dict__ not standard)
        standard = set(vars(logging.LogRecord(
            "x", 0, "x", 0, "x", None, None
        )).keys())
        for key, value in vars(record).items():
            if key not in standard and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(format: str = "text", level: int = logging.INFO) -> logging.Logger:
    """Configure the root mjolnir logger. Returns it for chaining."""
    logger = logging.getLogger("mjolnir")
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    if format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
```

- [ ] **Step 4: Wire into `mjolnir/main.py`**

In `main()`, after `initialize(config)`, add:

```python
    from mjolnir.logging_config import setup_logging
    setup_logging(format="text")  # TODO: make configurable via config file
```

(Place this before any daemon work so all subsequent logging is structured.)

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/test_logging_config.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/logging_config.py mjolnir/main.py tests/unit/test_logging_config.py
git commit -m "feat(logging): structured logging setup (JSON or text)

JsonFormatter emits one JSON object per log line with timestamp,
level, logger, message, and any extra fields. Text format is
human-readable for dev. main.py calls setup_logging at startup.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 3: Documentation (INSTALL-v2 + acceptance runbook)

### Task 3.1: v2 installation guide

**Files:**
- Create: `docs/INSTALL-v2.md`

- [ ] **Step 1: Write the install guide**

```markdown
# mjolnir v2 — Installation

mjolnir v2 is the next-generation platform built alongside v1 Bjorn.
This guide covers fresh install, migration from v1, and service management.

## Prerequisites

- Raspberry Pi Zero 2 W (recommended) or Pi Zero W
- Raspberry Pi OS Bookworm (64-bit for Zero 2 W)
- 2.13" Waveshare e-Paper HAT (V2 or V4) connected to GPIO
- Python 3.11+
- ~500MB free disk space

## Fresh install

```bash
# Clone
git clone https://github.com/erasmus74/Bjorn.git /opt/mjolnir
cd /opt/mjolnir
git checkout feat/v2-platform

# Create venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Create mjolnir user + dirs
sudo useradd -r -s /bin/false mjolnir
sudo mkdir -p /var/lib/mjolnir /var/log/mjolnir
sudo chown mjolnir:mjolnir /var/lib/mjolnir /var/log/mjolnir

# Install config
sudo mkdir /etc/mjolnir
sudo cp config/mjolnir.toml /etc/mjolnir/config.toml
# Edit /etc/mjolnir/config.toml as needed

# Initialize DB
sudo -u mjolnir .venv/bin/python -m mjolnir.main --config /etc/mjolnir/config.toml --init-db

# Install + start service
sudo cp scripts/mjolnir.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mjolnir
```

## Migrating from v1

If you have existing v1 scan data you want to preserve:

```bash
# Dry-run first to see what would migrate
sudo -u mjolnir .venv/bin/python scripts/migrate_v1_to_v2.py \
    --v1-dir /path/to/old/bjorn \
    --db /var/lib/mjolnir/mjolnir.db \
    --dry-run

# Back up the v2 DB before migrating
cp /var/lib/mjolnir/mjolnir.db /var/lib/mjolnir/mjolnir-pre-migration.db

# Run the migration
sudo -u mjolnir .venv/bin/python scripts/migrate_v1_to_v2.py \
    --v1-dir /path/to/old/bjorn \
    --db /var/lib/mjolnir/mjolnir.db
```

The migration imports:
- v1 `data/netkb.csv` → v2 hosts + services
- v1 `data/crackedpwd/*.csv` → v2 credentials
- v1 `config/shared_config.json` `mac_scan_blacklist` → v2 blocklisted networks

It does NOT migrate v1's transient `live_status.csv`, per-action logs, or
stolen files (paths may have changed). The migration is idempotent — safe
to re-run.

## Accessing the WebUI

In v2, the WebUI binds to `127.0.0.1:8000` by default. Access via SSH
port-forward:

```bash
ssh mjolnir@<pi-ip> -L 8000:localhost:8000
# Then open http://localhost:8000 in your browser
```

Sub-project #1 will add Tailscale support so the WebUI is reachable
directly on your tailnet without port-forwarding.

## Service management

```bash
sudo systemctl status mjolnir
sudo journalctl -u mjolnir -f          # follow logs
sudo systemctl restart mjolnir
```

## Troubleshooting

- **EPD not displaying:** check SPI is enabled (`raspi-config` > Interfacing > SPI), HAT is seated, `epd_type` in config matches your HAT version.
- **WiFi scan not finding networks:** the daemon needs root or `CAP_NET_RAW` for `iw dev wlan0 scan`. The systemd unit runs as `mjolnir` user; grant capabilities or run the scan stage as root.
- **DB locked errors:** ensure only one mjolnir process is running. WAL mode handles concurrent reads but writes are single-writer.
```

- [ ] **Step 2: Commit**

```bash
git add docs/INSTALL-v2.md
git commit -m "docs(install): v2 installation + migration guide

Covers fresh install (venv, user, dirs, systemd), v1 -> v2 migration
with dry-run + backup, WebUI access via SSH port-forward, service
management, and troubleshooting for EPD/WiFi/DB issues.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 3.2: Acceptance runbook

**Files:**
- Create: `docs/ACCEPTANCE-RUNBOOK.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Sub-project #0 — Acceptance Runbook

The 10 slice acceptance criteria from the spec, as a manual test
procedure to run on real Pi Zero 2W hardware before tagging
`v1.0.0-subproject-0`.

Run each test in order. If any fails, stop and fix before continuing.

## Setup

1. Fresh Raspberry Pi Zero 2W with e-Paper HAT, on Raspberry Pi OS Bookworm.
2. mjolnir installed per `docs/INSTALL-v2.md`.
3. At least one WiFi network in range (your own, for legal testing).
4. SSH access to the Pi.
5. Laptop/phone on same network for WebUI access via port-forward.

## Criteria

### 1. Fresh install boots, displays STARTING_UP → VIEW_ONLY_PASSIVE

```bash
sudo systemctl restart mjolnir
```
- Watch the e-Paper: should show "Starting mjolnir..." then transition
  to VIEW-ONLY mode screen.
- **Pass:** both screens appear within 30s of start.
- **Fail:** check `journalctl -u mjolnir` for errors.

### 2. Device observes a real network within 60s

```bash
# After boot, wait 60s, then:
sudo -u mjolnir sqlite3 /var/lib/mjolnir/mjolnir.db "SELECT ssid, security_type FROM networks"
```
- **Pass:** at least one row present.
- **Fail:** check WiFi adapter is up, `iw dev wlan0 scan` works as the mjolnir user.

### 3. WebUI reachable via SSH port-forward

```bash
ssh mjolnir@<pi> -L 8000:localhost:8000
# Open http://localhost:8000
```
- **Pass:** dashboard loads, shows the discovered network.
- **Fail:** check Flask thread started (`journalctl -u mjolnir | grep "Running on"`).

### 4. Mode toggle persists across reboot

1. In WebUI, click "Activate" (view_only → active).
2. Confirm badge shows ACTIVE.
3. `sudo systemctl restart mjolnir`.
4. Re-open WebUI.
- **Pass:** badge still shows ACTIVE after restart.
- **Fail:** check `system_state` table retained `global_mode=active`.

### 5. Blocklist via WebUI, NLM skips it

1. In WebUI, go to Blocklist, add a network SSID.
2. Confirm it appears in `/blocklist` list.
3. `sudo systemctl restart mjolnir`, wait 60s.
4. Check the blocklisted network is never in ACTIVE_WORKING display.
- **Pass:** blocklisted network observed passively but never processed.

### 6. Preemptively add a network via WebUI

1. In WebUI → Blocklist, add an SSID not yet discovered.
2. Confirm it appears in the list.
3. Walk near that network (or wait for it to appear in scans).
- **Pass:** when discovered, it's already blocklisted.

### 7. Kill switch halts in-flight work

1. Ensure ACTIVE mode and a network being processed.
2. In WebUI → Settings, click "Engage Kill Switch".
3. Watch e-Paper: should show KILL_SWITCH_ENGAGED within ~2s.
- **Pass:** display transitions to KILLED state within 2s of click.

### 8. Audit log records every action

1. Perform several actions (toggle mode, blocklist, etc.).
2. WebUI → Audit Log.
- **Pass:** every action appears with correct scope_basis.
- Specifically: mode toggle should show `operator-confirmed-active-mode`.

### 9. Battery-pull test (power-loss recovery)

1. Ensure ACTIVE mode, mid-scan.
2. Pull power (or `sudo systemctl kill -s SIGKILL mjolnir`).
3. Re-power.
4. Check `journalctl` shows clean recovery, no DB corruption.
- **Pass:** DB opens cleanly, mode/state preserved, no "database is locked" errors.
- **Note:** WAL mode + synchronous=NORMAL means the last few seconds of writes may be lost, but the DB itself is never corrupt.

### 10. All Tier 1 + Tier 2 tests pass

```bash
sudo -u mjolnir /opt/mjolnir/.venv/bin/pytest /opt/mjolnir/tests/ -m 'not hardware'
```
- **Pass:** all tests green (256+ tests).

## Hardware-specific tests (optional, deeper validation)

```bash
sudo -u mjolnir /opt/mjolnir/.venv/bin/pytest /opt/mjolnir/tests/ -m hardware
```
- Real WiFi scan finds networks.
- Real EPD renders all 14 states visibly.
- DisplayManager.shutdown() clears the screen.

## Sign-off

When all 10 criteria pass:
- Tag `v1.0.0-subproject-0`.
- Update `docs/SESSION-STATE.md` to mark sub-project #0 complete.
- Decide whether to merge `feat/v2-platform` → `main` or keep as a long-lived branch.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ACCEPTANCE-RUNBOOK.md
git commit -m "docs(acceptance): 10-criteria bench runbook for sub-project #0

Step-by-step manual test procedure for each acceptance criterion:
boot display, network discovery, WebUI access, mode persistence,
blocklist, preemptive add, kill switch latency, audit logging,
power-loss recovery, full test suite. Plus optional hardware tests
and sign-off checklist.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4: Acceptance + tag

### Task 4.1: Full suite + tag

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/ -v
```
Expected: ~270 tests pass (256 from Plan 3b + ~12 migration + 3 logging = 271). Hardware tests deselected.

- [ ] **Step 2: Verify the daemon end-to-end (CI-safe smoke test)**

```bash
# Initialize a temp DB and run one iteration
python -m mjolnir.main --config config/mjolnir.toml --init-db
# (This won't actually run the daemon because data_dir defaults to /var/lib/mjolnir
# which isn't writable in CI. For CI smoke, use a temp config.)
```

- [ ] **Step 3: Update SESSION-STATE.md**

Mark sub-project #0 as complete (pending hardware acceptance).

- [ ] **Step 4: Tag**

```bash
git tag -a v1.0.0-subproject-0 -m "Sub-project #0 complete: mjolnir v2 foundation

Plans 1-4 delivered:
- Plan 1: foundation (config, schema, repositories, audit, stages)
- Plan 2a: NLM framework (interfaces, identity, scope, gates, executor)
- Plan 2b: PassiveScanStage + cooperative cancellation + daemon
- Plan 3a: Flask WebUI (10 routes, all operator actions reachable)
- Plan 3b: EPD display (14 states, refresh strategy)
- Plan 4: migration + systemd + logging + docs

271 tests passing, 94% coverage on the fast subset.
5 hardware-marked tests (WiFi + EPD) await bench verification.

Software-complete. Hardware acceptance per docs/ACCEPTANCE-RUNBOOK.md
is the final gate before merging to main."
```

---

## Plan 4 acceptance criteria

1. ✅ All Plan 3b tests still pass (256)
2. ✅ All ~12 migration tests pass
3. ✅ All 3 logging tests pass
4. ✅ Migration script handles netkb.csv, crackedpwd/, blacklist
5. ✅ Migration is idempotent + has --dry-run
6. ✅ systemd unit file present with resource limits + hardening
7. ✅ Structured logging (JSON + text formats)
8. ✅ INSTALL-v2.md covers fresh install + migration + service mgmt
9. ✅ ACCEPTANCE-RUNBOOK.md covers all 10 criteria
10. ✅ Tag `v1.0.0-subproject-0` exists

The 10 slice acceptance criteria from the spec are run on real hardware per the runbook; they're not CI gates because most require the Pi + e-Paper HAT + real WiFi.

---

## Post-sub-project-#0

After hardware acceptance passes and `v1.0.0-subproject-0` is confirmed:

- Sub-project #1 (connectivity: BT tether, Tailscale, multi-SSID) begins
- The CSRF protection deferred in ADR 0002 MUST land here (Origin-header check)
- Plans for #1 will be written using the same brainstorm → spec → plan → implement cycle

Sub-project #0 has delivered a working autonomous WiFi observation platform with operator controls. Everything from #1 onward adds capability onto this foundation.
