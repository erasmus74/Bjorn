# Hardware Acceptance — Handoff for Fresh Session

**Purpose:** Resume the mjolnir v2 hardware acceptance on real Pi Zero 2W. This doc has everything a fresh session needs to continue.

**Prerequisite:** This session must have the pty-mcp tools loaded (persistent SSH). The operator enabled passwordless sudo on the Pi.

---

## What this is

Sub-project #0 of the mjolnir v2 effort is **software-complete** (tag `v1.0.0-subproject-0` on branch `feat/v2-platform` in repo `/home/master/workspace/bjorn`). All code, tests, migration script, systemd unit, and docs are done. The final gate is **hardware acceptance** — running the 10 acceptance criteria from `docs/ACCEPTANCE-RUNBOOK.md` on real Pi Zero 2W hardware.

The pty-mcp was added for persistent SSH access to the Pi. This doc lets a fresh session pick up where the prior session left off.

## Pi details

- **SSH:** `ssh master@10.0.191.248` (passwordless sudo enabled; SSH key already set up)
- **Hostname:** `zero2root`
- **OS:** DietPi / Debian 13 (trixie), aarch64
- **Python:** 3.13.5 (installed in prior session)
- **Git + pip:** installed in prior session
- **WiFi:** `wlan0` UP, MAC `e4:5f:01:94:c2:a9`
- **Disk:** 7.2G total, 4.3G free
- **RAM:** 462MB total, ~388MB available
- **SPI:** **disabled** — needs enabling for e-Paper HAT (add `dtparam=spi=on` to `/boot/firmware/config.txt` + reboot)

## Where we left off

The prior session:
1. ✅ SSHed to the Pi, ran pre-flight checks
2. ✅ Installed `python3`, `python3-venv`, `python3-pip`, `git` via `sudo apt-get install`
3. ✅ Verified Python 3.13.5, WiFi adapter up, disk/memory sufficient
4. ⏳ **Next:** Push `feat/v2-platform` branch to GitHub → clone on Pi → set up venv → install → initialize DB → run acceptance tests

The branch is local-only (not yet pushed to `origin/erasmus74/Bjorn`). Need to `git push origin feat/v2-platform` first.

## Instructions for the fresh session

### Step 1: Push the branch to GitHub

From the repo at `/home/master/workspace/bjorn`:
```bash
git push origin feat/v2-platform
```

### Step 2: Connect to the Pi via pty-mcp

Use the pty-mcp tools to open a persistent SSH session to `master@10.0.191.248`. The SSH key is already set up; no password needed.

### Step 3: Clone + install mjolnir on the Pi

```bash
# Clone the fork
cd /opt
sudo git clone https://github.com/erasmus74/Bjorn.git mjolnir
cd mjolnir
sudo git checkout feat/v2-platform

# Create venv
sudo python3 -m venv .venv
sudo .venv/bin/pip install -e .

# Install Pillow (needed for EPD rendering, may not be in the install deps yet)
sudo .venv/bin/pip install Pillow

# Create mjolnir user + dirs
sudo useradd -r -s /bin/false mjolnir || true
sudo mkdir -p /var/lib/mjolnir /var/log/mjolnir
sudo chown -R mjolnir:mjolnir /var/lib/mjolnir /var/log/mjolnir

# Install config
sudo mkdir -p /etc/mjolnir
sudo cp config/mjolnir.toml /etc/mjolnir/config.toml
# Edit data_dir to point at /var/lib/mjolnir (should already be default)

# Initialize DB
sudo .venv/bin/python -m mjolnir.main --config /etc/mjolnir/config.toml --init-db
```

### Step 4: Run software acceptance tests (no SPI needed)

These don't need the e-Paper HAT — test WiFi + WebUI + DB first:

1. **Start the daemon in --once mode** to verify NLM runs PassiveScanStage:
```bash
sudo .venv/bin/python -m mjolnir.main --config /etc/mjolnir/config.toml --once
```

2. **Check DB for discovered networks:**
```bash
sudo sqlite3 /var/lib/mjolnir/mjolnir.db "SELECT ssid, security_type, last_seen FROM networks"
```

3. **Run the Python test suite on-device** (skip hardware + subprocess markers):
```bash
sudo .venv/bin/python -m pytest tests/ -m 'not hardware and not subprocess' -q
```

4. **Test WebUI access via SSH port-forward** (from your dev machine):
```bash
ssh -L 8000:localhost:8000 master@10.0.191.248
# Then open http://localhost:8000 in a browser
```

5. **Start the daemon for real and test mode toggle / kill switch / blocklist** via the WebUI.

### Step 5: Enable SPI + reboot for EPD tests

```bash
# Enable SPI overlay
echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

After reboot, reconnect SSH and test the e-Paper:
```bash
cd /opt/mjolnir
sudo .venv/bin/python -m pytest tests/hardware/ -m hardware -v
```

### Step 6: Run the full acceptance runbook

Follow `docs/ACCEPTANCE-RUNBOOK.md` — all 10 criteria. Record pass/fail for each.

## Key docs to read (in this order)

1. **This file** — where we are and what to do
2. `docs/SESSION-STATE.md` — overall project state + recovery info
3. `docs/ACCEPTANCE-RUNBOOK.md` — the 10 criteria (the actual test procedure)
4. `docs/INSTALL-v2.md` — installation reference (may differ slightly from DietPi)

## Known issues to watch for

- **`iw dev wlan0 scan` needs root or CAP_NET_RAW** — the systemd unit runs as `mjolnir` user. For testing, run stages as root (`sudo`). For production, grant `CAP_NET_RAW` to the mjolnir user or run the daemon as root.
- **DietPi vs Raspberry Pi OS differences** — boot config is at `/boot/firmware/config.txt` (not `/boot/config.txt`). No `raspi-config`; use direct file edits or `dietpi-config`.
- **RLIMIT_AS memory limit** — production default is 128MB; test fixtures use 256MB. The Pi has 462MB total RAM, so 128MB per stage × 4 pool = 512MB theoretical max — tight. Lower `stage_pool_size` to 2 if OOM occurs.
- **Pillow may need system deps** — if `pip install Pillow` fails, install `libjpeg-dev zlib1g-dev` first.

## Acceptance sign-off

When all 10 criteria pass:
- The `v1.0.0-subproject-0` tag is confirmed hardware-verified.
- Update `docs/SESSION-STATE.md` to mark sub-project #0 hardware-complete.
- Begin sub-project #1 (connectivity: BT tether, Tailscale, multi-SSID).
- The CSRF fix deferred in ADR 0002 MUST land in sub-project #1.
