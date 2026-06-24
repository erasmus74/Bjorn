# Sub-project #0 — Plan 2b of 4: PassiveScanStage + Daemon

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first concrete Stage (`PassiveScanStage`), add the cooperative cancellation path that Plan 2a deferred, wire the NLM into `mjolnir/main.py` so `python -m mjolnir.main` actually runs the daemon, and verify the milestone: device boots, observes a real network within 60s, row appears in `networks` table.

**Architecture:** `PassiveScanStage` calls `ctx.interfaces.wifi.scan()`, runs the result through `IdentityResolver`, and writes new/updated rows to `networks`, `bssids`, and `bssid_sightings` via the repository bundle. Cooperative cancellation changes `mp.Pipe(duplex=False)` to `duplex=True` and adds a daemon thread in the child that polls the pipe for cancel messages. Main.py extends to start the NLM main loop in the foreground.

**Tech Stack:** Python 3.11+, existing mjolnir foundation + NLM framework.

**Spec reference:** `docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md`
**Depends on:** `v0.2.0-plan2a` (NLM framework complete)

**Branch:** `feat/v2-platform`

---

## File structure (Plan 2b scope)

```
mjolnir/
├── stages/
│   └── passive_scan.py                 ← NEW: first concrete Stage
├── nlm/
│   ├── executor.py                     ← MODIFY: Pipe(duplex=True), cancel protocol
│   └── runner.py                       ← MODIFY: spawn pipe-watcher thread, pass pipe to context
├── main.py                             ← MODIFY: extend with daemon loop
└── (other files unchanged)

tests/
├── unit/
│   └── stages/
│       └── test_passive_scan.py        ← NEW: full coverage with mocked interfaces
│   └── nlm/
│       └── test_cooperative_cancel.py  ← NEW: child polls pipe, Checkpoint.cancel() fires
└── integration/
    ├── test_passive_scan_lifecycle.py  ← NEW: scan + DB writes end-to-end
    └── test_daemon_loop.py             ← NEW: main.py runs NLM in subprocess
```

Hardware-marked tests (run on bench only, not in CI):
```
tests/hardware/
└── test_real_wifi_scan.py              ← NEW: real `iw` call, real APs in range
```

---

## Conventions

(same as Plans 1 and 2a — TDD, conventional commits, type hints, dataclasses, no comments unless WHY is non-obvious)

---

## Phase 1: PassiveScanStage

### Task 1.1: PassiveScanStage implementation

**Files:**
- Create: `mjolnir/stages/passive_scan.py`
- Test: `tests/unit/stages/test_passive_scan.py`

The stage calls `ctx.interfaces.wifi.scan()` and writes structured observations to the DB. Testable offline by mocking the InterfaceManager with a stub that returns canned `ScanResult` data.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/stages/test_passive_scan.py
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
    # Set the fake wifi to return observations of a new SSID
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

    # Verify DB has the new network
    networks = ctx.db.networks.find_by_ssid("BrandNewNet")
    assert len(networks) == 1
    new_net = networks[0]
    assert new_net.security_type == "WPA2"

    # Verify both BSSIDs were recorded
    bssids = ctx.db.bssids.list_for_network(new_net.id)
    bssid_macs = {b.bssid for b in bssids}
    assert "aa:bb:cc:dd:ee:01" in bssid_macs
    assert "aa:bb:cc:dd:ee:02" in bssid_macs


def test_passive_scan_extends_existing_network_via_bssid_overlap(ctx):
    """Re-sighting a known BSSID updates signal, doesn't create new network."""
    ctx, _ = ctx

    # First scan: see two BSSIDs
    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[
            _make_obs("AA:BB:CC:DD:EE:01", "MyNet", -50, 6),
            _make_obs("AA:BB:CC:DD:EE:02", "MyNet", -55, 6),
        ],
        scanned_at="2026-06-24T10:00:00Z",
    )
    stage = PassiveScanStage()
    stage.run(ctx, ctx.checkpoint)

    networks_before = ctx.db.networks.find_by_ssid("MyNet")
    assert len(networks_before) == 1
    original_net_id = networks_before[0].id

    # Second scan: same SSID, partial overlap (one new BSSID, one known)
    ctx.interfaces.wifi.scan_result = ScanResult(
        observations=[
            _make_obs("AA:BB:CC:DD:EE:02", "MyNet", -42, 6),  # overlap
            _make_obs("AA:BB:CC:DD:EE:03", "MyNet", -60, 6),  # new
        ],
        scanned_at="2026-06-24T11:00:00Z",
    )
    stage.run(ctx, ctx.checkpoint)

    networks_after = ctx.db.networks.find_by_ssid("MyNet")
    assert len(networks_after) == 1  # still one network, not two
    assert networks_after[0].id == original_net_id

    # All three BSSIDs now exist
    bssids = ctx.db.bssids.list_for_network(original_net_id)
    assert len(bssids) == 3
    # Signal of BSSID 02 should be the latest reading (-42)
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

    # Run again — should record another sighting
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
    assert result.outputs.get("networks_seen_count") == "2"  # X and Y


def test_passive_scan_handles_empty_scan(ctx):
    """No observations = success with zero counts."""
    ctx, _ = ctx
    ctx.interfaces.wifi.scan_result = ScanResult(observations=[], scanned_at="2026-06-24T10:00:00Z")
    result = PassiveScanStage().run(ctx, ctx.checkpoint)
    assert result.status == "succeeded"
    assert result.outputs.get("observations_count") == "0"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/unit/stages/test_passive_scan.py -v
```

- [ ] **Step 3: Write `mjolnir/stages/passive_scan.py`**

```python
"""PassiveScanStage: periodic WiFi beacon observation.

First concrete Stage implementation. Calls interfaces.wifi.scan(),
resolves ESS identity for each SSID via BSSID overlap, writes/updates
networks/bssids/bssid_sightings rows.
"""
from typing import ClassVar

from mjolnir.interfaces.types import ScanResult
from mjolnir.nlm.identity import IdentityResolver
from mjolnir.stages.base import (
    Checkpoint,
    CheckpointPolicy,
    InterfaceType,
    NetworkContext,
    ResourceProfile,
    Stage,
    StageResult,
)
from mjolnir.utils import iso_timestamp


class PassiveScanStage(Stage):
    name: ClassVar[str] = "passive_scan"
    description: ClassVar[str] = "Periodic WiFi beacon observation via iw scan"
    resources: ClassVar[ResourceProfile] = ResourceProfile(
        interfaces=[InterfaceType.WIFI],
        is_rf_transmitting=False,
        cpu_weight="light",
        est_duration_seconds=5,
    )
    checkpoint_policy: ClassVar[CheckpointPolicy] = CheckpointPolicy.RESTART_SAFE
    operates_in_view_only: ClassVar[bool] = True

    def __init__(self):
        self._resolver = IdentityResolver()

    def can_run(self, ctx: NetworkContext) -> bool:
        return True

    def run(self, ctx: NetworkContext, checkpoint: Checkpoint) -> StageResult:
        scan_result = ctx.interfaces.wifi.scan()

        if checkpoint.is_cancelled():
            return StageResult(status="failed", error="killed_before_processing")

        observations_by_ssid: dict[str, list] = {}
        for obs in scan_result.observations:
            observations_by_ssid.setdefault(obs.ssid, []).append(obs)

        networks_seen = 0
        for ssid, obs_list in observations_by_ssid.items():
            if checkpoint.is_cancelled():
                return StageResult(status="failed", error="killed_mid_processing")

            existing_networks = self._existing_networks_for_ssid(ctx, ssid)
            observed_bssids = {obs.bssid for obs in obs_list}
            resolution = self._resolver.resolve(ssid, observed_bssids, existing_networks)

            if resolution.action == "extend":
                network_id = resolution.target_network_id
                ctx.db.networks.update_last_seen(network_id, scan_result.scanned_at)
            else:
                new_net = ctx.db.networks.create(ssid=ssid, security_type=obs_list[0].security_type,
                                                  first_seen=scan_result.scanned_at)
                network_id = new_net.id
                ctx.db.networks.update_last_seen(network_id, scan_result.scanned_at)

            networks_seen += 1

            for obs in obs_list:
                if checkpoint.is_cancelled():
                    return StageResult(status="failed", error="killed_mid_write")
                bssid_row = ctx.db.bssids.upsert(
                    network_id=network_id,
                    bssid=obs.bssid,
                    security_type=obs.security_type,
                    channel=obs.channel,
                    signal_dbm=obs.signal_dbm,
                )
                ctx.db.bssid_sightings.record(
                    bssid_row.id, signal_dbm=obs.signal_dbm, channel=obs.channel,
                    when=scan_result.scanned_at,
                )

        return StageResult(
            status="succeeded",
            outputs={
                "observations_count": str(len(scan_result.observations)),
                "networks_seen_count": str(networks_seen),
            },
        )

    def _existing_networks_for_ssid(self, ctx: NetworkContext, ssid: str) -> list[dict]:
        networks = ctx.db.networks.find_by_ssid(ssid)
        result = []
        for net in networks:
            bssids_for_net = ctx.db.bssids.list_for_network(net.id)
            result.append({
                "id": net.id,
                "ssid": net.ssid,
                "bssids": {b.bssid for b in bssids_for_net},
            })
        return result
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/stages/test_passive_scan.py -v
```
Expected: PASS (9 tests)

- [ ] **Step 5: Register the stage so the NLM discovers it**

Edit `mjolnir/stages/__init__.py` to add:

```python
"""Stage framework: ABC, registry, supporting types."""
from mjolnir.stages.base import (
    Checkpoint,
    CheckpointPolicy,
    InterfaceType,
    NetworkContext,
    ResourceProfile,
    Stage,
    StageResult,
)
from mjolnir.stages.passive_scan import PassiveScanStage
from mjolnir.stages.registry import StageRegistry, registry

# Auto-register built-in stages
registry.register(PassiveScanStage)

__all__ = [
    "Checkpoint",
    "CheckpointPolicy",
    "InterfaceType",
    "NetworkContext",
    "PassiveScanStage",
    "ResourceProfile",
    "Stage",
    "StageResult",
    "StageRegistry",
    "registry",
]
```

- [ ] **Step 6: Re-run all tests to verify nothing broke**

```bash
pytest tests/ -v
```
Expected: 173 tests pass (164 prior + 9 passive_scan)

- [ ] **Step 7: Commit**

```bash
git add mjolnir/stages/passive_scan.py mjolnir/stages/__init__.py tests/unit/stages/test_passive_scan.py
git commit -m "feat(stages): PassiveScanStage (first concrete stage)

Calls interfaces.wifi.scan(), resolves ESS identity via BSSID overlap,
writes/updates networks/bssids/bssid_sightings. Records a sighting
per BSSID per scan for signal-history tracking.

Auto-registered at package import time so the NLM discovers it via
StageRegistry.stages_eligible_for_mode().

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 2: Cooperative cancellation (Plan 2a deferred work)

### Task 2.1: Make Pipe bidirectional + child-side pipe watcher

**Files:**
- Modify: `mjolnir/nlm/executor.py` (use `duplex=True`, send cancel protocol)
- Modify: `mjolnir/nlm/runner.py` (spawn pipe-watcher thread, propagate cancel to Checkpoint)
- Test: `tests/unit/nlm/test_cooperative_cancel.py`

Currently the parent writes `{"cmd": "cancel"}` but the child never reads it. We need:
1. `mp.Pipe(duplex=True)` so parent can send to child
2. Child spawns a daemon thread that polls the pipe
3. On cancel message, child calls `checkpoint.cancel(reason="kill_switch")`
4. Stages that poll `checkpoint.is_cancelled()` exit cleanly

- [ ] **Step 1: Write failing test**

```python
# tests/unit/nlm/test_cooperative_cancel.py
"""Verifies that kill-switch activation propagates through the pipe to the
child's Checkpoint object, allowing cooperative cancellation."""
import time
import multiprocessing as mp
import pytest

from mjolnir.nlm.executor import StageExecutor
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner


class CooperativeCancelStage(Stage):
    """Polls checkpoint in a loop, exits cleanly when cancelled."""
    name = "cooperative_cancel_test_stage"
    description = "test"
    resources = ResourceProfile(est_duration_seconds=30)
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        for _ in range(600):  # up to 30 seconds
            if checkpoint.is_cancelled():
                return StageResult(status="failed", error="killed_by_operator_cooperative")
            time.sleep(0.05)
        return StageResult(status="succeeded")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    from mjolnir.db.repositories import bundle_for
    bundle = bundle_for(conn)
    net = bundle.networks.create(ssid="X")
    network_id = net.id
    conn.close()

    reg = StageRegistry()
    reg.register(CooperativeCancelStage)
    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    executor = StageExecutor(
        db_path=tmp_path / "x.db",
        mem_limit_mb=256,
        kill_switch_event=mp.Event(),
    )
    return executor, network_id


def test_cooperative_cancel_propagates_to_child(setup):
    """Kill switch set after 0.3s; child should exit cooperatively within 1s."""
    executor, network_id = setup

    import threading
    def trigger():
        time.sleep(0.3)
        executor.kill_switch_event.set()
    threading.Thread(target=trigger, daemon=True).start()

    result = executor.execute(
        stage_name="cooperative_cancel_test_stage",
        network_id=network_id,
        timeout_seconds=10,
    )

    assert result.status == "failed"
    assert "cooperative" in (result.error or "").lower(), (
        f"expected cooperative cancel, got: {result.error}"
    )
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/nlm/test_cooperative_cancel.py -v
```
Expected: FAIL — current implementation SIGTERMs the child on kill switch, so the error would be "subprocess terminated" or similar, not "cooperative".

- [ ] **Step 3: Modify `mjolnir/nlm/executor.py`**

Change `mp.Pipe(duplex=False)` to `mp.Pipe(duplex=True)`. The watcher thread already sends `{"cmd": "cancel"}` via `parent_conn.send(...)`. With `duplex=True`, the parent_conn can send to the child.

Also: after sending cancel, **don't** immediately terminate. Give the child a grace period (default 2 seconds) to exit cooperatively. Only if it's still alive after grace, fall through to SIGTERM/SIGKILL.

Replace the existing `watch_kill_switch` and main loop with:

```python
def watch_kill_switch():
    while proc.is_alive() and not cancel_sent["value"]:
        if self.kill_switch_event.is_set():
            try:
                parent_conn.send({"cmd": "cancel"})
            except (BrokenPipeError, OSError):
                pass
            cancel_sent["value"] = True
            return
        time.sleep(0.05)

# After receiving cancel confirmation OR grace period:
# If the child returned a "killed_by_operator_*" result, exit cleanly.
# If still alive after 2s, fall through to terminate chain.
```

The main loop needs adjustment: after watcher fires cancel, allow up to 2 additional seconds for child to exit. If child exits with killed_by_operator_* status, return that. If child still alive after grace, terminate.

Specifically modify the loop section:

```python
deadline = time.monotonic() + timeout_seconds
grace_deadline = None  # set when cancel is sent
timed_out = False
result_msg: dict[str, Any] | None = None

while True:
    # If cancel was sent and grace period elapsed, terminate
    if grace_deadline is not None and time.monotonic() > grace_deadline and proc.is_alive():
        proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=1)
        result_msg = {"type": "error", "error": "kill_switch_terminated_after_grace"}
        break

    if proc.is_alive() and time.monotonic() > deadline:
        timed_out = True
        proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=1)
        break

    if parent_conn.poll(0.1):
        result_msg = parent_conn.recv()
        # If cancel was sent and we just received a cooperative-cancel result,
        # we're done. Otherwise continue the loop (child may send another message).
        if cancel_sent["value"] and result_msg.get("error", "").startswith("killed"):
            break
        if result_msg.get("type") == "result":
            break
        if result_msg.get("type") == "error":
            break

    if not proc.is_alive() and not parent_conn.poll(0):
        result_msg = {"type": "error", "error": f"subprocess_exited_code_{proc.exitcode}"}
        break

    # Set grace deadline when cancel is first sent
    if cancel_sent["value"] and grace_deadline is None:
        grace_deadline = time.monotonic() + 2.0
```

- [ ] **Step 4: Modify `mjolnir/nlm/runner.py`**

Add a pipe-watcher thread in the child. Replace the existing function body with:

```python
import resource
import threading
from pathlib import Path
from typing import Any

from mjolnir.audit.logger import AuditLogger
from mjolnir.config import BjornConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.interfaces.manager import InterfaceManager
from mjolnir.stages.base import Checkpoint, NetworkContext
from mjolnir.stages.registry import registry


def _watch_pipe_for_cancel(pipe: Any, checkpoint: Checkpoint) -> None:
    """Daemon thread: polls pipe for cancel message, sets checkpoint on receipt."""
    while True:
        try:
            if pipe.poll(0.1):
                msg = pipe.recv()
                if isinstance(msg, dict) and msg.get("cmd") == "cancel":
                    checkpoint.cancel(reason="kill_switch")
                    return
        except (EOFError, OSError):
            return
        except Exception:
            continue


def run_stage_in_subprocess(
    stage_name: str,
    network_id: int,
    db_path: str,
    config_dict: dict[str, Any],
    mem_limit_mb: int,
    pipe: Any,
) -> None:
    mem_bytes = mem_limit_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

    stage_cls = registry.get(stage_name)
    if stage_cls is None:
        pipe.send({"type": "error", "error": f"stage not found: {stage_name}"})
        return

    try:
        factory = ConnectionFactory(db_path=Path(db_path))
        conn = factory.connect()
        MigrationRunner(conn).initialize_fresh_db()
        bundle = bundle_for(conn)

        network = bundle.networks.get_by_id(network_id)
        if network is None:
            pipe.send({"type": "error", "error": f"network not found: {network_id}"})
            return

        audit = AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)
        interfaces = InterfaceManager()
        checkpoint = Checkpoint()

        # Spawn pipe-watcher thread to propagate cancel signals
        watcher = threading.Thread(
            target=_watch_pipe_for_cancel,
            args=(pipe, checkpoint),
            daemon=True,
        )
        watcher.start()

        ctx = NetworkContext(
            network=network,
            db=bundle,
            config=BjornConfig(),
            interfaces=interfaces,
            audit=audit,
            workdir=Path(db_path).parent / "stages" / str(network_id) / stage_name,
            checkpoint=checkpoint,
        )

        stage = stage_cls()
        result = stage.run(ctx, checkpoint)

        pipe.send({
            "type": "result",
            "status": result.status,
            "error": result.error,
            "outputs": result.outputs,
        })
    except Exception as e:
        pipe.send({"type": "error", "error": f"{type(e).__name__}: {e}"})
```

- [ ] **Step 5: Run new test to verify pass**

```bash
pytest tests/unit/nlm/test_cooperative_cancel.py -v
```
Expected: PASS (1 test). Should complete in under 2 seconds (cancel at 0.3s + grace).

- [ ] **Step 6: Run full suite to verify no regressions**

```bash
pytest tests/ -v
```
Expected: 174 tests pass (173 prior + 1 cooperative cancel). The existing `test_executor_returns_failed_on_cancellation` should still pass — it doesn't assert HOW the cancel happens, just that the result is `failed`.

- [ ] **Step 7: Commit**

```bash
git add mjolnir/nlm/executor.py mjolnir/nlm/runner.py tests/unit/nlm/test_cooperative_cancel.py
git commit -m "feat(nlm): cooperative cancellation via bidirectional Pipe

Plan 2a left a known gap: parent sent cancel via pipe, child never
read it. Now:
- mp.Pipe(duplex=True) so parent can send to child
- Child spawns daemon thread that polls pipe for {cmd: cancel}
- On cancel, child calls checkpoint.cancel(reason='kill_switch')
- Stages polling checkpoint.is_cancelled() exit cleanly

Parent still falls back to SIGTERM after a 2s grace period as the
authoritative backstop for misbehaving stages.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 3: Main.py daemon loop

### Task 3.1: Extend main.py to run the NLM daemon

**Files:**
- Modify: `mjolnir/main.py`
- Test: `tests/integration/test_daemon_loop.py`

Currently main.py just initializes the DB and exits. Now we extend it to start the NLM main loop when `--init-db` is not passed.

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_daemon_loop.py
"""Verify main.py starts the NLM and exits cleanly on SIGTERM."""
import multiprocessing as mp
import signal
import sys
import time
import threading
from pathlib import Path

import pytest

from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner


def test_main_runs_daemon_loop_until_shutdown(tmp_path: Path, monkeypatch):
    """main() should run the NLM loop and exit when shutdown is requested."""
    # Build a minimal config that points at our tmp DB
    config_path = tmp_path / "config.toml"
    config_path.write_text(f"""
[paths]
data_dir = "{tmp_path}"
log_dir = "{tmp_path}/logs"

[db]
filename = "test.db"

[nlm]
scan_interval_seconds = 1
stage_pool_size = 1
stage_memory_limit_mb = 256
""")

    # Initialize DB first (so daemon finds it)
    from mjolnir.main import main, initialize
    cfg_init = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="test.db"),
    )
    initialize(cfg_init)

    # Run main() in a thread; signal shutdown after 2 seconds
    shutdown_after_seconds = 2
    main_thread_result = {"exit_code": None}

    def run_main():
        main_thread_result["exit_code"] = main(argv=["--config", str(config_path)])

    t = threading.Thread(target=run_main, daemon=True)
    t.start()

    # Send SIGTERM to ourselves after the delay (simulates systemd stopping the service)
    def send_shutdown():
        time.sleep(shutdown_after_seconds)
        # The NLM main loop should respond to a shutdown flag.
        # For test purposes, we use a test-only hook.
        import mjolnir.main as main_mod
        main_mod._request_shutdown_for_tests()

    threading.Thread(target=send_shutdown, daemon=True).start()
    t.join(timeout=10)

    assert not t.is_alive(), "main() did not exit within 10s"
    assert main_thread_result["exit_code"] == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/integration/test_daemon_loop.py -v
```
Expected: FAIL — current main() prints "daemon loop not yet implemented" and returns immediately without running NLM.

- [ ] **Step 3: Modify `mjolnir/main.py`**

```python
"""mjolnir entrypoint."""
import argparse
import multiprocessing as mp
import signal
import sys
import threading
import time
from pathlib import Path

from mjolnir.config import BjornConfig, load_config
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.stages import registry as default_registry
from mjolnir.stages.registry import StageRegistry


# Test-only shutdown signal. Tests set this to True to stop the daemon loop.
_shutdown_requested = threading.Event()


def _request_shutdown_for_tests() -> None:
    """Test hook: signals the daemon loop to exit cleanly."""
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
    """SIGTERM/SIGINT trigger clean shutdown."""
    def handler(signum, frame):
        _shutdown_requested.set()
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def run_daemon(config: BjornConfig) -> int:
    """Run the NLM main loop until shutdown is requested."""
    _install_signal_handlers()
    _shutdown_requested.clear()

    kill_switch_event = mp.Event()
    mgr = NetworkLifecycleManager(
        db_path=config.db.path,
        config=config,
        registry=default_registry,
        kill_switch_event=kill_switch_event,
    )

    while not _shutdown_requested.is_set():
        try:
            mgr.run_once()
        except Exception as e:
            print(f"warning: NLM iteration failed: {e}", file=sys.stderr)
        # Sleep in small increments so shutdown is responsive
        for _ in range(config.nlm.scan_interval_seconds * 10):
            if _shutdown_requested.is_set():
                break
            time.sleep(0.1)

    return 0


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

    if args.once:
        # Single iteration: useful for testing and one-shot scripts
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
```

- [ ] **Step 4: Run test to verify pass**

```bash
pytest tests/integration/test_daemon_loop.py -v
```
Expected: PASS (1 test, ~2 seconds)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/main.py tests/integration/test_daemon_loop.py
git commit -m "feat(main): daemon loop runs NLM until shutdown

main() now starts the NLM main loop when --init-db is not passed.
SIGTERM/SIGINT set a shutdown flag; the loop exits cleanly.
--once flag runs a single iteration (useful for testing/one-shot).

Tests use a test-only _request_shutdown_for_tests() hook to avoid
needing real signal delivery in the test process.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4: End-to-end passive scan integration test

### Task 4.1: Verify PassiveScanStage runs via the NLM and writes to DB

**Files:**
- Test: `tests/integration/test_passive_scan_lifecycle.py`

This test wires everything together: NLM schedules PassiveScanStage, the stage runs in a subprocess, observations are written to the DB.

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_passive_scan_lifecycle.py
"""End-to-end: NLM runs PassiveScanStage in a real subprocess, writes rows.

Uses a stub InterfaceManager monkey-patched into PassiveScanStage's
interface call so we don't need a real WiFi adapter for CI. The
hardware test (Phase 5) replaces this with a real `iw` call."""
import multiprocessing as mp
from pathlib import Path

import pytest

from mjolnir.config import BjornConfig, DbConfig, NlmConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.interfaces.types import BssidObservation, ScanResult
from mjolnir.interfaces.wifi import WiFiInterface
from mjolnir.stages.registry import StageRegistry
from mjolnir.stages import passive_scan as passive_scan_mod


@pytest.fixture
def configured_db(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()
    return tmp_path / "x.db"


def test_nlm_passive_scan_discovers_new_network(configured_db, monkeypatch):
    """Monkey-patch wifi.scan() to return canned data; NLM should pick it up."""
    # Patch WiFiInterface.scan to return a fixed result
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

    # Register the real PassiveScanStage
    reg = StageRegistry()
    from mjolnir.stages.passive_scan import PassiveScanStage
    reg.register(PassiveScanStage)

    # Patch runner's registry so subprocess finds the stage
    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=configured_db.parent, log_dir=configured_db.parent / "logs"),
        db=DbConfig(data_dir=configured_db.parent, filename=configured_db.name),
        nlm=NlmConfig(stage_memory_limit_mb=256),
    )

    mgr = NetworkLifecycleManager(
        db_path=configured_db,
        config=cfg,
        registry=reg,
        kill_switch_event=mp.Event(),
    )

    # Default mode is view_only; PassiveScanStage operates_in_view_only so it's eligible
    executed = mgr.run_once()
    assert executed == 1

    # Verify the network was created
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
                    signal_dbm=-50 + scan_call_count["n"],  # changes each call
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
    from mjolnir.stages.passive_scan import PassiveScanStage
    reg.register(PassiveScanStage)
    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=configured_db.parent, log_dir=configured_db.parent / "logs"),
        db=DbConfig(data_dir=configured_db.parent, filename=configured_db.name),
        nlm=NlmConfig(stage_memory_limit_mb=256),
    )
    mgr = NetworkLifecycleManager(
        db_path=configured_db,
        config=cfg,
        registry=reg,
        kill_switch_event=mp.Event(),
    )

    # First run
    mgr.run_once()
    # Second run
    mgr.run_once()

    conn = ConnectionFactory(db_path=configured_db).connect()
    bundle = bundle_for(conn)
    networks = bundle.networks.find_by_ssid("ResumableNet")
    assert len(networks) == 1, "should still be one network after two scans"

    bssids = bundle.bssids.list_for_network(networks[0].id)
    assert len(bssids) == 1
    # Two sightings should exist
    sightings = bundle.bssid_sightings.list_for_bssid(bssids[0].id)
    assert len(sightings) == 2
    conn.close()
```

- [ ] **Step 2: Run to verify pass**

```bash
pytest tests/integration/test_passive_scan_lifecycle.py -v
```
Expected: PASS (2 tests). These spawn real subprocesses.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_passive_scan_lifecycle.py
git commit -m "test(integration): PassiveScanStage lifecycle via NLM

Verifies end-to-end:
- NLM schedules PassiveScanStage in subprocess
- Stage calls interfaces.wifi.scan() (monkey-patched for CI)
- Observations write to networks/bssids/bssid_sightings
- Second run on same network updates signal, doesn't duplicate

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 5: Hardware-marked tests

### Task 5.1: Real WiFi scan test (skipped in CI)

**Files:**
- Create: `tests/hardware/__init__.py`
- Create: `tests/hardware/test_real_wifi_scan.py`

These tests require real Pi Zero 2W hardware with a WiFi adapter in range of at least one AP. Marked with `@pytest.mark.hardware` so they're skipped by default in CI.

- [ ] **Step 1: Add pytest configuration for hardware marker**

Edit `pyproject.toml` to register conftest behavior:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
pythonpath = ["."]
addopts = "-ra --strict-markers -m 'not hardware'"
markers = [
    "hardware: requires real Pi Zero 2W hardware (deselected by default)",
]
```

The `-m 'not hardware'` flag in `addopts` ensures hardware tests are skipped by default. To run them on the bench: `pytest -m hardware`.

- [ ] **Step 2: Create hardware test file**

```python
# tests/hardware/__init__.py
# (empty — just makes tests/hardware a package)
```

```python
# tests/hardware/test_real_wifi_scan.py
"""Hardware-marked tests that exercise real WiFi hardware.

Run with: pytest -m hardware
These require:
- Real Pi Zero 2W with WiFi adapter on wlan0
- At least one AP in range (any SSID)
- Root privileges (for `iw dev wlan0 scan`)
"""
import subprocess
import time

import pytest

from mjolnir.config import BjornConfig, DbConfig, NlmConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.interfaces.wifi import WiFiInterface, parse_iw_scan_output
from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.stages.passive_scan import PassiveScanStage
from mjolnir.stages.registry import StageRegistry

import multiprocessing as mp


pytestmark = pytest.mark.hardware


def test_real_iw_scan_returns_output():
    """Sanity check: iw dev wlan0 scan produces parseable output."""
    iface = WiFiInterface(ifname="wlan0")
    result = iface.scan()
    # We don't assert any specific SSID (test environments vary), just that
    # the scan completed and returned a list of observations (possibly empty
    # if no APs in range).
    assert isinstance(result.observations, list)


def test_nlm_discovers_real_networks_within_60s(tmp_path):
    """Acceptance test: device boots, observes a real network within 60s.

    This is the milestone test for Plan 2b. Failure means the device can't
    do passive WiFi observation, which is the foundation of everything else.
    """
    # Initialize DB
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    networks_before = len(conn.execute("SELECT * FROM networks").fetchall())
    conn.close()

    # Build NLM with real PassiveScanStage
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

    # Run up to 3 iterations within 60 seconds
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
```

- [ ] **Step 3: Run with hardware marker (will skip by default)**

```bash
pytest tests/hardware/ -v
```
Expected: 2 tests deselected (because of `-m 'not hardware'` in addopts)

```bash
pytest tests/hardware/ -v -m hardware
```
Expected: would actually run on Pi Zero 2W; would FAIL or ERROR on dev machine without wlan0.

- [ ] **Step 4: Commit**

```bash
git add tests/hardware/__init__.py tests/hardware/test_real_wifi_scan.py pyproject.toml
git commit -m "test(hardware): real WiFi scan acceptance tests

Two hardware-marked tests that exercise the real iw dev wlan0 scan
path on Pi Zero 2W. Skipped by default via -m 'not hardware' in
pytest config; run on the bench with: pytest -m hardware

test_nlm_discovers_real_networks_within_60s is the Plan 2b
acceptance test — it fails if the device can't observe any WiFi
within 60s of starting.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 6: Acceptance

### Task 6.1: Full test suite green

- [ ] **Step 1: Run the entire test suite**

```bash
pytest tests/ -v
```

Expected: ~178 tests pass (164 from Plan 2a + 9 passive_scan + 1 cooperative_cancel + 1 daemon_loop + 2 passive_scan_integration = 177; hardware tests deselected).

- [ ] **Step 2: Run with coverage**

```bash
pytest tests/ --cov=mjolnir --cov-report=term
```

Expected: Coverage ≥ 85% (PassiveScanStage is fully covered by mocked tests; only the hardware-specific paths are untestable in CI).

### Task 6.2: Tag Plan 2b milestone

- [ ] **Step 1: Verify clean working tree**

```bash
git status
```

- [ ] **Step 2: Create annotated tag**

```bash
git tag -a v0.3.0-plan2b -m "Plan 2b of sub-project #0 complete: PassiveScanStage + daemon

- PassiveScanStage (first concrete stage; auto-registered)
- Cooperative cancellation via bidirectional Pipe + child-side watcher
- main.py daemon loop with SIGTERM/SIGINT handling + --once flag
- End-to-end integration tests with real subprocess execution
- Hardware-marked tests for real WiFi acceptance (bench-only)
- ~177 tests total (13 new since Plan 2a)

Milestone met: device boots, NLM schedules PassiveScanStage, real
WiFi scan writes rows to networks/bssids/bssid_sightings.
Plan 3 (Flask WebUI + EPD display) is next."
```

---

## Plan 2b acceptance criteria

1. ✅ All Plan 2a tests still pass (164)
2. ✅ All ~13 Plan 2b tests pass
3. ✅ Test coverage of `mjolnir/` ≥ 85%
4. ✅ `PassiveScanStage` registers at import time and is discovered by NLM
5. ✅ Cooperative cancellation propagates through bidirectional Pipe
6. ✅ `python -m mjolnir.main` runs the daemon loop and exits cleanly on SIGTERM
7. ✅ `python -m mjolnir.main --once` runs a single NLM iteration
8. ✅ End-to-end integration test: NLM schedules PassiveScanStage in subprocess, observations write to DB
9. ✅ Hardware tests marked and skipped in CI (bench-only acceptance)
10. ✅ Tag `v0.3.0-plan2b` exists

The final hardware acceptance test (`test_nlm_discovers_real_networks_within_60s`) requires real Pi Zero 2W hardware and is intentionally not part of CI.

---

## Plan 3 preview (next plan, not yet written)

Plan 3 will:

- Build the Flask WebUI (dashboard, networks inventory, network detail, blocklist form, settings for mode/kill switch)
- Build the EPD display state manager (14 priority-ordered states)
- Wire both to read NLM state via the repository bundle
- Plan 3 is purely software (no hardware needed); full CI coverage is achievable

Plan 3 is the last "framework" plan before sub-project #0 ships. Plan 4 then adds the v1→v2 migration script and finalizes the systemd unit.
