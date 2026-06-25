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
- **WiFi scan not finding networks:** the daemon needs root or `CAP_NET_RAW` for `iw dev wlan0 scan`. The systemd unit runs as `mjolnir` user; grant capabilities or run the scan stage with elevated privileges.
- **DB locked errors:** ensure only one mjolnir process is running. WAL mode handles concurrent reads but writes are single-writer.
- **Test suite slow (~150s):** this is the known multiprocessing fork() slowdown (ADR 0001). Use `pytest tests/unit/ui/ tests/unit/db/` for fast iteration during development.

## What's included in sub-project #0

- Full SQLite schema (23 tables covering all planned sub-projects)
- NLM framework with subprocess-per-stage execution + cooperative cancellation
- PassiveScanStage (WiFi beacon observation)
- Flask WebUI (dashboard, networks, blocklist, settings, audit, persistence auth)
- EPD display (14 priority-ordered states)
- v1→v2 migration script
- systemd unit + structured logging

Subsequent sub-projects (#1 connectivity, #3 WiFi offensive, #4 credential attacks, #5 exploitation) build on this foundation.
