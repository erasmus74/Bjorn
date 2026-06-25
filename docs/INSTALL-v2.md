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
# Clone. IMPORTANT: the checkout directory must NOT be named `mjolnir`.
# The Python package is also named `mjolnir`, and if the repo directory
# shares that name, pytest's sys.path handling makes the repo directory
# masquerade as the package (mjolnir.__path__ points at the repo root, so
# every submodule import fails). Use /opt/bjorn (repo name) instead.
git clone https://github.com/erasmus74/Bjorn.git /opt/bjorn
cd /opt/bjorn
git checkout feat/v2-platform

# Create venv. Install NON-editable (`pip install .`, not `-e`): the
# setuptools editable import-hook finder conflicts with pytest's rootdir
# handling on the Pi. Runtime deps install the same either way.
python3 -m venv .venv
source .venv/bin/activate
pip install '.[dev]'

# Create mjolnir user + dirs (the data/log/config dirs keep the mjolnir
# name — only the source-checkout directory must differ)
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
- v1 `data/netkb.csv` → v2 hosts + services (attached to a `v1-imported` placeholder network)
- v1 `data/crackedpwd/*.csv` → v2 credentials (one cred_type per protocol)
- v1 `config/shared_config.json` `mac_scan_blacklist` → v2 blocklisted network entries

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
directly on your tailnet without port-forwarding. When that lands, the
CSRF protection deferred in ADR 0002 MUST also land (Origin-header check).

## Service management

```bash
sudo systemctl status mjolnir
sudo journalctl -u mjolnir -f          # follow logs
sudo systemctl restart mjolnir
```

## Troubleshooting

- **EPD not displaying:** check SPI is enabled (`raspi-config` > Interfacing > SPI), HAT is seated, `epd_type` in config matches your HAT version. The daemon falls back to a FakeEPDDriver (no display) if the real driver can't initialize — check `journalctl` for the fallback message.
- **WiFi scan not finding networks:** the daemon shells out to `iw dev wlan0 scan`, which needs `CAP_NET_RAW` + `CAP_NET_ADMIN`. The shipped systemd unit grants both to the `mjolnir` user via `AmbientCapabilities`, so this works out of the box. If you run the daemon manually (not via the unit), do so as root or grant the caps yourself.
- **DB locked errors:** ensure only one mjolnir process is running. WAL mode handles concurrent reads but writes are single-writer.
- **Daemon discovers nothing although `--once` works:** raise `stage_memory_limit_mb` (default 256). A stage runs in a forked child that inherits the daemon's full VM (~208 MB with Flask resident); a limit below that kills the child before it works. `--once` skips Flask so it survives a smaller limit.
- **`ImportError: cannot import name ... from 'mjolnir.config'` running tests:** the checkout directory is named `mjolnir`, colliding with the package name (see Fresh install note). Re-clone into `/opt/bjorn`.
- **Test suite slow (~150s) / fork deadlock:** run the two partitions separately — `pytest` (default, excludes the `subprocess` marker) then `pytest -m 'subprocess and not hardware'`. Interleaving subprocess (fork) tests with tests that leave the process multi-threaded can deadlock (ADR 0001). For fast iteration use `pytest tests/unit/ui/ tests/unit/db/`.

## What's included in sub-project #0

- Full SQLite schema (23 tables covering all planned sub-projects)
- NLM framework with subprocess-per-stage execution + cooperative cancellation
- PassiveScanStage (WiFi beacon observation)
- Flask WebUI (dashboard, networks, blocklist, settings, audit, persistence auth)
- EPD display (14 priority-ordered states)
- v1→v2 migration script
- systemd unit + structured logging

Subsequent sub-projects (#1 connectivity, #3 WiFi offensive, #4 credential attacks, #5 exploitation) build on this foundation.
