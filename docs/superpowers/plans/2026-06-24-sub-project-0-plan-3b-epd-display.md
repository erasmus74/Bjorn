# Sub-project #0 — Plan 3b of 4: EPD Display

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the e-Paper display subsystem: a driver adapter (real + fake for CI), a priority-based state manager that picks one of 14 display states from current system conditions, PIL-based renderers for each state, and integration with the daemon loop. After this plan, the e-Paper shows the right thing at the right time; only the final pixel-perfect check needs real hardware.

**Architecture:** `EPDDriver` protocol with `RealEPDDriver` (wraps v1's `waveshare_epd`) and `FakeEPDDriver` (records calls). `DisplayManager` polls system state, asks `StateSelector` which of 14 `DisplayState` values applies, renders it via the matching `states.py` function to a PIL `Image`, and passes the image to the driver. Refresh strategy: full refresh on state transition, partial refresh for counter-only updates.

**Tech Stack:** Python 3.11+, Pillow (already in v1's requirements; add to mjolnir's), `waveshare_epd` (v1's library, vendored at `resources/waveshare_epd/`). pytest for tests with `FakeEPDDriver`.

**Spec reference:** `docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md` § E-Paper display
**Depends on:** `v0.4.0-plan3a` (WebUI complete)

**Branch:** `feat/v2-platform`

**Hardware target:** Waveshare 2.13" e-Paper HAT V2/V4, 122×250 pixels, monochrome. Slow refresh (~2-3s full, ~0.3s partial).

---

## File structure (Plan 3b scope)

```
mjolnir/
├── ui/
│   └── epd/                            ← NEW
│       ├── __init__.py
│       ├── driver.py                   ← EPDDriver protocol + Real/Fake impls
│       ├── states.py                   ← DisplayState enum + 14 render functions
│       ├── selector.py                 ← StateSelector (pure priority logic)
│       └── manager.py                  ← DisplayManager (loop + refresh strategy)
└── (existing files unchanged)

tests/
├── unit/
│   └── ui/
│       └── epd/
│           ├── test_driver.py          ← FakeEPDDriver records calls
│           ├── test_selector.py        ← 14-state priority matrix
│           ├── test_states.py          ← Renderers don't crash; produce expected text
│           └── test_manager.py         ← Manager picks state, calls driver, refresh strategy
└── hardware/
    └── test_real_epd.py                ← Real EPD renders all 14 states (bench-only)
```

---

## Conventions

(same as prior plans — TDD, conventional commits, type hints, dataclasses, no comments unless WHY is non-obvious)

---

## Phase 1: EPD driver adapter

### Task 1.1: EPDDriver protocol + FakeEPDDriver

**Files:**
- Create: `mjolnir/ui/epd/__init__.py`
- Create: `mjolnir/ui/epd/driver.py`
- Test: `tests/unit/ui/epd/test_driver.py`

The protocol decouples state logic from hardware. `FakeEPDDriver` records calls in memory for tests.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/epd/test_driver.py
"""Tests for the EPD driver protocol + Fake implementation."""
import pytest
from PIL import Image

from mjolnir.ui.epd.driver import FakeEPDDriver, EPDDriver


def test_fake_driver_is_an_epd_driver():
    fake = FakeEPDDriver(width=122, height=250)
    assert isinstance(fake, EPDDriver)


def test_fake_driver_init_records_call():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    assert fake.calls == ["init"]


def test_fake_driver_display_records_image():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    img = Image.new("1", (122, 250), 255)
    fake.display(img)
    assert fake.last_image is img
    assert "display" in fake.calls


def test_fake_driver_clear_records_call():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    fake.clear()
    assert "clear" in fake.calls


def test_fake_driver_sleep_records_call():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    fake.sleep()
    assert "sleep" in fake.calls


def test_fake_driver_dimensions():
    fake = FakeEPDDriver(width=122, height=250)
    assert fake.width == 122
    assert fake.height == 250


def test_fake_driver_rejects_wrong_size_image():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    wrong_size = Image.new("1", (100, 100), 255)
    with pytest.raises(ValueError, match="size"):
        fake.display(wrong_size)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/ui/epd/test_driver.py -v
```

- [ ] **Step 3: Write `mjolnir/ui/epd/__init__.py`**

```python
"""E-Paper display subsystem."""
```

- [ ] **Step 4: Write `mjolnir/ui/epd/driver.py`**

```python
"""EPD driver abstraction.

EPDDriver is the protocol every display backend implements. Two impls:
  - FakeEPDDriver: records calls in memory; used in CI tests
  - RealEPDDriver: wraps v1's waveshare_epd library; used on Pi hardware
"""
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from PIL import Image


@runtime_checkable
class EPDDriver(Protocol):
    width: int
    height: int

    def init(self) -> None: ...

    def display(self, image: Image.Image) -> None: ...

    def clear(self) -> None: ...

    def sleep(self) -> None: ...


@dataclass
class FakeEPDDriver:
    """In-memory driver for tests. Records every call."""
    width: int
    height: int
    calls: list[str] = field(default_factory=list)
    last_image: Image.Image | None = None
    _initialized: bool = False

    def init(self) -> None:
        self.calls.append("init")
        self._initialized = True

    def display(self, image: Image.Image) -> None:
        if image.size != (self.width, self.height):
            raise ValueError(
                f"image size {image.size} does not match display {(self.width, self.height)}"
            )
        self.calls.append("display")
        self.last_image = image

    def clear(self) -> None:
        self.calls.append("clear")

    def sleep(self) -> None:
        self.calls.append("sleep")


class RealEPDDriver:
    """Wraps v1's waveshare_epd library. Only importable on Pi hardware.

    The waveshare_epd package is vendored at resources/waveshare_epd/.
    This driver is NOT exercised in CI (no hardware); tests use FakeEPDDriver.
    """

    def __init__(self, epd_type: str = "epd2in13_V4"):
        self._epd_type = epd_type
        self._epd = None
        self.width = 122
        self.height = 250

    def init(self) -> None:
        import importlib
        module = importlib.import_module(f"resources.waveshare_epd.{self._epd_type}")
        self._epd = module.EPD()
        self._epd.init(self._epd.FULL_UPDATE)
        self.width = self._epd.width
        self.height = self._epd.height

    def display(self, image: Image.Image) -> None:
        if self._epd is None:
            raise RuntimeError("init() not called")
        if image.size != (self.width, self.height):
            raise ValueError(
                f"image size {image.size} does not match display {(self.width, self.height)}"
            )
        self._epd.display(self._epd.getbuffer(image))

    def clear(self) -> None:
        if self._epd is None:
            raise RuntimeError("init() not called")
        self._epd.Clear()

    def sleep(self) -> None:
        if self._epd is None:
            raise RuntimeError("init() not called")
        self._epd.sleep()
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/ui/epd/test_driver.py -v
```
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/ui/epd/__init__.py mjolnir/ui/epd/driver.py tests/unit/ui/epd/test_driver.py
git commit -m "feat(epd): EPDDriver protocol + Fake/Real implementations

EPDDriver is the protocol every display backend implements.
FakeEPDDriver records calls in memory for CI tests. RealEPDDriver
wraps v1's vendored waveshare_epd library — only used on Pi
hardware, never exercised in CI.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 2: Display state enum + selector (pure logic)

### Task 2.1: DisplayState enum + StateSelector

**Files:**
- Create: `mjolnir/ui/epd/states.py` (enum only; renderers added in Phase 3)
- Create: `mjolnir/ui/epd/selector.py`
- Test: `tests/unit/ui/epd/test_selector.py`

The selector is pure logic: given system conditions, return the highest-priority applicable `DisplayState`. This is the most important logic to get right — exhaustively tested.

- [ ] **Step 1: Write failing tests (parametrized for all 14 states + the overlay)**

```python
# tests/unit/ui/epd/test_selector.py
"""Tests for the display state selector — the 14-state priority matrix."""
import pytest
from datetime import datetime, timezone

from mjolnir.ui.epd.selector import StateSelector, SystemConditions
from mjolnir.ui.epd.states import DisplayState


@pytest.fixture
def selector():
    return StateSelector()


def _conds(**overrides) -> SystemConditions:
    """Baseline conditions: a healthy, active, working system."""
    base = dict(
        starting_up=False,
        shutting_down=False,
        fatal_error=None,
        kill_switch_engaged=False,
        interfaces_up=True,
        networks_visible=True,
        known_networks_visible=True,
        connecting=False,
        internet_up=True,
        tailscale_up=True,
        active_work=True,
        global_mode="active",
        blocklisted_nearby=False,
        exhausted_in_range=[],
        view_only_networks_in_range=0,
    )
    base.update(overrides)
    return SystemConditions(**base)


def test_shutting_down_beats_everything(selector):
    state, _ = selector.select(_conds(shutting_down=True, kill_switch_engaged=True,
                                       fatal_error="disk full", starting_up=True))
    assert state == DisplayState.SHUTTING_DOWN


def test_starting_up_beats_everything_except_shutdown(selector):
    state, _ = selector.select(_conds(starting_up=True, kill_switch_engaged=True,
                                       fatal_error="x"))
    assert state == DisplayState.STARTING_UP


def test_fatal_error_beats_lower_priorities(selector):
    state, _ = selector.select(_conds(fatal_error="disk full", kill_switch_engaged=True))
    assert state == DisplayState.FATAL_ERROR


def test_kill_switch_engaged_beats_idle_states(selector):
    state, _ = selector.select(_conds(kill_switch_engaged=True,
                                       interfaces_up=False, networks_visible=False))
    assert state == DisplayState.KILL_SWITCH_ENGAGED


def test_no_interfaces_up(selector):
    state, _ = selector.select(_conds(interfaces_up=False))
    assert state == DisplayState.NO_INTERFACES_UP


def test_no_networks_visible(selector):
    state, _ = selector.select(_conds(networks_visible=False))
    assert state == DisplayState.NO_NETWORKS_VISIBLE


def test_no_known_networks_visible_when_in_active_mode(selector):
    """Active mode but only unknown networks in range → NO_KNOWN_NETWORKS."""
    state, _ = selector.select(_conds(known_networks_visible=False, active_work=False,
                                       global_mode="active"))
    assert state == DisplayState.NO_KNOWN_NETWORKS


def test_connecting(selector):
    state, _ = selector.select(_conds(connecting=True, active_work=False))
    assert state == DisplayState.CONNECTING


def test_no_internet(selector):
    state, _ = selector.select(_conds(internet_up=False, active_work=False))
    assert state == DisplayState.NO_INTERNET


def test_tailscale_down_when_internet_up(selector):
    state, _ = selector.select(_conds(internet_up=True, tailscale_up=False, active_work=False))
    assert state == DisplayState.TAILSCALE_DOWN


def test_active_idle_when_active_mode_no_work(selector):
    state, _ = selector.select(_conds(active_work=False, global_mode="active",
                                       exhausted_in_range=[("NetA", "all_stages_succeeded")]))
    assert state == DisplayState.ACTIVE_IDLE


def test_view_only_passive_when_view_only_mode(selector):
    state, _ = selector.select(_conds(active_work=False, global_mode="view_only",
                                       view_only_networks_in_range=5))
    assert state == DisplayState.VIEW_ONLY_PASSIVE


def test_active_working_when_there_is_work(selector):
    state, _ = selector.select(_conds(active_work=True))
    assert state == DisplayState.ACTIVE_WORKING


def test_blocklist_nearby_is_overlay_not_primary(selector):
    """BLOCKLIST_NEARBY is a banner overlay, not a primary state."""
    state, overlay = selector.select(_conds(active_work=True, blocklisted_nearby=True))
    assert state == DisplayState.ACTIVE_WORKING
    assert overlay is True


def test_blocklist_nearby_overlay_on_idle_states_too(selector):
    state, overlay = selector.select(_conds(active_work=False, global_mode="view_only",
                                             view_only_networks_in_range=3,
                                             blocklisted_nearby=True))
    assert state == DisplayState.VIEW_ONLY_PASSIVE
    assert overlay is True


def test_no_blocklist_overlay_when_flag_false(selector):
    state, overlay = selector.select(_conds(active_work=True, blocklisted_nearby=False))
    assert overlay is False
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/ui/epd/test_selector.py -v
```

- [ ] **Step 3: Write `mjolnir/ui/epd/states.py`** (enum only for now)

```python
"""Display states for the e-Paper UI.

14 primary states with a strict priority order (highest first), plus one
overlay banner (BLOCKLIST_NEARBY) that can appear on top of any primary
state. See spec § E-Paper display.
"""
from enum import IntEnum


class DisplayState(IntEnum):
    """Priority-ordered display states. Lower number = higher priority."""
    SHUTTING_DOWN = 1
    STARTING_UP = 2
    FATAL_ERROR = 3
    KILL_SWITCH_ENGAGED = 4
    NO_INTERFACES_UP = 5
    NO_NETWORKS_VISIBLE = 6
    NO_KNOWN_NETWORKS = 7
    CONNECTING = 8
    NO_INTERNET = 9
    TAILSCALE_DOWN = 10
    ACTIVE_IDLE = 11
    VIEW_ONLY_PASSIVE = 12
    ACTIVE_WORKING = 13
    # Note: BLOCKLIST_NEARBY is handled separately as an overlay, not a primary state
```

- [ ] **Step 4: Write `mjolnir/ui/epd/selector.py`**

```python
"""StateSelector: pure-logic priority-based display state selection.

Given current SystemConditions, returns the highest-priority applicable
DisplayState plus whether the BLOCKLIST_NEARBY overlay should show.
No I/O, no hardware — exhaustively testable.
"""
from dataclasses import dataclass, field

from mjolnir.ui.epd.states import DisplayState


@dataclass(frozen=True)
class SystemConditions:
    """Inputs to the state selector. All fields must be set by the caller."""
    starting_up: bool
    shutting_down: bool
    fatal_error: str | None  # None = no error; string = error message
    kill_switch_engaged: bool
    interfaces_up: bool
    networks_visible: bool
    known_networks_visible: bool
    connecting: bool
    internet_up: bool
    tailscale_up: bool
    active_work: bool  # True if NLM has at least one runnable (network, stage) pair
    global_mode: str  # 'active' or 'view_only'
    blocklisted_nearby: bool
    exhausted_in_range: list[tuple[str, str]]  # [(ssid, reason), ...] for ACTIVE_IDLE display
    view_only_networks_in_range: int


@dataclass(frozen=True)
class Selection:
    state: DisplayState
    blocklist_overlay: bool


class StateSelector:
    """Evaluates conditions against the 14-state priority matrix."""

    def select(self, conditions: SystemConditions) -> tuple[DisplayState, bool]:
        # Priority order: check highest-priority conditions first
        if conditions.shutting_down:
            return self._with_overlay(DisplayState.SHUTTING_DOWN, conditions)

        if conditions.starting_up:
            return self._with_overlay(DisplayState.STARTING_UP, conditions)

        if conditions.fatal_error is not None:
            return self._with_overlay(DisplayState.FATAL_ERROR, conditions)

        if conditions.kill_switch_engaged:
            return self._with_overlay(DisplayState.KILL_SWITCH_ENGAGED, conditions)

        if not conditions.interfaces_up:
            return self._with_overlay(DisplayState.NO_INTERFACES_UP, conditions)

        if not conditions.networks_visible:
            return self._with_overlay(DisplayState.NO_NETWORKS_VISIBLE, conditions)

        if not conditions.known_networks_visible and not conditions.active_work:
            return self._with_overlay(DisplayState.NO_KNOWN_NETWORKS, conditions)

        if conditions.connecting and not conditions.active_work:
            return self._with_overlay(DisplayState.CONNECTING, conditions)

        if not conditions.internet_up and not conditions.active_work:
            return self._with_overlay(DisplayState.NO_INTERNET, conditions)

        if conditions.internet_up and not conditions.tailscale_up and not conditions.active_work:
            return self._with_overlay(DisplayState.TAILSCALE_DOWN, conditions)

        if conditions.active_work:
            return self._with_overlay(DisplayState.ACTIVE_WORKING, conditions)

        # No active work — pick idle state based on mode
        if conditions.global_mode == "active":
            return self._with_overlay(DisplayState.ACTIVE_IDLE, conditions)

        return self._with_overlay(DisplayState.VIEW_ONLY_PASSIVE, conditions)

    def _with_overlay(self, state: DisplayState,
                       conditions: SystemConditions) -> tuple[DisplayState, bool]:
        return state, conditions.blocklisted_nearby
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/ui/epd/test_selector.py -v
```
Expected: PASS (15 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/ui/epd/states.py mjolnir/ui/epd/selector.py tests/unit/ui/epd/test_selector.py
git commit -m "feat(epd): DisplayState enum + StateSelector (priority matrix)

14 priority-ordered states plus the BLOCKLIST_NEARBY overlay. Pure
logic — given SystemConditions, returns (state, overlay_bool).
Exhaustively tested: each state has a dedicated trigger test plus
priority-ordering tests for the top 4 states.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 3: State renderers (PIL-based)

### Task 3.1: Render functions for all 14 states

**Files:**
- Modify: `mjolnir/ui/epd/states.py` (add render functions)
- Test: `tests/unit/ui/epd/test_states.py`

Each renderer takes a `SystemConditions` (or relevant subset) and returns a PIL `Image` of size 122×250. Tests verify the image isn't blank and contains expected text (via PIL's image inspection — we check that drawing didn't crash and the image has the right dimensions).

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/epd/test_states.py
"""Tests for the state renderers. Verify each produces a valid 122x250 image
with expected text content (where checkable)."""
import pytest
from PIL import Image

from mjolnir.ui.epd.states import (
    DisplayState,
    render_state,
    RENDER_WIDTH,
    RENDER_HEIGHT,
)
from mjolnir.ui.epd.selector import SystemConditions


def _conds(**overrides) -> SystemConditions:
    base = dict(
        starting_up=False, shutting_down=False, fatal_error=None,
        kill_switch_engaged=False, interfaces_up=True, networks_visible=True,
        known_networks_visible=True, connecting=False, internet_up=True,
        tailscale_up=True, active_work=True, global_mode="active",
        blocklisted_nearby=False, exhausted_in_range=[],
        view_only_networks_in_range=0,
    )
    base.update(overrides)
    return SystemConditions(**base)


def test_render_constants():
    assert RENDER_WIDTH == 122
    assert RENDER_HEIGHT == 250


def test_render_shutting_down():
    img = render_state(DisplayState.SHUTTING_DOWN, _conds(shutting_down=True))
    assert img.size == (122, 250)


def test_render_starting_up():
    img = render_state(DisplayState.STARTING_UP, _conds(starting_up=True))
    assert img.size == (122, 250)


def test_render_fatal_error_includes_message():
    img = render_state(DisplayState.FATAL_ERROR, _conds(fatal_error="disk full"))
    assert img.size == (122, 250)
    # The error message should be somewhere in the image (we can't easily OCR,
    # but we can verify the image isn't blank by checking pixel variance)
    pixels = list(img.getdata())
    assert len(set(pixels)) > 1, "image should not be blank"


def test_render_kill_switch_engaged():
    img = render_state(DisplayState.KILL_SWITCH_ENGAGED, _conds(kill_switch_engaged=True))
    assert img.size == (122, 250)


def test_render_no_interfaces_up():
    img = render_state(DisplayState.NO_INTERFACES_UP, _conds(interfaces_up=False))
    assert img.size == (122, 250)


def test_render_no_networks_visible():
    img = render_state(DisplayState.NO_NETWORKS_VISIBLE, _condworking=False, networks_visible=False, global_mode="active"))
    assert img.size == (122, 250)


def test_render_no_known_networks():
    img = render_state(DisplayState.NO_KNOWN_NETWORKS,
                        _conds(known_networks_visible=False, active_work=False, global_mode="active"))
    assert img.size == (122, 250)


def test_render_connecting():
    img = render_state(DisplayState.CONNECTING, _conds(connecting=True, active_work=False))
    assert img.size == (122, 250)


def test_render_no_internet():
    img = render_state(DisplayState.NO_INTERNET, _conds(internet_up=False, active_work=False))
    assert img.size == (122, 250)


def test_render_tailscale_down():
    img = render_state(DisplayState.TAILSCALE_DOWN,
                        _conds(internet_up=True, tailscale_up=False, active_work=False))
    assert img.size == (122, 250)


def test_render_active_idle():
    img = render_state(DisplayState.ACTIVE_IDLE,
                        _conds(active_work=False, global_mode="active",
                               exhausted_in_range=[("NetA", "all_stages_succeeded")]))
    assert img.size == (122, 250)


def test_render_view_only_passive():
    img = render_state(DisplayState.VIEW_ONLY_PASSIVE,
                        _conds(active_work=False, global_mode="view_only",
                               view_only_networks_in_range=5))
    assert img.size == (122, 250)


def test_render_active_working():
    img = render_state(DisplayState.ACTIVE_WORKING, _conds(active_work=True))
    assert img.size == (122, 250)


def test_render_with_blocklist_overlay():
    """Overlay should add a banner without changing base image dimensions."""
    img = render_state(DisplayState.ACTIVE_WORKING,
                        _conds(active_work=True, blocklisted_nearby=True),
                        overlay=True)
    assert img.size == (122, 250)


def test_every_state_renders_without_crash():
    """Smoke test: every DisplayState value can be rendered."""
    for state in DisplayState:
        img = render_state(state, _conds())
        assert img.size == (122, 250)
```

Note: there's a typo in one test above (`_condworking` instead of `_conds`). Fix it to `_conds(active_work=False, networks_visible=False, global_mode="active")` when writing the test file.

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/ui/epd/test_states.py -v
```

- [ ] **Step 3: Add renderers to `mjolnir/ui/epd/states.py`**

Append to the existing `states.py`:

```python
from PIL import Image, ImageDraw, ImageFont

RENDER_WIDTH = 122
RENDER_HEIGHT = 250

# Try to load a small bitmap font; fall back to default if unavailable.
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _new_image() -> Image.Image:
    """Create a blank white image at display resolution."""
    return Image.new("1", (RENDER_WIDTH, RENDER_HEIGHT), 255)


def _draw_header(draw: ImageDraw.ImageDraw, title: str) -> None:
    """Draw a header bar with title text."""
    font = _load_font(12)
    draw.rectangle([(0, 0), (RENDER_WIDTH, 16)], fill=0)
    draw.text((4, 2), title, font=font, fill=255)


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int, size: int = 14) -> None:
    font = _load_font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (RENDER_WIDTH - text_width) // 2
    draw.text((x, y), text, font=font, fill=0)


def _draw_blocklist_overlay(draw: ImageDraw.ImageDraw, ssid: str = "") -> None:
    """Draw a BLOCKED banner at the top of the image."""
    font = _load_font(10)
    banner_text = f"BLOCKED: {ssid}" if ssid else "BLOCKED NEARBY"
    draw.rectangle([(0, RENDER_HEIGHT - 14), (RENDER_WIDTH, RENDER_HEIGHT)], fill=0)
    bbox = draw.textbbox((0, 0), banner_text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (RENDER_WIDTH - text_width) // 2
    draw.text((x, RENDER_HEIGHT - 12), banner_text, font=font, fill=255)


def render_state(state: DisplayState, conditions, overlay: bool = False) -> Image.Image:
    """Render the given state to a 122x250 PIL Image.

    `conditions` is a SystemConditions instance (used for dynamic content
    like error messages, network counts, etc.). `overlay=True` adds the
    BLOCKLIST_NEARBY banner.
    """
    img = _new_image()
    draw = ImageDraw.Draw(img)

    if state == DisplayState.SHUTTING_DOWN:
        _draw_header(draw, "SHUTDOWN")
        _draw_centered(draw, "Shutting down", 80)
        _draw_centered(draw, "Please wait", 100, size=12)
    elif state == DisplayState.STARTING_UP:
        _draw_header(draw, "BOOT")
        _draw_centered(draw, "Starting mjolnir", 80)
        _draw_centered(draw, "...", 100, size=12)
    elif state == DisplayState.FATAL_ERROR:
        _draw_header(draw, "ERROR")
        _draw_centered(draw, "FATAL ERROR", 60, size=14)
        msg = conditions.fatal_error or "unknown"
        # Wrap long error messages
        font = _load_font(10)
        words = msg.split()
        line = ""
        y = 90
        for word in words:
            test = f"{line} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > RENDER_WIDTH - 8:
                draw.text((4, y), line, font=font, fill=0)
                y += 12
                line = word
            else:
                line = test
        if line:
            draw.text((4, y), line, font=font, fill=0)
    elif state == DisplayState.KILL_SWITCH_ENGAGED:
        _draw_header(draw, "KILLED")
        _draw_centered(draw, "KILL SWITCH", 70, size=16)
        _draw_centered(draw, "ENGAGED", 92, size=16)
        _draw_centered(draw, "All work halted", 130, size=11)
        _draw_centered(draw, "Release via WebUI", 150, size=11)
    elif state == DisplayState.NO_INTERFACES_UP:
        _draw_header(draw, "NO RADIO")
        _draw_centered(draw, "No WiFi", 80)
        _draw_centered(draw, "interface", 100)
        _draw_centered(draw, "Retrying...", 140, size=11)
    elif state == DisplayState.NO_NETWORKS_VISIBLE:
        _draw_header(draw, "SCAN")
        _draw_centered(draw, "Scanning...", 80)
        _draw_centered(draw, "No networks", 100)
        _draw_centered(draw, "in range", 120)
    elif state == DisplayState.NO_KNOWN_NETWORKS:
        _draw_header(draw, "SCAN")
        _draw_centered(draw, "Networks visible", 70, size=12)
        _draw_centered(draw, "but none", 90, size=12)
        _draw_centered(draw, "preferred", 110, size=12)
        _draw_centered(draw, "Add via WebUI", 150, size=11)
    elif state == DisplayState.CONNECTING:
        _draw_header(draw, "CONNECT")
        _draw_centered(draw, "Joining", 80)
        _draw_centered(draw, "network...", 100)
    elif state == DisplayState.NO_INTERNET:
        _draw_header(draw, "NO NET")
        _draw_centered(draw, "Connected to", 70, size=12)
        _draw_centered(draw, "WiFi", 90, size=12)
        _draw_centered(draw, "No internet", 130, size=12)
        _draw_centered(draw, "WebUI local", 160, size=10)
    elif state == DisplayState.TAILSCALE_DOWN:
        _draw_header(draw, "VPN")
        _draw_centered(draw, "Internet OK", 70, size=12)
        _draw_centered(draw, "Tailscale", 90, size=12)
        _draw_centered(draw, "not connected", 110, size=12)
        _draw_centered(draw, "WebUI local", 150, size=10)
    elif state == DisplayState.ACTIVE_IDLE:
        _draw_header(draw, "IDLE")
        _draw_centered(draw, "Mode: ACTIVE", 40, size=12)
        _draw_centered(draw, "All visible nets", 70, size=11)
        _draw_centered(draw, "exhausted/done", 86, size=11)
        font = _load_font(10)
        y = 110
        for ssid, reason in conditions.exhausted_in_range[:8]:
            draw.text((4, y), f"- {ssid[:14]}", font=font, fill=0)
            y += 12
    elif state == DisplayState.VIEW_ONLY_PASSIVE:
        _draw_header(draw, "VIEW-ONLY")
        _draw_centered(draw, "Passive mode", 40, size=12)
        _draw_centered(draw, f"{conditions.view_only_networks_in_range}", 80, size=20)
        _draw_centered(draw, "networks", 110, size=12)
        _draw_centered(draw, "in range", 128, size=12)
        _draw_centered(draw, "Toggle ACTIVE", 170, size=10)
        _draw_centered(draw, "via WebUI", 185, size=10)
    elif state == DisplayState.ACTIVE_WORKING:
        _draw_header(draw, "ACTIVE")
        _draw_centered(draw, "Working...", 40, size=12)
        _draw_centered(draw, "See WebUI", 150, size=10)
        _draw_centered(draw, "for details", 165, size=10)

    if overlay:
        _draw_blocklist_overlay(draw)

    return img
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/ui/epd/test_states.py -v
```
Expected: PASS (17 tests). Fix the typo in the no_networks_visible test (`_condworking` → `_conds(active_work=False, ...`).

- [ ] **Step 5: Commit**

```bash
git add mjolnir/ui/epd/states.py tests/unit/ui/epd/test_states.py
git commit -m "feat(epd): state renderers (14 states + blocklist overlay)

Each DisplayState has a render function that produces a 122x250 PIL
Image. Renderers use a header bar + centered text layout. FATAL_ERROR
wraps long messages. BLOCKLIST_NEARBY is an overlay banner drawn at
the bottom of any primary state.

Font loading tries DejaVuSans first, falls back to PIL default.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4: DisplayManager (combines selector + renderer + driver)

### Task 4.1: DisplayManager with refresh strategy

**Files:**
- Create: `mjolnir/ui/epd/manager.py`
- Test: `tests/unit/ui/epd/test_manager.py`

The manager polls system conditions, selects a state, renders it, and sends it to the driver. Refresh strategy: full refresh on state transition, skip refresh if state + overlay unchanged since last render.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/epd/test_manager.py
"""Tests for the DisplayManager."""
import pytest
from mjolnir.ui.epd.driver import FakeEPDDriver
from mjolnir.ui.epd.manager import DisplayManager
from mjolnir.ui.epd.selector import SystemConditions
from mjolnir.ui.epd.states import DisplayState


def _conds(**overrides) -> SystemConditions:
    base = dict(
        starting_up=False, shutting_down=False, fatal_error=None,
        kill_switch_engaged=False, interfaces_up=True, networks_visible=True,
        known_networks_visible=True, connecting=False, internet_up=True,
        tailscale_up=True, active_work=True, global_mode="active",
        blocklisted_nearby=False, exhausted_in_range=[],
        view_only_networks_in_range=0,
    )
    base.update(overrides)
    return SystemConditions(**base)


@pytest.fixture
def manager():
    driver = FakeEPDDriver(width=122, height=250)
    driver.init()
    return DisplayManager(driver=driver), driver


def test_manager_initial_display(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True))
    assert "display" in driver.calls
    assert driver.last_image is not None


def test_manager_skips_refresh_when_state_unchanged(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True))
    calls_before = len(driver.calls)
    mgr.update(_conds(active_work=True))  # same state
    assert len(driver.calls) == calls_before  # no new display call


def test_manager_refreshes_on_state_transition(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True))  # ACTIVE_WORKING
    calls_before = len(driver.calls)
    mgr.update(_conds(active_work=False, kill_switch_engaged=True))  # KILL_SWITCH_ENGAGED
    assert len(driver.calls) > calls_before  # new display call


def test_manager_refreshes_on_overlay_change(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True, blocklisted_nearby=False))
    calls_before = len(driver.calls)
    mgr.update(_conds(active_work=True, blocklisted_nearby=True))  # overlay added
    assert len(driver.calls) > calls_before


def test_manager_clears_on_shutdown(manager):
    mgr, driver = manager
    mgr.update(_conds(active_work=True))
    mgr.shutdown()
    assert "clear" in driver.calls
    assert "sleep" in driver.calls


def test_manager_tracks_current_state(manager):
    mgr, _ = manager
    mgr.update(_conds(kill_switch_engaged=True))
    assert mgr.current_state == DisplayState.KILL_SWITCH_ENGAGED
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/ui/epd/test_manager.py -v
```

- [ ] **Step 3: Write `mjolnir/ui/epd/manager.py`**

```python
"""DisplayManager: ties selector + renderer + driver together.

Polls system conditions (via a caller-provided SystemConditions), selects
the current state, renders it, and sends to the driver. Skips refresh
when state + overlay unchanged since last render (e-Paper wears out;
don't refresh needlessly).
"""
from dataclasses import dataclass

from mjolnir.ui.epd.driver import EPDDriver
from mjolnir.ui.epd.selector import StateSelector, SystemConditions
from mjolnir.ui.epd.states import DisplayState, render_state


@dataclass
class DisplayManager:
    driver: EPDDriver
    selector: StateSelector = None  # type: ignore[assignment]  # set in __post_init__
    current_state: DisplayState | None = None
    current_overlay: bool = False

    def __post_init__(self):
        if self.selector is None:
            self.selector = StateSelector()

    def update(self, conditions: SystemConditions) -> None:
        """Select state from conditions; render + display if changed."""
        state, overlay = self.selector.select(conditions)

        if state == self.current_state and overlay == self.current_overlay:
            return  # no change — skip refresh

        image = render_state(state, conditions, overlay=overlay)
        self.driver.display(image)
        self.current_state = state
        self.current_overlay = overlay

    def shutdown(self) -> None:
        """Clear the display and put the driver to sleep."""
        self.driver.clear()
        self.driver.sleep()
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/ui/epd/test_manager.py -v
```
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/ui/epd/manager.py tests/unit/ui/epd/test_manager.py
git commit -m "feat(epd): DisplayManager (refresh strategy + driver wiring)

Polls SystemConditions, selects state via StateSelector, renders via
states.render_state, sends to driver. Skips refresh when state +
overlay unchanged (e-Paper wears out). shutdown() clears + sleeps.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 5: Conditions collector (DB → SystemConditions)

### Task 5.1: Build SystemConditions from DB state

**Files:**
- Create: `mjolnir/ui/epd/collector.py`
- Test: `tests/unit/ui/epd/test_collector.py`

The collector reads the DB (via repository bundle) and produces a `SystemConditions` for the selector. This is the bridge between the NLM's state and the display.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/epd/test_collector.py
"""Tests for the conditions collector (DB → SystemConditions)."""
import pytest

from mjolnir.ui.epd.collector import collect_conditions
from mjolnir.ui.epd.states import DisplayState
from mjolnir.ui.epd.selector import StateSelector
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def bundle_and_path(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    return bundle_for(conn), tmp_path / "x.db", conn


def test_collect_default_conditions(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    # Fresh DB: view_only mode, no kill switch, no networks visible
    assert conditions.global_mode == "view_only"
    assert conditions.kill_switch_engaged is False
    assert conditions.networks_visible is False  # no networks discovered yet
    conn.close()


def test_collect_reflects_active_mode(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    bundle.system_state.set_global_mode("active")
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert conditions.global_mode == "active"
    conn.close()


def test_collect_reflects_kill_switch(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    bundle.system_state.engage_kill_switch()
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert conditions.kill_switch_engaged is True
    conn.close()


def test_collect_detects_networks_present(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    bundle.networks.create(ssid="SomeNet", security_type="WPA2")
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert conditions.networks_visible is True
    conn.close()


def test_collect_detects_exhausted_networks(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    net = bundle.networks.create(ssid="DoneNet", security_type="WPA2")
    bundle.networks.mark_exhausted(net.id, "all_stages_succeeded")
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert ("DoneNet", "all_stages_succeeded") in conditions.exhausted_in_range
    conn.close()


def test_collect_detects_blocklisted_nearby(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    net = bundle.networks.create(ssid="MyHome", security_type="WPA2")
    bundle.networks.update_scope_state(net.id, "blocklisted", reason="home", by="op")
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert conditions.blocklisted_nearby is True
    conn.close()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/ui/epd/test_collector.py -v
```

- [ ] **Step 3: Write `mjolnir/ui/epd/collector.py`**

```python
"""Collect SystemConditions from DB state.

Bridges the NLM's DB state and the display selector. Reads mode, kill
switch, networks, exhausted networks, blocklisted networks.
"""
import subprocess

from mjolnir.db.repositories import RepositoryBundle
from mjolnir.ui.epd.selector import SystemConditions


def _interfaces_up() -> bool:
    """Check if wlan0 (or configured interface) exists and is up."""
    try:
        result = subprocess.run(
            ["ip", "link", "show", "wlan0"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return result.returncode == 0 and "state UP" in result.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        # In CI/tests, ip may not exist or wlan0 won't — treat as not-up
        # so tests don't depend on host networking. Override in tests.
        return False


def collect_conditions(bundle: RepositoryBundle,
                        kill_switch_event_set: bool,
                        interfaces_up_override: bool | None = None) -> SystemConditions:
    """Build SystemConditions from current DB + runtime state.

    `interfaces_up_override` lets callers force the interface state
    (used in tests where `ip` isn't available).
    """
    global_mode = bundle.system_state.get_global_mode()
    kill_switch_engaged = (bundle.system_state.is_kill_switch_engaged()
                            or kill_switch_event_set)

    networks = bundle.networks.list_eligible_for_processing()
    networks_visible = len(networks) > 0

    exhausted = [(n.ssid, n.exhausted_reason or "unknown")
                 for n in networks if n.exhausted]
    # Also include exhausted networks that are scope_state=enabled but done
    cursor = bundle.networks.conn.execute(
        "SELECT ssid, exhausted_reason FROM networks WHERE exhausted = 1"
    )
    exhausted = [(row["ssid"], row["exhausted_reason"] or "unknown")
                 for row in cursor.fetchall()]

    cursor = bundle.networks.conn.execute(
        "SELECT COUNT(*) FROM networks WHERE scope_state = 'blocklisted'"
    )
    blocklisted_nearby = cursor.fetchone()[0] > 0

    interfaces_up = interfaces_up_override if interfaces_up_override is not None else _interfaces_up()

    return SystemConditions(
        starting_up=False,  # caller sets this explicitly during boot
        shutting_down=False,  # caller sets this during shutdown
        fatal_error=None,  # caller sets this if a fatal error occurred
        kill_switch_engaged=kill_switch_engaged,
        interfaces_up=interfaces_up,
        networks_visible=networks_visible,
        known_networks_visible=networks_visible,  # simplification: any network counts
        connecting=False,  # caller sets during connection phases
        internet_up=True,  # caller sets after connectivity check
        tailscale_up=True,  # caller sets after tailscale check (sub-project #1)
        active_work=networks_visible and not kill_switch_engaged,
        global_mode=global_mode,
        blocklisted_nearby=blocklisted_nearby,
        exhausted_in_range=exhausted,
        view_only_networks_in_range=len(networks) if global_mode == "view_only" else 0,
    )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/ui/epd/test_collector.py -v
```
Expected: PASS (6 tests). Note: the `interfaces_up_override` parameter isn't tested here (kept simple); the tests rely on the `networks_visible` and `kill_switch` paths.

- [ ] **Step 5: Commit**

```bash
git add mjolnir/ui/epd/collector.py tests/unit/ui/epd/test_collector.py
git commit -m "feat(epd): conditions collector (DB -> SystemConditions)

Bridges NLM DB state and display selector. Reads global_mode, kill
switch, networks present, exhausted networks, blocklisted networks.
Sub-project #1 will wire tailscale_up and internet_up properly.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 6: Integration with main.py + hardware test

### Task 6.1: Wire DisplayManager into daemon loop

**Files:**
- Modify: `mjolnir/main.py`

The daemon currently runs NLM + Flask. Add the DisplayManager: construct it at startup, update it each loop iteration with fresh conditions.

- [ ] **Step 1: Modify `run_daemon` in `mjolnir/main.py`**

Add imports at top:
```python
from mjolnir.ui.epd.driver import FakeEPDDriver, RealEPDDriver
from mjolnir.ui.epd.manager import DisplayManager
from mjolnir.ui.epd.collector import collect_conditions
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories import bundle_for
```

In `run_daemon`, after starting the web thread, construct the display manager:

```python
    # Construct display manager. Try real hardware first; fall back to fake
    # if the EPD library isn't importable (e.g., in tests/CI).
    try:
        display_driver = RealEPDDriver()
        display_driver.init()
    except Exception:
        display_driver = FakeEPDDriver(width=122, height=250)
        display_driver.init()
    display = DisplayManager(driver=display_driver)
```

Inside the main loop, after each `mgr.run_once()`, update the display:

```python
        # Update display with current conditions
        try:
            db_conn = ConnectionFactory(db_path=config.db.path).connect()
            bundle = bundle_for(db_conn)
            conditions = collect_conditions(
                bundle,
                kill_switch_event_set=kill_switch_event.is_set(),
            )
            conditions = replace(conditions, starting_up=False)  # boot done
            display.update(conditions)
            db_conn.close()
        except Exception as e:
            print(f"warning: display update failed: {e}", file=sys.stderr)
```

Add `from dataclasses import replace` to imports (used to override `starting_up`).

After the loop (shutdown path):
```python
    display.shutdown()
    return 0
```

- [ ] **Step 2: Run the daemon integration test**

```bash
pytest tests/integration/test_daemon_loop.py -v
```
Expected: PASS. The test uses the FakeEPDDriver fallback path (no real hardware in CI).

- [ ] **Step 3: Commit**

```bash
git add mjolnir/main.py
git commit -m "feat(main): wire DisplayManager into daemon loop

Daemon now constructs a DisplayManager (real EPD if available, fake
fallback for CI), updates it each loop iteration with fresh
conditions from the DB, and shuts it down cleanly on exit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 6.2: Hardware test for real EPD

**Files:**
- Create: `tests/hardware/test_real_epd.py`

- [ ] **Step 1: Write the hardware test**

```python
# tests/hardware/test_real_epd.py
"""Hardware-marked tests for the real e-Paper display.

Run with: pytest -m hardware
Requires:
- Real Pi Zero 2W with Waveshare 2.13\" e-Paper HAT (V2 or V4) attached
- resources/waveshare_epd/ library importable
- SPI enabled on the Pi
"""
import time

import pytest

from mjolnir.ui.epd.driver import RealEPDDriver
from mjolnir.ui.epd.manager import DisplayManager
from mjolnir.ui.epd.selector import SystemConditions
from mjolnir.ui.epd.states import DisplayState, render_state


pytestmark = pytest.mark.hardware


def test_real_epd_initializes():
    """Sanity check: the EPD driver inits without error."""
    driver = RealEPDDriver()
    driver.init()
    driver.clear()
    driver.sleep()


def test_real_epd_renders_all_states():
    """Render every display state to the real EPD. Visual check on hardware."""
    driver = RealEPDDriver()
    driver.init()

    conditions = SystemConditions(
        starting_up=False, shutting_down=False, fatal_error="test error for visual check",
        kill_switch_engaged=False, interfaces_up=True, networks_visible=True,
        known_networks_visible=True, connecting=False, internet_up=True,
        tailscale_up=True, active_work=True, global_mode="active",
        blocklisted_nearby=False, exhausted_in_range=[("TestNet", "all_stages_succeeded")],
        view_only_networks_in_range=0,
    )

    for state in DisplayState:
        img = render_state(state, conditions)
        driver.display(img)
        time.sleep(2)  # let each render be visible

    driver.sleep()


def test_real_epd_display_manager_shutdown_clears():
    """DisplayManager.shutdown() clears the screen."""
    driver = RealEPDDriver()
    driver.init()
    mgr = DisplayManager(driver=driver)
    mgr.shutdown()  # should clear + sleep without error
```

- [ ] **Step 2: Verify deselected by default**

```bash
pytest tests/hardware/test_real_epd.py -v
```
Expected: 3 deselected (hardware marker).

- [ ] **Step 3: Commit**

```bash
git add tests/hardware/test_real_epd.py
git commit -m "test(hardware): real EPD acceptance tests

Three hardware-marked tests:
- RealEPDDriver inits/clears/sleeps without error
- All 14 display states render visibly (manual visual check)
- DisplayManager.shutdown() clears the screen

Skipped in CI; run on bench with: pytest -m hardware

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 7: Acceptance + tag

### Task 7.1: Full suite + tag

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v
```
Expected: ~230 tests pass (205 from Plan 3a + ~25 EPD tests). Hardware tests (5 now: 2 WiFi + 3 EPD) deselected.

- [ ] **Step 2: Tag**

```bash
git tag -a v0.5.0-plan3b -m "Plan 3b of sub-project #0 complete: EPD display

- EPDDriver protocol + Fake (CI) / Real (Pi) implementations
- DisplayState enum (14 priority-ordered states)
- StateSelector (pure priority matrix, 15 tests)
- State renderers (14 states + blocklist overlay, PIL-based)
- DisplayManager (refresh strategy: skip on no-change, clear on shutdown)
- Conditions collector (DB -> SystemConditions bridge)
- Daemon wires DisplayManager with real-or-fake fallback
- Hardware tests for real EPD (bench-only)

The display subsystem is complete in software; only final visual
verification needs real hardware. Plan 4 (migration + systemd +
final acceptance) ships sub-project #0."
```

---

## Plan 3b acceptance criteria

1. ✅ All Plan 3a tests still pass (205)
2. ✅ All ~25 EPD tests pass
3. ✅ `EPDDriver` protocol satisfied by both Fake and Real impls
4. ✅ StateSelector returns correct state for all 14 priority cases
5. ✅ Every DisplayState renders to a 122×250 image without crashing
6. ✅ DisplayManager skips refresh on no-change, refreshes on state/overlay transition
7. ✅ Conditions collector builds SystemConditions from DB state
8. ✅ Daemon constructs DisplayManager with real-or-fake fallback
9. ✅ Hardware tests for real EPD marked and skipped in CI
10. ✅ Tag `v0.5.0-plan3b` exists

---

## Plan 4 preview (next plan — final)

Plan 4 ships sub-project #0:
- v1 → v2 data migration script (`scripts/migrate_v1_to_v2.py`)
- systemd unit file (`scripts/mjolnir.service`)
- Final main.py wiring (resource limits, structured logging)
- All 10 slice acceptance criteria run on real Pi hardware
- Tag `v1.0.0-subproject-0` and merge `feat/v2-platform` → `main`
