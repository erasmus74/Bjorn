# Sub-project #0 — Acceptance Runbook

The 10 slice acceptance criteria from the spec, as a manual test
procedure to run on real Pi Zero 2W hardware before tagging
`v1.0.0-subproject-0` as hardware-verified.

Run each test in order. If any fails, stop and fix before continuing.

## Setup

1. Fresh Raspberry Pi Zero 2W with 2.13" e-Paper HAT, on Raspberry Pi OS Bookworm (64-bit).
2. mjolnir installed per `docs/INSTALL-v2.md`.
3. At least one WiFi network in range (your own, for legal testing).
4. SSH access to the Pi.
5. Laptop/phone on same network for WebUI access via port-forward.

## Criteria

### 1. Fresh install boots, displays STARTING_UP → VIEW_ONLY_PASSIVE

```bash
sudo systemctl restart mjolnir
```
- Watch the e-Paper: should show "Starting mjolnir..." then transition to the VIEW-ONLY mode screen.
- **Pass:** both screens appear within 30s of start.
- **Fail:** check `journalctl -u mjolnir` for errors.

### 2. Device observes a real network within 60s

```bash
# After boot, wait 60s, then:
sudo -u mjolnir sqlite3 /var/lib/mjolnir/mjolnir.db "SELECT ssid, security_type FROM networks"
```
- **Pass:** at least one row present.
- **Fail:** check WiFi adapter is up, `iw dev wlan0 scan` works as the mjolnir user (may need `CAP_NET_RAW`).

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
- **Fail:** check `system_state` table retained `global_mode=active` (it should — mode persists per spec).

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
- **Note:** cooperative cancellation (Plan 2b) means checkpointable stages save progress before exit; the 2s grace period is the backstop.

### 8. Audit log records every action

1. Perform several actions (toggle mode, blocklist, etc.).
2. WebUI → Audit Log.
- **Pass:** every action appears with correct scope_basis.
- Specifically: mode toggle should show `operator-confirmed-active-mode`; persistence grant should show `operator-authorized-network-persistence-N<id>`.

### 9. Battery-pull test (power-loss recovery)

1. Ensure ACTIVE mode, mid-scan.
2. Pull power (or `sudo systemctl kill -s SIGKILL mjolnir`).
3. Re-power.
4. Check `journalctl` shows clean recovery, no DB corruption.
- **Pass:** DB opens cleanly, mode/state preserved, no "database is locked" or "database disk image is malformed" errors.
- **Note:** WAL mode + synchronous=NORMAL means the last few seconds of writes may be lost, but the DB itself is never corrupt.

### 10. All Tier 1 + Tier 2 tests pass

```bash
sudo -u mjolnir /opt/mjolnir/.venv/bin/pytest /opt/mjolnir/tests/ -m 'not hardware'
```
- **Pass:** all tests green (~270 tests).
- **Note:** the suite takes ~150s due to the known multiprocessing fork() slowdown (ADR 0001); this is expected.

## Hardware-specific tests (optional, deeper validation)

```bash
sudo -u mjolnir /opt/mjolnir/.venv/bin/pytest /opt/mjolnir/tests/ -m hardware
```
- Real WiFi scan finds networks (`test_real_iw_scan_returns_output`, `test_nlm_discovers_real_networks_within_60s`).
- Real EPD renders all 14 states visibly (`test_real_epd_renders_all_states`).
- DisplayManager.shutdown() clears the screen (`test_real_epd_display_manager_shutdown_clears`).

## Sign-off

When all 10 criteria pass:
- Tag `v1.0.0-subproject-0` (already created in software; this confirms hardware verification).
- Update `docs/SESSION-STATE.md` to mark sub-project #0 hardware-verified.
- Decide whether to merge `feat/v2-platform` → `main` or keep as a long-lived branch.
- Begin sub-project #1 (connectivity: BT tether, Tailscale, multi-SSID priority).
