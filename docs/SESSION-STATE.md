# Bjorn/mjolnir v2 — Session State

**Last updated:** 2026-06-25
**Branch:** `feat/v2-platform`
**Fork:** `erasmus74/Bjorn` (forked from `infinition/bjorn`)

This document is the "if we lose context, read this first" recovery file. It captures the current state of the v2 effort and points to the documents that hold the actual design and plans.

## Current state

**Sub-project:** #0 of 6 — Network Lifecycle Manager & v2 Architecture
**Status:** Software-complete (`v1.0.0-subproject-0` tagged). Awaits hardware acceptance per `docs/ACCEPTANCE-RUNBOOK.md`.
**Next action:** Run the 10-criteria acceptance runbook on real Pi Zero 2W hardware, then begin sub-project #1 (connectivity).

## Quick navigation

| Document | Purpose |
|---|---|
| `docs/ROADMAP.md` | The 6-sub-project roadmap (ordering + rationale) |
| `docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md` | The design spec for sub-project #0 |
| `docs/superpowers/plans/2026-06-23-sub-project-0-plan-1-foundation.md` | Plan 1: foundation layer (ready to implement) |
| `docs/superpowers/plans/plan-2-preview.md` | Plan 2 scope sketch (NLM + first stage) |
| `docs/superpowers/plans/plan-3-preview.md` | Plan 3 scope sketch (UI) |
| `docs/superpowers/plans/plan-4-preview.md` | Plan 4 scope sketch (migration + acceptance) |
| `docs/decisions/0000-index.md` | ADR index |

## The v2 effort, briefly

v2 turns Bjorn from a network scanner into an autonomous authorized-security-testing platform. Same hardware (Raspberry Pi Zero 2 W + 2.13" e-Paper HAT). Built mostly ground-up alongside v1 (which stays in `v1/` as reference). The new package is called **`mjolnir`** (Thor's hammer — Norse myth theme matches Bjorn = "bear").

Decomposed into 6 ordered sub-projects:

| # | Sub-project | Status |
|---|---|---|
| 0 | Authorization/scope/audit framework + foundation + slice | ✅ Software-complete (`v1.0.0-subproject-0`); awaits hardware acceptance |
| 1 | Connectivity layer (BT tether + Tailscale + multi-SSID priority) | Pending — **CSRF fix (ADR 0002) MUST land here** |
| 2 | Updated WebGUI & HTTP targeting API | Partially absorbed into #0 |
| 3 | WiFi offensive layer (automated + targeted cracking) | Pending |
| 4 | Credential attack orchestration | Pending |
| 5 | Vulnerability discovery & exploitation (incl. persistence) | Pending |
| 6 | Autonomy & orchestration integration | Pending |

## Sub-project #0 — the plan breakdown (all complete)

- **Plan 1 — Foundation** ✅ `v0.1.0-plan1`: config, schema (23 tables), 7 repositories, audit logger, Stage ABC
- **Plan 2a — NLM framework** ✅ `v0.2.0-plan2a`: interfaces, ESS identity, scope checker, gates, subprocess executor
- **Plan 2b — PassiveScanStage + daemon** ✅ `v0.3.0-plan2b`: first concrete stage, cooperative cancellation, main.py daemon loop
- **Plan 3a — Flask WebUI** ✅ `v0.4.0-plan3a`: 10 routes, all operator actions reachable via HTTP
- **Plan 3b — EPD display** ✅ `v0.5.0-plan3b`: 14 priority-ordered states, refresh strategy, conditions collector
- **Plan 4 — Ship** ✅ `v1.0.0-subproject-0`: v1→v2 migration, systemd unit, structured logging, install + acceptance docs

Plans live in `docs/superpowers/plans/`. See `docs/ACCEPTANCE-RUNBOOK.md` for the hardware gate.

## Key design decisions (locked in during brainstorming)

1. **Mode default**: `view_only` on fresh install; **persists across reboots** (operator's choice)
2. **Kill switch**: WebUI-only (no physical button — GPIO fully used by e-Paper HAT)
3. **Persistence stage authorization**: two-tier (network-level AND host-level, both required, both via WebUI with confirmation)
4. **DB**: SQLite (WAL mode, synchronous=NORMAL, foreign_keys=ON, busy_timeout=5s)
5. **Web framework**: Flask + Jinja2 + HTMX (no SPA, no FastAPI)
6. **WebUI binding**: default `127.0.0.1` for Plan 1; `tailscale0` after sub-project #1
7. **Stage execution**: subprocess-per-stage with `RLIMIT_AS` (memory isolation)
8. **Stage list**: 11 stages — `passive_scan`, `wifi_probe`, `wifi_crack`, `lan_enum`, `service_enum`, `credential_attack`, `vuln_scan`, `exploitation`, `privesc`, `lateral_movement`, `persistence`
9. **Stage checkpoint policy**: restart-safe (re-run from start) for discovery stages; checkpointable (resume from disk) for wordlist/exploit/privesc/lateral/persistence
10. **Package name**: `mjolnir` (renamed from `bjorn_v2`)
11. **Schema**: 22 tables covering all 6 sub-projects' data needs up front
12. **Approach**: rebuild (Approach 3) — v1 kept as reference, not modified

## Resume protocol

If you (the operator or future-me) need to resume work after context loss:

1. Read this file
2. Read `docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md` (the full design)
3. Read the current plan being implemented (likely Plan 1)
4. Run `git log --oneline -20` and `git status` to see actual progress
5. Check `tests/` — passing tests = implementation matches plan; failing or missing tests = implementation is mid-task
6. Continue from where `git log` last shows a Plan 1 commit

## Operator preferences (from this session)

- Concise responses; the user is technically strong and trusts design judgment
- Norse mythology theme (Bjorn → mjolnir)
- Wants comprehensive tooling: "kali linux or metasploit framework equivalent" for the platform
- Two-tier persistence authorization is non-negotiable (legal/ethical concern)
- Resource constraints matter (Pi Zero 2W, 512MB RAM, 4-core A53)
- Mode toggling should persist across reboots
- Display should be display-only (no buttons), with idle-reason messaging
- Tailscale-only WebUI access is the end goal (sub-project #1)
- Subagent-driven implementation preferred
