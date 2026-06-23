# Bjorn v2 Platform — Roadmap

This is the integration roadmap for the v2 effort: turning Bjorn from a network scanner into an autonomous authorized-security-testing platform. Each sub-project goes through its own spec → plan → implementation cycle on a short-lived branch off `feat/v2-platform`.

**Hardware target:** unchanged from v1 — Raspberry Pi Zero 2 W with 2.13" e-Paper HAT. The constraint drives several design choices (single WiFi radio, limited RAM/CPU).

**Intended use:** authorized security research, pentests against owned/lab infrastructure, CTFs, and defensive study. Every sub-project includes scope/authorization guardrails as a first-class concern.

## Branching strategy

- `feat/v2-platform` — long-lived integration branch; all v2 work lands here
- `feat/v2-platform/<sub-project>` — short-lived branch per sub-project, merged back into the integration branch
- `feat/v2-platform` → `main` — merged at v2 milestones

## Sub-project sequence

| # | Sub-project | Status | Spec | Plan |
|---|---|---|---|---|
| 0 | Authorization, scope & audit framework | Brainstorming | TBD | TBD |
| 1 | Connectivity layer (BT tether + Tailscale + multi-SSID priority) | Pending | — | — |
| 2 | Updated web GUI & HTTP targeting API | Pending | — | — |
| 3 | WiFi offensive layer (automated + targeted cracking) | Pending | — | — |
| 4 | Credential attack orchestration | Pending | — | — |
| 5 | Vulnerability discovery & exploitation layer | Pending | — | — |
| 6 | Autonomy & orchestration integration | Pending | — | — |

## Ordering rationale

0 before everything: every offensive subsystem depends on a scope/audit substrate to be safe to build and operate.

1 next: unblocks field use; pure plumbing, no offensive code yet.

2 next: gives us a UI to drive later layers; benefits from connectivity being in place.

3 next: the WiFi offensive layer needs the connectivity layer (to manage the radio) and the GUI (for manual targeting).

4 next: orchestrates credential attacks mostly over existing connectors — fast win once 3 lands.

5 last of the substantive layers: riskiest, depends on everything else, benefits most from a mature audit/scope framework.

6 is the final tie-together: chains 3+4+5 into a goal-driven autonomous loop.

## Definition of done for the v2 effort

- All sub-projects merged into `feat/v2-platform`
- Integration test pass on actual hardware (Zero 2W + e-Paper HAT)
- Authorization framework demonstrably gates every offensive action
- Full audit trail reconstructable from logs
- Documentation updated (README, INSTALL, new docs/)
- Tagged release `v2.0.0`
