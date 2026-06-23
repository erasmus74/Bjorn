# Sub-project #0 — Plan 1 of 4: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the foundation of the `mjolnir` package — package layout, typed config, SQLite DB layer (connection, schema, migrations), audit logger, and Stage ABC + registry. After this plan, `mjolnir` can be imported, the DB can be initialized from scratch, audit rows can be written, and stages can be defined and discovered.

**Architecture:** New `mjolnir/` package built alongside the existing v1 code (which stays at the repo root untouched). All DB access goes through repository objects. Stage framework is an ABC plus a registry that auto-discovers stages via import-time decoration. Tests run against real SQLite in temp directories (no mocks of the DB).

**Tech Stack:** Python 3.11+, SQLite3 (stdlib), `tomllib` (stdlib, config), `dataclasses` (typed config), `pytest` (tests), `pytest-cov` (coverage).

**Spec reference:** `docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md`

**Branch:** `feat/v2-platform` (already created)

---

## File structure (Plan 1 scope)

```
mjolnir/                              ← new package root
├── __init__.py                       ← version, package marker
├── config.py                         ← typed config loader (BjornConfig dataclass)
├── main.py                           ← stub entrypoint (just initializes config + DB)
├── db/
│   ├── __init__.py                   ← exports
│   ├── connection.py                 ← ConnectionFactory (PRAGMAs, busy_timeout)
│   ├── schema.sql                    ← full DDL (23 tables, all indexes)
│   ├── migrations.py                 ← migration runner (schema_version tracking)
│   └── repositories/
│       ├── __init__.py               ← RepositoryBundle dataclass + bundle_for()
│       ├── system_state.py           ← key/value state (global_mode, kill_switch)
│       ├── networks.py               ← networks CRUD
│       ├── bssids.py                 ← bssids CRUD
│       ├── bssid_sightings.py        ← time-series observations
│       ├── stage_states.py           ← per-network stage status
│       ├── stage_outputs.py          ← per-stage structured outputs
│       └── action_log.py             ← append-only audit trail
├── audit/
│   ├── __init__.py
│   └── logger.py                     ← AuditLogger (writes to action_log)
├── stages/
│   ├── __init__.py                   ← exports Stage, registry
│   ├── base.py                       ← Stage ABC, StageResult, ResourceProfile, etc.
│   └── registry.py                   ← StageRegistry (auto-discovery via decorator)
└── utils.py                          ← small helpers (iso_timestamp, etc.)

config/
└── mjolnir.toml                      ← default config file

tests/
├── conftest.py                       ← shared fixtures (temp_dir, fresh_db)
├── unit/
│   ├── test_config.py
│   ├── test_utils.py
│   ├── db/
│   │   ├── test_connection.py
│   │   ├── test_migrations.py
│   │   └── repositories/
│   │       ├── test_system_state.py
│   │       ├── test_networks.py
│   │       ├── test_bssids.py
│   │       ├── test_bssid_sightings.py
│   │       ├── test_stage_states.py
│   │       ├── test_stage_outputs.py
│   │       └── test_action_log.py
│   ├── audit/
│   │   └── test_logger.py
│   └── stages/
│       ├── test_base.py
│       └── test_registry.py
└── integration/
    └── test_db_lifecycle.py          ← init from scratch → migrate → write → read

pyproject.toml                        ← package metadata + pytest config
requirements-mjolnir.txt              ← pinned deps for mjolnir
```

Files NOT in Plan 1 (deferred to Plans 2–4): `interfaces/`, `nlm/`, `ui/`, any concrete Stage implementations, the migration script for v1→v2 data, the systemd unit.

---

## Conventions

- **TDD loop**: write failing test → run to confirm failure → write minimal code → run to confirm pass → commit.
- **Commit style**: conventional commits (`feat:`, `test:`, `chore:`, `docs:`, `refactor:`). Each commit ends with `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`.
- **Test names**: `test_<unit>_<condition>_<expected>` (e.g., `test_networks_insert_assigns_id`).
- **Python style**: type hints on all signatures; dataclasses for value types; no class-level mutable defaults.
- **Filenames**: snake_case for modules, CamelCase for classes.
- **No comments in code** unless a non-obvious invariant is being protected.

---

## Phase 1: Project skeleton

### Task 1.1: Create pyproject.toml + requirements file

**Files:**
- Create: `pyproject.toml`
- Create: `requirements-mjolnir.txt`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "mjolnir"
version = "0.1.0"
description = "Autonomous authorized-security-testing platform (v2 of Bjorn)"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "erasmus74" }]
dependencies = [
    "Flask>=3.0,<4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
    "pytest-cov>=4.1,<5.0",
]

[tool.setuptools.packages.find]
include = ["mjolnir*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
pythonpath = ["."]
addopts = "-ra --strict-markers"
markers = [
    "hardware: requires real Pi Zero 2W hardware (deselected by default)",
]
```

- [ ] **Step 2: Write `requirements-mjolnir.txt`**

```
Flask>=3.0,<4.0
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml requirements-mjolnir.txt
git commit -m "$(cat <<'EOF'
chore: add pyproject.toml + requirements for mjolnir package

Sets up Python package metadata, pins Flask as the only runtime
dependency, configures pytest with hardware-test marker.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 1.2: Create package skeleton

**Files:**
- Create: `mjolnir/__init__.py`
- Create: `mjolnir/utils.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the failing test for `iso_timestamp`**

```python
# tests/unit/test_utils.py
from datetime import datetime, timezone
from mjolnir.utils import iso_timestamp


def test_iso_timestamp_returns_utc_iso8601():
    fixed = datetime(2026, 6, 23, 13, 42, 0, tzinfo=timezone.utc)
    result = iso_timestamp(fixed)
    assert result == "2026-06-23T13:42:00Z"


def test_iso_timestamp_no_arg_uses_now():
    result = iso_timestamp()
    assert result.endswith("Z")
    assert len(result) == 20  # YYYY-MM-DDTHH:MM:SSZ
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_utils.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'mjolnir.utils'`

- [ ] **Step 3: Write `mjolnir/__init__.py`**

```python
"""mjolnir: autonomous authorized-security-testing platform."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write `mjolnir/utils.py`**

```python
"""Small utility helpers used across mjolnir."""
from datetime import datetime, timezone


def iso_timestamp(when: datetime | None = None) -> str:
    """Return an ISO-8601 UTC timestamp string with second precision.

    Format: YYYY-MM-DDTHH:MM:SSZ  (lexicographically sortable).
    """
    if when is None:
        when = datetime.now(timezone.utc)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/test_utils.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 6: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
import sqlite3
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Per-test temp directory for filesystem state."""
    return tmp_path


@pytest.fixture
def fresh_db(temp_dir: Path) -> Iterator[sqlite3.Connection]:
    """A sqlite3 connection to a fresh in-temp-dir DB, schema applied."""
    from mjolnir.db.connection import ConnectionFactory
    factory = ConnectionFactory(db_path=temp_dir / "test.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    yield conn
    conn.close()
```

- [ ] **Step 7: Commit**

```bash
git add mjolnir/__init__.py mjolnir/utils.py tests/unit/test_utils.py tests/conftest.py
git commit -m "$(cat <<'EOF'
feat: package skeleton + iso_timestamp utility

Adds mjolnir package root, utils module with ISO-8601 UTC
timestamp helper, test conftest with temp_dir and fresh_db
fixtures (fresh_db is forward-looking; the connection factory
it references will be built in the next task).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 1.3: Default config file

**Files:**
- Create: `config/mjolnir.toml`

- [ ] **Step 1: Write the default config**

```toml
# config/mjolnir.toml — default configuration for mjolnir
# Override by copying to /etc/mjolnir/config.toml or passing --config <path>.

[paths]
data_dir = "/var/lib/mjolnir"
log_dir = "/var/log/mjolnir"

[db]
filename = "mjolnir.db"
wal_checkpoint_interval_seconds = 3600

[web]
bind_interface = "127.0.0.1"
port = 8000
require_auth = false

[nlm]
scan_interval_seconds = 30
stage_pool_size = 4
stage_memory_limit_mb = 25

[disk]
warning_gb = 8
hard_stop_gb = 16
```

- [ ] **Step 2: Commit**

```bash
git add config/mjolnir.toml
git commit -m "chore: default mjolnir.toml config

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 2: Typed config loader

### Task 2.1: BjornConfig dataclass + loader

**Files:**
- Create: `mjolnir/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_config.py
from pathlib import Path
import pytest
from mjolnir.config import BjornConfig, load_config


def test_load_config_defaults_from_minimal_file(tmp_path: Path):
    config_path = tmp_path / "empty.toml"
    config_path.write_text("")
    cfg = load_config(config_path)
    assert isinstance(cfg, BjornConfig)
    assert cfg.web.bind_interface == "127.0.0.1"
    assert cfg.web.port == 8000
    assert cfg.nlm.stage_pool_size == 4
    assert cfg.disk.warning_gb == 8


def test_load_config_overrides(tmp_path: Path):
    config_path = tmp_path / "custom.toml"
    config_path.write_text("""
[web]
bind_interface = "tailscale0"
port = 9000

[nlm]
stage_pool_size = 2
""")
    cfg = load_config(config_path)
    assert cfg.web.bind_interface == "tailscale0"
    assert cfg.web.port == 9000
    assert cfg.nlm.stage_pool_size == 2


def test_load_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.toml")


def test_db_path_resolves_against_data_dir(tmp_path: Path):
    config_path = tmp_path / "c.toml"
    config_path.write_text("""
[paths]
data_dir = "/opt/mjolnir/data"
""")
    cfg = load_config(config_path)
    assert cfg.db.path == Path("/opt/mjolnir/data/mjolnir.db")
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/test_config.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'mjolnir.config'`

- [ ] **Step 3: Write `mjolnir/config.py`**

```python
"""Typed configuration loader for mjolnir."""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PathsConfig:
    data_dir: Path = Path("/var/lib/mjolnir")
    log_dir: Path = Path("/var/log/mjolnir")


@dataclass(frozen=True)
class DbConfig:
    filename: str = "mjolnir.db"
    wal_checkpoint_interval_seconds: int = 3600
    path: Path = Path("/var/lib/mjolnir/mjolnir.db")


@dataclass(frozen=True)
class WebConfig:
    bind_interface: str = "127.0.0.1"
    port: int = 8000
    require_auth: bool = False


@dataclass(frozen=True)
class NlmConfig:
    scan_interval_seconds: int = 30
    stage_pool_size: int = 4
    stage_memory_limit_mb: int = 25


@dataclass(frozen=True)
class DiskConfig:
    warning_gb: int = 8
    hard_stop_gb: int = 16


@dataclass(frozen=True)
class BjornConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    db: DbConfig = field(default_factory=DbConfig)
    web: WebConfig = field(default_factory=WebConfig)
    nlm: NlmConfig = field(default_factory=NlmConfig)
    disk: DiskConfig = field(default_factory=DiskConfig)


def load_config(path: Path) -> BjornConfig:
    """Load typed config from a TOML file. Missing file raises FileNotFoundError."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as f:
        raw = tomllib.load(f)

    paths_data = raw.get("paths", {})
    db_data = raw.get("db", {})
    web_data = raw.get("web", {})
    nlm_data = raw.get("nlm", {})
    disk_data = raw.get("disk", {})

    paths = PathsConfig(
        data_dir=Path(paths_data.get("data_dir", "/var/lib/mjolnir")),
        log_dir=Path(paths_data.get("log_dir", "/var/log/mjolnir")),
    )

    db = DbConfig(
        filename=db_data.get("filename", "mjolnir.db"),
        wal_checkpoint_interval_seconds=db_data.get("wal_checkpoint_interval_seconds", 3600),
        path=paths.data_dir / db_data.get("filename", "mjolnir.db"),
    )

    web = WebConfig(
        bind_interface=web_data.get("bind_interface", "127.0.0.1"),
        port=web_data.get("port", 8000),
        require_auth=web_data.get("require_auth", False),
    )

    nlm = NlmConfig(
        scan_interval_seconds=nlm_data.get("scan_interval_seconds", 30),
        stage_pool_size=nlm_data.get("stage_pool_size", 4),
        stage_memory_limit_mb=nlm_data.get("stage_memory_limit_mb", 25),
    )

    disk = DiskConfig(
        warning_gb=disk_data.get("warning_gb", 8),
        hard_stop_gb=disk_data.get("hard_stop_gb", 16),
    )

    return BjornConfig(paths=paths, db=db, web=web, nlm=nlm, disk=disk)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/test_config.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/config.py tests/unit/test_config.py
git commit -m "feat(config): typed BjornConfig loader from TOML

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 3: SQLite schema

### Task 3.1: Schema DDL file

**Files:**
- Create: `mjolnir/db/schema.sql`

This is a one-shot task (no TDD; the SQL itself is validated by the migrations test in Task 3.3).

- [ ] **Step 1: Write the schema file**

```sql
-- mjolnir/db/schema.sql
-- Full DDL for the mjolnir database. Idempotent — safe to run multiple times.
-- Schema version is tracked in system_state('schema_version').

-- ============================================================
-- Core entities
-- ============================================================

CREATE TABLE IF NOT EXISTS networks (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    ssid                        TEXT NOT NULL,
    disambiguator               INTEGER NOT NULL DEFAULT 1,
    security_type               TEXT,
    scope_state                 TEXT NOT NULL DEFAULT 'enabled'
                                CHECK (scope_state IN ('enabled','disabled','blocklisted')),
    blocklist_reason            TEXT,
    scope_changed_at            TEXT,
    scope_changed_by            TEXT,
    current_stage               TEXT,
    exhausted                   INTEGER NOT NULL DEFAULT 0,
    exhausted_reason            TEXT,
    persistence_authorized      INTEGER NOT NULL DEFAULT 0,
    persistence_authorized_at   TEXT,
    persistence_authorized_by   TEXT,
    operator_notes_summary      TEXT,
    ess_color_tag               TEXT,
    first_seen                  TEXT NOT NULL,
    last_seen                   TEXT,
    UNIQUE(ssid, disambiguator)
);

CREATE TABLE IF NOT EXISTS bssids (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id      INTEGER NOT NULL REFERENCES networks(id) ON DELETE CASCADE,
    bssid           TEXT NOT NULL,
    security_type   TEXT,
    channel         INTEGER,
    last_signal_dbm INTEGER,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    UNIQUE(bssid)
);

CREATE TABLE IF NOT EXISTS bssid_sightings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bssid_id        INTEGER NOT NULL REFERENCES bssids(id) ON DELETE CASCADE,
    seen_at         TEXT NOT NULL,
    signal_dbm      INTEGER,
    channel         INTEGER
);

CREATE TABLE IF NOT EXISTS hosts (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id                  INTEGER NOT NULL REFERENCES networks(id) ON DELETE CASCADE,
    mac                         TEXT,
    ip                          TEXT,
    hostname                    TEXT,
    os_guess                    TEXT,
    device_type                 TEXT,
    is_gateway                  INTEGER NOT NULL DEFAULT 0,
    is_self                     INTEGER NOT NULL DEFAULT 0,
    persistence_authorized      INTEGER NOT NULL DEFAULT 0,
    persistence_authorized_at   TEXT,
    persistence_authorized_by   TEXT,
    notes                       TEXT,
    first_seen                  TEXT NOT NULL,
    last_seen                   TEXT NOT NULL,
    UNIQUE(network_id, mac)
);

CREATE TABLE IF NOT EXISTS services (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id                 INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    port                    INTEGER NOT NULL,
    protocol                TEXT NOT NULL CHECK (protocol IN ('tcp','udp')),
    service_name            TEXT,
    version                 TEXT,
    banner                  TEXT,
    encryption              TEXT,
    default_creds_checked   INTEGER NOT NULL DEFAULT 0,
    discovered_at           TEXT NOT NULL,
    UNIQUE(host_id, port, protocol)
);

CREATE TABLE IF NOT EXISTS credentials (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id          INTEGER REFERENCES networks(id) ON DELETE CASCADE,
    host_id             INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
    cred_type           TEXT NOT NULL,
    username            TEXT,
    secret              TEXT NOT NULL,
    privilege_level     TEXT CHECK (privilege_level IN ('anonymous','user','admin','root', NULL)),
    validity_state      TEXT NOT NULL DEFAULT 'unverified'
                        CHECK (validity_state IN ('unverified','valid','invalid','expired')),
    last_validated_at   TEXT,
    source              TEXT,
    discovered_at       TEXT NOT NULL,
    discovered_by_stage TEXT
);

CREATE TABLE IF NOT EXISTS vulnerabilities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id             INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    cve_id              TEXT,
    description         TEXT,
    severity            TEXT,
    exploitability      TEXT CHECK (exploitability IN ('weaponized','poc','theoretical', NULL)),
    discovery_method    TEXT,
    discovered_at       TEXT NOT NULL,
    UNIQUE(host_id, cve_id)
);

-- ============================================================
-- Lifecycle and audit
-- ============================================================

CREATE TABLE IF NOT EXISTS stage_states (
    network_id      INTEGER NOT NULL REFERENCES networks(id) ON DELETE CASCADE,
    stage_name      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','succeeded','failed',
                                      'permanently_failed','skipped')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    completed_at    TEXT,
    failure_reason  TEXT,
    PRIMARY KEY (network_id, stage_name)
);

CREATE TABLE IF NOT EXISTS stage_outputs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id      INTEGER NOT NULL REFERENCES networks(id) ON DELETE CASCADE,
    stage_name      TEXT NOT NULL,
    output_key      TEXT NOT NULL,
    output_value    TEXT,
    recorded_at     TEXT NOT NULL,
    UNIQUE(network_id, stage_name, output_key)
);

CREATE TABLE IF NOT EXISTS action_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT NOT NULL,
    global_mode         TEXT NOT NULL,
    scope_basis         TEXT NOT NULL,
    action_type         TEXT NOT NULL,
    stage_name          TEXT,
    target_network_id   INTEGER REFERENCES networks(id),
    target_bssid        TEXT,
    target_host_id      INTEGER REFERENCES hosts(id),
    target_service_id   INTEGER REFERENCES services(id),
    outcome             TEXT NOT NULL,
    details_json        TEXT
);

CREATE TABLE IF NOT EXISTS system_state (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operator_notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type     TEXT NOT NULL,
    target_id       INTEGER NOT NULL,
    note_text       TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    created_by      TEXT NOT NULL DEFAULT 'operator'
);

-- ============================================================
-- WiFi offensive layer
-- ============================================================

CREATE TABLE IF NOT EXISTS wifi_captures (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id                  INTEGER NOT NULL REFERENCES networks(id) ON DELETE CASCADE,
    bssid_id                    INTEGER REFERENCES bssids(id),
    capture_type                TEXT NOT NULL,
    interface                   TEXT,
    local_path                  TEXT NOT NULL,
    size_bytes                  INTEGER,
    hash_sha256                 TEXT,
    captured_at                 TEXT NOT NULL,
    crack_status                TEXT NOT NULL DEFAULT 'untried'
                                CHECK (crack_status IN ('untried','cracking','cracked','exhausted')),
    crack_attempts              INTEGER NOT NULL DEFAULT 0,
    last_crack_attempt_at       TEXT,
    cracked_credential_id       INTEGER REFERENCES credentials(id),
    notes                       TEXT
);

-- ============================================================
-- Loot, sessions, exploitation
-- ============================================================

CREATE TABLE IF NOT EXISTS file_loot (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id          INTEGER NOT NULL REFERENCES networks(id) ON DELETE CASCADE,
    host_id             INTEGER REFERENCES hosts(id),
    service_id          INTEGER REFERENCES services(id),
    source_protocol     TEXT,
    source_path         TEXT NOT NULL,
    local_path          TEXT NOT NULL,
    size_bytes          INTEGER,
    hash_sha256         TEXT,
    captured_at         TEXT NOT NULL,
    captured_by_stage   TEXT,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id             INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    credential_id       INTEGER REFERENCES credentials(id),
    session_type        TEXT NOT NULL,
    transport           TEXT,
    privilege_level     TEXT NOT NULL DEFAULT 'user'
                        CHECK (privilege_level IN ('anonymous','user','root','system')),
    established_at      TEXT NOT NULL,
    last_activity_at    TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1,
    tunnel_id           INTEGER REFERENCES tunnels(id),
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS payloads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    payload_type    TEXT NOT NULL,
    target_arch     TEXT,
    target_os       TEXT,
    format          TEXT,
    local_path      TEXT NOT NULL,
    size_bytes      INTEGER,
    hash_sha256     TEXT,
    generated_at    TEXT NOT NULL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS listeners (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listener_type   TEXT NOT NULL,
    bind_address    TEXT NOT NULL,
    port            INTEGER NOT NULL,
    ssl_cert_path   TEXT,
    started_at      TEXT NOT NULL,
    stopped_at      TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS exploit_attempts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id             INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    service_id          INTEGER REFERENCES services(id),
    vulnerability_id    INTEGER REFERENCES vulnerabilities(id),
    exploit_module      TEXT NOT NULL,
    cve_id              TEXT,
    attempted_at        TEXT NOT NULL,
    duration_ms         INTEGER,
    succeeded           INTEGER NOT NULL DEFAULT 0,
    payload_id          INTEGER REFERENCES payloads(id),
    session_id          INTEGER REFERENCES sessions(id),
    error_message       TEXT,
    details_json        TEXT
);

CREATE TABLE IF NOT EXISTS privesc_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id         INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    session_id      INTEGER REFERENCES sessions(id),
    technique       TEXT NOT NULL,
    attempted_at    TEXT NOT NULL,
    succeeded       INTEGER NOT NULL DEFAULT 0,
    from_priv       TEXT,
    to_priv         TEXT,
    details_json    TEXT
);

-- ============================================================
-- Credential attack resources
-- ============================================================

CREATE TABLE IF NOT EXISTS wordlists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    resource_type   TEXT NOT NULL,
    local_path      TEXT NOT NULL,
    size_bytes      INTEGER,
    line_count      INTEGER,
    hash_sha256     TEXT,
    source          TEXT,
    added_at        TEXT NOT NULL,
    notes           TEXT
);

-- ============================================================
-- Connectivity layer
-- ============================================================

CREATE TABLE IF NOT EXISTS bt_devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    address         TEXT NOT NULL UNIQUE,
    name            TEXT,
    device_class    TEXT,
    appearance      INTEGER,
    rssi            INTEGER,
    is_paired       INTEGER NOT NULL DEFAULT 0,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS tunnels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tunnel_type     TEXT NOT NULL,
    interface_name  TEXT,
    local_ip        TEXT,
    remote_network  TEXT,
    config_json     TEXT,
    started_at      TEXT NOT NULL,
    stopped_at      TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS preferred_ssids (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ssid                TEXT NOT NULL,
    priority            INTEGER NOT NULL,
    security_type       TEXT,
    psk                 TEXT,
    auto_connect        INTEGER NOT NULL DEFAULT 1,
    last_connected_at   TEXT,
    notes               TEXT,
    UNIQUE(ssid)
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_bssids_network_id        ON bssids(network_id);
CREATE INDEX IF NOT EXISTS idx_sightings_bssid_seen     ON bssid_sightings(bssid_id, seen_at);
CREATE INDEX IF NOT EXISTS idx_hosts_network            ON hosts(network_id);
CREATE INDEX IF NOT EXISTS idx_services_host            ON services(host_id);
CREATE INDEX IF NOT EXISTS idx_stage_states_status      ON stage_states(status);
CREATE INDEX IF NOT EXISTS idx_action_log_timestamp     ON action_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_action_log_network       ON action_log(target_network_id);
CREATE INDEX IF NOT EXISTS idx_networks_scope_state     ON networks(scope_state);
CREATE INDEX IF NOT EXISTS idx_networks_last_seen       ON networks(last_seen);
CREATE INDEX IF NOT EXISTS idx_wifi_captures_network    ON wifi_captures(network_id, crack_status);
CREATE INDEX IF NOT EXISTS idx_file_loot_host           ON file_loot(host_id);
CREATE INDEX IF NOT EXISTS idx_file_loot_network        ON file_loot(network_id);
CREATE INDEX IF NOT EXISTS idx_sessions_host_active     ON sessions(host_id, is_active);
CREATE INDEX IF NOT EXISTS idx_exploit_attempts_host    ON exploit_attempts(host_id, succeeded);
CREATE INDEX IF NOT EXISTS idx_privesc_attempts_host    ON privesc_attempts(host_id, succeeded);
CREATE INDEX IF NOT EXISTS idx_wordlists_type           ON wordlists(resource_type);
CREATE INDEX IF NOT EXISTS idx_bt_devices_seen          ON bt_devices(last_seen);
CREATE INDEX IF NOT EXISTS idx_tunnels_active           ON tunnels(is_active);
CREATE INDEX IF NOT EXISTS idx_preferred_ssids_prio     ON preferred_ssids(priority);
CREATE INDEX IF NOT EXISTS idx_operator_notes_target    ON operator_notes(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_stage_outputs_lookup     ON stage_outputs(network_id, stage_name);
```

- [ ] **Step 2: Commit**

```bash
git add mjolnir/db/schema.sql
git commit -m "feat(db): full schema DDL (23 tables + 21 indexes)

All tables for sub-projects 0-6 defined up front. Empty tables
cost nothing; future sub-projects fill them in without schema
migrations.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 3.2: ConnectionFactory with PRAGMAs

**Files:**
- Create: `mjolnir/db/__init__.py`
- Create: `mjolnir/db/connection.py`
- Test: `tests/unit/db/test_connection.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/db/test_connection.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `mjolnir/db/__init__.py`**

```python
"""Database layer for mjolnir."""
```

- [ ] **Step 4: Write `mjolnir/db/connection.py`**

```python
"""SQLite connection factory with mjolnir-standard PRAGMAs."""
import sqlite3
from pathlib import Path

_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-2000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
)

_SCHEMA_SQL_PATH = Path(__file__).parent / "schema.sql"


class ConnectionFactory:
    """Creates SQLite connections configured for mjolnir's workload."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,
            timeout=5.0,
        )
        conn.row_factory = sqlite3.Row
        for pragma in _PRAGMAS:
            conn.execute(pragma)
        return conn

    def apply_schema(self, conn: sqlite3.Connection) -> None:
        """Apply schema.sql to the connection. Idempotent (uses CREATE IF NOT EXISTS)."""
        sql = _SCHEMA_SQL_PATH.read_text()
        conn.executescript(sql)
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/db/test_connection.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/db/__init__.py mjolnir/db/connection.py tests/unit/db/test_connection.py
git commit -m "feat(db): ConnectionFactory with PRAGMAs + schema apply

Opens SQLite connections with WAL, synchronous=NORMAL, FK on,
busy_timeout=5s. apply_schema() executes schema.sql idempotently.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 3.3: Migrations framework

**Files:**
- Create: `mjolnir/db/migrations.py`
- Test: `tests/unit/db/test_migrations.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/db/test_migrations.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `mjolnir/db/migrations.py`**

```python
"""Schema migrations for mjolnir.

Migrations are forward-only and versioned. Each migration is a callable
that takes a sqlite3.Connection. The current schema version is tracked
in system_state('schema_version').
"""
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from mjolnir.utils import iso_timestamp

CURRENT_SCHEMA_VERSION = 1


@dataclass
class Migration:
    version: int
    description: str
    apply: Callable[[sqlite3.Connection], None]


# Future migrations will be appended here as the schema evolves. Example:
# def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
#     conn.execute("ALTER TABLE networks ADD COLUMN new_col TEXT")
#
# _MIGRATIONS: list[Migration] = [
#     Migration(version=2, description="add new_col", apply=_migrate_v1_to_v2),
# ]

_MIGRATIONS: list[Migration] = []


class MigrationRunner:
    """Applies pending migrations to bring DB up to CURRENT_SCHEMA_VERSION."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def initialize_fresh_db(self) -> None:
        """Apply schema and seed system_state defaults on a fresh DB. Idempotent."""
        # Apply schema first (idempotent via CREATE IF NOT EXISTS) so the
        # INSERTs below have a target table. Tests call this method on a
        # bare connection without separate apply_schema().
        from mjolnir.db.connection import _SCHEMA_SQL_PATH
        self.conn.executescript(_SCHEMA_SQL_PATH.read_text())

        defaults = [
            ("global_mode", "view_only"),
            ("kill_switch_engaged", ""),
            ("schema_version", str(CURRENT_SCHEMA_VERSION)),
        ]
        for key, value in defaults:
            self.conn.execute(
                """
                INSERT INTO system_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (key, value, iso_timestamp()),
            )

    def get_schema_version(self) -> int:
        cursor = self.conn.execute(
            "SELECT value FROM system_state WHERE key = 'schema_version'"
        )
        row = cursor.fetchone()
        if row is None:
            return 0
        return int(row["value"])

    def _set_schema_version(self, version: int) -> None:
        self.conn.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES ('schema_version', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (str(version), iso_timestamp()),
        )

    def run_pending_migrations(self) -> list[str]:
        """Apply all migrations newer than the current schema version. Returns descriptions."""
        current = self.get_schema_version()
        applied: list[str] = []
        for migration in sorted(_MIGRATIONS, key=lambda m: m.version):
            if migration.version <= current:
                continue
            self.conn.execute("BEGIN")
            try:
                migration.apply(self.conn)
                self._set_schema_version(migration.version)
                self.conn.execute("COMMIT")
                applied.append(migration.description)
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return applied
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/db/test_migrations.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/db/migrations.py tests/unit/db/test_migrations.py
git commit -m "feat(db): migration runner + fresh-DB seeding

Versioned forward-only migrations tracked in system_state.
Fresh installs seed global_mode='view_only', kill_switch='',
schema_version=1. Idempotent on re-run.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4: Repositories

### Task 4.1: SystemState repository

**Files:**
- Create: `mjolnir/db/repositories/__init__.py`
- Create: `mjolnir/db/repositories/system_state.py`
- Test: `tests/unit/db/repositories/test_system_state.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/db/repositories/test_system_state.py
import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories.system_state import SystemStateRepository


@pytest.fixture
def repo(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    return SystemStateRepository(conn)


def test_get_existing_key(repo):
    assert repo.get("global_mode") == "view_only"


def test_get_missing_key_returns_none(repo):
    assert repo.get("nonexistent") is None


def test_set_new_key(repo):
    repo.set("custom_key", "custom_value")
    assert repo.get("custom_key") == "custom_value"


def test_set_updates_existing_key(repo):
    repo.set("global_mode", "active")
    assert repo.get("global_mode") == "active"


def test_get_global_mode_default(repo):
    assert repo.get_global_mode() == "view_only"


def test_set_global_mode(repo):
    repo.set_global_mode("active")
    assert repo.get_global_mode() == "active"


def test_engage_kill_switch_sets_timestamp(repo):
    repo.engage_kill_switch()
    val = repo.get("kill_switch_engaged")
    assert val != ""
    assert val.endswith("Z")


def test_release_kill_switch(repo):
    repo.engage_kill_switch()
    repo.release_kill_switch()
    assert repo.get("kill_switch_engaged") == ""


def test_is_kill_switch_engaged(repo):
    assert repo.is_kill_switch_engaged() is False
    repo.engage_kill_switch()
    assert repo.is_kill_switch_engaged() is True
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/db/repositories/test_system_state.py -v
```

- [ ] **Step 3: Write `mjolnir/db/repositories/__init__.py`**

```python
"""Repository objects for mjolnir DB tables."""
```

- [ ] **Step 4: Write `mjolnir/db/repositories/system_state.py`**

```python
"""Repository for the system_state key/value table."""
import sqlite3
from typing import Any

from mjolnir.utils import iso_timestamp


class SystemStateRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, key: str) -> str | None:
        cursor = self.conn.execute(
            "SELECT value FROM system_state WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: Any) -> None:
        self.conn.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, str(value), iso_timestamp()),
        )

    def get_global_mode(self) -> str:
        return self.get("global_mode") or "view_only"

    def set_global_mode(self, mode: str) -> None:
        assert mode in ("view_only", "active"), f"invalid mode: {mode}"
        self.set("global_mode", mode)

    def engage_kill_switch(self) -> None:
        self.set("kill_switch_engaged", iso_timestamp())

    def release_kill_switch(self) -> None:
        self.set("kill_switch_engaged", "")

    def is_kill_switch_engaged(self) -> bool:
        val = self.get("kill_switch_engaged")
        return val is not None and val != ""
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/db/repositories/test_system_state.py -v
```
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/db/repositories/__init__.py mjolnir/db/repositories/system_state.py tests/unit/db/repositories/test_system_state.py
git commit -m "feat(db): SystemStateRepository

CRUD on key/value system_state plus typed helpers for
global_mode and kill_switch_engaged.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 4.2: Networks repository

**Files:**
- Create: `mjolnir/db/repositories/networks.py`
- Test: `tests/unit/db/repositories/test_networks.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/db/repositories/test_networks.py
import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository, Network


@pytest.fixture
def repo(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return NetworksRepository(conn)


def test_create_assigns_id_and_default_disambiguator(repo):
    net = repo.create(ssid="HomeWiFi", security_type="WPA2")
    assert net.id is not None
    assert net.ssid == "HomeWiFi"
    assert net.disambiguator == 1
    assert net.scope_state == "enabled"
    assert net.exhausted == 0
    assert net.persistence_authorized == 0


def test_create_two_networks_same_ssid_increments_disambiguator(repo):
    n1 = repo.create(ssid="linksys")
    n2 = repo.create(ssid="linksys")
    assert n1.disambiguator == 1
    assert n2.disambiguator == 2


def test_get_by_id_returns_network(repo):
    created = repo.create(ssid="X")
    fetched = repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.ssid == "X"


def test_get_by_id_missing_returns_none(repo):
    assert repo.get_by_id(99999) is None


def test_find_by_ssid_returns_all_disambiguators(repo):
    repo.create(ssid="attwifi")
    repo.create(ssid="attwifi")
    repo.create(ssid="other")
    matches = repo.find_by_ssid("attwifi")
    assert len(matches) == 2


def test_update_scope_state(repo):
    net = repo.create(ssid="X")
    repo.update_scope_state(net.id, "blocklisted", reason="my home", by="operator")
    fetched = repo.get_by_id(net.id)
    assert fetched.scope_state == "blocklisted"
    assert fetched.blocklist_reason == "my home"
    assert fetched.scope_changed_by == "operator"


def test_update_scope_state_invalid_value(repo):
    net = repo.create(ssid="X")
    with pytest.raises(Exception):
        repo.update_scope_state(net.id, "weird-state")


def test_mark_exhausted(repo):
    net = repo.create(ssid="X")
    repo.mark_exhausted(net.id, "all_stages_succeeded")
    fetched = repo.get_by_id(net.id)
    assert fetched.exhausted == 1
    assert fetched.exhausted_reason == "all_stages_succeeded"


def test_list_enabled_non_exhausted(repo):
    enabled = repo.create(ssid="enabled")
    exhausted = repo.create(ssid="done")
    blocked = repo.create(ssid="blocked")
    repo.mark_exhausted(exhausted.id, "all_stages_succeeded")
    repo.update_scope_state(blocked.id, "blocklisted", reason="x", by="op")

    eligible = repo.list_eligible_for_processing()
    eligible_ids = {n.id for n in eligible}
    assert enabled.id in eligible_ids
    assert exhausted.id not in eligible_ids
    assert blocked.id not in eligible_ids


def test_update_last_seen(repo):
    net = repo.create(ssid="X")
    when = "2026-06-23T13:42:00Z"
    repo.update_last_seen(net.id, when)
    fetched = repo.get_by_id(net.id)
    assert fetched.last_seen == when


def test_set_current_stage(repo):
    net = repo.create(ssid="X")
    repo.set_current_stage(net.id, "wifi_crack")
    fetched = repo.get_by_id(net.id)
    assert fetched.current_stage == "wifi_crack"


def test_authorize_persistence(repo):
    net = repo.create(ssid="X")
    repo.authorize_persistence(net.id, by="operator")
    fetched = repo.get_by_id(net.id)
    assert fetched.persistence_authorized == 1
    assert fetched.persistence_authorized_by == "operator"
    assert fetched.persistence_authorized_at is not None


def test_revoke_persistence_authorization(repo):
    net = repo.create(ssid="X")
    repo.authorize_persistence(net.id, by="op")
    repo.revoke_persistence_authorization(net.id)
    fetched = repo.get_by_id(net.id)
    assert fetched.persistence_authorized == 0
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/db/repositories/test_networks.py -v
```

- [ ] **Step 3: Write `mjolnir/db/repositories/networks.py`**

```python
"""Repository for the networks table."""
import sqlite3
from dataclasses import dataclass

from mjolnir.utils import iso_timestamp


@dataclass
class Network:
    id: int | None
    ssid: str
    disambiguator: int
    security_type: str | None
    scope_state: str
    blocklist_reason: str | None
    scope_changed_at: str | None
    scope_changed_by: str | None
    current_stage: str | None
    exhausted: int
    exhausted_reason: str | None
    persistence_authorized: int
    persistence_authorized_at: str | None
    persistence_authorized_by: str | None
    operator_notes_summary: str | None
    ess_color_tag: str | None
    first_seen: str
    last_seen: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Network":
        return cls(
            id=row["id"],
            ssid=row["ssid"],
            disambiguator=row["disambiguator"],
            security_type=row["security_type"],
            scope_state=row["scope_state"],
            blocklist_reason=row["blocklist_reason"],
            scope_changed_at=row["scope_changed_at"],
            scope_changed_by=row["scope_changed_by"],
            current_stage=row["current_stage"],
            exhausted=row["exhausted"],
            exhausted_reason=row["exhausted_reason"],
            persistence_authorized=row["persistence_authorized"],
            persistence_authorized_at=row["persistence_authorized_at"],
            persistence_authorized_by=row["persistence_authorized_by"],
            operator_notes_summary=row["operator_notes_summary"],
            ess_color_tag=row["ess_color_tag"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )


class NetworksRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, ssid: str, security_type: str | None = None,
               first_seen: str | None = None) -> Network:
        when = first_seen or iso_timestamp()
        disambiguator = self._next_disambiguator(ssid)
        cursor = self.conn.execute(
            """
            INSERT INTO networks (ssid, disambiguator, security_type, first_seen)
            VALUES (?, ?, ?, ?)
            """,
            (ssid, disambiguator, security_type, when),
        )
        net_id = cursor.lastrowid
        return self.get_by_id(net_id)

    def _next_disambiguator(self, ssid: str) -> int:
        cursor = self.conn.execute(
            "SELECT MAX(disambiguator) AS m FROM networks WHERE ssid = ?", (ssid,)
        )
        row = cursor.fetchone()
        if row["m"] is None:
            return 1
        return int(row["m"]) + 1

    def get_by_id(self, network_id: int) -> Network | None:
        cursor = self.conn.execute(
            "SELECT * FROM networks WHERE id = ?", (network_id,)
        )
        row = cursor.fetchone()
        return Network.from_row(row) if row else None

    def find_by_ssid(self, ssid: str) -> list[Network]:
        cursor = self.conn.execute(
            "SELECT * FROM networks WHERE ssid = ? ORDER BY disambiguator",
            (ssid,),
        )
        return [Network.from_row(r) for r in cursor.fetchall()]

    def update_scope_state(self, network_id: int, state: str,
                           reason: str | None = None, by: str | None = None) -> None:
        self.conn.execute(
            """
            UPDATE networks
            SET scope_state = ?, blocklist_reason = ?,
                scope_changed_at = ?, scope_changed_by = ?
            WHERE id = ?
            """,
            (state, reason, iso_timestamp(), by, network_id),
        )

    def mark_exhausted(self, network_id: int, reason: str) -> None:
        self.conn.execute(
            "UPDATE networks SET exhausted = 1, exhausted_reason = ? WHERE id = ?",
            (reason, network_id),
        )

    def update_last_seen(self, network_id: int, when: str | None = None) -> None:
        self.conn.execute(
            "UPDATE networks SET last_seen = ? WHERE id = ?",
            (when or iso_timestamp(), network_id),
        )

    def set_current_stage(self, network_id: int, stage_name: str | None) -> None:
        self.conn.execute(
            "UPDATE networks SET current_stage = ? WHERE id = ?",
            (stage_name, network_id),
        )

    def authorize_persistence(self, network_id: int, by: str) -> None:
        self.conn.execute(
            """
            UPDATE networks
            SET persistence_authorized = 1,
                persistence_authorized_at = ?,
                persistence_authorized_by = ?
            WHERE id = ?
            """,
            (iso_timestamp(), by, network_id),
        )

    def revoke_persistence_authorization(self, network_id: int) -> None:
        self.conn.execute(
            """
            UPDATE networks
            SET persistence_authorized = 0,
                persistence_authorized_at = NULL,
                persistence_authorized_by = NULL
            WHERE id = ?
            """,
            (network_id,),
        )

    def list_eligible_for_processing(self) -> list[Network]:
        cursor = self.conn.execute(
            """
            SELECT * FROM networks
            WHERE scope_state = 'enabled' AND exhausted = 0
            ORDER BY last_seen DESC
            """
        )
        return [Network.from_row(r) for r in cursor.fetchall()]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/db/repositories/test_networks.py -v
```
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/db/repositories/networks.py tests/unit/db/repositories/test_networks.py
git commit -m "feat(db): NetworksRepository

Full CRUD for networks table including scope_state transitions,
exhaustion marking, persistence authorization, and the
list_eligible_for_processing query the NLM will use to find work.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 4.3: BSSIDs repository

**Files:**
- Create: `mjolnir/db/repositories/bssids.py`
- Test: `tests/unit/db/repositories/test_bssids.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/db/repositories/test_bssids.py
import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.bssids import BssidsRepository


@pytest.fixture
def repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return (
        NetworksRepository(conn),
        BssidsRepository(conn),
    )


def test_upsert_new_bssid_assigns_id(repos):
    networks, bssids = repos
    net = networks.create(ssid="X")
    bssid = bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01",
                          security_type="WPA2", channel=6, signal_dbm=-42)
    assert bssid.id is not None
    assert bssid.network_id == net.id
    assert bssid.last_signal_dbm == -42


def test_upsert_existing_bssid_updates_signal(repos):
    networks, bssids = repos
    net = networks.create(ssid="X")
    bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01", signal_dbm=-50)
    bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01", signal_dbm=-42)
    fetched = bssids.get_by_bssid("AA:BB:CC:DD:EE:01")
    assert fetched.last_signal_dbm == -42


def test_upsert_existing_bssid_does_not_change_network(repos):
    """If BSSID already exists, network_id stays fixed (ESS identity rule)."""
    networks, bssids = repos
    n1 = networks.create(ssid="X")
    n2 = networks.create(ssid="Y")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:01")
    bssids.upsert(network_id=n2.id, bssid="AA:BB:CC:DD:EE:01")
    fetched = bssids.get_by_bssid("AA:BB:CC:DD:EE:01")
    assert fetched.network_id == n1.id


def test_get_by_bssid_missing_returns_none(repos):
    _, bssids = repos
    assert bssids.get_by_bssid("FF:FF:FF:FF:FF:FF") is None


def test_list_for_network(repos):
    networks, bssids = repos
    n1 = networks.create(ssid="X")
    n2 = networks.create(ssid="Y")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:01")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:02")
    bssids.upsert(network_id=n2.id, bssid="AA:BB:CC:DD:EE:03")

    result = bssids.list_for_network(n1.id)
    assert len(result) == 2


def test_find_by_bssid_set_returns_matches(repos):
    """Used by the ESS union-find logic to detect overlap."""
    networks, bssids = repos
    n1 = networks.create(ssid="X")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:01")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:02")
    bssids.upsert(network_id=n1.id, bssid="AA:BB:CC:DD:EE:03")

    result = bssids.find_by_bssid_set({"AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02", "FF:FF:FF:FF:FF:FF"})
    assert len(result) == 2
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/db/repositories/test_bssids.py -v
```

- [ ] **Step 3: Write `mjolnir/db/repositories/bssids.py`**

```python
"""Repository for the bssids table."""
import sqlite3
from dataclasses import dataclass

from mjolnir.utils import iso_timestamp


@dataclass
class Bssid:
    id: int | None
    network_id: int
    bssid: str
    security_type: str | None
    channel: int | None
    last_signal_dbm: int | None
    first_seen: str
    last_seen: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Bssid":
        return cls(
            id=row["id"],
            network_id=row["network_id"],
            bssid=row["bssid"],
            security_type=row["security_type"],
            channel=row["channel"],
            last_signal_dbm=row["last_signal_dbm"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )


class BssidsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, network_id: int, bssid: str,
               security_type: str | None = None,
               channel: int | None = None,
               signal_dbm: int | None = None) -> Bssid:
        when = iso_timestamp()
        self.conn.execute(
            """
            INSERT INTO bssids (network_id, bssid, security_type, channel,
                                last_signal_dbm, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bssid) DO UPDATE SET
                last_signal_dbm = excluded.last_signal_dbm,
                channel = COALESCE(excluded.channel, bssids.channel),
                security_type = COALESCE(excluded.security_type, bssids.security_type),
                last_seen = excluded.last_seen
            """,
            (network_id, bssid, security_type, channel, signal_dbm, when, when),
        )
        return self.get_by_bssid(bssid)

    def get_by_bssid(self, bssid: str) -> Bssid | None:
        cursor = self.conn.execute(
            "SELECT * FROM bssids WHERE bssid = ?", (bssid,)
        )
        row = cursor.fetchone()
        return Bssid.from_row(row) if row else None

    def list_for_network(self, network_id: int) -> list[Bssid]:
        cursor = self.conn.execute(
            "SELECT * FROM bssids WHERE network_id = ? ORDER BY last_seen DESC",
            (network_id,),
        )
        return [Bssid.from_row(r) for r in cursor.fetchall()]

    def find_by_bssid_set(self, bssids: set[str]) -> list[Bssid]:
        if not bssids:
            return []
        placeholders = ",".join("?" * len(bssids))
        cursor = self.conn.execute(
            f"SELECT * FROM bssids WHERE bssid IN ({placeholders})",
            tuple(bssids),
        )
        return [Bssid.from_row(r) for r in cursor.fetchall()]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/db/repositories/test_bssids.py -v
```
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/db/repositories/bssids.py tests/unit/db/repositories/test_bssids.py
git commit -m "feat(db): BssidsRepository

Upsert (preserves original network_id per ESS identity rule),
list_for_network, and find_by_bssid_set for union-find overlap
detection in the identity resolver (Plan 2).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 4.4: BSSID sightings repository

**Files:**
- Create: `mjolnir/db/repositories/bssid_sightings.py`
- Test: `tests/unit/db/repositories/test_bssid_sightings.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/db/repositories/test_bssid_sightings.py
import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.bssids import BssidsRepository
from mjolnir.db.repositories.bssid_sightings import BssidSightingsRepository


@pytest.fixture
def repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    networks = NetworksRepository(conn)
    bssids = BssidsRepository(conn)
    sightings = BssidSightingsRepository(conn)
    return networks, bssids, sightings


def test_record_sighting(repos):
    networks, bssids, sightings = repos
    net = networks.create(ssid="X")
    b = bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01")
    sighting_id = sightings.record(b.id, signal_dbm=-42, channel=6)
    assert sighting_id is not None


def test_list_for_bssid_ordered_by_seen_at_desc(repos):
    networks, bssids, sightings = repos
    net = networks.create(ssid="X")
    b = bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01")
    sightings.record(b.id, signal_dbm=-50, channel=6, when="2026-06-23T10:00:00Z")
    sightings.record(b.id, signal_dbm=-42, channel=6, when="2026-06-23T11:00:00Z")
    sightings.record(b.id, signal_dbm=-55, channel=6, when="2026-06-23T09:00:00Z")

    result = sightings.list_for_bssid(b.id, limit=10)
    assert len(result) == 3
    assert result[0]["seen_at"] == "2026-06-23T11:00:00Z"
    assert result[1]["seen_at"] == "2026-06-23T10:00:00Z"
    assert result[2]["seen_at"] == "2026-06-23T09:00:00Z"


def test_count_for_bssid(repos):
    networks, bssids, sightings = repos
    net = networks.create(ssid="X")
    b = bssids.upsert(network_id=net.id, bssid="AA:BB:CC:DD:EE:01")
    sightings.record(b.id)
    sightings.record(b.id)
    sightings.record(b.id)
    assert sightings.count_for_bssid(b.id) == 3
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/db/repositories/test_bssid_sightings.py -v
```

- [ ] **Step 3: Write `mjolnir/db/repositories/bssid_sightings.py`**

```python
"""Repository for the bssid_sightings table."""
import sqlite3

from mjolnir.utils import iso_timestamp


class BssidSightingsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(self, bssid_id: int,
               signal_dbm: int | None = None,
               channel: int | None = None,
               when: str | None = None) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO bssid_sightings (bssid_id, seen_at, signal_dbm, channel)
            VALUES (?, ?, ?, ?)
            """,
            (bssid_id, when or iso_timestamp(), signal_dbm, channel),
        )
        return int(cursor.lastrowid)

    def list_for_bssid(self, bssid_id: int, limit: int = 100) -> list[sqlite3.Row]:
        cursor = self.conn.execute(
            """
            SELECT * FROM bssid_sightings
            WHERE bssid_id = ?
            ORDER BY seen_at DESC
            LIMIT ?
            """,
            (bssid_id, limit),
        )
        return list(cursor.fetchall())

    def count_for_bssid(self, bssid_id: int) -> int:
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM bssid_sightings WHERE bssid_id = ?",
            (bssid_id,),
        )
        return int(cursor.fetchone()[0])
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/db/repositories/test_bssid_sightings.py -v
```

- [ ] **Step 5: Commit**

```bash
git add mjolnir/db/repositories/bssid_sightings.py tests/unit/db/repositories/test_bssid_sightings.py
git commit -m "feat(db): BssidSightingsRepository

Time-series observation writer for resume-on-return signal
history.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 4.5: Stage states repository

**Files:**
- Create: `mjolnir/db/repositories/stage_states.py`
- Test: `tests/unit/db/repositories/test_stage_states.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/db/repositories/test_stage_states.py
import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.stage_states import StageStatesRepository


@pytest.fixture
def repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return NetworksRepository(conn), StageStatesRepository(conn)


def test_get_or_create_seeds_pending(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.network_id == net.id
    assert state.stage_name == "passive_scan"
    assert state.status == "pending"
    assert state.attempts == 0


def test_get_or_create_is_idempotent(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    s1 = stages.get_or_create(net.id, "passive_scan")
    s2 = stages.get_or_create(net.id, "passive_scan")
    assert s1.network_id == s2.network_id
    assert s1.stage_name == s2.stage_name


def test_mark_running_increments_attempts(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_running(net.id, "passive_scan")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.status == "running"
    assert state.attempts == 1
    stages.mark_running(net.id, "passive_scan")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.attempts == 2


def test_mark_succeeded(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_succeeded(net.id, "passive_scan")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.status == "succeeded"
    assert state.completed_at is not None


def test_mark_failed_with_reason(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_failed(net.id, "passive_scan", reason="radio unavailable")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.status == "failed"
    assert state.failure_reason == "radio unavailable"


def test_mark_permanently_failed(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_permanently_failed(net.id, "wifi_crack", reason="all strategies exhausted")
    state = stages.get_or_create(net.id, "wifi_crack")
    assert state.status == "permanently_failed"


def test_mark_skipped(repos):
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_skipped(net.id, "wifi_crack", reason="network is open")
    state = stages.get_or_create(net.id, "wifi_crack")
    assert state.status == "skipped"
    assert state.failure_reason == "network is open"


def test_mark_pending_resets_running(repos):
    """Kill switch path: killed stages return to pending for resume."""
    networks, stages = repos
    net = networks.create(ssid="X")
    stages.mark_running(net.id, "passive_scan")
    stages.mark_pending(net.id, "passive_scan")
    state = stages.get_or_create(net.id, "passive_scan")
    assert state.status == "pending"


def test_list_in_state(repos):
    """Used by NLM to find work: WHERE status = 'pending'."""
    networks, stages = repos
    n1 = networks.create(ssid="X")
    n2 = networks.create(ssid="Y")
    n3 = networks.create(ssid="Z")
    stages.mark_running(n1.id, "passive_scan")
    stages.get_or_create(n2.id, "passive_scan")
    stages.get_or_create(n3.id, "passive_scan")

    pending = stages.list_in_state("pending")
    network_ids = {s.network_id for s in pending}
    assert n2.id in network_ids
    assert n3.id in network_ids
    assert n1.id not in network_ids
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/db/repositories/test_stage_states.py -v
```

- [ ] **Step 3: Write `mjolnir/db/repositories/stage_states.py`**

```python
"""Repository for the stage_states table."""
import sqlite3
from dataclasses import dataclass

from mjolnir.utils import iso_timestamp


@dataclass
class StageState:
    network_id: int
    stage_name: str
    status: str
    attempts: int
    last_attempt_at: str | None
    completed_at: str | None
    failure_reason: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "StageState":
        return cls(
            network_id=row["network_id"],
            stage_name=row["stage_name"],
            status=row["status"],
            attempts=row["attempts"],
            last_attempt_at=row["last_attempt_at"],
            completed_at=row["completed_at"],
            failure_reason=row["failure_reason"],
        )


class StageStatesRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_or_create(self, network_id: int, stage_name: str) -> StageState:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO stage_states (network_id, stage_name, status)
            VALUES (?, ?, 'pending')
            """,
            (network_id, stage_name),
        )
        cursor = self.conn.execute(
            "SELECT * FROM stage_states WHERE network_id = ? AND stage_name = ?",
            (network_id, stage_name),
        )
        return StageState.from_row(cursor.fetchone())

    def _update(self, network_id: int, stage_name: str,
                status: str, reason: str | None = None) -> None:
        if status == "running":
            self.conn.execute(
                """
                UPDATE stage_states
                SET status = ?, attempts = attempts + 1, last_attempt_at = ?,
                    failure_reason = NULL
                WHERE network_id = ? AND stage_name = ?
                """,
                (status, iso_timestamp(), network_id, stage_name),
            )
        elif status in ("succeeded", "permanently_failed"):
            self.conn.execute(
                """
                UPDATE stage_states
                SET status = ?, completed_at = ?, failure_reason = ?
                WHERE network_id = ? AND stage_name = ?
                """,
                (status, iso_timestamp(), reason, network_id, stage_name),
            )
        else:
            self.conn.execute(
                """
                UPDATE stage_states
                SET status = ?, failure_reason = ?
                WHERE network_id = ? AND stage_name = ?
                """,
                (status, reason, network_id, stage_name),
            )

    def mark_running(self, network_id: int, stage_name: str) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "running")

    def mark_succeeded(self, network_id: int, stage_name: str) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "succeeded")

    def mark_failed(self, network_id: int, stage_name: str, reason: str | None = None) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "failed", reason)

    def mark_permanently_failed(self, network_id: int, stage_name: str, reason: str | None = None) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "permanently_failed", reason)

    def mark_skipped(self, network_id: int, stage_name: str, reason: str | None = None) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "skipped", reason)

    def mark_pending(self, network_id: int, stage_name: str) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "pending")

    def list_in_state(self, status: str) -> list[StageState]:
        cursor = self.conn.execute(
            "SELECT * FROM stage_states WHERE status = ?", (status,)
        )
        return [StageState.from_row(r) for r in cursor.fetchall()]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/db/repositories/test_stage_states.py -v
```
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/db/repositories/stage_states.py tests/unit/db/repositories/test_stage_states.py
git commit -m "feat(db): StageStatesRepository

Per-(network, stage) status tracking. mark_running increments
attempts; mark_pending resets killed stages for resume.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 4.6: Stage outputs repository

**Files:**
- Create: `mjolnir/db/repositories/stage_outputs.py`
- Test: `tests/unit/db/repositories/test_stage_outputs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/db/repositories/test_stage_outputs.py
import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.stage_outputs import StageOutputsRepository


@pytest.fixture
def repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return NetworksRepository(conn), StageOutputsRepository(conn)


def test_set_new_key(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    outputs.set(net.id, "passive_scan", "discovered_hosts_count", "0")
    result = outputs.get(net.id, "passive_scan", "discovered_hosts_count")
    assert result == "0"


def test_set_overwrites_existing(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    outputs.set(net.id, "passive_scan", "counter", "1")
    outputs.set(net.id, "passive_scan", "counter", "2")
    assert outputs.get(net.id, "passive_scan", "counter") == "2"


def test_get_missing_returns_none(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    assert outputs.get(net.id, "passive_scan", "nope") is None


def test_list_for_stage(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    outputs.set(net.id, "passive_scan", "k1", "v1")
    outputs.set(net.id, "passive_scan", "k2", "v2")
    outputs.set(net.id, "wifi_crack", "k3", "v3")

    result = outputs.list_for_stage(net.id, "passive_scan")
    assert dict(result) == {"k1": "v1", "k2": "v2"}


def test_set_many_atomic(repos):
    networks, outputs = repos
    net = networks.create(ssid="X")
    outputs.set_many(net.id, "passive_scan", {"a": "1", "b": "2", "c": "3"})
    result = outputs.list_for_stage(net.id, "passive_scan")
    assert result == {"a": "1", "b": "2", "c": "3"}
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/db/repositories/test_stage_outputs.py -v
```

- [ ] **Step 3: Write `mjolnir/db/repositories/stage_outputs.py`**

```python
"""Repository for the stage_outputs table."""
import sqlite3

from mjolnir.utils import iso_timestamp


class StageOutputsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def set(self, network_id: int, stage_name: str, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO stage_outputs (network_id, stage_name, output_key, output_value, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(network_id, stage_name, output_key) DO UPDATE SET
                output_value = excluded.output_value,
                recorded_at = excluded.recorded_at
            """,
            (network_id, stage_name, key, value, iso_timestamp()),
        )

    def set_many(self, network_id: int, stage_name: str, items: dict[str, str]) -> None:
        when = iso_timestamp()
        rows = [(network_id, stage_name, k, v, when) for k, v in items.items()]
        self.conn.executemany(
            """
            INSERT INTO stage_outputs (network_id, stage_name, output_key, output_value, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(network_id, stage_name, output_key) DO UPDATE SET
                output_value = excluded.output_value,
                recorded_at = excluded.recorded_at
            """,
            rows,
        )

    def get(self, network_id: int, stage_name: str, key: str) -> str | None:
        cursor = self.conn.execute(
            """
            SELECT output_value FROM stage_outputs
            WHERE network_id = ? AND stage_name = ? AND output_key = ?
            """,
            (network_id, stage_name, key),
        )
        row = cursor.fetchone()
        return row["output_value"] if row else None

    def list_for_stage(self, network_id: int, stage_name: str) -> dict[str, str]:
        cursor = self.conn.execute(
            """
            SELECT output_key, output_value FROM stage_outputs
            WHERE network_id = ? AND stage_name = ?
            """,
            (network_id, stage_name),
        )
        return {row["output_key"]: row["output_value"] for row in cursor.fetchall()}
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/db/repositories/test_stage_outputs.py -v
```

- [ ] **Step 5: Commit**

```bash
git add mjolnir/db/repositories/stage_outputs.py tests/unit/db/repositories/test_stage_outputs.py
git commit -m "feat(db): StageOutputsRepository

Per-stage key/value outputs (counters, metrics).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 4.7: Action log repository

**Files:**
- Create: `mjolnir/db/repositories/action_log.py`
- Test: `tests/unit/db/repositories/test_action_log.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/db/repositories/test_action_log.py
import json
import pytest
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories.action_log import ActionLogRepository
from mjolnir.db.repositories.networks import NetworksRepository


@pytest.fixture
def repos(tmp_path):
    """Return (ActionLogRepository, NetworksRepository) sharing one connection.

    Networks must be seeded before referencing target_network_id because
    action_log has FK constraints enforced via PRAGMA foreign_keys=ON.
    """
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    return ActionLogRepository(conn), NetworksRepository(conn)


def test_insert_assigns_id(repos):
    repo, _ = repos
    entry = repo.insert(
        global_mode="active",
        scope_basis="operator-confirmed-active-mode",
        action_type="passive_scan.started",
        outcome="started",
    )
    assert entry.id is not None
    assert entry.timestamp is not None


def test_insert_with_full_fields(repos):
    repo, networks = repos
    net = networks.create(ssid="X")
    repo.insert(
        global_mode="active",
        scope_basis="operator-confirmed-active-mode",
        action_type="ssh_brute.started",
        stage_name="credential_attack",
        target_network_id=net.id,
        target_bssid="AA:BB:CC:DD:EE:FF",
        outcome="started",
        details={"wordlist": "rockyou.txt", "line": 1234},
    )
    fetched = repo.list_recent(limit=1)[0]
    assert fetched["target_network_id"] == net.id
    assert fetched["stage_name"] == "credential_attack"
    assert json.loads(fetched["details_json"])["wordlist"] == "rockyou.txt"


def test_list_recent_orders_desc(repos):
    repo, _ = repos
    for i in range(5):
        repo.insert(
            global_mode="active",
            scope_basis="x",
            action_type=f"a{i}.started",
            outcome="started",
            when=f"2026-06-23T10:0{i}:00Z",
        )
    result = repo.list_recent(limit=3)
    assert len(result) == 3
    assert result[0]["timestamp"] > result[1]["timestamp"] > result[2]["timestamp"]


def test_list_recent_filter_by_network(repos):
    repo, networks = repos
    n1 = networks.create(ssid="X")
    n2 = networks.create(ssid="Y")
    repo.insert("active", "x", "a.started", target_network_id=n1.id, outcome="started")
    repo.insert("active", "x", "b.started", target_network_id=n2.id, outcome="started")
    result = repo.list_for_network(network_id=n1.id, limit=10)
    assert len(result) == 1
    assert result[0]["target_network_id"] == n1.id


def test_count_total(repo):
    for _ in range(7):
        repo.insert("active", "x", "a.started", outcome="started")
    assert repo.count_total() == 7
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/db/repositories/test_action_log.py -v
```

- [ ] **Step 3: Write `mjolnir/db/repositories/action_log.py`**

```python
"""Repository for the action_log table (append-only audit trail)."""
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from mjolnir.utils import iso_timestamp


@dataclass
class ActionLogEntry:
    id: int | None
    timestamp: str
    global_mode: str
    scope_basis: str
    action_type: str
    stage_name: str | None = None
    target_network_id: int | None = None
    target_bssid: str | None = None
    target_host_id: int | None = None
    target_service_id: int | None = None
    outcome: str = "started"
    details_json: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ActionLogEntry":
        return cls(
            id=row["id"],
            timestamp=row["timestamp"],
            global_mode=row["global_mode"],
            scope_basis=row["scope_basis"],
            action_type=row["action_type"],
            stage_name=row["stage_name"],
            target_network_id=row["target_network_id"],
            target_bssid=row["target_bssid"],
            target_host_id=row["target_host_id"],
            target_service_id=row["target_service_id"],
            outcome=row["outcome"],
            details_json=row["details_json"],
        )


class ActionLogRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(
        self,
        global_mode: str,
        scope_basis: str,
        action_type: str,
        outcome: str = "started",
        stage_name: str | None = None,
        target_network_id: int | None = None,
        target_bssid: str | None = None,
        target_host_id: int | None = None,
        target_service_id: int | None = None,
        details: dict[str, Any] | None = None,
        when: str | None = None,
    ) -> ActionLogEntry:
        details_json = json.dumps(details) if details is not None else None
        timestamp = when or iso_timestamp()
        cursor = self.conn.execute(
            """
            INSERT INTO action_log (
                timestamp, global_mode, scope_basis, action_type, stage_name,
                target_network_id, target_bssid, target_host_id, target_service_id,
                outcome, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, global_mode, scope_basis, action_type, stage_name,
             target_network_id, target_bssid, target_host_id, target_service_id,
             outcome, details_json),
        )
        return ActionLogEntry(
            id=int(cursor.lastrowid),
            timestamp=timestamp,
            global_mode=global_mode,
            scope_basis=scope_basis,
            action_type=action_type,
            stage_name=stage_name,
            target_network_id=target_network_id,
            target_bssid=target_bssid,
            target_host_id=target_host_id,
            target_service_id=target_service_id,
            outcome=outcome,
            details_json=details_json,
        )

    def list_recent(self, limit: int = 50) -> list[sqlite3.Row]:
        cursor = self.conn.execute(
            """
            SELECT * FROM action_log
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return list(cursor.fetchall())

    def list_for_network(self, network_id: int, limit: int = 100) -> list[sqlite3.Row]:
        cursor = self.conn.execute(
            """
            SELECT * FROM action_log
            WHERE target_network_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (network_id, limit),
        )
        return list(cursor.fetchall())

    def count_total(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM action_log")
        return int(cursor.fetchone()[0])
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/db/repositories/test_action_log.py -v
```

- [ ] **Step 5: Commit**

```bash
git add mjolnir/db/repositories/action_log.py tests/unit/db/repositories/test_action_log.py
git commit -m "feat(db): ActionLogRepository

Append-only audit-trail writer with list_recent and per-network
filters. ActionLogEntry dataclass mirrors the row.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 4.8: RepositoryBundle factory

**Files:**
- Modify: `mjolnir/db/repositories/__init__.py`
- Test: `tests/unit/db/repositories/test_bundle.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/db/repositories/test_bundle.py
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories import RepositoryBundle, bundle_for


def test_bundle_for_returns_all_repos(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    bundle = bundle_for(conn)
    assert isinstance(bundle, RepositoryBundle)
    assert bundle.system_state is not None
    assert bundle.networks is not None
    assert bundle.bssids is not None
    assert bundle.bssid_sightings is not None
    assert bundle.stage_states is not None
    assert bundle.stage_outputs is not None
    assert bundle.action_log is not None


def test_bundle_shares_connection(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    bundle = bundle_for(conn)
    bundle.system_state.set("test_key", "test_value")
    fetched = bundle.system_state.get("test_key")
    assert fetched == "test_value"
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/unit/db/repositories/test_bundle.py -v
```

- [ ] **Step 3: Update `mjolnir/db/repositories/__init__.py`**

```python
"""Repository objects for mjolnir DB tables."""
import sqlite3
from dataclasses import dataclass

from mjolnir.db.repositories.action_log import ActionLogRepository
from mjolnir.db.repositories.bssid_sightings import BssidSightingsRepository
from mjolnir.db.repositories.bssids import BssidsRepository
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.stage_outputs import StageOutputsRepository
from mjolnir.db.repositories.stage_states import StageStatesRepository
from mjolnir.db.repositories.system_state import SystemStateRepository


@dataclass
class RepositoryBundle:
    """Bundle of all repositories sharing a single connection."""
    system_state: SystemStateRepository
    networks: NetworksRepository
    bssids: BssidsRepository
    bssid_sightings: BssidSightingsRepository
    stage_states: StageStatesRepository
    stage_outputs: StageOutputsRepository
    action_log: ActionLogRepository


def bundle_for(conn: sqlite3.Connection) -> RepositoryBundle:
    """Construct a RepositoryBundle over a single connection."""
    return RepositoryBundle(
        system_state=SystemStateRepository(conn),
        networks=NetworksRepository(conn),
        bssids=BssidsRepository(conn),
        bssid_sightings=BssidSightingsRepository(conn),
        stage_states=StageStatesRepository(conn),
        stage_outputs=StageOutputsRepository(conn),
        action_log=ActionLogRepository(conn),
    )
```

- [ ] **Step 4: Run test to verify pass**

```bash
pytest tests/unit/db/repositories/test_bundle.py -v
```

- [ ] **Step 5: Commit**

```bash
git add mjolnir/db/repositories/__init__.py tests/unit/db/repositories/test_bundle.py
git commit -m "feat(db): RepositoryBundle + bundle_for() factory

Single connection wired into all repositories. Used by NLM (Plan 2)
and AuditLogger.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 5: Audit logger

### Task 5.1: AuditLogger facade

**Files:**
- Create: `mjolnir/audit/__init__.py`
- Create: `mjolnir/audit/logger.py`
- Test: `tests/unit/audit/test_logger.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/audit/test_logger.py
import json
import pytest
from mjolnir.audit.logger import AuditLogger, ScopeBasis
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def logger(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    return AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)


def test_log_offensive_started_writes_row(logger):
    logger.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE,
        action_type="ssh_brute.started",
        stage_name="credential_attack",
        target_network_id=1,
        outcome="started",
        details={"wordlist": "rockyou.txt"},
    )
    rows = logger.action_log.list_recent(limit=1)
    assert len(rows) == 1
    assert rows[0]["action_type"] == "ssh_brute.started"
    assert rows[0]["global_mode"] == "view_only"


def test_log_offensive_global_mode_captured_at_log_time(logger):
    logger.system_state.set_global_mode("active")
    logger.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE,
        action_type="x.started",
        outcome="started",
    )
    rows = logger.action_log.list_recent(limit=1)
    assert rows[0]["global_mode"] == "active"


def test_scope_basis_enum_serializes_to_value(logger):
    logger.log_offensive_action(
        scope_basis=ScopeBasis.KILLED_BY_OPERATOR,
        action_type="y.failed",
        outcome="failed",
    )
    rows = logger.action_log.list_recent(limit=1)
    assert rows[0]["scope_basis"] == "killed-by-operator"


def test_log_mode_transition(logger):
    logger.log_mode_transition(from_mode="view_only", to_mode="active",
                                scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE)
    rows = logger.action_log.list_recent(limit=1)
    assert rows[0]["action_type"] == "mode_transition"
    details = json.loads(rows[0]["details_json"])
    assert details["from"] == "view_only"
    assert details["to"] == "active"


def test_network_authorized_scope_basis_appends_network_id(logger):
    logger.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_AUTHORIZED_NETWORK,
        action_type="z.started",
        target_network_id=42,
        outcome="started",
    )
    rows = logger.action_log.list_recent(limit=1)
    assert rows[0]["scope_basis"] == "operator-authorized-network-N42"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/audit/test_logger.py -v
```

- [ ] **Step 3: Write `mjolnir/audit/__init__.py`**

```python
"""Audit log facade."""
```

- [ ] **Step 4: Write `mjolnir/audit/logger.py`**

```python
"""AuditLogger: facade over ActionLogRepository for offensive-action logging.

Stages call this; they cannot bypass it because the NLM's run_stage_safely
wrapper (Plan 2) calls log_offensive_action() automatically.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mjolnir.db.repositories.action_log import ActionLogRepository
from mjolnir.db.repositories.system_state import SystemStateRepository


class ScopeBasis(Enum):
    """Closed vocabulary for the scope_basis column. See spec § Audit log."""
    OPERATOR_CONFIRMED_ACTIVE_MODE = "operator-confirmed-active-mode"
    OPERATOR_AUTHORIZED_NETWORK = "operator-authorized-network"
    OPERATOR_AUTHORIZED_HOST_PERSISTENCE = "operator-authorized-host-persistence"
    KILLED_BY_OPERATOR = "killed-by-operator"
    MODE_VIOLATION_ABORTED = "mode-violation-aborted"
    BLOCKLIST_VIOLATION_ABORTED = "blocklist-violation-aborted"


@dataclass
class AuditLogger:
    action_log: ActionLogRepository
    system_state: SystemStateRepository

    def log_offensive_action(
        self,
        scope_basis: ScopeBasis,
        action_type: str,
        outcome: str,
        stage_name: str | None = None,
        target_network_id: int | None = None,
        target_bssid: str | None = None,
        target_host_id: int | None = None,
        target_service_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write one audit row capturing global_mode at the moment of action."""
        global_mode = self.system_state.get_global_mode()
        basis_str = scope_basis.value
        if target_network_id is not None and scope_basis == ScopeBasis.OPERATOR_AUTHORIZED_NETWORK:
            basis_str = f"{basis_str}-N{target_network_id}"
        if target_host_id is not None and scope_basis == ScopeBasis.OPERATOR_AUTHORIZED_HOST_PERSISTENCE:
            basis_str = f"{basis_str}-H{target_host_id}"

        self.action_log.insert(
            global_mode=global_mode,
            scope_basis=basis_str,
            action_type=action_type,
            outcome=outcome,
            stage_name=stage_name,
            target_network_id=target_network_id,
            target_bssid=target_bssid,
            target_host_id=target_host_id,
            target_service_id=target_service_id,
            details=details,
        )

    def log_mode_transition(self, from_mode: str, to_mode: str,
                            scope_basis: ScopeBasis) -> None:
        self.action_log.insert(
            global_mode=to_mode,
            scope_basis=scope_basis.value,
            action_type="mode_transition",
            outcome="completed",
            details={"from": from_mode, "to": to_mode},
        )
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/audit/test_logger.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/audit/__init__.py mjolnir/audit/logger.py tests/unit/audit/test_logger.py
git commit -m "feat(audit): AuditLogger facade + ScopeBasis closed enum

Wraps ActionLogRepository, captures global_mode at log time,
and enforces the closed scope_basis vocabulary from spec § Audit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 6: Stage ABC + registry

### Task 6.1: Stage base classes + supporting types

**Files:**
- Create: `mjolnir/stages/__init__.py`
- Create: `mjolnir/stages/base.py`
- Create: `mjolnir/stages/registry.py`
- Test: `tests/unit/stages/test_base.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/stages/test_base.py
import pytest
from mjolnir.stages.base import (
    Stage, StageResult, ResourceProfile, CheckpointPolicy,
    InterfaceType, Checkpoint,
)


def test_stage_result_defaults():
    r = StageResult(status="succeeded")
    assert r.error is None
    assert r.outputs == {}
    assert r.retry_after_seconds is None


def test_resource_profile_defaults():
    rp = ResourceProfile()
    assert rp.interfaces == []
    assert rp.is_rf_transmitting is False
    assert rp.cpu_weight == "light"
    assert rp.est_duration_seconds == 60


def test_checkpoint_is_cancelled_initially_false():
    cp = Checkpoint()
    assert cp.is_cancelled() is False


def test_checkpoint_cancel_flips_to_true():
    cp = Checkpoint()
    cp.cancel(reason="kill switch")
    assert cp.is_cancelled() is True
    assert cp.cancel_reason == "kill switch"


def test_stage_is_abstract():
    with pytest.raises(TypeError):
        Stage()


def test_concrete_stage_subclass_works():
    class FakeStage(Stage):
        name = "fake"
        description = "test fixture"
        resources = ResourceProfile()
        checkpoint_policy = CheckpointPolicy.RESTART_SAFE

        def can_run(self, ctx):
            return True

        def run(self, ctx, checkpoint):
            return StageResult(status="succeeded")

    s = FakeStage()
    assert s.name == "fake"
    assert s.operates_in_view_only is False
    assert s.requires_extra_auth is False


def test_checkpoint_policy_enum_values():
    assert CheckpointPolicy.RESTART_SAFE.value == "restart_safe"
    assert CheckpointPolicy.CHECKPOINTABLE.value == "checkpointable"


def test_interface_type_enum_values():
    assert InterfaceType.WIFI.value == "wifi"
    assert InterfaceType.BLUETOOTH.value == "bluetooth"
    assert InterfaceType.BLE.value == "ble"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/stages/test_base.py -v
```

- [ ] **Step 3: Write `mjolnir/stages/base.py`**

```python
"""Stage ABC and supporting types.

The Stage ABC is the contract every capability plugs into. Concrete
stages register themselves via @registry.register.

See docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md § Stage ABC.
"""
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Literal


class InterfaceType(Enum):
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    BLE = "ble"


class CheckpointPolicy(Enum):
    RESTART_SAFE = "restart_safe"
    CHECKPOINTABLE = "checkpointable"


@dataclass
class ResourceProfile:
    interfaces: list[InterfaceType] = field(default_factory=list)
    is_rf_transmitting: bool = False
    cpu_weight: Literal["light", "medium", "heavy"] = "light"
    est_duration_seconds: int = 60


@dataclass
class StageResult:
    status: Literal["succeeded", "failed", "permanently_failed", "partial"]
    error: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    retry_after_seconds: int | None = None


@dataclass
class Checkpoint:
    """Cooperative cancellation token passed to Stage.run().

    Stages poll is_cancelled() at natural break points. The NLM sets
    cancel_reason when activating the kill switch.
    """
    _event: threading.Event = field(default_factory=threading.Event)
    cancel_reason: str | None = None

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self, reason: str = "killed") -> None:
        self.cancel_reason = reason
        self._event.set()

    def reset(self) -> None:
        self._event.clear()
        self.cancel_reason = None


@dataclass
class NetworkContext:
    """Passed to every stage invocation. The only way a stage touches the world."""
    network: Any
    db: Any
    config: Any
    interfaces: Any
    audit: Any
    workdir: Path
    checkpoint: Checkpoint


class Stage(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    resources: ClassVar[ResourceProfile]
    checkpoint_policy: ClassVar[CheckpointPolicy]
    operates_in_view_only: ClassVar[bool] = False
    requires_extra_auth: ClassVar[bool] = False

    @abstractmethod
    def can_run(self, ctx: NetworkContext) -> bool: ...

    @abstractmethod
    def run(self, ctx: NetworkContext, checkpoint: Checkpoint) -> StageResult: ...

    def resume_from_checkpoint(
        self, ctx: NetworkContext, checkpoint_data: dict[str, Any]
    ) -> StageResult | None:
        return None

    def on_interrupt(self, ctx: NetworkContext) -> None:
        return None
```

- [ ] **Step 4: Write `mjolnir/stages/registry.py`**

```python
"""Stage registry: tracks all Stage subclasses, provides filtering by mode."""
from mjolnir.stages.base import Stage


class StageRegistry:
    def __init__(self):
        self._stages: dict[str, type[Stage]] = {}

    def register(self, stage_cls: type[Stage]) -> type[Stage]:
        self._stages[stage_cls.name] = stage_cls
        return stage_cls

    def get(self, name: str) -> type[Stage] | None:
        return self._stages.get(name)

    def all_stages(self) -> list[type[Stage]]:
        return list(self._stages.values())

    def stages_eligible_for_mode(self, mode: str) -> list[type[Stage]]:
        if mode == "active":
            return self.all_stages()
        if mode == "view_only":
            return [s for s in self.all_stages() if s.operates_in_view_only]
        raise ValueError(f"unknown mode: {mode}")


registry = StageRegistry()
```

- [ ] **Step 5: Write `mjolnir/stages/__init__.py`**

```python
"""Stage framework: ABC, registry, supporting types."""
from mjolnir.stages.base import (
    Checkpoint,
    CheckpointPolicy,
    InterfaceType,
    NetworkContext,
    ResourceProfile,
    Stage,
    StageResult,
)
from mjolnir.stages.registry import StageRegistry, registry

__all__ = [
    "Checkpoint",
    "CheckpointPolicy",
    "InterfaceType",
    "NetworkContext",
    "ResourceProfile",
    "Stage",
    "StageResult",
    "StageRegistry",
    "registry",
]
```

- [ ] **Step 6: Run tests to verify pass**

```bash
pytest tests/unit/stages/test_base.py -v
```
Expected: PASS (8 tests)

- [ ] **Step 7: Commit**

```bash
git add mjolnir/stages/__init__.py mjolnir/stages/base.py mjolnir/stages/registry.py tests/unit/stages/test_base.py
git commit -m "feat(stages): Stage ABC + supporting types

Stage ABC with two abstract methods (can_run, run) plus opt-in
hooks for checkpointable resumption and interrupt handling.
Checkpoint, StageResult, ResourceProfile, NetworkContext defined.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 6.2: Registry decorator + tests

**Files:**
- Test: `tests/unit/stages/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/stages/test_registry.py
import pytest

from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry


def make_stage(name: str, operates_in_view_only: bool = False):
    class _S(Stage):
        resources = ResourceProfile()
        checkpoint_policy = CheckpointPolicy.RESTART_SAFE
        operates_in_view_only = operates_in_view_only

        def can_run(self, ctx):
            return True

        def run(self, ctx, checkpoint):
            return StageResult(status="succeeded")

    _S.name = name
    _S.description = f"test stage {name}"
    return _S


def test_register_stores_class_by_name():
    reg = StageRegistry()
    s = make_stage("alpha")
    reg.register(s)
    assert reg.get("alpha") is s


def test_register_returns_class_for_decorator_use():
    reg = StageRegistry()
    s = make_stage("beta")
    returned = reg.register(s)
    assert returned is s


def test_get_missing_returns_none():
    reg = StageRegistry()
    assert reg.get("nope") is None


def test_all_stages_returns_list():
    reg = StageRegistry()
    reg.register(make_stage("a"))
    reg.register(make_stage("b"))
    names = sorted(s.name for s in reg.all_stages())
    assert names == ["a", "b"]


def test_register_duplicate_name_overwrites():
    reg = StageRegistry()
    reg.register(make_stage("dup"))
    reg.register(make_stage("dup"))
    assert len(reg.all_stages()) == 1


def test_all_stages_empty_when_no_registrations():
    reg = StageRegistry()
    assert reg.all_stages() == []


def test_stages_eligible_for_view_only():
    reg = StageRegistry()
    reg.register(make_stage("passive", operates_in_view_only=True))
    reg.register(make_stage("active_only", operates_in_view_only=False))
    eligible = reg.stages_eligible_for_mode("view_only")
    names = {s.name for s in eligible}
    assert names == {"passive"}


def test_stages_eligible_for_active_returns_all():
    reg = StageRegistry()
    reg.register(make_stage("a"))
    reg.register(make_stage("b"))
    assert len(reg.stages_eligible_for_mode("active")) == 2


def test_stages_eligible_for_invalid_mode_raises():
    reg = StageRegistry()
    with pytest.raises(ValueError):
        reg.stages_eligible_for_mode("weird")
```

- [ ] **Step 2: Run tests to verify pass**

```bash
pytest tests/unit/stages/test_registry.py -v
```
Expected: PASS (9 tests). The registry was already implemented in Task 6.1 Step 4; these tests verify its behavior.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/stages/test_registry.py
git commit -m "test(stages): StageRegistry behavior coverage

Register/get/duplicate-overwrite, list-all, mode-based filtering
for view_only vs active.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 7: main.py + integration test

### Task 7.1: main.py stub entrypoint

**Files:**
- Create: `mjolnir/main.py`

This is a stub. Plan 2 adds the NLM loop; Plan 3 adds Flask. No test for the stub itself — the integration test in Task 7.2 covers the initialization path.

- [ ] **Step 1: Write `mjolnir/main.py`**

```python
"""mjolnir entrypoint.

For Plan 1: initializes the database and exits. Subsequent plans extend
this with the NLM main loop, Flask WebUI, and EPD renderer.
"""
import argparse
import sys
from pathlib import Path

from mjolnir.config import BjornConfig, load_config
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mjolnir daemon")
    parser.add_argument(
        "--config", type=Path, default=Path("/etc/mjolnir/config.toml"),
        help="path to TOML config file",
    )
    parser.add_argument(
        "--init-db", action="store_true",
        help="initialize the database and exit",
    )
    return parser.parse_args(argv)


def initialize(config: BjornConfig) -> None:
    """Open the DB, apply schema, run migrations, seed defaults. Idempotent."""
    factory = ConnectionFactory(db_path=config.db.path)
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"error: config file not found: {args.config}", file=sys.stderr)
        return 2

    initialize(config)

    if args.init_db:
        print(f"initialized db at {config.db.path}")
        return 0

    print("mjolnir initialized; daemon loop not yet implemented (see Plan 2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit**

```bash
git add mjolnir/main.py
git commit -m "feat(main): entrypoint stub with --init-db

Initializes DB + applies schema + seeds defaults. Daemon loop
will be added in Plan 2; --init-db flag exits after setup.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 7.2: Integration test — DB lifecycle end-to-end

**Files:**
- Test: `tests/integration/test_db_lifecycle.py`

- [ ] **Step 1: Write the integration test**

```python
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
        db=DbConfig(path=data_dir / "mjolnir.db"),
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
    assert any(r["action_type"] == "mode_transition" for r in rows)

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
```

- [ ] **Step 2: Run integration tests**

```bash
pytest tests/integration/ -v
```
Expected: PASS (3 tests)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_db_lifecycle.py
git commit -m "test(integration): DB lifecycle end-to-end

Verifies connect -> schema -> seed -> write -> close -> reopen ->
read-back. Mode toggle and audit-log writes survive simulated
reboot. Migration version tracking is current. initialize() is
idempotent across calls.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 8: Plan 1 acceptance

### Task 8.1: Full test suite green

- [ ] **Step 1: Run the entire test suite with coverage**

```bash
pytest tests/ -v --cov=mjolnir --cov-report=term-missing
```

Expected:
- All tests pass (60+ tests across unit + integration)
- Coverage of `mjolnir/` >= 85%

- [ ] **Step 2: If coverage <85% or any test fails, fix before proceeding**

Common gaps to watch for:
- Error paths in repository methods (CHECK constraint violations)
- Network disambiguator boundary cases
- Stage registry with empty registry

### Task 8.2: README note + tag

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append a v2 section to README.md**

Add to root `README.md` after the v1 content:

```markdown
---

## mjolnir (v2)

v2 is the next-generation platform, built mostly ground-up alongside v1.
See `docs/ROADMAP.md` for the v2 effort plan, and
`docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md` for
the design.

To initialize the v2 DB:

    python -m mjolnir.main --config config/mjolnir.toml --init-db
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): note mjolnir v2 alongside v1

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

- [ ] **Step 3: Verify clean working tree**

```bash
git status
```
Expected: "nothing to commit, working tree clean"

- [ ] **Step 4: Create annotated tag**

```bash
git tag -a v0.1.0-plan1 -m "Plan 1 of sub-project #0 complete: foundation layer

- mjolnir package skeleton + typed config
- Full SQLite schema (23 tables, 21 indexes)
- Connection factory with PRAGMAs
- Migration framework with version tracking
- Repositories: system_state, networks, bssids, bssid_sightings, stage_states, stage_outputs, action_log
- AuditLogger with ScopeBasis closed enum
- Stage ABC + registry with mode filtering
- main.py entrypoint stub with --init-db
- 60+ unit tests + 3 integration tests"
```

- [ ] **Step 5: Verify tag**

```bash
git tag -l "v0.1*"
```
Expected: `v0.1.0-plan1` listed

---

## Plan 1 acceptance criteria

Sub-project #0, Plan 1, is complete when ALL of the following are true:

1. All ~60 unit tests pass
2. All 3 integration tests pass
3. Test coverage of `mjolnir/` >= 85%
4. `python -m mjolnir.main --config config/mjolnir.toml --init-db` runs without error against a fresh temp directory
5. Fresh DB seeds `global_mode='view_only'`, `kill_switch_engaged=''`, `schema_version=1`
6. Mode toggle persists across simulated reboot (verified by integration test)
7. Audit log writes include `global_mode` captured at log time
8. `Stage` subclass can be defined and registered
9. `StageRegistry.stages_eligible_for_mode("view_only")` filters correctly
10. Tag `v0.1.0-plan1` exists

---

## Plan 2 preview (next plan, not yet written)

Plan 2 will build on this foundation to deliver:

- `mjolnir/interfaces/` — `InterfaceManager`, `WiFiInterface` (passive scan only), BT/BLE stubs
- `mjolnir/nlm/` — Network Lifecycle Manager (state machine, scheduler, mode transitions, kill switch handler, ESS union-find identity resolver)
- `mjolnir/stages/passive_scan.py` — first concrete Stage implementation
- Subprocess-per-stage execution wrapper with `RLIMIT_AS` enforcement
- Checkpoint save/load for CHECKPOINTABLE stages
- Integration: device boots, observes a real WiFi network within 60s, row appears in `networks` table

Plan 2 cannot be written until Plan 1 is implemented and any reality corrections to the spec are captured. Implement Plan 1 first.
