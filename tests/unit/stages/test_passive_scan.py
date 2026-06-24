"""PassiveScanStage tests. Uses a fake interface manager so no real WiFi needed."""
import pytest
from dataclasses import dataclass

from mjolnir.stages.passive_scan import PassiveScanStage
from mjolnir.stages.base import NetworkContext, Checkpoint
from mjolnir.interfaces.types import BssidObservation, ScanResult
from mjolnir.config import BjornConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.audit.logger import AuditLogger


@dataclass
class FakeWiFi:
    """Stub WiFiInterface returning a canned ScanResult."""
    scan_result: ScanResult

    def scan(self) -> ScanResult:
        return self.scan_result


@dataclass
class FakeInterfaceManager:
    wifi: FakeWiFi

    def halt_all_transmissions(self):
        pass


def _make_obs(bssid: str, ssid: str, signal: int, channel: int, sec: str = "WPA2") -> BssidObservation:
    return BssidObservation(
        bssid=bssid, ssid=ssid, signal_dbm=signal, channel=channel,
        security_type=sec,
        first_seen="2026-06-24T10:00:00Z", last_seen="2026-06-24T10:00:00Z",
    )


@pytest.fixture
def ctx(tmp_path):
    """Build a NetworkContext with stub interfaces and a real DB."""
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    network = bundle.networks.create(ssid="ExistingNet", security_type="WPA2")

    fake_wifi = FakeWiFi(scan_result=ScanResult(observations=[], scanned_at="2026-06-24T10:00:00Z"))
    fake_interfaces = FakeInterfaceManager(wifi=fake_wifi)

    audit = AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)

    ctx = NetworkContext(
        network=network,
        db=bundle,
        config=BjornConfig(),
        interfaces=fake_interfaces,
        audit=audit,
        workdir=tmp_path / "work",
        checkpoint=Checkpoint(),
    )
    return ctx, conn


def test_passive_scan_stage_class_attributes():
    """Verify the Stage ABC contract is satisfied."""
    from mjolnir.stages.base import CheckpointPolicy, ResourceProfile, InterfaceType
    stage = PassiveScanStage()
    assert stage.name == "passive_scan"
    assert stage.checkpoint_policy == CheckpointPolicy.RESTART_SAFE
    assert stage.operates_in_view_only is True
    assert stage.requires_extra_auth is False
    assert InterfaceType.WIFI in stage.resources.interfaces
    assert stage.resources.is_rf_transmitting is False


def test_passive_scan_can_run_returns_true(ctx):
    """passive_scan is always runnable."""
    ctx, _ = ctx
    stage = PassiveScanStage()
    assert stage.can_run(ctx) is True


def test_passive_scan_writes_new_network_and_bssids(ctx):
    """First sighting of an SSID creates a new networks row + bssids."""
    ctx, _ = ctx
    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[
            _make_obs("AA:BB:CC:DD:EE:01", "BrandNewNet", -42, 6),
            _make_obs("AA:BB:CC:DD:EE:02", "BrandNewNet", -55, 6),
        ],
        scanned_at="2026-06-24T10:00:00Z",
    )

    stage = PassiveScanStage()
    result = stage.run(ctx, ctx.checkpoint)

    assert result.status == "succeeded"

    networks = ctx.db.networks.find_by_ssid("BrandNewNet")
    assert len(networks) == 1
    new_net = networks[0]
    assert new_net.security_type == "WPA2"

    bssids = ctx.db.bssids.list_for_network(new_net.id)
    bssid_macs = {b.bssid for b in bssids}
    assert "aa:bb:cc:dd:ee:01" in bssid_macs
    assert "aa:bb:cc:dd:ee:02" in bssid_macs


def test_passive_scan_extends_existing_network_via_bssid_overlap(ctx):
    """Re-sighting a known BSSID updates signal, doesn't create new network."""
    ctx, _ = ctx

    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[
            _make_obs("AA:BB:CC:DD:EE:01", "MyNet", -50, 6),
            _make_obs("AA:BB:CC:DD:EE:02", "MyNet", -55, 6),
        ],
        scanned_at="2026-06-24T10:00:00Z",
    )
    PassiveScanStage().run(ctx, ctx.checkpoint)

    networks_before = ctx.db.networks.find_by_ssid("MyNet")
    assert len(networks_before) == 1
    original_net_id = networks_before[0].id

    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[
            _make_obs("AA:BB:CC:DD:EE:02", "MyNet", -42, 6),  # overlap
            _make_obs("AA:BB:CC:DD:EE:03", "MyNet", -60, 6),  # new
        ],
        scanned_at="2026-06-24T11:00:00Z",
    )
    PassiveScanStage().run(ctx, ctx.checkpoint)

    networks_after = ctx.db.networks.find_by_ssid("MyNet")
    assert len(networks_after) == 1
    assert networks_after[0].id == original_net_id

    bssids = ctx.db.bssids.list_for_network(original_net_id)
    assert len(bssids) == 3
    b02 = next(b for b in bssids if b.bssid == "aa:bb:cc:dd:ee:02")
    assert b02.last_signal_dbm == -42


def test_passive_scan_creates_disambiguated_network_on_no_overlap(ctx):
    """Same SSID but disjoint BSSIDs = new disambiguated network."""
    ctx, _ = ctx

    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[_make_obs("11:22:33:44:55:01", "linksys", -50, 6)],
        scanned_at="2026-06-24T10:00:00Z",
    )
    PassiveScanStage().run(ctx, ctx.checkpoint)

    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[_make_obs("AA:BB:CC:DD:EE:99", "linksys", -60, 11)],  # no overlap
        scanned_at="2026-06-24T11:00:00Z",
    )
    PassiveScanStage().run(ctx, ctx.checkpoint)

    networks = ctx.db.networks.find_by_ssid("linksys")
    assert len(networks) == 2
    disambiguators = {n.disambiguator for n in networks}
    assert disambiguators == {1, 2}


def test_passive_scan_records_sightings(ctx):
    """Each scan writes a bssid_sightings row for each BSSID seen."""
    ctx, _ = ctx

    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[_make_obs("AA:BB:CC:DD:EE:01", "X", -50, 6)],
        scanned_at="2026-06-24T10:00:00Z",
    )
    PassiveScanStage().run(ctx, ctx.checkpoint)

    net = ctx.db.networks.find_by_ssid("X")[0]
    bssid = ctx.db.bssids.list_for_network(net.id)[0]
    assert ctx.db.bssid_sightings.count_for_bssid(bssid.id) == 1

    PassiveScanStage().run(ctx, ctx.checkpoint)
    assert ctx.db.bssid_sightings.count_for_bssid(bssid.id) == 2


def test_passive_scan_updates_last_seen_on_network(ctx):
    ctx, _ = ctx

    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[_make_obs("AA:BB:CC:DD:EE:01", "X", -50, 6)],
        scanned_at="2026-06-24T10:00:00Z",
    )
    PassiveScanStage().run(ctx, ctx.checkpoint)
    net_after_first = ctx.db.networks.find_by_ssid("X")[0]
    assert net_after_first.last_seen == "2026-06-24T10:00:00Z"

    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[_make_obs("AA:BB:CC:DD:EE:01", "X", -50, 6)],
        scanned_at="2026-06-24T11:00:00Z",
    )
    PassiveScanStage().run(ctx, ctx.checkpoint)
    net_after_second = ctx.db.networks.find_by_ssid("X")[0]
    assert net_after_second.last_seen == "2026-06-24T11:00:00Z"


def test_passive_scan_returns_outputs_with_counts(ctx):
    ctx, _ = ctx

    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[
            _make_obs("AA:BB:CC:DD:EE:01", "X", -50, 6),
            _make_obs("AA:BB:CC:DD:EE:02", "X", -55, 6),
            _make_obs("AA:BB:CC:DD:EE:03", "Y", -60, 11),
        ],
        scanned_at="2026-06-24T10:00:00Z",
    )
    result = PassiveScanStage().run(ctx, ctx.checkpoint)

    assert result.outputs.get("observations_count") == "3"
    assert result.outputs.get("networks_seen_count") == "2"


def test_passive_scan_handles_empty_scan(ctx):
    """No observations = success with zero counts."""
    ctx, _ = ctx
    ctx.interfaces.wifi.scan_result = ScanResult(observations=[], scanned_at="2026-06-24T10:00:00Z")
    result = PassiveScanStage().run(ctx, ctx.checkpoint)
    assert result.status == "succeeded"
    assert result.outputs.get("observations_count") == "0"
