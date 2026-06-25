# ADR 0001: multiprocessing fork() test isolation (RESOLVED)

- Status: Resolved
- Date: 2026-06-25

## Context

After Plan 2b Phase 2 (cooperative cancellation via bidirectional `mp.Pipe`), the full test suite went from ~2s to ~150s, and eventually began **deadlocking entirely** (full suite never completes).

Root cause: the subprocess executor (`StageExecutor`) uses `mp.get_context("fork")` on Linux. Forking from a multi-threaded process can deadlock — the DeprecationWarning explicitly flags this. Multiple contamination sources left the pytest process multi-threaded:

1. **NLM tests** constructed `StageExecutor` directly, forking on every `run_once()` call
2. **Flask dev server** (`app.run()`) in the daemon integration test spawned a non-stoppable thread
3. **Dedicated subprocess executor tests** (10 tests) fork as part of their purpose

## Resolution (2026-06-25)

Three changes eliminated the deadlock:

### 1. InProcessExecutor — NLM tests no longer fork

Created `mjolnir/nlm/in_process_executor.py` with `InProcessExecutor` that runs stages in the calling process (same DB, same stage logic, zero forks). `NetworkLifecycleManager` now accepts an injectable `executor` parameter:

- **Production**: `StageExecutor` (subprocess-per-stage with `RLIMIT_AS` isolation)
- **Tests**: `InProcessExecutor` (no fork, instant, full fidelity on scheduling/scope/gate logic)

All NLM manager tests, passive-scan integration tests, and NLM lifecycle tests now use `InProcessExecutor` → 0 forks in the NLM test suite.

### 2. Stoppable Flask server — daemon test no longer leaks threads

Changed `main.py`'s `run_daemon()` from `web_app.run()` (blocks forever, no shutdown API) to `werkzeug.serving.make_server()` (returns a server object with `shutdown()`). On daemon exit: `server.shutdown()` + `web_thread.join(timeout=5)` fully stops Flask before the process returns.

### 3. Subprocess test isolation — remaining forks run separately

The 10 dedicated executor/runner/cooperative-cancel tests MUST fork (they test the subprocess machinery). These are marked `@pytest.mark.subprocess` and excluded from the default run via `addopts = "-m 'not hardware and not subprocess'"`.

- Default `pytest tests/`: **257 tests, 3.66s** — fast, reliable, zero forks
- `pytest tests/ -m subprocess`: **10 tests, ~10s** — the fork/pipe/cancel protocol
- `pytest tests/ -m hardware`: **5 tests** — WiFi + EPD on real Pi (bench-only)

## Consequences

**Positive:**
- Default test suite is fast (3.66s) and never deadlocks
- NLM tests run at full fidelity via InProcessExecutor (real stages, real DB, real scope/gate logic — just no fork)
- Subprocess machinery still fully tested (separate run)
- The `executor` injection point is a clean architecture improvement (test double for execution strategy, not for the stage itself)

**Negative:**
- Two test invocations needed for full coverage (`pytest tests/` + `pytest tests/ -m subprocess`)
- The subprocess tests still emit the `DeprecationWarning` (fork from multi-threaded) — cosmetic, no deadlocks observed when run in isolation

**Future improvement (not needed now):**
Switch `StageExecutor` from `fork` to `spawn` start method. This requires serializing test fixtures through a mechanism that survives re-import (spawn re-imports modules). The `InProcessExecutor` approach makes this unnecessary for now — only the 10 dedicated subprocess tests would benefit, and they run reliably in isolation.
