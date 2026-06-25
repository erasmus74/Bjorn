# tests/integration/test_passive_scan_lifecycle.py
"""End-to-end: NLM runs PassiveScanStage in a real subprocess, writes rows."""
import multiprocessing as mp
from pathlib import Path

import pytest

from mjolnir.config import BjornConfig, DbConfig, NlmConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.nlm.in_process_executor import InProcessExecutor
from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.interfaces.types import BssidObservation, ScanResult
from mjolnir.interfaces.wifi import WiFiInterface
from mjolnir.stages.registry import StageRegistry
from mjolnir.stages.passive_scan import PassiveScanStage


@pytest.fixture
def configured_db(tmp_path: Path):
    """Initialise a fresh DB with one bootstrap network.

    The NLM scheduler pairs stages with eligible networks
    (scope_state='enabled', exhausted=0). Without a seeded row,
    find_eligible_work() returns an empty list and no stage ever runs.
    PassiveScanStage itself creates additional networks as it discovers
    them; this bootstrap row exists only to give the scheduler something
    to attach the first run to.
    """
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    bundle.networks.create(ssid="BootstrapNet")
    conn.close()
    return tmp_path / "x.db"


def test_nlm_passive_scan_discovers_new_network(configured_db, monkeypatch):
    """Monkey-patch wifi.scan() to return canned data; NLM should pick it up."""
    canned = ScanResult(
        observations=[
            BssidObservation(
                bssid="aa:bb:cc:dd:ee:01", ssid="IntegrationSSID",
                signal_dbm=-42, channel=6, security_type="WPA2",
                first_seen="2026-06-24T10:00:00Z", last_seen="2026-06-24T10:00:00Z",
            ),
        ],
        scanned_at="2026-06-24T10:00:00Z",
    )

    def fake_scan(self):
        return canned

    monkeypatch.setattr(WiFiInterface, "scan", fake_scan)

    reg = StageRegistry()
    reg.register(PassiveScanStage)

    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=configured_db.parent, log_dir=configured_db.parent / "logs"),
        db=DbConfig(data_dir=configured_db.parent, filename=configured_db.name),
        nlm=NlmConfig(stage_memory_limit_mb=256),
    )

    __ks = mp.Event()
    mgr = NetworkLifecycleManager(
        db_path=configured_db,
        config=cfg,
        registry=reg,
        kill_switch_event=__ks,
        executor=InProcessExecutor(db_path=configured_db, registry=reg, kill_switch_event=__ks),
    )

    executed = mgr.run_once()
    assert executed == 1

    conn = ConnectionFactory(db_path=configured_db).connect()
    bundle = bundle_for(conn)
    networks = bundle.networks.find_by_ssid("IntegrationSSID")
    assert len(networks) == 1
    assert networks[0].security_type == "WPA2"

    bssids = bundle.bssids.list_for_network(networks[0].id)
    assert len(bssids) == 1
    assert bssids[0].bssid == "aa:bb:cc:dd:ee:01"
    assert bssids[0].last_signal_dbm == -42

    sightings = bundle.bssid_sightings.list_for_bssid(bssids[0].id)
    assert len(sightings) == 1

    conn.close()


def test_nlm_passive_scan_resumable_across_runs(configured_db, monkeypatch):
    """Running the NLM twice updates the same network instead of creating a new one."""
    scan_call_count = {"n": 0}

    def make_scan_result(scanned_at: str) -> ScanResult:
        return ScanResult(
            observations=[
                BssidObservation(
                    bssid="aa:bb:cc:dd:ee:01", ssid="ResumableNet",
                    signal_dbm=-50 + scan_call_count["n"],
                    channel=6, security_type="WPA2",
                    first_seen=scanned_at, last_seen=scanned_at,
                ),
            ],
            scanned_at=scanned_at,
        )

    def fake_scan(self):
        scan_call_count["n"] += 1
        return make_scan_result(f"2026-06-24T1{scan_call_count['n']}:00:00Z")

    monkeypatch.setattr(WiFiInterface, "scan", fake_scan)

    reg = StageRegistry()
    reg.register(PassiveScanStage)
    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=configured_db.parent, log_dir=configured_db.parent / "logs"),
        db=DbConfig(data_dir=configured_db.parent, filename=configured_db.name),
        nlm=NlmConfig(stage_memory_limit_mb=256),
    )
    __ks = mp.Event()
    mgr = NetworkLifecycleManager(
        db_path=configured_db,
        config=cfg,
        registry=reg,
        kill_switch_event=__ks,
        executor=InProcessExecutor(db_path=configured_db, registry=reg, kill_switch_event=__ks),
    )

    mgr.run_once()
    mgr.run_once()

    conn = ConnectionFactory(db_path=configured_db).connect()
    bundle = bundle_for(conn)
    networks = bundle.networks.find_by_ssid("ResumableNet")
    assert len(networks) == 1, "should still be one network after two scans"

    bssids = bundle.bssids.list_for_network(networks[0].id)
    assert len(bssids) == 1
    sightings = bundle.bssid_sightings.list_for_bssid(bssids[0].id)
    assert len(sightings) == 2
    conn.close()
