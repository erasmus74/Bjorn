"""Verify main.py starts the NLM and exits cleanly on shutdown signal."""
import threading
import time
from pathlib import Path

from mjolnir.config import BjornConfig, DbConfig, PathsConfig


def test_main_runs_daemon_loop_until_shutdown(tmp_path: Path):
    """main() should run the NLM loop and exit when shutdown is requested.

    The test cannot send a real SIGTERM to itself (pytest would catch it),
    so it uses the test-only _request_shutdown_for_tests() hook. To make the
    test FAIL meaningfully if main() returns immediately (instead of looping),
    we assert the thread is still alive at the 2-second mark — before the
    shutdown request is sent.
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(f"""
[paths]
data_dir = "{tmp_path}"
log_dir = "{tmp_path}/logs"

[db]
filename = "test.db"

[web]
port = 0

[nlm]
scan_interval_seconds = 1
stage_pool_size = 1
stage_memory_limit_mb = 256
""")

    from mjolnir.main import main, initialize
    cfg_init = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="test.db"),
    )
    initialize(cfg_init)

    main_thread_result = {"exit_code": None}

    def run_main():
        main_thread_result["exit_code"] = main(argv=["--config", str(config_path)])

    t = threading.Thread(target=run_main, daemon=True)
    t.start()

    # At the 2-second mark: the daemon must still be running. If main()
    # returned immediately (no loop), the thread would be dead here and
    # the assertion below would fail.
    time.sleep(2)
    assert t.is_alive(), (
        "main() exited before shutdown was requested — daemon loop not running"
    )

    import mjolnir.main as main_mod
    main_mod._request_shutdown_for_tests()

    t.join(timeout=10)

    assert not t.is_alive(), "main() did not exit within 10s after shutdown"
    assert main_thread_result["exit_code"] == 0
