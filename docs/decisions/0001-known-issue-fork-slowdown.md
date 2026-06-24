# ADR 0001: Known issue — multiprocessing fork() slows test suite after Phase 2 (Plan 2b)

- Status: Accepted
- Date: 2026-06-24

## Context

After Plan 2b Phase 2 (cooperative cancellation via bidirectional `mp.Pipe`), the full test suite runtime jumped from ~2s to ~150s. The slowdown is reproducible and order-dependent:

- Running `tests/unit/stages/test_passive_scan.py` alone: 0.04s
- Running `tests/unit/stages/test_passive_scan.py` + `tests/unit/nlm/`: ~22s (passive_scan first, nlm second)
- Running the full suite in alphabetical order: ~150s (nlm tests run first, poisoning the pytest process)

CPython emits a `DeprecationWarning`:
```
This process (pid=...) is multi-threaded, use of fork() may lead to deadlocks in the child.
```

This warning fires because the executor's `watch_kill_switch` thread and the cooperative-cancel `mp.Event` shared state leave the pytest main process in a multi-threaded state. Subsequent `fork()` calls (Python 3.14's default for `multiprocessing`) copy larger page tables and hit internal-lock contention, making each fork progressively slower.

The explicit `mp.get_context("fork")` in `mjolnir/nlm/executor.py` (chosen in Plan 2a Phase 5 so test fixtures that monkey-patch the registry are visible to children) is the proximate cause. `forkserver` or `spawn` would avoid the slowdown but lose the monkey-patch visibility.

## Decision

Accept the slowdown as a known issue for now. Tests pass; correctness is unaffected; the slowness is a development-experience cost, not a production cost.

Workarounds for fast iteration during development:
- `pytest tests/unit/stages/ tests/unit/db/` — fast (no subprocess tests)
- `pytest -k "not executor and not cooperative and not manager"` — skip the subprocess-heavy tests
- The full `pytest tests/` run is the "before commit / before tag" gate; expect ~2.5 minutes

## Consequences

**Positive:**
- Test fixtures can monkey-patch module-level state (registry, WiFiInterface) and the changes are visible to forked children — this is load-bearing for the cooperative-cancel and passive-scan integration tests
- No need for a separate "stage runner" CLI script (which spawn/forkserver would require)

**Negative:**
- Full suite takes ~150s instead of ~2s
- Fork-from-multi-threaded-process warning on stderr (cosmetic; no actual deadlocks observed)

**Future fix options (not pursued now):**
- Make the executor's watcher threads fully joinable so the pytest process returns to single-threaded between tests
- Switch to `mp.get_context("spawn")` and serialize test fixtures through a shared config file or environment variables instead of monkey-patching
- Run subprocess-heavy tests in a subprocess of pytest itself (`pytest-forked` or similar)
- Migrate to a test-double architecture where the executor accepts an injectable `ProcessFactory` so tests don't fork at all
