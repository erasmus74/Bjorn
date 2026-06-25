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

# Repo-root sys.path bootstrap: this script lives in <repo>/scripts/, and
# mjolnir is imported from <repo>/. When run as a standalone CLI (python
# scripts/migrate_v1_to_v2.py) Python only puts this file's directory on
# sys.path, so we add the repo root ourselves. No-op when mjolnir is
# pip-installed or invoked via -m from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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
    # "v1-imported" network to attach all migrated hosts to. Reuse an existing
    # one if present so re-running the migration is idempotent (hosts have a
    # UNIQUE(network_id, mac) key, so a fresh network each run would duplicate).
    existing = bundle.networks.find_by_ssid("v1-imported")
    if existing:
        network_id = existing[0].id
    else:
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

                # Idempotent: credentials has no natural-key UNIQUE constraint,
                # so check-before-insert on (cred_type, username, secret) to
                # avoid duplicating rows on re-run.
                existing = bundle.networks.conn.execute(
                    "SELECT id FROM credentials "
                    "WHERE cred_type = ? AND secret = ? "
                    "AND (username IS ? OR username = ?)",
                    (cred_type, password, username or None, username or None),
                ).fetchone()
                if existing:
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
        # Create a placeholder network for the blacklisted MAC and blocklist it.
        # Reuse an existing one if already migrated so re-runs are idempotent.
        ssid = f"v1-blacklist-{normalized}"
        existing = bundle.networks.find_by_ssid(ssid)
        if existing:
            stats["blacklisted"] += 1
            continue
        net = bundle.networks.create(ssid=ssid)
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
