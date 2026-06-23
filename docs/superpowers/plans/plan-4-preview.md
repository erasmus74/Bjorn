# Plan 4 Preview — Migration + Acceptance

**Status:** SCOPE SKETCH — not yet a real plan. Will be expanded into a full TDD plan using the writing-plans skill **after Plan 3 is implemented**.

**Dependency:** Plan 3 (`v0.3.0-plan3`) complete.

## Goal

Ship sub-project #0. Build the v1 -> v2 data migration script, wire everything into a systemd unit, and pass all 10 slice acceptance criteria on real hardware.

## Architecture summary

- `scripts/migrate_v1_to_v2.py` — one-shot migration script
- `scripts/mjolnir.service` — systemd unit file
- `mjolnir/main.py` — final form, starts NLM + Flask + EPD together
- `INSTALL.md` updates — v2 installation instructions
- Acceptance test runbook

## Milestone

All 10 slice acceptance criteria pass on real Pi Zero 2W hardware:

1. Fresh install boots, displays `STARTING_UP` -> `VIEW_ONLY_PASSIVE` state
2. Device observes a real network within 60s, row appears in `networks` table
3. WebUI reachable via SSH port-forward, dashboard shows discovered network
4. Operator can toggle `view_only` -> `active` and back; mode persists across reboot
5. Operator can blocklist a network via WebUI, NLM skips it
6. Operator can preemptively add a network via WebUI form
7. Kill switch via WebUI halts in-flight work within 1s for RF, within 10s for non-RF
8. Audit log records every action with correct `scope_basis`
9. Battery-pull test: pull power mid-stage, reboot, verify state resumed correctly
10. All Tier 1 + Tier 2 tests pass

## v1 -> v2 migration

**Migrates:**
- `config/shared_config.json` -> selected keys -> `system_state` + `mjolnir/config.py` defaults
- `data/output/*.csv` (networks/hosts/ports discovered by v1) -> `networks`, `hosts`, `services` tables
- `data/mac_blacklist.json` -> `networks.scope_state='blocklisted'` (matched by BSSID)
- Captured handshakes in `data/` -> `wifi_captures` rows with `crack_status='untried'`

**Doesn't migrate:**
- v1's `live_status.csv` (transient)
- v1's per-action logs (different schema)
- v1's stolen files (paths may have changed; operator can re-link via WebUI)
- v1's `comments/` directory (cosmetic feature)

**Behavior:**
- Idempotent — natural keys used for upsert
- `--dry-run` mode shows what would migrate without writing
- Every migration decision logged to `data/logs/migration.log`
- SQLite backup created before writing (`bjorn-pre-migration-YYYYMMDD.db`)

## Phase breakdown (rough)

1. **Migration script** — parse v1 CSV/JSON, transform, upsert into v2 tables
2. **Migration tests** — fixture v1 data, verify v2 state after migration
3. **systemd unit** — service definition with proper dependencies (network-online, etc.)
4. **main.py final wiring** — start NLM + Flask + EPD together, signal handling for graceful shutdown
5. **INSTALL.md update** — v2 install/run instructions
6. **Acceptance runbook** — manual test procedure for each of the 10 criteria
7. **Hardware acceptance pass** — run all 10 on real Pi
8. **Documentation sweep** — README, INSTALL, TROUBLESHOOTING, ADRs finalized
9. **Tag `v0.4.0-subproject-0`** and merge `feat/v2-platform` -> `main`

## Things to nail down during implementation

- systemd service type (simple? forking? notify?)
- Resource limits via systemd (MemoryMax, CPUQuota) — defense in depth alongside in-process limits
- How `main.py` orchestrates three threads (NLM, Flask, EPD) cleanly
- Graceful shutdown sequencing: SIGTERM -> checkpointable stages save -> close DB -> exit
- Migration script error modes: what if v1 CSV is malformed? Skip row + log? Abort?
- Where to put ADRs (`docs/decisions/`) and how to number them

## Acceptance

Plan 4 (and sub-project #0) is complete when:
- All 10 slice acceptance criteria pass on real hardware
- All Plan 1 + 2 + 3 tests still pass
- Migration script works end-to-end on a real v1 data directory
- systemd service starts/stops cleanly
- `feat/v2-platform` merged to `main`
- Tag `v0.4.0-subproject-0` exists
- Ready to begin sub-project #1 (connectivity layer)
