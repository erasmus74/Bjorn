"""mjolnir entrypoint.

Three modes:
  --init-db : initialize the database and exit (Plan 1)
  --once    : run a single NLM iteration and exit (testing / one-shot)
  (default) : run the NLM main loop until shutdown (Plan 2b Phase 3)

Shutdown is triggered by SIGTERM, SIGINT, or the test-only
_request_shutdown_for_tests() hook. The loop polls the shutdown flag every
100ms so shutdown is responsive even when scan_interval_seconds is large.
"""
import argparse
import multiprocessing as mp
import signal
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

from mjolnir.config import BjornConfig, load_config
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.stages import registry as default_registry
from mjolnir.ui.epd.collector import collect_conditions
from mjolnir.ui.epd.driver import FakeEPDDriver, RealEPDDriver
from mjolnir.ui.epd.manager import DisplayManager


_shutdown_requested = threading.Event()


def _request_shutdown_for_tests() -> None:
    """Test hook: signals the daemon loop to exit cleanly.

    Tests cannot reliably send real signals to the pytest process, so they
    call this directly. Production code uses SIGTERM/SIGINT instead.
    """
    _shutdown_requested.set()


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
    parser.add_argument(
        "--once", action="store_true",
        help="run a single NLM iteration and exit (for testing)",
    )
    return parser.parse_args(argv)


def initialize(config: BjornConfig) -> None:
    """Open the DB, apply schema, run migrations, seed defaults. Idempotent."""
    factory = ConnectionFactory(db_path=config.db.path)
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()


def _install_signal_handlers() -> None:
    """SIGTERM/SIGINT trigger clean shutdown by setting the event.

    signal.signal() only works in the main thread; if main() is invoked
    from a worker thread (as in tests), we skip installation — the test
    uses _request_shutdown_for_tests() directly.
    """
    if threading.current_thread() is not threading.main_thread():
        return
    def handler(signum, frame):
        _shutdown_requested.set()
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def run_daemon(config: BjornConfig) -> int:
    """Run the NLM main loop + Flask WebUI until shutdown is requested.

    Clears the shutdown flag at start so a previous shutdown signal does
    not leak into a fresh invocation. Polls the flag every 100ms during
    the scan-interval sleep so shutdown is responsive.

    The Flask WebUI runs in a daemon thread so the operator can reach
    it on config.web.bind_interface:port while the NLM loop runs in
    the foreground.
    """
    _install_signal_handlers()
    _shutdown_requested.clear()

    kill_switch_event = mp.Event()
    mgr = NetworkLifecycleManager(
        db_path=config.db.path,
        config=config,
        registry=default_registry,
        kill_switch_event=kill_switch_event,
    )

    # Start Flask WebUI in a background thread
    from mjolnir.ui.web.app import create_app
    web_app = create_app(config)
    web_thread = threading.Thread(
        target=lambda: web_app.run(
            host=config.web.bind_interface,
            port=config.web.port,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    )
    web_thread.start()

    # Construct display manager. Try real hardware first; fall back to fake
    # if the EPD library isn't importable (e.g., in tests/CI or dev machines
    # without the HAT attached).
    try:
        display_driver = RealEPDDriver()
        display_driver.init()
    except Exception:
        display_driver = FakeEPDDriver(width=122, height=250)
        display_driver.init()
    display = DisplayManager(driver=display_driver)

    while not _shutdown_requested.is_set():
        try:
            mgr.run_once()
        except Exception as e:
            print(f"warning: NLM iteration failed: {e}", file=sys.stderr)

        # Update display with current conditions
        try:
            db_conn = ConnectionFactory(db_path=config.db.path).connect()
            bundle = bundle_for(db_conn)
            conditions = collect_conditions(
                bundle,
                kill_switch_event_set=kill_switch_event.is_set(),
            )
            conditions = replace(conditions, starting_up=False)
            display.update(conditions)
            db_conn.close()
        except Exception as e:
            print(f"warning: display update failed: {e}", file=sys.stderr)

        # Sleep in 100ms ticks so we notice shutdown promptly.
        for _ in range(config.nlm.scan_interval_seconds * 10):
            if _shutdown_requested.is_set():
                break
            time.sleep(0.1)

    display.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"error: config file not found: {args.config}", file=sys.stderr)
        return 2

    initialize(config)

    from mjolnir.logging_config import setup_logging
    log = setup_logging(format="text")  # config-driven format is a follow-up

    if args.init_db:
        print(f"initialized db at {config.db.path}")
        return 0

    if args.once:
        kill_switch_event = mp.Event()
        mgr = NetworkLifecycleManager(
            db_path=config.db.path,
            config=config,
            registry=default_registry,
            kill_switch_event=kill_switch_event,
        )
        mgr.run_once()
        return 0

    return run_daemon(config)


if __name__ == "__main__":
    sys.exit(main())
