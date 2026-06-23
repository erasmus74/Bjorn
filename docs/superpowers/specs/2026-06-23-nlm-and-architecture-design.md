# Sub-project #0 — Network Lifecycle Manager & v2 Architecture

**Status:** Proposed
**Date:** 2026-06-23
**Branch:** `feat/v2-platform`
**Sub-project:** #0 of the v2 platform effort (see `docs/ROADMAP.md`)

## Purpose

Establish the safety substrate and architectural foundation for the v2 Bjorn effort. v2 turns Bjorn from a network scanner into an autonomous authorized-security-testing platform. This sub-project lands:

- A **Network Lifecycle Manager (NLM)** that drives per-network state machines with resume-on-return
- A **mode toggle** (`view_only` ↔ `active`) as the primary safety guardrail — default-off, persists across reboots
- A **per-network scope model** (`enabled` / `disabled` / `blocklisted`) managed via WebUI
- A **kill switch** for instant deactivation of offensive operations
- A **persistence-authorization framework** requiring two-tier explicit operator opt-in (network + host)
- An **audit log** recording every offensive action with scope basis
- A **clean package layout** (`bjorn_v2/`) built alongside v1, which stays as reference
- A **Stage ABC** that all future capabilities plug into
- A **vertical slice** proving every architectural layer end-to-end via `PassiveScanStage`

## Hardware target

Raspberry Pi Zero 2 W with 2.13" e-Paper HAT (Waveshare V2/V4). Same hardware as v1; no hardware changes.

- **CPU**: 1GHz quad-core ARM Cortex-A53
- **RAM**: 512MB
- **Storage**: microSD card (8GB minimum, 64GB recommended)
- **WiFi**: single radio (b/g/n) — the radio is a contended resource
- **Bluetooth**: BT/BLE — used by future sub-projects, not in scope for #0
- **GPIO**: fully consumed by the e-Paper HAT — no buttons

Resource constraints drive several design choices: SQLite over a heavier DB; Flask over FastAPI; subprocess-per-stage memory isolation; bounded thread pools.

## Goals

1. **Safety substrate first.** Build authorization, scope, audit, kill switch before any offensive capability lands.
2. **Default-safe.** Fresh install boots in `view_only` mode; offensive operations require explicit operator opt-in that persists across reboots.
3. **Per-network state machine.** Each discovered network is a persistent, resumable entity progressing through defined lifecycle stages.
4. **Clean architecture.** Stage ABC is the single extension point; adding capabilities in sub-projects #3–#6 means adding new Stage implementations, not modifying the NLM.
5. **Reference-comparable.** v1 codebase stays in-tree; v2 can be validated against v1 behavior.

## Non-goals

- Implementing offensive stages beyond `passive_scan` (those are sub-projects #3–#5)
- BT tether, Tailscale, multi-SSID priority (sub-project #1)
- WebUI auth, persistence-stage UI beyond the authorization flow (future)
- BLE interface implementation (future)

## Architecture

### Package layout

v1 stays at the repo root, relocated to `v1/` for clarity. v2 lives in `bjorn_v2/`. Both coexist during the v2 build-out; v1 is the reference implementation.

```
bjorn/
├── v1/                       ← v1 code relocated here (reference)
├── bjorn_v2/                 ← v2 package
│   ├── main.py               ← systemd entrypoint
│   ├── config.py             ← typed config loader
│   ├── nlm/                  ← Network Lifecycle Manager
│   │   ├── manager.py        ← main loop + scheduling
│   │   ├── state.py          ← per-network state machine
│   │   ├── identity.py       ← SSID/BSSID grouping, ESS union-find
│   │   └── scope.py          ← mode toggle + blocklist + per-network enable
│   ├── stages/
│   │   ├── base.py           ← Stage ABC, StageResult, ResourceProfile
│   │   ├── registry.py       ← stage auto-discovery
│   │   └── passive_scan.py   ← slice implementation
│   ├── db/
│   │   ├── schema.sql        ← idempotent DDL
│   │   ├── connection.py     ← connection factory + PRAGMAs
│   │   ├── migrations.py     ← versioned schema migrations
│   │   └── repositories/     ← one per table/network aggregate
│   ├── interfaces/
│   │   ├── manager.py        ← InterfaceManager
│   │   ├── wifi.py           ← WiFiInterface (passive scan only in #0)
│   │   ├── bluetooth.py      ← stub (raises NotImplementedError)
│   │   └── ble.py            ← stub (future)
│   ├── ui/
│   │   ├── web/              ← Flask app, Jinja2 templates, HTMX
│   │   └── epd/              ← display state manager + 14 layouts
│   ├── audit/
│   │   └── logger.py         ← action_log writer
│   └── utils.py
├── data/
│   ├── bjorn.db              ← SQLite (created on first run)
│   ├── logs/
│   ├── backups/
│   ├── captures/             ← wifi_captures.local_path target
│   ├── loot/                 ← file_loot.local_path target
│   └── stages/               ← per-network workdir, checkpoint.json files
├── config/
│   └── v2_config.toml
├── scripts/
│   ├── migrate_v1_to_v2.py
│   └── bjorn.service
└── docs/
```

### Module boundary rules

- **`nlm/`** is the only module that decides what work to do next. Nothing else schedules work.
- **`stages/`** is where work happens. Every capability is a `Stage` subclass. Adding capabilities = adding files here.
- **`db/`** is the only thing that touches SQLite. Stages and the NLM talk to repository objects.
- **`interfaces/`** is the only module allowed to transmit or use monitor mode. The kill switch's "halt all RF" is a single method call here.
- **`audit/`** is append-only. The `Stage.run()` wrapper in NLM calls `audit.log()` — stages cannot bypass it.

### Web framework

Flask + Jinja2 templates + HTMX (no SPA framework). Rationale: minimal dependency tree, well-suited to single-user embedded UI, HTMX handles "click button → fetch HTML → swap" without bespoke JS.

## Data model

SQLite. One file at `data/bjorn.db`. 22 tables total — full DDL lives in `bjorn_v2/db/schema.sql`. Summary below.

### Connection PRAGMAs

Applied on every connection open:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-2000;       -- 2MB page cache
PRAGMA temp_store=MEMORY;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

### Tables

**Core entities**

- `networks` — ESS-level entity (SSID + disambiguator). Carries `scope_state`, `persistence_authorized`, lifecycle stage info, exhaustion status.
- `bssids` — physical APs under each network. Unique on BSSID.
- `bssid_sightings` — time-series observations (signal, channel) for resume-on-return and signal history.
- `hosts` — discovered devices. MAC unique per network. `is_gateway`, `is_self`, `device_type`, `persistence_authorized`.
- `services` — open ports on hosts. Port+protocol unique per host.
- `credentials` — cracked creds (WiFi PSK + service creds). `privilege_level`, `validity_state`.
- `vulnerabilities` — confirmed CVEs on hosts. `exploitability`, `discovery_method`.

**Lifecycle and audit**

- `stage_states` — `(network_id, stage_name)` composite key. `status` ∈ `pending` / `running` / `succeeded` / `failed` / `permanently_failed` / `skipped`. `attempts`, `last_attempt_at`, `completed_at`, `failure_reason`.
- `action_log` — append-only offensive-action audit trail. `scope_basis`, `action_type`, `outcome`, `target_*` fields, `details_json`.
- `system_state` — key/value singleton. Holds `global_mode`, `kill_switch_engaged`, `schema_version`.
- `stage_outputs` — per-stage structured key/value results (counters, computed metrics).
- `operator_notes` — freeform notes attached to any entity (`target_type`, `target_id`).

**WiFi offensive layer (#3-ready)**

- `wifi_captures` — handshakes, PMKIDs, raw pcaps. `crack_status`, `crack_attempts`, `cracked_credential_id`.

**Loot / sessions / exploitation (#5-ready, Metasploit-domain entities)**

- `file_loot` — stolen files with sha256 for dedup.
- `sessions` — active sessions on compromised hosts. `session_type`, `privilege_level`.
- `payloads` — generated payloads.
- `listeners` — active listeners for reverse shells.
- `exploit_attempts` — CVE-based attempts with success/fail tracking.
- `privesc_attempts` — privilege escalation attempts.

**Credential attack resources**

- `wordlists` — wordlists, rule files, masks. Hash-indexed for dedup.

**Connectivity (#1-ready)**

- `bt_devices` — discovered Bluetooth/BLE devices.
- `tunnels` — active tunnels (Tailscale, BT tether, VPN).
- `preferred_ssids` — operator-known networks with priority for auto-join.

### Key schema decisions

- **No separate `blocklist` table.** Blocklist is `networks.scope_state = 'blocklisted'` + `blocklist_reason`. Avoids sync between two tables.
- **Integer surrogate primary keys** everywhere. Natural keys (BSSID, SSID) get uniqueness constraints but aren't used for joins.
- **ISO-8601 TEXT timestamps.** Lexicographically sortable; no timezone ambiguity.
- **`credentials.secret` stored in plaintext.** Plaintext is the loot. DB file is `chmod 600`; disk encryption is operator's responsibility.
- **Two-tier persistence authorization** as columns on `networks` and `hosts`: `persistence_authorized` + `_at` + `_by`. Both must be true for persistence stage to run on a given host.

### Indexes

```sql
CREATE INDEX idx_bssids_network_id        ON bssids(network_id);
CREATE INDEX idx_sightings_bssid_seen     ON bssid_sightings(bssid_id, seen_at);
CREATE INDEX idx_hosts_network            ON hosts(network_id);
CREATE INDEX idx_services_host            ON services(host_id);
CREATE INDEX idx_stage_states_status      ON stage_states(status);
CREATE INDEX idx_action_log_timestamp     ON action_log(timestamp);
CREATE INDEX idx_action_log_network       ON action_log(target_network_id);
CREATE INDEX idx_networks_scope_state     ON networks(scope_state);
CREATE INDEX idx_networks_last_seen       ON networks(last_seen);
CREATE INDEX idx_wifi_captures_network    ON wifi_captures(network_id, crack_status);
CREATE INDEX idx_file_loot_host           ON file_loot(host_id);
CREATE INDEX idx_file_loot_network        ON file_loot(network_id);
CREATE INDEX idx_sessions_host_active     ON sessions(host_id, is_active);
CREATE INDEX idx_exploit_attempts_host    ON exploit_attempts(host_id, succeeded);
CREATE INDEX idx_privesc_attempts_host    ON privesc_attempts(host_id, succeeded);
CREATE INDEX idx_wordlists_type           ON wordlists(resource_type);
CREATE INDEX idx_bt_devices_seen          ON bt_devices(last_seen);
CREATE INDEX idx_tunnels_active           ON tunnels(is_active);
CREATE INDEX idx_preferred_ssids_prio     ON preferred_ssids(priority);
CREATE INDEX idx_operator_notes_target    ON operator_notes(target_type, target_id);
CREATE INDEX idx_stage_outputs_lookup     ON stage_outputs(network_id, stage_name);
```

## Stage ABC and lifecycle state machine

### Stage ABC

```python
class InterfaceType(Enum):
    WIFI = 'wifi'
    BLUETOOTH = 'bluetooth'
    BLE = 'ble'

class CheckpointPolicy(Enum):
    RESTART_SAFE = 'restart_safe'
    CHECKPOINTABLE = 'checkpointable'

@dataclass
class ResourceProfile:
    interfaces: list[InterfaceType] = field(default_factory=list)
    is_rf_transmitting: bool = False
    cpu_weight: Literal['light', 'medium', 'heavy'] = 'light'
    est_duration_seconds: int = 60

@dataclass
class StageResult:
    status: Literal['succeeded', 'failed', 'permanently_failed', 'partial']
    error: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    retry_after_seconds: int | None = None

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

    def resume_from_checkpoint(self, ctx: NetworkContext,
                                checkpoint_data: dict) -> StageResult | None:
        """Override for CHECKPOINTABLE stages that opt into resumption."""
        return None

    def on_interrupt(self, ctx: NetworkContext) -> None: ...
```

### NetworkContext

The only object passed to stage invocations. The only way a stage touches the outside world.

```python
@dataclass
class NetworkContext:
    network: Network
    db: RepositoryBundle
    config: BjornConfig
    interfaces: InterfaceManager
    audit: AuditLogger
    workdir: Path
    checkpoint: Checkpoint
```

### Stage registry

Stages self-register at import time via a decorator. NLM discovers them without hard-coding.

```python
@registry.register
class PassiveScanStage(Stage):
    name = 'passive_scan'
    ...
```

Unregistered stages in the spine (i.e., not yet implemented) are skipped — `can_run` defaults to False for any stage not in the registry. The linear spine can list all 11 stages from day one without breaking on unimplemented ones.

### Lifecycle stages (linear spine)

| # | Stage | Mode | Checkpoint policy | Notes |
|---|---|---|---|---|
| 1 | `passive_scan` | either | Restart-safe | Operates in view_only |
| 2 | `wifi_probe` | either | Restart-safe | Operates in view_only |
| 3 | `wifi_crack` | active | Restart-safe | RF transmit; capture file is the checkpoint |
| 4 | `lan_enum` | active | Restart-safe | Re-scan no-ops known hosts |
| 5 | `service_enum` | active | Restart-safe | nmap-driven |
| 6 | `credential_attack` | active | Checkpointable | Wordlist position per service |
| 7 | `vuln_scan` | active | Restart-safe | nmap NSE |
| 8 | `exploitation` | active | Checkpointable | Exploits-tried set |
| 9 | `privesc` | active | Checkpointable | Techniques-tried set |
| 10 | `lateral_movement` | active | Checkpointable | Visited-hosts set |
| 11 | `persistence` | active + `persistence_authorized` | Checkpointable | Two-tier auth: network + host |

### Data-availability gates

Stages gate on data presence, not on predecessor stage status:

```
passive_scan:        always runnable
wifi_probe:          network.last_seen within 5 minutes
wifi_crack:          wifi_probe succeeded AND network.security_type != 'open'
                     AND no wifi_psk credential exists for this network
lan_enum:            network.security_type == 'open' OR wifi_psk credential exists
                     AND lan_enum not yet succeeded
service_enum:        lan_enum succeeded AND at least 1 host discovered
credential_attack:   service_enum succeeded AND ≥1 service in cred-attack portlist
                     AND not yet attempted on all such services
vuln_scan:           service_enum succeeded AND hosts exist
exploitation:        vuln_scan succeeded AND ≥1 vulnerability.exploit_available=1
privesc:             ≥1 active session exists AND privesc not yet attempted
lateral_movement:    ≥1 session with privilege_level in ('root','system','admin')
                     AND multiple hosts exist on network
persistence:         network.persistence_authorized = 1
                     AND ≥1 host with hosts.persistence_authorized = 1
                     AND ≥1 active session with privilege_level in ('root','system','admin')
```

### Exhaustion

A network is `exhausted` when no stage has status `pending` or `running` — every stage is `succeeded`, `permanently_failed`, or `skipped`.

`networks.exhausted_reason` is one of:

- `all_stages_succeeded` — happy path
- `cannot_crack_wifi` — `wifi_crack` permanently failed
- `no_vulnerable_hosts` — got in, but nothing exploitable
- `no_credentials_found` — got in, services found, no creds worked
- `all_lateral_targets_exhausted` — pivoted everywhere reachable

### Parallelism within a stage

The spine is linear (one stage at a time per network). Within a stage, the implementation may fan out internally (e.g., `credential_attack` runs SSH/FTP/SMB/RDP/Telnet/SQL brutes concurrently, bounded by a per-stage semaphore defaulting to 4 on Zero 2W). The Stage's `run()` manages its own internal concurrency; the NLM only guarantees "no two stages run simultaneously on the same network" and "no two transmitting stages share the radio".

### ESS identity rule (BSSID-overlap union-find)

When the device sees an SSID that already exists in the DB, match against the stored network(s) for that SSID:

- **Any BSSID overlap** with an existing network → same ESS, extend that network's BSSID set with the newly-seen APs.
- **Zero BSSID overlap** → create a new network entry under the same SSID, disambiguator incremented (`<SSID> #2`, `#3`, etc.).

## Control flow

### Boot sequence

1. systemd starts `bjorn.service` → `bjorn_v2.main:main()`
2. Load typed config from `config/v2_config.toml`. Fail fast on missing required keys.
3. Initialize SQLite: apply PRAGMAs, run pending migrations, seed `system_state` defaults if fresh DB.
4. Restore persisted mode: read `system_state.global_mode`. **Fresh install defaults to `view_only`.** Subsequent boots restore the last persisted mode.
5. Initialize `InterfaceManager` (acquires interface handles; does NOT transmit).
6. Start Flask WebUI in background thread, bound to `config.web.bind_interface` (default `127.0.0.1` for #0).
7. Initialize EPD renderer; show `STARTING_UP` screen.
8. Initialize NLM (loads stage registry, rebuilds per-network state from DB).
9. NLM enters main loop (foreground).

### NLM main loop

```python
def main_loop(self):
    while not self.shutdown_requested:
        if self.kill_switch_engaged():
            self.wait_for_release()
            continue

        eligible_stages = ([s for s in self.registry if s.operates_in_view_only]
                           if self.global_mode == 'view_only'
                           else list(self.registry))

        work = self.find_eligible_work(eligible_stages)
        # Returns (network, stage) pairs where:
        #   - stage.can_run(ctx) returned True
        #   - data-availability prerequisites are satisfied
        #   - interface resources are available
        #   - network.scope_state == 'enabled'
        #   - network not exhausted
        #   - persistence-specific gates pass for persistence stage

        if not work:
            self.idle_sleep(seconds=30)
            continue

        with self.stage_pool as pool:           # size 4
            for network, stage in work:
                if self.can_acquire_resources(stage.resources):
                    pool.submit(self.run_stage_safely, network, stage)

        self.mark_exhausted_networks()
        self.refresh_epd_display()
        self.idle_sleep(seconds=self.config.scan_interval)
```

### `run_stage_safely` wrapper

Every stage runs through this; stages cannot bypass it:

1. Acquire interface resources (exclusive locks on WiFi/BT/BLE).
2. Mark `stage_states` row `status='running'`, increment `attempts`.
3. Write `action_log` row: `outcome='started'`, `scope_basis=<computed>`.
4. Build `NetworkContext`.
5. Create `Checkpoint` bound to kill-switch event.
6. **Subprocess invocation**: stage runs in a child process with `RLIMIT_AS` enforced. Parent communicates via stdin/stdout JSON lines.
7. If `CheckpointPolicy.CHECKPOINTABLE` and `workdir/checkpoint.json` exists, call `stage.resume_from_checkpoint(ctx, checkpoint_data)`; else call `stage.run(ctx, checkpoint)`.
8. On `Checkpoint.is_cancelled()` becoming True: stage exits at next natural break with `StageResult(status='failed', error='killed')`; NLM marks stage back to `pending` for resume; checkpointable stages save progress first.
9. On uncaught exception: log to application log, mark stage `failed`, write `action_log` row with `outcome='failed'`.
10. Write `result.outputs` to `stage_outputs`.
11. Update `stage_states` row with final `status`, `completed_at`, `failure_reason`.
12. Write `action_log` row: `outcome=<result.status>`.
13. Release interface resources.
14. If `permanently_failed`: cascade `skipped` to downstream stages whose data-gate depends on this stage's success.

### Mode transitions

**`view_only` → `active`** (via WebUI toggle):

1. Operator clicks "Activate"; confirmation dialog shown.
2. Flask endpoint writes `system_state.global_mode = 'active'`, `updated_at = now`.
3. Next main loop iteration reads new mode; `eligible_stages` expands.
4. Previously-paused stages (`status='pending'`) resume naturally.
5. `action_log` records transition: `action_type='mode_transition'`, `details_json={'from':'view_only','to':'active'}`, `scope_basis='operator-activated'`.

**`active` → `view_only`** (kill switch or WebUI toggle):

1. `system_state.kill_switch_engaged = <ISO timestamp>` written.
2. `Checkpoint.is_cancelled()` returns True for all in-flight stages.
3. `interfaces.halt_all_transmissions()` called immediately — RF-transmitting stages hard-halt at the radio layer.
4. In-flight non-RF stages exit at next checkpoint (sub-second typically).
5. Killed stages marked back to `pending` (not `failed`) for resume on re-activation.
6. Checkpointable stages save progress to `workdir/checkpoint.json` before exit.
7. Kill switch stays engaged until operator explicitly releases via WebUI.

**Per-network `blocklisted`** (via WebUI form):

1. Set `networks.scope_state = 'blocklisted'`, `scope_changed_at = now`, `scope_changed_by = operator`.
2. NLM main loop skips this network in `find_eligible_work`.
3. Any in-flight stage on this network is killed via checkpoint.
4. `stage_states` rows preserved — un-blocklisting resumes from where we left off.
5. Passive scan may still *observe* blocklisted BSSIDs; the network appears in the WebUI list with a `BLOCKED` tag.

### Shutdown sequence

1. systemd sends SIGTERM.
2. Main loop sets `shutdown_requested = True`.
3. Wait for in-flight stages to reach checkpoint or finish (max 10s grace).
4. Checkpointable stages save progress to `workdir/checkpoint.json`.
5. Close SQLite WAL cleanly (`PRAGMA wal_checkpoint(TRUNCATE)`).
6. Display `SHUTTING_DOWN` screen.
7. Exit 0.

## UI surfaces

### WebUI

**Stack**: Flask + Jinja2 + HTMX, no auth in #0, server-rendered.

**Bind interface**: configurable in `v2_config.toml`. Default `127.0.0.1` (SSH port-forward access) for #0; sub-project #1 changes default to `tailscale0`.

**Endpoints**:

```
/                          Dashboard
/networks                  Networks inventory (list + filters)
/networks/<id>             Network detail (BSSIDs, hosts, services, creds, vulns, stage progress)
/networks/<id>/hosts/<hid> Host detail (services, vulnerabilities, sessions, loot, persistence)
/blocklist                 Blocklist manager
/preferred                 Preferred SSIDs (populated by #1)
/credentials               All cracked credentials
/loot                      All stolen files
/captures                  WiFi captures
/tunnels                   Active tunnels (populated by #1)
/audit                     Action log (filterable)
/settings                  System state (mode, kill switch, scope config)
```

**Dashboard**: current mode banner, kill switch status, summary stats (networks discovered/exhausted/cracked, hosts, credentials, vulnerabilities), active work list, recent action log (last 20 entries), quick toggles.

**Networks inventory**: table with filters (`scope_state`, `exhausted`, `security_type`, `has_credentials`); per-row actions (View, Blocklist, Disable, Authorize persistence); preemptive-add form.

**Network detail**: header + stage progress bar (11 stages) + counters + sub-tabs (BSSIDs, Hosts, Credentials, Vulnerabilities, Loot, Captures, Audit, Notes) + danger-zone authorization buttons.

**Host detail**: header + services table + active sessions + vulnerabilities + loot + persistence status + per-host persistence authorization button (enabled only when network is authorized).

**Persistence authorization UI** — two separate buttons, both with confirmation dialogs requiring the user to type the SSID or hostname/IP to confirm. Revoke buttons clear the flag immediately (do not undo already-planted persistence — that requires manual cleanup; audit log records what was planted where).

### E-Paper display

**Hardware**: 122×250 pixels, monochrome, slow refresh (~2-3s full, ~0.3s partial). Display-only — no buttons.

**Display state priority** — the display manager picks one state based on current system status; higher-priority states preempt lower-priority ones.

| Priority | State | Trigger |
|---|---|---|
| 1 | `SHUTTING_DOWN` | Shutdown sequence running |
| 2 | `STARTING_UP` | Boot sequence not yet complete |
| 3 | `FATAL_ERROR` | Unrecoverable error |
| 4 | `KILL_SWITCH_ENGAGED` | `system_state.kill_switch_engaged` set |
| 5 | `NO_INTERFACES_UP` | No WiFi adapter available |
| 6 | `NO_NETWORKS_VISIBLE` | Scanning but no beacons seen |
| 7 | `NO_KNOWN_NETWORKS` | Networks visible but none in `preferred_ssids` |
| 8 | `CONNECTING` | Joining a known SSID |
| 9 | `NO_INTERNET` | Connected to WiFi but no upstream |
| 10 | `TAILSCALE_DOWN` | Internet OK, Tailscale not connected |
| 11 | `ACTIVE_IDLE` | Active mode, no pending work, networks exhausted |
| 12 | `VIEW_ONLY_PASSIVE` | View-only mode, passively observing |
| 13 | `ACTIVE_WORKING` | Active mode, stage(s) running — 3 rotating sub-screens |
| Overlay | `BLOCKLIST_NEARBY` | Banner shown on any state when a blocklisted network is in range |

Every idle state explicitly answers "why am I idle?" — never just a blank screen.

**Refresh strategy**:

- Active work: partial refresh every 4s for counters; full refresh every 60s
- Idle/error/kill: full refresh on state transition only
- Startup/shutdown: single full refresh per transition

## Audit log

**Table**: `action_log` (see schema).

**Write triggers**: every offensive action writes two rows — `outcome='started'` before `stage.run()`, `outcome=<final status>` after. Written by the NLM `run_stage_safely` wrapper; stages cannot bypass.

**`scope_basis` vocabulary** (closed set, validated):

| Value | When |
|---|---|
| `operator-confirmed-active-mode` | Default for any action in active mode |
| `operator-authorized-network-N` | Network explicitly enabled by operator |
| `operator-authorized-host-N-persistence` | Persistence stage specifically authorized |
| `killed-by-operator` | Stage exited because kill switch activated |
| `mode-violation-aborted` | Stage attempted to run in view_only — bug indicator |
| `blocklist-violation-aborted` | Stage attempted to run on blocklisted network — bug indicator |

The last two are panic values. They're written *instead of* the offensive action, marking that the gating logic caught a violation. A CI invariant test verifies no row in `action_log` has these values.

**Retention**: append-only, never auto-deleted.

**Export**: WebUI buttons export as JSON Lines, CSV, or formatted HTML engagement report.

**Backups**: SQLite `.backup` API every 6 hours to `data/backups/bjorn-YYYYMMDD-HHMMSS.db`, 7-day retention.

## Resource budget

### Memory (target ≤350MB for the entire Bjorn process)

```
OS reserved                  150 MB
Flask + Jinja                  30 MB
SQLite (cache + WAL)            4 MB
EPD framebuffer                 1 MB
NLM main loop + threading      20 MB
Per-stage subprocess overhead  20 MB  (~5MB per subprocess × 4 pool)
Stage working set cap         100 MB  (4 × 25MB avg)
Buffer/headroom               ~150 MB
```

**Enforcement**: stages run in **subprocesses** (not just threads), with `resource.setrlimit(RLIMIT_AS, ...)` capping the address space. Threads within the stage share the stage's address space. Runaway stages can't OOM the box.

### CPU

```
4-core A53 budget:
  OS + Flask              0.2 cores
  NLM main loop           0.1 cores
  EPD refresh             0.1 cores (bursty)
  Available for stages    ~3.5 cores

Per-stage CPU cap:
  cpu_weight='light'      1 core max
  cpu_weight='medium'     2 cores max
  cpu_weight='heavy'      3 cores max
```

**Enforcement**: `nice` + `taskset` to pin stages; `cpulimit` for hard caps where needed.

### Disk

- **Thresholds** (configurable): warning at 8GB, hard-stop at 16GB (assuming 64GB card)
- **WAL management**: `PRAGMA wal_checkpoint(TRUNCATE)` every 1 hour
- **Loot retention**: operator-configurable N-day retention for loot files; metadata rows preserved
- **Logs**: rotated daily, 14-day retention

### Boot time

Target ≤30s from systemd-start to NLM-main-loop-entered.

## Testing strategy

### Tier 1: Unit tests (CI, fast)

- Stage logic with mocked `NetworkContext`
- Repository CRUD against in-memory SQLite
- Mode/scope state machine transitions
- Display state selection logic
- Audit `scope_basis` computation
- ESS union-find (BSSID overlap) algorithm

Target: 90% line coverage on non-stage code.

### Tier 2: Integration tests (CI, slower)

- NLM main loop with real SQLite (temp dir)
- Multi-stage flow on synthetic networks
- Kill switch activation mid-stage
- Persistence authorization gating (network + host levels)
- Mode persistence across simulated reboot (re-init NLM from DB)
- WebUI smoke tests with Flask test client

Target: full happy-path coverage of all stages in slice.

### Tier 3: Hardware-in-loop tests (manual, on the bench)

- Real WiFi beacon capture (`passive_scan`)
- Real e-Paper rendering (all 14 display states)
- Real Tailscale bring-up (#1)
- Reference comparison: run v1 and v2 side-by-side, compare discovered hosts

Marked `@pytest.mark.hardware`, skipped in CI.

### Slice acceptance criteria

1. Fresh install boots, displays `STARTING_UP` → `VIEW_ONLY_PASSIVE` state
2. Device observes a real network within 60s, row appears in `networks` table
3. WebUI reachable via SSH port-forward, dashboard shows discovered network
4. Operator can toggle `view_only` → `active` and back; mode persists across reboot
5. Operator can blocklist a network via WebUI, NLM skips it
6. Operator can preemptively add a network via WebUI form
7. Kill switch via WebUI halts in-flight work within 1s for RF, within 10s for non-RF
8. Audit log records every action with correct `scope_basis`
9. Battery-pull test: pull power mid-stage, reboot, verify state resumed correctly
10. All Tier 1 + Tier 2 tests pass

## Vertical slice scope

### In scope for #0

**Architecture (all layers exercised)**:

- `bjorn_v2/db/` — SQLite, schema (all 22 tables), migrations framework, repositories for tables touched by the slice
- `bjorn_v2/nlm/` — NLM (main loop, scheduler, state machine, mode/scope/kill-switch)
- `bjorn_v2/stages/` — Stage ABC, registry, one concrete implementation: `PassiveScanStage`
- `bjorn_v2/interfaces/` — `InterfaceManager`, `WiFiInterface` (passive scan only), BT/BLE stubs
- `bjorn_v2/audit/` — `AuditLogger` writing to `action_log`
- `bjorn_v2/ui/web/` — Flask app with dashboard, networks inventory, network detail, blocklist/preferred-SSID form, settings (mode/kill switch)
- `bjorn_v2/ui/epd/` — Display state manager + all 14 display states
- `bjorn_v2/config.py` — typed config loader
- `scripts/bjorn.service` — systemd unit
- `scripts/migrate_v1_to_v2.py` — best-effort migration
- Tier 1 + Tier 2 tests covering the slice

### Out of scope (deferred)

| Capability | Sub-project |
|---|---|
| `wifi_probe`, `wifi_crack` stages | #3 |
| `lan_enum`, `service_enum` stages | #3 (tightly coupled with post-WiFi-crack recon) |
| `credential_attack`, `vuln_scan` stages | #4 / #5 |
| `exploitation`, `privesc`, `lateral_movement`, `persistence` stages | #5 |
| Bluetooth tether (`BluetoothInterface` impl) | #1 |
| Tailscale tunnel + bind web to `tailscale0` | #1 |
| Multi-SSID priority connection logic | #1 |
| BLE interface | future |
| WebUI auth | future |
| Operator notes WebUI editing | future |

## Migration plan (v1 → v2)

**Migrates**:

- `config/shared_config.json` → selected keys → `system_state` + `bjorn_v2/config.py` defaults
- `data/output/*.csv` (networks/hosts/ports discovered by v1) → `networks`, `hosts`, `services` tables
- `data/mac_blacklist.json` → `networks.scope_state='blocklisted'` (matched by BSSID)
- Captured handshakes in `data/` → `wifi_captures` rows with `crack_status='untried'`

**Doesn't migrate**:

- v1's `live_status.csv` (transient)
- v1's per-action logs (different schema)
- v1's stolen files (paths may have changed; operator can re-link via WebUI)
- v1's `comments/` directory (cosmetic feature)

**Behavior**:

- Idempotent — natural keys used for upsert
- `--dry-run` mode shows what would migrate without writing
- Every migration decision logged to `data/logs/migration.log`
- SQLite backup created before writing (`bjorn-pre-migration-YYYYMMDD.db`)

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Subprocess-per-stage adds latency to fast idle/active cycling | Stage pool warm-keeps 2 subprocesses ready |
| SQLite contention between Flask reads and NLM writes | WAL mode + `busy_timeout=5000ms` |
| EPD driver behaves differently on Zero 2W (64-bit) vs Zero W (32-bit) | Keep v1's `waveshare_epd/` library |
| Mode persistence resumes offensive ops after power cycle | Documented; operator responsibility; kill switch always available via WebUI |
| Migration corrupts DB | Always backs up before writing; dry-run mode available |

## Open questions (resolve during implementation)

- Exact config file format (TOML vs YAML vs JSON) — proposing TOML
- Whether to use `pydantic` for config validation or stdlib `dataclasses` + manual validation
- Logging format: structured JSON vs human-readable text

These will be settled during implementation and captured as ADRs.

## Acceptance

This sub-project is complete when:

1. All 10 slice acceptance criteria pass
2. Tier 1 + Tier 2 test suites green in CI
3. Code review approved by operator
4. Documentation updated (INSTALL.md for v2, README updated to mention v2)
5. ADRs written for decisions made during implementation
6. Migration script tested on a real v1 data directory
