"""Hardware-marked tests that exercise real WiFi hardware.

Run with: pytest -m hardware

These require:
- Real Pi Zero 2W with WiFi adapter on wlan0
- At least one AP in range (any SSID)
- Root privileges (for `iw dev wlan0 scan`)
"""
import time

import pytest

from mjolnir.config import BjornConfig, DbConfig, NlmConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.interfaces.wifi import WiFiInterface
from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.stages.passive_scan import PassiveScanStage
from mjolnir.stages.registry import StageRegistry

import multiprocessing as mp


pytestmark = pytest.mark.hardware


def test_real_iw_scan_returns_output():
    """Sanity check: iw dev wlan0 scan produces parseable output."""
    iface = WiFiInterface(ifname="wlan0")
    result = iface.scan()
    assert isinstance(result.observations, list)


def test_nlm_discovers_real_networks_within_60s(tmp_path):
    """Acceptance test: device boots, observes a real network within 60s.

    This is the milestone test for Plan 2b. Failure means the device can't
    do passive WiFi observation, which is the foundation of everything else.

    Note: requires a seeded 'BootstrapNet' row because the NLM scheduler
    attaches work to existing networks. See test_passive_scan_lifecycle.py
    for the same pattern. Long-term fix is to allow discovery-class stages
    to run without a network attachment.
    """
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()

    from mjolnir.db.repositories import bundle_for
    bundle = bundle_for(conn)
    bundle.networks.create(ssid="BootstrapNet", security_type=None)
    networks_before = len(conn.execute("SELECT * FROM networks").fetchall())
    conn.close()

    reg = StageRegistry()
    reg.register(PassiveScanStage)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
        nlm=NlmConfig(stage_memory_limit_mb=256),
    )
    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=mp.Event(),
    )

    deadline = time.monotonic() + 60
    discovered = False
    while time.monotonic() < deadline and not discovered:
        mgr.run_once()
        conn = factory.connect()
        networks_after = len(conn.execute("SELECT * FROM networks").fetchall())
        conn.close()
        if networks_after > networks_before:
            discovered = True
            break

    assert discovered, "No networks discovered within 60 seconds — check WiFi adapter and permissions"
