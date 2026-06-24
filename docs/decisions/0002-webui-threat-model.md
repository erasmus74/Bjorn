# ADR 0002: WebUI threat model — trusted context, no rate limiting; sensitive-data display deferred

- Status: Accepted
- Date: 2026-06-24

## Context

Automated security review of the Plan 3a WebUI commits flagged two findings:

1. **DENIAL OF SERVICE - NO RATE LIMITING** in `mjolnir/ui/web/routes.py`
2. **SENSITIVE-TO-OBSERVABILITY** in `mjolnir/ui/web/routes.py`

## Decision

Both findings are acknowledged but neither is fixed in code now. The reasoning differs.

### Finding 1: No rate limiting — intentionally absent

The WebUI threat model (from spec § UI surfaces) is:

- **Single-user, trusted-context.** One operator drives the device.
- **Not public-facing.** Bound to `127.0.0.1` in sub-project #0 (SSH port-forward access only). Sub-project #1 changes the bind to `tailscale0` — still not public, only reachable from the operator's tailnet.
- **No unauthenticated clients.** Anyone who can reach the WebUI already has SSH-equivalent trust (they're on the tailnet or have tunneled in).

Rate limiting protects a public endpoint from a flood of unauthenticated requests. There is no such flood vector here. Adding rate limiting would:

- Interfere with HTMX partial-refresh polling (the dashboard polls every 2s)
- Add complexity for no security gain
- Create false confidence (rate limits don't help if the attacker is already on the tailnet)

**Action:** Document the threat model here. Do not add rate limiting. Revisit if the bind interface ever becomes publicly routable (it shouldn't).

### Finding 2: Sensitive-to-observability — deferred to when it actually applies

The current WebUI routes (`/`, `/networks`, `/networks/<id>`, `/blocklist`, `/settings`, `/audit`) do **not** display plaintext secrets:

- `/audit` shows `details_json`, which currently contains action metadata (wordlist names, line numbers, observation counts) — not credentials themselves
- No `/credentials` or `/loot` route exists yet (those are spec'd but deferred to sub-projects #3-#5 when the underlying data exists)
- WiFi PSKs in the `credentials` table are not rendered anywhere in the UI today

The finding becomes real when `/credentials` and `/loot` land. At that point, rendering plaintext secrets in HTML means they live in:

- Browser memory and tab state
- Browser history / cache
- Any screenshot or screen-share
- HTML in the response body (visible to anything logging HTTP traffic)

**Action:** When `/credentials` and `/loot` routes are implemented (sub-projects #3-#5), they MUST use a "click to reveal" pattern:

- Secrets masked by default (`••••••••`)
- A per-row button that fetches the plaintext via a separate POST (so it's not in the initial page render)
- The reveal endpoint logs to `action_log` (every secret view is auditable)

This is captured here so it isn't forgotten when those routes are built. No code change in Plan 3a.

## Consequences

**Positive:**
- Plan 3a ships without security-theater complexity
- Threat model is explicit and auditable
- The click-to-reveal requirement is documented for future implementers

**Negative:**
- A future reviewer running the same scanner will see the same finding; they'll need to find this ADR to understand why it's accepted
- If the bind interface ever becomes public (against the spec), the lack of rate limiting becomes a real vulnerability

**Tracking:**
- Revisit Finding 2 when `/credentials` route is implemented (sub-project #3 or #4)
- Revisit Finding 1 if the bind interface changes from `tailscale0`/`127.0.0.1` to anything public
