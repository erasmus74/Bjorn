# Plan 2 Preview — NLM + First Stage

**Status:** SCOPE SKETCH — not yet a real plan. Will be expanded into a full TDD plan using the writing-plans skill **after Plan 1 is implemented** and any reality-corrections are folded back into the spec.

**Dependency:** Plan 1 (`v0.1.0-plan1`) complete.

## Goal

Build the Network Lifecycle Manager (NLM) on top of Plan 1's foundation. Ship the first concrete Stage implementation (`PassiveScanStage`) so the device boots, observes real WiFi networks, and writes rows to the `networks` table.

## Architecture summary

- `mjolnir/interfaces/` — `InterfaceManager` (the only thing allowed to touch hardware), `WiFiInterface` (passive scan only — `iw dev wlan0 scan` or `iwlist`), `BluetoothInterface` and `BLEInterface` stubs that raise `NotImplementedError`
- `mjolnir/nlm/` — the brain:
  - `manager.py` — main loop (`find_eligible_work` -> submit to subprocess pool -> mark exhausted -> refresh display)
  - `state.py` — per-network lifecycle state machine (the 11 stages from spec)
  - `identity.py` — ESS union-find (BSSID-overlap rule for "is this the same network?")
  - `scope.py` — mode toggle enforcement, blocklist check, persistence authorization check
  - `executor.py` — subprocess-per-stage runner with `RLIMIT_AS`, checkpoint load/save, audit-log wrapping
- `mjolnir/stages/passive_scan.py` — first Stage implementation; registers via `@registry.register`
- `mjolnir/main.py` — extended to start the NLM main loop

## Milestone

End-to-end passive scan works:
1. Fresh install boots -> DB initialized -> mode restored from `system_state` (or default `view_only`)
2. NLM main loop starts, picks `passive_scan` stage
3. `WiFiInterface` runs `iw dev wlan0 scan` (or equivalent) periodically
4. For each observed SSID+BSSID, ESS identity resolver groups them into `networks` rows
5. After 60s of operation, at least one row exists in `networks` for a real WiFi network in range

## Phase breakdown (rough)

1. **InterfaceManager + WiFiInterface (passive)** — wrap `iw`/`iwlist`, return structured scan results
2. **Stage executor** — subprocess-per-stage with resource limits, checkpoint handling
3. **ESS identity resolver** — union-find over BSSID overlaps per SSID
4. **Stage registry integration with NLM** — NLM discovers stages via `StageRegistry.stages_eligible_for_mode()`
5. **PassiveScanStage** — first concrete Stage; observes beacons, writes `networks`/`bssids`/`bssid_sightings`
6. **NLM main loop** — scheduler with kill-switch check, mode check, resource check
7. **Scope enforcement** — `network.scope_state` and `global_mode` gating in `can_run()`
8. **Integration test** — run on real hardware, verify rows appear in DB
9. **main.py wiring** — `python -m mjolnir.main` runs the full daemon loop
10. **Tag `v0.2.0-plan2`**

## Things to nail down during implementation

- Exact subprocess IPC protocol (JSON lines on stdin/stdout is the leading candidate — structured, debuggable, no arbitrary-code-execution risk like deserialization formats that execute code)
- `iw` output parsing — handling different versions, error states, permissions
- Checkpoint file format (JSON; size cap?)
- Kill switch latency on the radio — does `iw` honor SIGINT cleanly mid-scan?
- What happens if two networks share SSID *and* BSSID set partially — the union-find rule needs edge-case tests
- Hardware test markers (`@pytest.mark.hardware`) for tests that need a real WiFi adapter

## Acceptance

Plan 2 is complete when:
- All Plan 1 tests still pass
- ~60 new tests for interfaces, NLM, executor, identity resolver
- Real WiFi scan produces a row in `networks` within 60s on hardware
- Kill switch activation halts `passive_scan` mid-scan cleanly
- Mode toggle: in `view_only`, only stages with `operates_in_view_only=True` run
- Subprocess-per-stage enforced: kill a stage subprocess, NLM continues
- Tag `v0.2.0-plan2` exists
