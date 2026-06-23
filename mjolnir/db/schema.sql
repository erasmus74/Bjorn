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
    -- Audit log: FKs intentionally omit ON DELETE CASCADE so audit records
    -- survive target deletion (preserves engagement history for legal defense).
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
    tunnel_id           INTEGER REFERENCES tunnels(id),  -- forward reference; tunnels defined below, FK resolved at query time
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
