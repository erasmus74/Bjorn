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
