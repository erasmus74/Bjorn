# Sub-project #0 — Plan 2a of 4: NLM Framework

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Network Lifecycle Manager framework: interface abstractions, ESS identity resolver, scope enforcement, subprocess-per-stage executor, and NLM scheduler. After this plan, the framework is complete and fully tested with stub stages; Plan 2b adds the first real stage (`PassiveScanStage`) and wires everything into the daemon loop.

**Architecture:** All hardware access goes through `InterfaceManager` and its children (`WiFiInterface`, `BluetoothInterface`, `BLEInterface`). Stage execution runs in a child process via `multiprocessing.Process` with `RLIMIT_AS` enforced. The NLM main loop picks work via `StageRegistry.stages_eligible_for_mode()`, filters by data-availability gates, dispatches via the executor, and writes audit/status via the existing repositories.

**Tech Stack:** Python 3.11+, `multiprocessing` (stdlib), `resource` (stdlib, RLIMIT), `psutil` (optional, for live memory monitoring), existing mjolnir foundation.

**Spec reference:** `docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md`
**Depends on:** `v0.1.0-plan1` (foundation layer complete)

**Branch:** `feat/v2-platform`

---

## File structure (Plan 2a scope)

```
mjolnir/
├── interfaces/                         ← NEW
│   ├── __init__.py
│   ├── manager.py                      ← InterfaceManager (single entry point)
│   ├── wifi.py                         ← WiFiInterface (passive scan + managed mode)
│   ├── bluetooth.py                    ← BluetoothInterface (stub, NotImplementedError)
│   ├── ble.py                          ← BLEInterface (stub, NotImplementedError)
│   └── types.py                        ← ScanResult, BssidObservation dataclasses
├── nlm/                                ← NEW
│   ├── __init__.py
│   ├── manager.py                      ← NetworkLifecycleManager main loop
│   ├── identity.py                     ← ESS union-find over BSSID overlaps
│   ├── scope.py                        ← ScopeChecker (mode + blocklist + persistence gates)
│   ├── executor.py                     ← StageExecutor (subprocess-per-stage + RLIMIT)
│   ├── gates.py                        ← Data-availability gate evaluation
│   └── runner.py                       ← Subprocess entry point (called by multiprocessing)
├── stages/
│   └── passive_scan.py                 ← STUB ONLY (Plan 2b implements)
└── (existing files unchanged)

tests/
├── unit/
│   ├── interfaces/
│   │   ├── test_manager.py
│   │   ├── test_wifi.py                ← Uses captured `iw` output as fixtures
│   │   └── test_types.py
│   ├── nlm/
│   │   ├── test_identity.py            ← Pure-Python ESS union-find
│   │   ├── test_scope.py
│   │   ├── test_executor.py            ← Uses stub stages (no real work)
│   │   ├── test_gates.py
│   │   └── test_manager.py             ← NLM main loop with stub stages
└── integration/
    └── test_nlm_lifecycle.py           ← End-to-end with stub stage in subprocess
```

Files NOT in Plan 2a (deferred to Plan 2b):
- `mjolnir/stages/passive_scan.py` (real implementation)
- Hardware-marked tests (`@pytest.mark.hardware`)
- `mjolnir/main.py` daemon loop extension
- Real `iw` integration

---

## Conventions

(same as Plan 1 — TDD, conventional commits with `Co-Authored-By: Claude Opus 4.7`, type hints everywhere, `dataclass` for value types, no comments unless WHY is non-obvious)

---

## Phase 1: Interface abstractions

### Task 1.1: Interface type definitions + scan result dataclasses

**Files:**
- Create: `mjolnir/interfaces/__init__.py`
- Create: `mjolnir/interfaces/types.py`
- Test: `tests/unit/interfaces/test_types.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/interfaces/test_types.py
from datetime import datetime, timezone
from mjolnir.interfaces.types import BssidObservation, ScanResult


def test_bssidobservation_basic_fields():
    obs = BssidObservation(
        bssid="AA:BB:CC:DD:EE:01",
        ssid="TestNet",
        signal_dbm=-42,
        channel=6,
        security_type="WPA2",
        first_seen="2026-06-23T10:00:00Z",
        last_seen="2026-06-23T10:00:00Z",
    )
    assert obs.bssid == "AA:BB:CC:DD:EE:01"
    assert obs.signal_dbm == -42
    assert obs.security_type == "WPA2"


def test_scanresult_contains_observations():
    obs1 = BssidObservation(
        bssid="AA:BB:CC:DD:EE:01", ssid="X", signal_dbm=-42, channel=6,
        security_type="WPA2",
        first_seen="2026-06-23T10:00:00Z", last_seen="2026-06-23T10:00:00Z",
    )
    obs2 = BssidObservation(
        bssid="AA:BB:CC:DD:EE:02", ssid="X", signal_dbm=-55, channel=6,
        security_type="WPA2",
        first_seen="2026-06-23T10:00:00Z", last_seen="2026-06-23T10:00:00Z",
    )
    result = ScanResult(observations=[obs1, obs2], scanned_at="2026-06-23T10:00:00Z")
    assert len(result.observations) == 2
    assert result.observations[0].bssid == "AA:BB:CC:DD:EE:01"


def test_bssidobservation_security_type_allows_none():
    obs = BssidObservation(
        bssid="AA:BB:CC:DD:EE:01", ssid="X", signal_dbm=-42, channel=6,
        security_type=None,
        first_seen="2026-06-23T10:00:00Z", last_seen="2026-06-23T10:00:00Z",
    )
    assert obs.security_type is None
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/interfaces/test_types.py -v
```

- [ ] **Step 3: Write `mjolnir/interfaces/__init__.py`**

```python
"""Hardware interface abstractions: WiFi, Bluetooth, BLE."""
```

- [ ] **Step 4: Write `mjolnir/interfaces/types.py`**

```python
"""Data types shared across interface implementations."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BssidObservation:
    """One row from a WiFi scan: a single AP sighting."""
    bssid: str
    ssid: str
    signal_dbm: int
    channel: int
    security_type: str | None  # 'WPA2', 'WPA3', 'WEP', 'open', None if unknown
    first_seen: str  # ISO-8601
    last_seen: str   # ISO-8601


@dataclass(frozen=True)
class ScanResult:
    """The output of a single WiFi scan call."""
    observations: list[BssidObservation]
    scanned_at: str  # ISO-8601
```

- [ ] **Step 5: Run to verify pass**

```bash
pytest tests/unit/interfaces/test_types.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/interfaces/__init__.py mjolnir/interfaces/types.py tests/unit/interfaces/test_types.py
git commit -m "feat(interfaces): scan result types

BssidObservation and ScanResult frozen dataclasses — the
structured outputs interface.scan() returns.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 1.2: WiFiInterface with `iw` output parser (offline-testable)

**Files:**
- Create: `mjolnir/interfaces/wifi.py`
- Test: `tests/unit/interfaces/test_wifi.py`

This task implements the `WiFiInterface` class with one method (`scan()`) that calls `iw dev <ifname> scan`. The parser for `iw` output is the testable part — we feed it real captured output and verify structured results.

- [ ] **Step 1: Write failing tests (using captured `iw` output)**

```python
# tests/unit/interfaces/test_wifi.py
import pytest
from mjolnir.interfaces.wifi import WiFiInterface, parse_iw_scan_output


# Captured real `iw dev wlan0 scan` output (truncated to relevant fields).
# Two APs: one WPA2, one WPA3, one open.
SAMPLE_IW_OUTPUT = """
BSS aa:bb:cc:dd:ee:01 on wlan0	assoc:0
	freq: 2437
	chan: 6
	signal: -42.00 dBm
	last seen: 1000 ms ago
	Super Net
.capabilities:ESS Privacy SpectrumMgt ShortSlotTime
	RSN:	 * Version: 1
		 * Group cipher: CCMP
		 * Pairwise ciphers: CCMP
		 * Authentication suites: PSK
BSS aa:bb:cc:dd:ee:02 on wlan0	assoc:0
	freq: 5180
	chan: 36
	signal: -55.00 dBm
	last seen: 1000 ms ago
	Another Net
.capabilities:ESS Privacy SpectrumMgt ShortSlotTime
	RSN:	 * Version: 1
		 * Group cipher: CCMP
		 * Pairwise ciphers: CCMP
		 * Authentication suites: SAE
BSS aa:bb:cc:dd:ee:03 on wlan0	assoc:0
	freq: 2412
	chan: 1
	signal: -68.00 dBm
	last seen: 1000 ms ago
	Open Net
.capabilities:ESS ShortSlotTime
"""


def test_parse_iw_output_extracts_three_bssids():
    results = parse_iw_scan_output(SAMPLE_IW_OUTPUT)
    assert len(results) == 3


def test_parse_iw_output_extracts_bssid_mac():
    results = parse_iw_scan_output(SAMPLE_IW_OUTPUT)
    bssids = {r.bssid for r in results}
    assert "aa:bb:cc:dd:ee:01" in bssids
    assert "aa:bb:cc:dd:ee:02" in bssids
    assert "aa:bb:cc:dd:ee:03" in bssids


def test_parse_iw_output_extracts_signal_dbm():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:01"].signal_dbm == -42
    assert results["aa:bb:cc:dd:ee:02"].signal_dbm == -55


def test_parse_iw_output_extracts_channel():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:01"].channel == 6
    assert results["aa:bb:cc:dd:ee:02"].channel == 36


def test_parse_iw_output_extracts_ssid():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:01"].ssid == "Super Net"
    assert results["aa:bb:cc:dd:ee:03"].ssid == "Open Net"


def test_parse_iw_output_classifies_security_wpa2_psk():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:01"].security_type == "WPA2"


def test_parse_iw_output_classifies_security_wpa3_sae():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:02"].security_type == "WPA3"


def test_parse_iw_output_classifies_security_open():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:03"].security_type == "open"


def test_parse_iw_output_empty_input():
    results = parse_iw_scan_output("")
    assert results == []


def test_parse_iw_output_handles_hidden_ssid():
    """AP with no SSID line — hidden network."""
    hidden_output = """
BSS aa:bb:cc:dd:ee:04 on wlan0
	freq: 2412
	chan: 1
	signal: -70.00 dBm
.capabilities:ESS Privacy
"""
    results = parse_iw_scan_output(hidden_output)
    assert len(results) == 1
    assert results[0].ssid == ""  # empty string for hidden
    assert results[0].security_type == "WPA2"  # Privacy flag set, no RSN → assume WPA2


def test_wifi_interface_constructor_requires_ifname():
    iface = WiFiInterface(ifname="wlan0")
    assert iface.ifname == "wlan0"


def test_wifi_interface_scan_calls_subprocess(monkeypatch, tmp_path):
    """scan() shells out to `iw`; we mock subprocess.run and verify the call."""
    captured = {}

    class FakeResult:
        stdout = SAMPLE_IW_OUTPUT
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeResult()

    import mjolnir.interfaces.wifi as wifi_mod
    monkeypatch.setattr(wifi_mod.subprocess, "run", fake_run)

    iface = WiFiInterface(ifname="wlan0")
    result = iface.scan()

    assert captured["cmd"] == ["iw", "dev", "wlan0", "scan"]
    assert len(result.observations) == 3
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/interfaces/test_wifi.py -v
```

- [ ] **Step 3: Write `mjolnir/interfaces/wifi.py`**

```python
"""WiFiInterface: passive scan via `iw dev <ifname> scan`.

The parser is a pure function (parse_iw_scan_output) so it can be tested
without actually running `iw`. The WiFiInterface class is a thin shell
that invokes `iw` and feeds output to the parser.
"""
import re
import subprocess
from dataclasses import dataclass

from mjolnir.interfaces.types import BssidObservation, ScanResult
from mjolnir.utils import iso_timestamp

_BSS_HEADER_RE = re.compile(r"^BSS ([0-9a-fA-F:]{17})\s+on\s+\S+")
_SIGNAL_RE = re.compile(r"^\tsignal:\s+(-?\d+\.\d+)\s+dBm")
_CHAN_RE = re.compile(r"^\tchan:\s+(\d+)")
_SSID_RE = re.compile(r"^\t(.+\.?capabilities:.*)")
_SSID_LINE_RE = re.compile(r"^\t([^\t]+)$")
_PRIVACY_RE = re.compile(r"capabilities:.*Privacy")
_RSN_AUTH_PSK_RE = re.compile(r"Authentication suites:\s*PSK")
_RSN_AUTH_SAE_RE = re.compile(r"Authentication suites:\s*SAE")


def parse_iw_scan_output(output: str) -> list[BssidObservation]:
    """Parse `iw dev <if> scan` output into structured observations.

    Pure function — no I/O. Tests feed captured output.
    """
    observations: list[BssidObservation] = []
    current: dict | None = None
    when = iso_timestamp()

    for line in output.splitlines():
        bss_match = _BSS_HEADER_RE.match(line)
        if bss_match:
            if current is not None:
                observations.append(_finalize_observation(current, when))
            current = {
                "bssid": bss_match.group(1).lower(),
                "signal_dbm": None,
                "channel": None,
                "ssid": None,
                "has_privacy": False,
                "auth_psk": False,
                "auth_sae": False,
            }
            continue

        if current is None:
            continue

        signal_m = _SIGNAL_RE.match(line)
        if signal_m:
            current["signal_dbm"] = int(float(signal_m.group(1)))
            continue

        chan_m = _CHAN_RE.match(line)
        if chan_m:
            current["channel"] = int(chan_m.group(1))
            continue

        if _PRIVACY_RE.search(line):
            current["has_privacy"] = True
            continue

        if _RSN_AUTH_PSK_RE.search(line):
            current["auth_psk"] = True
            continue

        if _RSN_AUTH_SAE_RE.search(line):
            current["auth_sae"] = True
            continue

        # SSID line: a tab followed by non-tab text that isn't a known field.
        # Heuristic: must be a single tab + content + not match other patterns.
        ssid_m = _SSID_LINE_RE.match(line)
        if ssid_m and current["ssid"] is None:
            text = ssid_m.group(1).strip()
            # Skip known field markers
            if text and not text.endswith(":") and "capabilities:" not in text:
                current["ssid"] = text

    if current is not None:
        observations.append(_finalize_observation(current, when))

    return observations


def _finalize_observation(d: dict, when: str) -> BssidObservation:
    ssid = d.get("ssid") or ""
    if d.get("auth_sae"):
        sec = "WPA3"
    elif d.get("auth_psk"):
        sec = "WPA2"
    elif d.get("has_privacy"):
        sec = "WPA2"  # privacy flag set, no RSN details → assume WPA2
    else:
        sec = "open"
    return BssidObservation(
        bssid=d["bssid"],
        ssid=ssid,
        signal_dbm=d["signal_dbm"] if d["signal_dbm"] is not None else -100,
        channel=d["channel"] or 0,
        security_type=sec,
        first_seen=when,
        last_seen=when,
    )


@dataclass
class WiFiInterface:
    """Passive WiFi interface wrapper. Calls `iw dev <ifname> scan`."""
    ifname: str

    def scan(self) -> ScanResult:
        result = subprocess.run(
            ["iw", "dev", self.ifname, "scan"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return ScanResult(observations=[], scanned_at=iso_timestamp())
        observations = parse_iw_scan_output(result.stdout)
        return ScanResult(observations=observations, scanned_at=iso_timestamp())
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/unit/interfaces/test_wifi.py -v
```
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/interfaces/wifi.py tests/unit/interfaces/test_wifi.py
git commit -m "feat(interfaces): WiFiInterface + iw scan output parser

Pure-function parser testable offline via captured iw output.
WiFiInterface.scan() invokes iw and feeds output to parser.
Classifies security type from RSN auth suites (PSK→WPA2, SAE→WPA3,
Privacy-no-RSN→WPA2, no-Privacy→open).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 1.3: Bluetooth + BLE stubs

**Files:**
- Create: `mjolnir/interfaces/bluetooth.py`
- Create: `mjolnir/interfaces/ble.py`
- Test: `tests/unit/interfaces/test_stubs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/interfaces/test_stubs.py
import pytest
from mjolnir.interfaces.bluetooth import BluetoothInterface
from mjolnir.interfaces.ble import BLEInterface


def test_bluetooth_interface_exists():
    iface = BluetoothInterface(adapter="hci0")
    assert iface.adapter == "hci0"


def test_bluetooth_interface_scan_raises_not_implemented():
    iface = BluetoothInterface(adapter="hci0")
    with pytest.raises(NotImplementedError):
        iface.scan()


def test_ble_interface_exists():
    iface = BLEInterface(adapter="hci0")
    assert iface.adapter == "hci0"


def test_ble_interface_scan_raises_not_implemented():
    iface = BLEInterface(adapter="hci0")
    with pytest.raises(NotImplementedError):
        iface.scan()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/interfaces/test_stubs.py -v
```

- [ ] **Step 3: Write `mjolnir/interfaces/bluetooth.py`**

```python
"""BluetoothInterface: stub for sub-project #1 (BT tether)."""
from dataclasses import dataclass


@dataclass
class BluetoothInterface:
    """Placeholder. Methods raise NotImplementedError until sub-project #1."""
    adapter: str = "hci0"

    def scan(self):
        raise NotImplementedError("BluetoothInterface not implemented until sub-project #1")
```

- [ ] **Step 4: Write `mjolnir/interfaces/ble.py`**

```python
"""BLEInterface: stub for future BLE recon/attack work."""
from dataclasses import dataclass


@dataclass
class BLEInterface:
    """Placeholder. Methods raise NotImplementedError."""
    adapter: str = "hci0"

    def scan(self):
        raise NotImplementedError("BLEInterface not implemented")
```

- [ ] **Step 5: Run to verify pass**

```bash
pytest tests/unit/interfaces/test_stubs.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/interfaces/bluetooth.py mjolnir/interfaces/ble.py tests/unit/interfaces/test_stubs.py
git commit -m "feat(interfaces): Bluetooth + BLE stubs

Sub-project #1 fills in BluetoothInterface (BT tether). Future
sub-project adds BLEInterface. Stubs make InterfaceManager's
interface surface complete from day one.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 1.4: InterfaceManager

**Files:**
- Create: `mjolnir/interfaces/manager.py`
- Test: `tests/unit/interfaces/test_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/interfaces/test_manager.py
import pytest
from mjolnir.interfaces.manager import InterfaceManager
from mjolnir.interfaces.wifi import WiFiInterface
from mjolnir.interfaces.bluetooth import BluetoothInterface
from mjolnir.interfaces.ble import BLEInterface


def test_interface_manager_constructs_default_interfaces():
    mgr = InterfaceManager()
    assert isinstance(mgr.wifi, WiFiInterface)
    assert isinstance(mgr.bluetooth, BluetoothInterface)
    assert isinstance(mgr.ble, BLEInterface)


def test_interface_manager_wifi_ifname_configurable():
    mgr = InterfaceManager(wifi_ifname="wlan1")
    assert mgr.wifi.ifname == "wlan1"


def test_interface_manager_halt_all_transmissions_noop_when_idle():
    """No active transmissions → halt is a no-op."""
    mgr = InterfaceManager()
    mgr.halt_all_transmissions()  # must not raise


def test_interface_manager_halt_all_transmissions_calls_wifi_halt(monkeypatch):
    """When WiFi is transmitting, halt propagates."""
    mgr = InterfaceManager()
    called = {"halted": False}

    def fake_halt(self):
        called["halted"] = True

    monkeypatch.setattr(WiFiInterface, "halt_transmissions", fake_halt, raising=False)
    mgr.wifi._transmitting = True  # set internal flag if implementation needs it
    mgr.halt_all_transmissions()
    # Manager should call wifi.halt_transmissions() unconditionally (safe no-op)
    assert called["halted"]


def test_interface_manager_wifi_property_returns_same_instance():
    mgr = InterfaceManager()
    w1 = mgr.wifi
    w2 = mgr.wifi
    assert w1 is w2
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/interfaces/test_manager.py -v
```

- [ ] **Step 3: Write `mjolnir/interfaces/manager.py`**

```python
"""InterfaceManager: single entry point for all hardware access.

Stages acquire interfaces through NetworkContext.interfaces. The kill
switch path calls halt_all_transmissions() which propagates to every
interface that may be transmitting.
"""
from dataclasses import dataclass

from mjolnir.interfaces.ble import BLEInterface
from mjolnir.interfaces.bluetooth import BluetoothInterface
from mjolnir.interfaces.wifi import WiFiInterface


@dataclass
class InterfaceManager:
    """Owns all hardware interfaces. Constructed once at startup."""
    wifi_ifname: str = "wlan0"
    bt_adapter: str = "hci0"
    ble_adapter: str = "hci0"
    _wifi: WiFiInterface | None = None
    _bluetooth: BluetoothInterface | None = None
    _ble: BLEInterface | None = None

    @property
    def wifi(self) -> WiFiInterface:
        if self._wifi is None:
            self._wifi = WiFiInterface(ifname=self.wifi_ifname)
        return self._wifi

    @property
    def bluetooth(self) -> BluetoothInterface:
        if self._bluetooth is None:
            self._bluetooth = BluetoothInterface(adapter=self.bt_adapter)
        return self._bluetooth

    @property
    def ble(self) -> BLEInterface:
        if self._ble is None:
            self._ble = BLEInterface(adapter=self.ble_adapter)
        return self._ble

    def halt_all_transmissions(self) -> None:
        """Kill-switch path. Propagates to every interface that supports halting.

        Each interface's halt_transmissions() must be safe to call when no
        transmission is in progress (no-op).
        """
        for iface in (self.wifi, self.bluetooth, self.ble):
            halt = getattr(iface, "halt_transmissions", None)
            if halt is not None:
                halt()
```

- [ ] **Step 4: Add `halt_transmissions` no-op to WiFiInterface**

Edit `mjolnir/interfaces/wifi.py` and add this method to the `WiFiInterface` dataclass:

```python
    def halt_transmissions(self) -> None:
        """Kill-switch hook. Passive scan mode has no transmissions to halt;
        future monitor-mode work (deauth, evil AP) will override."""
        return
```

- [ ] **Step 5: Run to verify pass**

```bash
pytest tests/unit/interfaces/test_manager.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/interfaces/manager.py mjolnir/interfaces/wifi.py tests/unit/interfaces/test_manager.py
git commit -m "feat(interfaces): InterfaceManager

Single entry point for hardware access. Lazy-constructs WiFi/BT/BLE
interfaces. halt_all_transmissions() is the kill-switch propagation
path; each interface must make halt_transmissions() a safe no-op
when idle.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 2: ESS identity resolver (union-find over BSSID overlaps)

### Task 2.1: IdentityResolver

**Files:**
- Create: `mjolnir/nlm/__init__.py`
- Create: `mjolnir/nlm/identity.py`
- Test: `tests/unit/nlm/test_identity.py`

The identity resolver decides: when a new scan observation comes in with SSID `X` and BSSID set `S`, which existing `networks` row (if any) should we attach it to? Rule: any existing network with the same SSID AND non-empty BSSID set intersection.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/nlm/test_identity.py
import pytest
from mjolnir.nlm.identity import IdentityResolver, Resolution


@pytest.fixture
def resolver():
    return IdentityResolver()


def test_resolve_with_no_existing_networks_creates_new(resolver):
    """No prior networks with this SSID → must create a new one."""
    res = resolver.resolve(ssid="X", observed_bssids={"AA:BB:CC:DD:EE:01"},
                            existing_networks=[])
    assert res.action == "create_new"
    assert res.target_network_id is None


def test_resolve_with_overlapping_bssid_merges(resolver):
    """SSID matches an existing network AND BSSID sets overlap → extend it."""
    existing = [
        {"id": 1, "ssid": "X", "bssids": {"AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"}},
    ]
    res = resolver.resolve(ssid="X",
                            observed_bssids={"AA:BB:CC:DD:EE:02", "AA:BB:CC:DD:EE:03"},
                            existing_networks=existing)
    assert res.action == "extend"
    assert res.target_network_id == 1


def test_resolve_with_no_overlap_creates_new_disambiguator(resolver):
    """SSID matches but BSSID sets disjoint → new network with bumped disambiguator."""
    existing = [
        {"id": 1, "ssid": "X", "bssids": {"AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"}},
    ]
    res = resolver.resolve(ssid="X",
                            observed_bssids={"FF:FF:FF:FF:FF:01", "FF:FF:FF:FF:FF:02"},
                            existing_networks=existing)
    assert res.action == "create_new"
    assert res.target_network_id is None


def test_resolve_picks_max_overlap_when_multiple_match(resolver):
    """If multiple existing networks share the SSID, pick the one with most overlap."""
    existing = [
        {"id": 1, "ssid": "X", "bssids": {"AA:BB:CC:DD:EE:01"}},
        {"id": 2, "ssid": "X", "bssids": {"AA:BB:CC:DD:EE:02", "AA:BB:CC:DD:EE:03", "AA:BB:CC:DD:EE:04"}},
    ]
    res = resolver.resolve(ssid="X",
                            observed_bssids={"AA:BB:CC:DD:EE:03", "AA:BB:CC:DD:EE:04", "AA:BB:CC:DD:EE:05"},
                            existing_networks=existing)
    assert res.action == "extend"
    assert res.target_network_id == 2  # max overlap (2) > network 1's overlap (0)


def test_resolve_with_empty_observed_bssids_creates_new(resolver):
    """No observed BSSIDs is degenerate; create_new to be safe."""
    res = resolver.resolve(ssid="X", observed_bssids=set(),
                            existing_networks=[])
    assert res.action == "create_new"


def test_resolve_ignores_networks_with_different_ssid(resolver):
    """Different SSIDs never merge, even with BSSID overlap (which would be unusual)."""
    existing = [
        {"id": 1, "ssid": "Y", "bssids": {"AA:BB:CC:DD:EE:01"}},
    ]
    res = resolver.resolve(ssid="X",
                            observed_bssids={"AA:BB:CC:DD:EE:01"},
                            existing_networks=existing)
    assert res.action == "create_new"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/nlm/test_identity.py -v
```

- [ ] **Step 3: Write `mjolnir/nlm/__init__.py`**

```python
"""Network Lifecycle Manager."""
```

- [ ] **Step 4: Write `mjolnir/nlm/identity.py`**

```python
"""ESS identity resolver: BSSID-overlap union-find.

When the device sees SSID X with BSSID set S, decide which existing
networks row to attach to (extend) or whether to create a new one.

Rule: any existing network with same SSID AND non-empty BSSID set
intersection gets considered. Pick the one with maximum intersection
size. If no overlap exists, create a new network with bumped disambiguator.
"""
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Resolution:
    action: Literal["create_new", "extend"]
    target_network_id: int | None  # only set when action == "extend"


class IdentityResolver:
    """Pure-logic resolver. No DB access — callers pass in the existing networks."""

    def resolve(
        self,
        ssid: str,
        observed_bssids: set[str],
        existing_networks: list[dict[str, Any]],
    ) -> Resolution:
        if not observed_bssids:
            return Resolution(action="create_new", target_network_id=None)

        candidates: list[tuple[int, int]] = []  # (network_id, overlap_size)
        for net in existing_networks:
            if net["ssid"] != ssid:
                continue
            overlap = len(observed_bssids & net["bssids"])
            if overlap > 0:
                candidates.append((net["id"], overlap))

        if not candidates:
            return Resolution(action="create_new", target_network_id=None)

        # Pick max overlap; tie-break by lowest network_id for determinism
        candidates.sort(key=lambda x: (-x[1], x[0]))
        target_id = candidates[0][0]
        return Resolution(action="extend", target_network_id=target_id)
```

- [ ] **Step 5: Run to verify pass**

```bash
pytest tests/unit/nlm/test_identity.py -v
```
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/nlm/__init__.py mjolnir/nlm/identity.py tests/unit/nlm/test_identity.py
git commit -m "feat(nlm): ESS identity resolver (BSSID-overlap union-find)

Pure-logic resolver: given an observed SSID+BSSID set and a list of
existing same-SSID networks, returns create_new or extend. Picks
maximum-overlap candidate on ties. Deterministic via network_id
tie-break.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 3: Scope enforcement

### Task 3.1: ScopeChecker

**Files:**
- Create: `mjolnir/nlm/scope.py`
- Test: `tests/unit/nlm/test_scope.py`

The scope checker answers: "given the current global mode, kill switch state, network scope_state, and (for persistence) the two-tier authorization flags, is this stage allowed to run on this network?"

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/nlm/test_scope.py
import pytest
from mjolnir.nlm.scope import ScopeChecker, ScopeDecision
from mjolnir.db.repositories.networks import Network


def _make_net(**overrides) -> Network:
    defaults = dict(
        id=1, ssid="X", disambiguator=1, security_type="WPA2",
        scope_state="enabled", blocklist_reason=None,
        scope_changed_at=None, scope_changed_by=None,
        current_stage=None, exhausted=0, exhausted_reason=None,
        persistence_authorized=0, persistence_authorized_at=None,
        persistence_authorized_by=None, operator_notes_summary=None,
        ess_color_tag=None, first_seen="2026-06-23T00:00:00Z", last_seen=None,
    )
    defaults.update(overrides)
    return Network(**defaults)


def test_view_only_mode_blocks_active_stage():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="view_only",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "view_only" in decision.reason


def test_view_only_mode_allows_view_only_stage():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="view_only",
        kill_switch_engaged=False,
        stage_operates_in_view_only=True,
        stage_requires_extra_auth=False,
        network=_make_net(),
        host_persistence_authorized=None,
    )
    assert decision.allowed is True


def test_kill_switch_blocks_everything():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=True,
        stage_operates_in_view_only=True,
        stage_requires_extra_auth=False,
        network=_make_net(),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "kill_switch" in decision.reason


def test_blocklisted_network_blocks_active_stages():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(scope_state="blocklisted"),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "blocklisted" in decision.reason


def test_disabled_network_blocks_active_stages():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(scope_state="disabled"),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "disabled" in decision.reason


def test_persistence_stage_requires_network_authorization():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=True,
        network=_make_net(persistence_authorized=0),
        host_persistence_authorized=True,
    )
    assert decision.allowed is False
    assert "network-level persistence" in decision.reason


def test_persistence_stage_requires_host_authorization():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=True,
        network=_make_net(persistence_authorized=1),
        host_persistence_authorized=False,
    )
    assert decision.allowed is False
    assert "host-level persistence" in decision.reason


def test_persistence_stage_allowed_when_both_tiers_authorized():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=True,
        network=_make_net(persistence_authorized=1),
        host_persistence_authorized=True,
    )
    assert decision.allowed is True


def test_normal_active_stage_allowed_happy_path():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(scope_state="enabled"),
        host_persistence_authorized=None,
    )
    assert decision.allowed is True


def test_exhausted_network_blocks_all_stages():
    checker = ScopeChecker()
    decision = checker.check(
        global_mode="active",
        kill_switch_engaged=False,
        stage_operates_in_view_only=False,
        stage_requires_extra_auth=False,
        network=_make_net(exhausted=1),
        host_persistence_authorized=None,
    )
    assert decision.allowed is False
    assert "exhausted" in decision.reason
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/nlm/test_scope.py -v
```

- [ ] **Step 3: Write `mjolnir/nlm/scope.py`**

```python
"""ScopeChecker: enforces mode + blocklist + authorization gates.

Stages call this (via the executor wrapper) before doing any work.
The NLM also consults it during scheduling to skip ineligible work.
"""
from dataclasses import dataclass
from typing import Literal

from mjolnir.db.repositories.networks import Network


@dataclass(frozen=True)
class ScopeDecision:
    allowed: bool
    reason: str


class ScopeChecker:
    """Pure logic. No I/O. Tests cover every gate."""

    def check(
        self,
        global_mode: str,
        kill_switch_engaged: bool,
        stage_operates_in_view_only: bool,
        stage_requires_extra_auth: bool,
        network: Network,
        host_persistence_authorized: bool | None,
    ) -> ScopeDecision:
        if kill_switch_engaged:
            return ScopeDecision(False, "kill_switch_engaged")

        if global_mode == "view_only" and not stage_operates_in_view_only:
            return ScopeDecision(False, "view_only_mode_blocks_active_stage")

        if network.exhausted:
            return ScopeDecision(False, "network_exhausted")

        if network.scope_state == "blocklisted":
            return ScopeDecision(False, "network_blocklisted")

        if network.scope_state == "disabled":
            return ScopeDecision(False, "network_disabled")

        if stage_requires_extra_auth:
            if not network.persistence_authorized:
                return ScopeDecision(False, "missing_network-level_persistence_authorization")
            if not host_persistence_authorized:
                return ScopeDecision(False, "missing_host-level_persistence_authorization")

        return ScopeDecision(True, "allowed")
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/unit/nlm/test_scope.py -v
```
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/nlm/scope.py tests/unit/nlm/test_scope.py
git commit -m "feat(nlm): ScopeChecker (mode + blocklist + persistence gates)

Pure-logic gate evaluation. Order: kill_switch > view_only mode >
exhausted > blocklisted > disabled > persistence_auth (two-tier).
Returns ScopeDecision(allowed, reason) — reason is human-readable
for audit logging.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4: Data-availability gates

### Task 4.1: GateEvaluator

**Files:**
- Create: `mjolnir/nlm/gates.py`
- Test: `tests/unit/nlm/test_gates.py`

This module answers: "given the current DB state for this network, does stage X have its data prerequisites met?" The gates are the spec's data-availability requirements (e.g., `credential_attack` requires ≥1 service in cred-attack portlist).

For Plan 2a, we only have stub implementations of gates for the stages we know about. The framework is extensible.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/nlm/test_gates.py
import pytest
from mjolnir.nlm.gates import GateEvaluator, GateResult
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def evaluator_and_bundle(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    return GateEvaluator(bundle), bundle


def test_passive_scan_gate_always_satisfied(evaluator_and_bundle):
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X")
    result = evaluator.evaluate(stage_name="passive_scan", network_id=net.id)
    assert result.satisfied is True


def test_unknown_stage_gate_fails_open_with_warning(evaluator_and_bundle):
    """Stages we don't know about get an 'unknown_stage' result — fail-open
    is wrong, fail-closed is safer."""
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X")
    result = evaluator.evaluate(stage_name="nonexistent_stage", network_id=net.id)
    assert result.satisfied is False
    assert "unknown" in result.reason.lower()


def test_wifi_probe_gate_requires_recent_last_seen(evaluator_and_bundle):
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X")
    # Network was just created so last_seen is recent — gate satisfied
    result = evaluator.evaluate(stage_name="wifi_probe", network_id=net.id)
    assert result.satisfied is True


def test_wifi_probe_gate_fails_when_stale(evaluator_and_bundle):
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X")
    # Set last_seen to 1 hour ago
    bundle.networks.update_last_seen(net.id, "2020-01-01T00:00:00Z")
    result = evaluator.evaluate(stage_name="wifi_probe", network_id=net.id)
    assert result.satisfied is False
    assert "stale" in result.reason.lower()


def test_wifi_crack_gate_skipped_when_open(evaluator_and_bundle):
    """Open networks don't need cracking."""
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="OpenNet", security_type="open")
    result = evaluator.evaluate(stage_name="wifi_crack", network_id=net.id)
    assert result.satisfied is False
    assert "open" in result.reason.lower()


def test_wifi_crack_gate_skipped_when_already_cracked(evaluator_and_bundle):
    """If we already have a wifi_psk credential for this network, no need to crack."""
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X", security_type="WPA2")
    bundle.action_log.conn.execute(
        "INSERT INTO credentials (network_id, cred_type, secret, discovered_at) VALUES (?, ?, ?, ?)",
        (net.id, "wifi_psk", "somepassword", "2026-06-23T00:00:00Z"),
    )
    result = evaluator.evaluate(stage_name="wifi_crack", network_id=net.id)
    assert result.satisfied is False
    assert "already" in result.reason.lower()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/nlm/test_gates.py -v
```

- [ ] **Step 3: Write `mjolnir/nlm/gates.py`**

```python
"""Data-availability gates for stage scheduling.

Each stage has prerequisites expressed as DB queries. The GateEvaluator
runs the relevant query for a given (stage_name, network_id) and returns
whether the stage is runnable now.

Stages not in the registry return GateResult(satisfied=False, reason='unknown_stage')
— fail-closed is safer than fail-open.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from mjolnir.db.repositories import RepositoryBundle
from mjolnir.utils import iso_timestamp

_STALE_THRESHOLD = timedelta(minutes=5)


@dataclass(frozen=True)
class GateResult:
    satisfied: bool
    reason: str


class GateEvaluator:
    """Evaluates stage-specific data-availability gates against current DB state."""

    def __init__(self, bundle: RepositoryBundle):
        self.bundle = bundle

    def evaluate(self, stage_name: str, network_id: int) -> GateResult:
        method = getattr(self, f"_gate_{stage_name}", None)
        if method is None:
            return GateResult(False, f"unknown_stage:{stage_name}")
        return method(network_id)

    def _gate_passive_scan(self, network_id: int) -> GateResult:
        return GateResult(True, "always_runnable")

    def _gate_wifi_probe(self, network_id: int) -> GateResult:
        net = self.bundle.networks.get_by_id(network_id)
        if net is None or net.last_seen is None:
            return GateResult(True, "never_seen_no_stale_check")
        try:
            last = datetime.fromisoformat(net.last_seen.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return GateResult(True, "unparseable_last_seen_no_stale_check")
        now = datetime.now(timezone.utc)
        if now - last > _STALE_THRESHOLD:
            return GateResult(False, f"stale_last_seen:{net.last_seen}")
        return GateResult(True, "recently_seen")

    def _gate_wifi_crack(self, network_id: int) -> GateResult:
        net = self.bundle.networks.get_by_id(network_id)
        if net is None:
            return GateResult(False, "network_not_found")
        if net.security_type == "open":
            return GateResult(False, "open_network_no_crack_needed")
        cursor = self.bundle.action_log.conn.execute(
            "SELECT COUNT(*) FROM credentials WHERE network_id = ? AND cred_type = 'wifi_psk'",
            (network_id,),
        )
        if cursor.fetchone()[0] > 0:
            return GateResult(False, "already_cracked")
        return GateResult(True, "encrypted_no_existing_psk")
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/unit/nlm/test_gates.py -v
```
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/nlm/gates.py tests/unit/nlm/test_gates.py
git commit -m "feat(nlm): GateEvaluator (data-availability gates)

Per-stage prerequisites expressed as DB queries. passive_scan always
runnable; wifi_probe checks last_seen freshness; wifi_crack checks
for existing wifi_psk credential or open security type. Unknown
stages fail-closed (safer than fail-open).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 5: Stage executor (subprocess-per-stage)

### Task 5.1: Subprocess entry point + Checkpoint IPC

**Files:**
- Create: `mjolnir/nlm/runner.py`
- Test: `tests/unit/nlm/test_runner.py`

The subprocess entry point is the function called inside the child process. It receives a serialized NetworkContext (or constructs one from a network_id + DB path), runs the stage, and sends the result back via a multiprocessing Pipe.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/nlm/test_runner.py
"""Tests for the subprocess entry point. We don't actually fork — we call
the runner function directly with a fake pipe and verify it does the
right thing."""
import json
import pytest
from mjolnir.nlm.runner import run_stage_in_subprocess
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy


class FakeStage(Stage):
    name = "fake_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        return StageResult(status="succeeded", outputs={"hello": "world"})


class FailingStage(Stage):
    name = "failing_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        raise RuntimeError("boom")


class CancelledStage(Stage):
    name = "cancelled_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        # Poll checkpoint a few times then exit when cancelled
        for _ in range(100):
            if checkpoint.is_cancelled():
                return StageResult(status="failed", error="killed_by_operator")
        return StageResult(status="succeeded")


class FakePipe:
    """Two-ended pipe for testing."""
    def __init__(self):
        self.sent = []
        self.cancel_received = False

    def send(self, msg):
        self.sent.append(msg)

    def poll(self):
        return False  # never receives cancel in default test

    def recv(self):
        return None


def test_runner_executes_stage_and_sends_result(tmp_path):
    """Register a fake stage, call runner, verify result was sent."""
    from mjolnir.stages.registry import StageRegistry
    reg = StageRegistry()
    reg.register(FakeStage)

    pipe = FakePipe()
    # The runner imports the registry; for test we monkey-patch
    import mjolnir.nlm.runner as runner_mod
    original_reg = runner_mod.registry
    runner_mod.registry = reg
    try:
        run_stage_in_subprocess(
            stage_name="fake_test_stage",
            network_id=1,
            db_path=str(tmp_path / "x.db"),
            config_dict={},
            mem_limit_mb=25,
            pipe=pipe,
        )
    finally:
        runner_mod.registry = original_reg

    assert len(pipe.sent) == 1
    result_msg = pipe.sent[0]
    assert result_msg["type"] == "result"
    assert result_msg["status"] == "succeeded"
    assert result_msg["outputs"] == {"hello": "world"}


def test_runner_sends_error_on_stage_exception(tmp_path):
    from mjolnir.stages.registry import StageRegistry
    reg = StageRegistry()
    reg.register(FailingStage)

    pipe = FakePipe()
    import mjolnir.nlm.runner as runner_mod
    original_reg = runner_mod.registry
    runner_mod.registry = reg
    try:
        run_stage_in_subprocess(
            stage_name="failing_test_stage",
            network_id=1,
            db_path=str(tmp_path / "x.db"),
            config_dict={},
            mem_limit_mb=25,
            pipe=pipe,
        )
    finally:
        runner_mod.registry = original_reg

    assert len(pipe.sent) == 1
    result_msg = pipe.sent[0]
    assert result_msg["type"] == "error"
    assert "boom" in result_msg["error"]


def test_runner_unknown_stage_sends_error(tmp_path):
    pipe = FakePipe()
    run_stage_in_subprocess(
        stage_name="nonexistent",
        network_id=1,
        db_path=str(tmp_path / "x.db"),
        config_dict={},
        mem_limit_mb=25,
        pipe=pipe,
    )
    assert len(pipe.sent) == 1
    assert pipe.sent[0]["type"] == "error"
    assert "not found" in pipe.sent[0]["error"]


def test_runner_sets_memory_limit(tmp_path, monkeypatch):
    """Verify RLIMIT_AS is called in the subprocess entry."""
    import resource
    called = {"limits": None}

    def fake_setrlimit(resource_id, limits):
        called["limits"] = (resource_id, limits)

    monkeypatch.setattr("mjolnir.nlm.runner.resource.setrlimit", fake_setrlimit)

    from mjolnir.stages.registry import StageRegistry
    reg = StageRegistry()
    reg.register(FakeStage)

    pipe = FakePipe()
    import mjolnir.nlm.runner as runner_mod
    original_reg = runner_mod.registry
    runner_mod.registry = reg
    try:
        run_stage_in_subprocess(
            stage_name="fake_test_stage",
            network_id=1,
            db_path=str(tmp_path / "x.db"),
            config_dict={},
            mem_limit_mb=25,
            pipe=pipe,
        )
    finally:
        runner_mod.registry = original_reg

    # RLIMIT_AS should have been set to 25MB
    assert called["limits"] is not None
    assert called["limits"][0] == resource.RLIMIT_AS
    assert called["limits"][1][0] == 25 * 1024 * 1024
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/nlm/test_runner.py -v
```

- [ ] **Step 3: Write `mjolnir/nlm/runner.py`**

```python
"""Subprocess entry point for stage execution.

Called by multiprocessing.Process in executor.py. Sets RLIMIT_AS for
memory isolation, constructs NetworkContext, runs the stage, sends
result back via pipe.
"""
import resource
import sqlite3
from pathlib import Path
from typing import Any

from mjolnir.audit.logger import AuditLogger
from mjolnir.config import BjornConfig, load_config
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.interfaces.manager import InterfaceManager
from mjolnir.stages.base import Checkpoint, NetworkContext
from mjolnir.stages.registry import registry


def run_stage_in_subprocess(
    stage_name: str,
    network_id: int,
    db_path: str,
    config_dict: dict[str, Any],
    mem_limit_mb: int,
    pipe: Any,
) -> None:
    """Entry point called in the child process.

    `pipe` is the child end of a multiprocessing.Pipe. We send:
      {"type": "result", "status": ..., "outputs": ..., "error": ...}
    or:
      {"type": "error", "error": "<message>"}
    """
    # Enforce memory limit
    mem_bytes = mem_limit_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

    # Look up stage class
    stage_cls = registry.get(stage_name)
    if stage_cls is None:
        pipe.send({"type": "error", "error": f"stage not found: {stage_name}"})
        return

    try:
        # Open DB connection (per-subprocess; do NOT share with parent)
        factory = ConnectionFactory(db_path=Path(db_path))
        conn = factory.connect()
        MigrationRunner(conn).initialize_fresh_db()
        bundle = bundle_for(conn)

        network = bundle.networks.get_by_id(network_id)
        if network is None:
            pipe.send({"type": "error", "error": f"network not found: {network_id}"})
            return

        # Construct context
        audit = AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)
        interfaces = InterfaceManager()
        checkpoint = Checkpoint()
        ctx = NetworkContext(
            network=network,
            db=bundle,
            config=BjornConfig(),  # default; could deserialize from config_dict
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

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/unit/nlm/test_runner.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/nlm/runner.py tests/unit/nlm/test_runner.py
git commit -m "feat(nlm): subprocess entry point for stage execution

run_stage_in_subprocess() enforces RLIMIT_AS, opens a per-subprocess
DB connection, looks up the stage from the registry, builds
NetworkContext, runs the stage, sends result back via multiprocessing
Pipe. Catches all exceptions and sends them as error messages so a
crash in a stage can't bring down the NLM.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 5.2: StageExecutor

**Files:**
- Create: `mjolnir/nlm/executor.py`
- Test: `tests/unit/nlm/test_executor.py`

The executor is the parent-side wrapper. It spawns the subprocess, monitors it, handles cancellation, and returns a `StageResult` to the caller. This is the NLM's only path to running stages.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/nlm/test_executor.py
"""Tests for StageExecutor. We use a real subprocess but with stub stages
registered in a test-only registry to verify the executor protocol."""
import time
import pytest
import multiprocessing as mp

from mjolnir.nlm.executor import StageExecutor, ExecutionResult
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner


class SucceedImmediatelyStage(Stage):
    name = "succeed_immediately_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        return StageResult(status="succeeded", outputs={"marker": "yes"})


class SlowStage(Stage):
    name = "slow_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        for _ in range(100):
            if checkpoint.is_cancelled():
                return StageResult(status="failed", error="killed_by_operator")
            time.sleep(0.05)
        return StageResult(status="succeeded")


@pytest.fixture
def executor_with_db(tmp_path, monkeypatch):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    # Create a network for tests to reference
    from mjolnir.db.repositories import bundle_for
    bundle = bundle_for(conn)
    net = bundle.networks.create(ssid="TestNet")
    network_id = net.id
    conn.close()

    # Build a test registry
    reg = StageRegistry()
    reg.register(SucceedImmediatelyStage)
    reg.register(SlowStage)

    # Patch the runner module to use our test registry
    import mjolnir.nlm.runner as runner_mod
    monkeypatch.setattr(runner_mod, "registry", reg)

    executor = StageExecutor(
        db_path=tmp_path / "x.db",
        mem_limit_mb=50,
        kill_switch_event=mp.Event(),
    )
    return executor, network_id


def test_executor_returns_success_on_clean_run(executor_with_db):
    executor, network_id = executor_with_db
    result = executor.execute(
        stage_name="succeed_immediately_test_stage",
        network_id=network_id,
        timeout_seconds=10,
    )
    assert isinstance(result, ExecutionResult)
    assert result.status == "succeeded"
    assert result.outputs == {"marker": "yes"}
    assert result.error is None


def test_executor_returns_failed_on_cancellation(executor_with_db):
    executor, network_id = executor_with_db
    # Trigger kill switch after 0.2s
    import threading
    def trigger():
        time.sleep(0.2)
        executor.kill_switch_event.set()
    threading.Thread(target=trigger, daemon=True).start()

    result = executor.execute(
        stage_name="slow_test_stage",
        network_id=network_id,
        timeout_seconds=10,
    )
    assert result.status == "failed"
    assert "killed" in (result.error or "").lower()


def test_executor_returns_failed_on_timeout(executor_with_db):
    executor, network_id = executor_with_db
    result = executor.execute(
        stage_name="slow_test_stage",
        network_id=network_id,
        timeout_seconds=1,  # shorter than the stage takes
    )
    assert result.status == "failed"
    assert "timeout" in (result.error or "").lower()


def test_executor_returns_error_on_unknown_stage(executor_with_db):
    executor, network_id = executor_with_db
    result = executor.execute(
        stage_name="nonexistent_stage",
        network_id=network_id,
        timeout_seconds=5,
    )
    assert result.status == "failed"
    assert "not found" in (result.error or "").lower()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/nlm/test_executor.py -v
```

- [ ] **Step 3: Write `mjolnir/nlm/executor.py`**

```python
"""StageExecutor: parent-side wrapper that runs stages in subprocesses.

Spawns a child process via multiprocessing.Process, sends result back
via Pipe, handles timeout and kill-switch cancellation.

The NLM's only path to running stages. Stages cannot bypass audit logging
because the NLM wraps every execute() call with log writes.
"""
import multiprocessing as mp
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from mjolnir.nlm.runner import run_stage_in_subprocess


@dataclass
class ExecutionResult:
    status: Literal["succeeded", "failed", "permanently_failed", "partial"]
    error: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)


class StageExecutor:
    """Runs stages in isolated subprocesses."""

    def __init__(self, db_path: Path, mem_limit_mb: int, kill_switch_event: Any):
        self.db_path = Path(db_path)
        self.mem_limit_mb = mem_limit_mb
        self.kill_switch_event = kill_switch_event

    def execute(
        self,
        stage_name: str,
        network_id: int,
        timeout_seconds: int,
    ) -> ExecutionResult:
        parent_conn, child_conn = mp.Pipe(duplex=False)
        proc = mp.Process(
            target=run_stage_in_subprocess,
            args=(
                stage_name,
                network_id,
                str(self.db_path),
                {},  # config_dict — empty for now
                self.mem_limit_mb,
                child_conn,
            ),
        )
        proc.start()
        child_conn.close()  # parent doesn't need the child end

        # Spawn a watcher thread to handle kill-switch activation
        cancel_sent = {"value": False}

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

        watcher = threading.Thread(target=watch_kill_switch, daemon=True)
        watcher.start()

        # Wait for completion, timeout, or kill switch
        deadline = time.monotonic() + timeout_seconds
        timed_out = False
        result_msg: dict[str, Any] | None = None

        while True:
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
                break

            if not proc.is_alive() and not parent_conn.poll(0):
                # Process exited without sending result
                result_msg = {"type": "error", "error": f"subprocess_exited_code_{proc.exitcode}"}
                break

        if timed_out:
            return ExecutionResult(status="failed", error=f"timeout_after_{timeout_seconds}s")
        if result_msg is None:
            return ExecutionResult(status="failed", error="no_result_received")

        if result_msg.get("type") == "error":
            return ExecutionResult(status="failed", error=result_msg.get("error", "unknown_error"))

        return ExecutionResult(
            status=result_msg.get("status", "failed"),
            error=result_msg.get("error"),
            outputs=result_msg.get("outputs", {}),
        )
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/unit/nlm/test_executor.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/nlm/executor.py tests/unit/nlm/test_executor.py
git commit -m "feat(nlm): StageExecutor (subprocess-per-stage + cancellation)

Parent-side wrapper. Spawns child via multiprocessing.Process, sends
result via Pipe. Watches kill_switch_event in a background thread;
on activation sends cancel to child. Handles timeout via terminate
then kill. Returns ExecutionResult with status/error/outputs.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 6: NLM scheduler + main loop

### Task 6.1: NetworkLifecycleManager skeleton + scheduling

**Files:**
- Create: `mjolnir/nlm/manager.py`
- Test: `tests/unit/nlm/test_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/nlm/test_manager.py
"""Tests for the NLM main loop. Uses stub stages + the real DB layer."""
import pytest
import multiprocessing as mp

from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.nlm.executor import StageExecutor
from mjolnir.nlm.gates import GateEvaluator
from mjolnir.nlm.scope import ScopeChecker
from mjolnir.nlm.identity import IdentityResolver
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


class CountingStage(Stage):
    """Records each invocation via class-level counter."""
    name = "counting_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE
    operates_in_view_only = True

    invocations = 0

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        CountingStage.invocations += 1
        return StageResult(status="succeeded", outputs={"count": str(CountingStage.invocations)})


@pytest.fixture
def manager(tmp_path, monkeypatch):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    # Seed a network to give the manager something to work on
    bundle.networks.create(ssid="TestNet")
    conn.close()

    reg = StageRegistry()
    reg.register(CountingStage)
    CountingStage.invocations = 0

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path),
    )

    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=mp.Event(),
    )
    return mgr


def test_manager_constructs(manager):
    assert manager.registry is not None
    assert manager.scope_checker is not None
    assert manager.gate_evaluator is not None


def test_find_eligible_work_returns_pending_work(manager):
    """In view_only mode with a network present and a view-only stage,
    find_eligible_work returns at least one (network, stage) pair."""
    work = manager.find_eligible_work()
    assert len(work) >= 1
    network_ids = {n.id for n, _ in work}
    stage_names = {s.name for _, s in work}
    assert "counting_test_stage" in stage_names


def test_find_eligible_work_empty_when_no_networks(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()

    reg = StageRegistry()
    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path),
    )
    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=mp.Event(),
    )
    work = mgr.find_eligible_work()
    assert work == []


def test_find_eligible_work_filters_blocklisted(manager):
    # Blocklist the existing network
    from mjolnir.db.repositories import bundle_for
    factory = ConnectionFactory(db_path=manager.db_path)
    conn = factory.connect()
    bundle = bundle_for(conn)
    net = bundle.networks.list_eligible_for_processing()[0]
    bundle.networks.update_scope_state(net.id, "blocklisted", reason="test", by="op")
    conn.close()

    work = manager.find_eligible_work()
    # Even view-only stages shouldn't run on blocklisted networks
    assert work == []


def test_run_once_executes_eligible_work(manager):
    """Single pass of the main loop: find work, execute one stage."""
    manager.run_once()
    # The CountingStage should have been invoked
    assert CountingStage.invocations >= 1


def test_run_once_with_no_work_does_nothing(manager):
    """If no eligible work, run_once completes without invoking stages."""
    # Blocklist the network
    from mjolnir.db.repositories import bundle_for
    factory = ConnectionFactory(db_path=manager.db_path)
    conn = factory.connect()
    bundle = bundle_for(conn)
    net = bundle.networks.list_eligible_for_processing()[0]
    bundle.networks.update_scope_state(net.id, "blocklisted", reason="test", by="op")
    conn.close()

    manager.run_once()
    assert CountingStage.invocations == 0


def test_kill_switch_prevents_new_work(manager):
    manager.kill_switch_event.set()
    work = manager.find_eligible_work()
    assert work == []
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/nlm/test_manager.py -v
```

- [ ] **Step 3: Write `mjolnir/nlm/manager.py`**

```python
"""NetworkLifecycleManager: the brain that schedules stage execution.

Main loop: find_eligible_work() -> execute() -> mark_exhausted. Kill-switch
and mode-toggled via system_state. Mode persisted across reboots.
"""
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mjolnir.config import BjornConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import RepositoryBundle, bundle_for
from mjolnir.nlm.executor import StageExecutor
from mjolnir.nlm.gates import GateEvaluator
from mjolnir.nlm.identity import IdentityResolver
from mjolnir.nlm.scope import ScopeChecker
from mjolnir.stages.base import Stage
from mjolnir.stages.registry import StageRegistry


@dataclass
class WorkItem:
    network_id: int
    stage_name: str


class NetworkLifecycleManager:
    """Schedules stage execution across all known networks."""

    def __init__(
        self,
        db_path: Path,
        config: BjornConfig,
        registry: StageRegistry,
        kill_switch_event: Any,
    ):
        self.db_path = Path(db_path)
        self.config = config
        self.registry = registry
        self.kill_switch_event = kill_switch_event
        self.scope_checker = ScopeChecker()
        self.identity_resolver = IdentityResolver()

    def _open_db(self) -> tuple[sqlite3.Connection, RepositoryBundle]:
        factory = ConnectionFactory(db_path=self.db_path)
        conn = factory.connect()
        return conn, bundle_for(conn)

    def find_eligible_work(self) -> list[tuple[Any, type[Stage]]]:
        """Find all (network, stage) pairs that can run right now."""
        if self.kill_switch_event.is_set():
            return []

        conn, bundle = self._open_db()
        try:
            global_mode = bundle.system_state.get_global_mode()
            eligible_stages = self.registry.stages_eligible_for_mode(global_mode)

            if not eligible_stages:
                return []

            gate_eval = GateEvaluator(bundle)
            networks = bundle.networks.list_eligible_for_processing()
            work: list[tuple[Any, type[Stage]]] = []

            for net in networks:
                for stage_cls in eligible_stages:
                    scope_decision = self.scope_checker.check(
                        global_mode=global_mode,
                        kill_switch_engaged=False,
                        stage_operates_in_view_only=stage_cls.operates_in_view_only,
                        stage_requires_extra_auth=stage_cls.requires_extra_auth,
                        network=net,
                        host_persistence_authorized=None,  # gate-level placeholder
                    )
                    if not scope_decision.allowed:
                        continue

                    gate_result = gate_eval.evaluate(stage_cls.name, net.id)
                    if not gate_result.satisfied:
                        continue

                    work.append((net, stage_cls))

            return work
        finally:
            conn.close()

    def run_once(self) -> int:
        """Single pass: find work, execute one item, return number executed."""
        work = self.find_eligible_work()
        if not work:
            return 0

        # Pick first item (could prioritize by signal strength, last_seen, etc.)
        net, stage_cls = work[0]

        executor = StageExecutor(
            db_path=self.db_path,
            mem_limit_mb=self.config.nlm.stage_memory_limit_mb,
            kill_switch_event=self.kill_switch_event,
        )

        # Mark stage as running
        conn, bundle = self._open_db()
        try:
            bundle.stage_states.mark_running(net.id, stage_cls.name)
            bundle.networks.set_current_stage(net.id, stage_cls.name)
        finally:
            conn.close()

        result = executor.execute(
            stage_name=stage_cls.name,
            network_id=net.id,
            timeout_seconds=stage_cls.resources.est_duration_seconds * 3,
        )

        # Update state based on result
        conn, bundle = self._open_db()
        try:
            if result.status == "succeeded":
                bundle.stage_states.mark_succeeded(net.id, stage_cls.name)
                if result.outputs:
                    bundle.stage_outputs.set_many(net.id, stage_cls.name, result.outputs)
            elif result.status == "permanently_failed":
                bundle.stage_states.mark_permanently_failed(net.id, stage_cls.name, result.error)
            else:
                bundle.stage_states.mark_failed(net.id, stage_cls.name, result.error)
            bundle.networks.set_current_stage(net.id, None)
        finally:
            conn.close()

        return 1
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/unit/nlm/test_manager.py -v
```
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/nlm/manager.py tests/unit/nlm/test_manager.py
git commit -m "feat(nlm): NetworkLifecycleManager main loop

Schedules stage execution across networks. find_eligible_work()
combines mode filter + scope checker + gate evaluator to produce
runnable (network, stage) pairs. run_once() picks the first item,
marks the stage running, executes via StageExecutor, updates state
based on result.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 7: Integration test (end-to-end with real subprocess)

### Task 7.1: NLM lifecycle integration test

**Files:**
- Test: `tests/integration/test_nlm_lifecycle.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_nlm_lifecycle.py
"""End-to-end: NLM runs a stub stage in a real subprocess, verifies DB updates."""
import multiprocessing as mp
from pathlib import Path

import pytest

from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.nlm.manager import NetworkLifecycleManager
from mjolnir.stages.base import Stage, StageResult, ResourceProfile, CheckpointPolicy
from mjolnir.stages.registry import StageRegistry


class RecordingStage(Stage):
    """Writes a marker output to stage_outputs so we can verify it ran."""
    name = "recording_integration_test_stage"
    description = "test"
    resources = ResourceProfile()
    checkpoint_policy = CheckpointPolicy.RESTART_SAFE
    operates_in_view_only = True

    def can_run(self, ctx):
        return True

    def run(self, ctx, checkpoint):
        return StageResult(
            status="succeeded",
            outputs={"ran_in_subprocess": "yes", "network_id": str(ctx.network.id)},
        )


def test_nlm_runs_stage_in_subprocess_and_persists_outputs(tmp_path: Path):
    # Setup DB with one network
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    net = bundle.networks.create(ssid="IntegrationNet")
    network_id = net.id
    conn.close()

    # Build NLM with our test stage
    reg = StageRegistry()
    reg.register(RecordingStage)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path),
    )
    kill_switch = mp.Event()
    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=kill_switch,
    )

    executed = mgr.run_once()
    assert executed == 1

    # Verify DB reflects the run
    conn = factory.connect()
    bundle = bundle_for(conn)

    state = bundle.stage_states.get_or_create(network_id, "recording_integration_test_stage")
    assert state.status == "succeeded"
    assert state.attempts == 1

    outputs = bundle.stage_outputs.list_for_stage(network_id, "recording_integration_test_stage")
    assert outputs["ran_in_subprocess"] == "yes"
    assert outputs["network_id"] == str(network_id)

    conn.close()


def test_nlm_mode_change_filters_eligible_stages(tmp_path: Path):
    """In view_only, only view_only stages are eligible."""
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    bundle.networks.create(ssid="X")
    conn.close()

    class ViewOnlyStage(Stage):
        name = "view_only_test_stage"
        resources = ResourceProfile()
        checkpoint_policy = CheckpointPolicy.RESTART_SAFE
        operates_in_view_only = True

        def can_run(self, ctx):
            return True

        def run(self, ctx, checkpoint):
            return StageResult(status="succeeded")

    class ActiveOnlyStage(Stage):
        name = "active_only_test_stage"
        resources = ResourceProfile()
        checkpoint_policy = CheckpointPolicy.RESTART_SAFE
        operates_in_view_only = False

        def can_run(self, ctx):
            return True

        def run(self, ctx, checkpoint):
            return StageResult(status="succeeded")

    reg = StageRegistry()
    reg.register(ViewOnlyStage)
    reg.register(ActiveOnlyStage)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path),
    )

    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=mp.Event(),
    )

    # Default mode is view_only
    work = mgr.find_eligible_work()
    stage_names = {s.name for _, s in work}
    assert "view_only_test_stage" in stage_names
    assert "active_only_test_stage" not in stage_names

    # Toggle to active
    conn = factory.connect()
    bundle = bundle_for(conn)
    bundle.system_state.set_global_mode("active")
    conn.close()

    work = mgr.find_eligible_work()
    stage_names = {s.name for _, s in work}
    assert "view_only_test_stage" in stage_names
    assert "active_only_test_stage" in stage_names


def test_nlm_kill_switch_blocks_all_work(tmp_path: Path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    bundle.networks.create(ssid="X")
    conn.close()

    reg = StageRegistry()

    class AlwaysRunStage(Stage):
        name = "always_run_test_stage"
        resources = ResourceProfile()
        checkpoint_policy = CheckpointPolicy.RESTART_SAFE
        operates_in_view_only = True

        def can_run(self, ctx):
            return True

        def run(self, ctx, checkpoint):
            return StageResult(status="succeeded")

    reg.register(AlwaysRunStage)

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path),
    )
    kill_switch = mp.Event()
    kill_switch.set()  # engaged

    mgr = NetworkLifecycleManager(
        db_path=tmp_path / "x.db",
        config=cfg,
        registry=reg,
        kill_switch_event=kill_switch,
    )

    assert mgr.find_eligible_work() == []
    assert mgr.run_once() == 0
```

- [ ] **Step 2: Run to verify pass**

```bash
pytest tests/integration/test_nlm_lifecycle.py -v
```
Expected: PASS (3 tests). Note: these spawn real subprocesses so will be slower (~1-2 seconds per test).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_nlm_lifecycle.py
git commit -m "test(integration): NLM lifecycle end-to-end with real subprocesses

Verifies:
- Stage runs in subprocess, outputs persist to DB
- Mode toggle (view_only/active) filters eligible stages correctly
- Kill switch activation blocks all work immediately

Integration tests use real multiprocessing.Process forks; slower
than unit tests but prove the subprocess-per-stage architecture
actually works end-to-end.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 8: Acceptance

### Task 8.1: Full test suite green + coverage check

- [ ] **Step 1: Run the entire test suite with coverage**

```bash
pytest tests/ -v --cov=mjolnir --cov-report=term-missing
```

Expected:
- All tests pass (~125 tests: 99 from Plan 1 + ~26 new)
- Coverage of `mjolnir/` ≥ 80% (lower than Plan 1's 85% because hardware-specific paths in WiFiInterface can't be tested without a real adapter)

- [ ] **Step 2: If any test fails or coverage is significantly lower, investigate before proceeding**

Common issues:
- multiprocessing tests can be flaky on systems with limited cores
- `RLIMIT_AS` may behave differently on macOS vs Linux (Linux is the target platform)

### Task 8.2: Tag Plan 2a milestone

- [ ] **Step 1: Verify clean working tree**

```bash
git status
```

- [ ] **Step 2: Create annotated tag**

```bash
git tag -a v0.2.0-plan2a -m "Plan 2a of sub-project #0 complete: NLM framework

- InterfaceManager + WiFiInterface (passive scan, iw output parser)
- Bluetooth + BLE stubs (NotImplementedError)
- ESS identity resolver (BSSID-overlap union-find, pure Python)
- ScopeChecker (mode + blocklist + two-tier persistence gates)
- GateEvaluator (data-availability gates per stage)
- Subprocess-per-stage executor with RLIMIT_AS memory isolation
- NLM main loop (find_eligible_work + run_once + kill switch)
- ~26 new tests (most use real subprocesses)
- Framework ready for first real stage (Plan 2b: PassiveScanStage)"
```

---

## Plan 2a acceptance criteria

Sub-project #0, Plan 2a, is complete when ALL of the following are true:

1. ✅ All Plan 1 tests still pass (99 tests)
2. ✅ All ~26 Plan 2a tests pass
3. ✅ Test coverage of `mjolnir/` ≥ 80%
4. ✅ Interface abstractions work: `InterfaceManager().wifi.scan()` returns parsed observations from captured `iw` output
5. ✅ ESS identity resolver: BSSID-overlap logic correct (6 test cases)
6. ✅ Scope checker: 10 gate combinations verified
7. ✅ Gate evaluator: 5 stage-specific gates implemented
8. ✅ Stage executor: subprocess isolation works; cancellation propagates; timeout terminates cleanly
9. ✅ NLM main loop: schedules work, persists outputs, respects mode and kill switch
10. ✅ Integration test: real subprocess execution produces DB state changes
11. ✅ Tag `v0.2.0-plan2a` exists

---

## Plan 2b preview (next plan, not yet written)

Plan 2b will:

- Implement `mjolnir/stages/passive_scan.py` (the first concrete Stage)
- Wire the NLM into `mjolnir/main.py` so `python -m mjolnir.main` actually runs the daemon
- Add hardware-marked tests (`@pytest.mark.hardware`) that hit a real WiFi adapter
- Verify the milestone: device boots, observes a real network within 60s, row appears in `networks` table

Plan 2b requires real Pi Zero 2W hardware for the final acceptance tests.
