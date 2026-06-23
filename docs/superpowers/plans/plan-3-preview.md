# Plan 3 Preview — UI Surfaces

**Status:** SCOPE SKETCH — not yet a real plan. Will be expanded into a full TDD plan using the writing-plans skill **after Plan 2 is implemented**.

**Dependency:** Plan 2 (`v0.2.0-plan2`) complete.

## Goal

Build both UI surfaces: the e-Paper display state manager (14 states from spec § "E-Paper display") and the Flask WebUI. After this plan, the operator can see state on the e-Paper and drive the device via the WebUI.

## Architecture summary

- `mjolnir/ui/epd/` — e-Paper display manager
  - `manager.py` — picks one of 14 states by priority (kill switch > fatal error > idle reasons > active work)
  - `states.py` — one render function per state
  - `driver.py` — wraps v1's `waveshare_epd/` library (kept intact from v1)
  - Partial-refresh for counter updates, full-refresh on state transitions
- `mjolnir/ui/web/` — Flask app
  - `app.py` — Flask factory, HTMX integration, no auth in #0
  - `routes/` — one blueprint per area (dashboard, networks, blocklist, settings, audit, etc.)
  - `templates/` — Jinja2 templates, server-rendered, dark theme
  - `static/` — minimal CSS (~5KB), HTMX library (~14KB)

## WebUI endpoints (from spec)

```
/                          Dashboard
/networks                  Networks inventory
/networks/<id>             Network detail
/networks/<id>/hosts/<hid> Host detail
/blocklist                 Blocklist manager
/preferred                 Preferred SSIDs (populated by sub-project #1)
/credentials               All credentials
/loot                      All stolen files
/captures                  WiFi captures
/tunnels                   Active tunnels
/audit                     Action log
/settings                  Mode + kill switch
```

## E-Paper display states (14, from spec, priority order)

1. `SHUTTING_DOWN`
2. `STARTING_UP`
3. `FATAL_ERROR`
4. `KILL_SWITCH_ENGAGED`
5. `NO_INTERFACES_UP`
6. `NO_NETWORKS_VISIBLE`
7. `NO_KNOWN_NETWORKS`
8. `CONNECTING`
9. `NO_INTERNET`
10. `TAILSCALE_DOWN`
11. `ACTIVE_IDLE`
12. `VIEW_ONLY_PASSIVE`
13. `ACTIVE_WORKING` (3 rotating sub-screens)
14. `BLOCKLIST_NEARBY` (overlay banner)

## Milestone

1. Fresh boot shows `STARTING_UP` -> `VIEW_ONLY_PASSIVE` on e-Paper
2. WebUI reachable via SSH port-forward (`ssh pi@bjorn -L 8000:localhost:8000`)
3. Dashboard shows: current mode, kill switch status, summary stats, active work list, recent audit log
4. Networks inventory shows discovered networks with filters
5. Network detail page shows stage progress (11 stages), counters, sub-tabs
6. Blocklist form works — preemptively add network by SSID/BSSID
7. Mode toggle (view_only <-> active) works via WebUI, persists across reboot
8. Kill switch toggle works via WebUI, halts in-flight work within 1s RF / 10s non-RF
9. Persistence authorization flow has confirmation dialogs requiring typed SSID/hostname

## Phase breakdown (rough)

1. **EPD driver adapter** — wrap v1's `waveshare_epd/` cleanly
2. **Display state manager** — priority-based state selection
3. **14 state renderers** — one per state, with layout templates
4. **Partial vs full refresh logic**
5. **Flask app skeleton** — factory, config, no-auth
6. **Dashboard route + template** — pulls from NLM state via repository bundle
7. **Networks inventory + detail routes**
8. **Blocklist form route** — POST handler with idempotent upsert
9. **Settings route** — mode toggle, kill switch
10. **Audit log route** — filter by network, action_type, time
11. **Persistence authorization UI** — two-tier with typed-confirmation dialogs
12. **HTMX integration** — partial-refresh on dashboard, live mode toggle
13. **Tag `v0.3.0-plan3`**

## Things to nail down during implementation

- EPD refresh timing on Zero 2W (v1's `screen_delay` config — we keep this pattern)
- Image rendering: PIL (already in v1's `requirements.txt` as Pillow 9.4.0)
- Template structure: base template + per-route templates, or include-heavy?
- HTMX version pinning
- Testing strategy for templates (snapshot tests? Jinja test client?)
- How the Flask app gets NLM state (shared DB connection? in-process queue?)

## Acceptance

Plan 3 is complete when:
- All Plan 1 + Plan 2 tests still pass
- ~50 new tests for display manager + Flask routes
- All 14 display states render correctly (verifiable via screenshot capture in test)
- WebUI smoke test: every route returns 200
- Mode toggle persists across reboot (verified end-to-end)
- Kill switch via WebUI halts in-flight work
- Tag `v0.3.0-plan3` exists
