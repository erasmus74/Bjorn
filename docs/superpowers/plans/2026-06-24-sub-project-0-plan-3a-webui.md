# Sub-project #0 — Plan 3a of 4: Flask WebUI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Flask WebUI that lets the operator drive mjolnir: view networks discovered, toggle global mode (view_only ↔ active), manage the blocklist, preemptively add networks, engage/release the kill switch, view the audit log, and authorize persistence on specific networks/hosts (two-tier confirmation). After this plan, every operator action in the spec is reachable via HTTP.

**Architecture:** Flask app factory + Jinja2 templates + HTMX for partial refresh. No SPA, no auth in #0 (bind to `127.0.0.1`, SSH port-forward access). Reads NLM state via the repository bundle from Plan 1; writes via the same repositories. Single dark-theme CSS, server-rendered.

**Tech Stack:** Python 3.11+, Flask 3.x (already in requirements), Jinja2 (Flask dep), HTMX 2.x (static file, no build step). pytest + Flask test client for tests.

**Spec reference:** `docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md` § UI surfaces
**Depends on:** `v0.3.0-plan2b` (NLM framework + PassiveScanStage complete)

**Branch:** `feat/v2-platform`

---

## File structure (Plan 3a scope)

```
mjolnir/
├── ui/
│   ├── __init__.py
│   └── web/
│       ├── __init__.py
│       ├── app.py                     ← Flask app factory
│       ├── routes.py                  ← All HTTP routes (single module; small app)
│       └── templates/
│           ├── base.html              ← Layout: nav + content block
│           ├── dashboard.html
│           ├── networks.html
│           ├── network_detail.html
│           ├── blocklist.html
│           ├── preferred_ssids.html
│           ├── audit.html
│           ├── settings.html
│           └── _partials/             ← HTMX partial responses
│               ├── _mode_badge.html
│               └── _recent_actions.html
└── (existing files unchanged)

tests/
└── unit/
    └── ui/
        └── web/
            ├── test_app.py            ← App factory + config
            ├── test_routes_dashboard.py
            ├── test_routes_networks.py
            ├── test_routes_blocklist.py
            ├── test_routes_settings.py
            └── test_routes_audit.py
```

Files NOT in Plan 3a (deferred to Plan 3b):
- `mjolnir/ui/epd/` — e-Paper display manager + 14 state renderers
- Real HTMX library file (downloaded to `static/` in Plan 3b or Phase 7 of 3a)

---

## Conventions

(same as Plans 1, 2a, 2b — TDD, conventional commits, type hints, dataclasses, no comments unless WHY is non-obvious)

---

## Phase 1: Flask app skeleton + dashboard

### Task 1.1: Flask app factory

**Files:**
- Create: `mjolnir/ui/__init__.py`
- Create: `mjolnir/ui/web/__init__.py`
- Create: `mjolnir/ui/web/app.py`
- Test: `tests/unit/ui/web/test_app.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/web/test_app.py
"""Tests for the Flask app factory."""
import pytest
from pathlib import Path

from mjolnir.ui.web.app import create_app
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner


@pytest.fixture
def app(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg)


def test_create_app_returns_flask_app(app):
    from flask import Flask
    assert isinstance(app, Flask)


def test_app_has_db_path_attribute(app):
    assert app.config["MJOLNIR_DB_PATH"] is not None


def test_app_test_client_returns_404_for_unknown_route(app):
    client = app.test_client()
    response = client.get("/nonexistent")
    assert response.status_code == 404


def test_app_dashboard_route_returns_200(app):
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"mjolnir" in response.data.lower() or b"Mjolnir" in response.data
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/ui/web/test_app.py -v
```

- [ ] **Step 3: Write `mjolnir/ui/__init__.py`**

```python
"""Operator-facing UI surfaces: WebUI (Plan 3a) + EPD display (Plan 3b)."""
```

- [ ] **Step 4: Write `mjolnir/ui/web/__init__.py`**

```python
"""Flask WebUI for mjolnir."""
```

- [ ] **Step 5: Write `mjolnir/ui/web/app.py`**

```python
"""Flask app factory for mjolnir's WebUI.

Single-user, trusted-context app. No auth in sub-project #0 (bind to
127.0.0.1, SSH port-forward access). Reads NLM state via repository
bundle from Plan 1; writes via same repositories.
"""
from pathlib import Path

from flask import Flask, render_template

from mjolnir.config import BjornConfig


def create_app(config: BjornConfig) -> Flask:
    app = Flask(__name__)
    app.config["MJOLNIR_CONFIG"] = config
    app.config["MJOLNIR_DB_PATH"] = str(config.db.path)

    from mjolnir.ui.web.routes import register_routes
    register_routes(app)

    return app
```

- [ ] **Step 6: Create `mjolnir/ui/web/routes.py`** (minimal, just the dashboard for now)

```python
"""HTTP routes for mjolnir's WebUI."""
from flask import Flask, render_template

from mjolnir.config import BjornConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories import bundle_for


def _get_bundle(app: Flask):
    db_path = app.config["MJOLNIR_DB_PATH"]
    factory = ConnectionFactory(db_path=db_path)
    conn = factory.connect()
    return conn, bundle_for(conn)


def register_routes(app: Flask) -> None:

    @app.route("/")
    def dashboard():
        conn, bundle = _get_bundle(app)
        try:
            global_mode = bundle.system_state.get_global_mode()
            kill_switch_engaged = bundle.system_state.is_kill_switch_engaged()
            networks = bundle.networks.list_eligible_for_processing()
            recent_actions = bundle.action_log.list_recent(limit=20)
            return render_template(
                "dashboard.html",
                global_mode=global_mode,
                kill_switch_engaged=kill_switch_engaged,
                networks=networks,
                recent_actions=recent_actions,
            )
        finally:
            conn.close()
```

- [ ] **Step 7: Create `mjolnir/ui/web/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}mjolnir{% endblock %}</title>
    <style>
        :root {
            --bg: #0d1117;
            --fg: #c9d1d9;
            --accent: #58a6ff;
            --danger: #f85149;
            --success: #3fb950;
            --warn: #d29922;
            --muted: #8b949e;
            --border: #30363d;
        }
        body {
            background: var(--bg);
            color: var(--fg);
            font-family: -apple-system, sans-serif;
            margin: 0;
            padding: 1rem;
        }
        nav { margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }
        nav a { color: var(--accent); margin-right: 1rem; text-decoration: none; }
        nav a:hover { text-decoration: underline; }
        h1, h2 { color: var(--fg); }
        .badge { padding: 0.2rem 0.5rem; border-radius: 3px; font-size: 0.85rem; font-weight: bold; }
        .badge-active { background: var(--danger); color: white; }
        .badge-view-only { background: var(--success); color: white; }
        .badge-killed { background: var(--warn); color: var(--bg); }
        table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
        th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
        th { color: var(--muted); font-size: 0.85rem; text-transform: uppercase; }
        form { margin: 1rem 0; }
        button, input[type="submit"] {
            background: var(--accent); color: var(--bg); border: none;
            padding: 0.5rem 1rem; border-radius: 3px; cursor: pointer; font-weight: bold;
        }
        button:hover { opacity: 0.9; }
        button.danger { background: var(--danger); color: white; }
        input[type="text"] {
            background: #161b22; color: var(--fg); border: 1px solid var(--border);
            padding: 0.4rem; border-radius: 3px; width: 100%; box-sizing: border-box;
        }
        .danger-zone { border: 1px solid var(--danger); padding: 1rem; border-radius: 5px; margin: 1rem 0; }
        .muted { color: var(--muted); }
    </style>
</head>
<body>
    <nav>
        <strong>mjolnir</strong>
        <a href="/">Dashboard</a>
        <a href="/networks">Networks</a>
        <a href="/blocklist">Blocklist</a>
        <a href="/audit">Audit Log</a>
        <a href="/settings">Settings</a>
    </nav>
    {% block content %}{% endblock %}
</body>
</html>
```

- [ ] **Step 8: Create `mjolnir/ui/web/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}mjolnir — Dashboard{% endblock %}
{% block content %}
<h1>Dashboard</h1>

<p>
    Mode:
    {% if global_mode == "active" %}
        <span class="badge badge-active">ACTIVE</span>
    {% else %}
        <span class="badge badge-view-only">VIEW-ONLY</span>
    {% endif %}
    {% if kill_switch_engaged %}
        <span class="badge badge-killed">KILL SWITCH ENGAGED</span>
    {% endif %}
</p>

<h2>Networks ({{ networks|length }} eligible)</h2>
{% if networks %}
<table>
    <tr><th>SSID</th><th>Security</th><th>Last Seen</th><th>Current Stage</th></tr>
    {% for net in networks %}
    <tr>
        <td><a href="/networks/{{ net.id }}">{{ net.ssid }}{% if net.disambiguator > 1 %} #{{ net.disambiguator }}{% endif %}</a></td>
        <td>{{ net.security_type or "unknown" }}</td>
        <td>{{ net.last_seen or "never" }}</td>
        <td>{{ net.current_stage or "—" }}</td>
    </tr>
    {% endfor %}
</table>
{% else %}
<p class="muted">No networks discovered yet. Ensure the NLM daemon is running.</p>
{% endif %}

<h2>Recent Actions</h2>
{% if recent_actions %}
<table>
    <tr><th>Time</th><th>Action</th><th>Mode</th><th>Outcome</th></tr>
    {% for action in recent_actions %}
    <tr>
        <td>{{ action.timestamp }}</td>
        <td>{{ action.action_type }}</td>
        <td>{{ action.global_mode }}</td>
        <td>{{ action.outcome }}</td>
    </tr>
    {% endfor %}
</table>
{% else %}
<p class="muted">No actions logged yet.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 9: Run tests to verify pass**

```bash
pytest tests/unit/ui/web/test_app.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 10: Commit**

```bash
git add mjolnir/ui/ tests/unit/ui/web/test_app.py
git commit -m "feat(ui): Flask app factory + dashboard route

App factory wires config + DB path; dashboard route reads global_mode,
kill_switch, eligible networks, recent audit log via repository
bundle. Base template with dark theme and nav.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 2: Networks inventory + detail

### Task 2.1: Networks inventory route

**Files:**
- Modify: `mjolnir/ui/web/routes.py`
- Create: `mjolnir/ui/web/templates/networks.html`
- Test: `tests/unit/ui/web/test_routes_networks.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/web/test_routes_networks.py
"""Tests for the networks inventory + detail routes."""
import pytest

from mjolnir.ui.web.app import create_app
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def client(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    # Seed a couple of networks
    n1 = bundle.networks.create(ssid="HomeWiFi", security_type="WPA2")
    n2 = bundle.networks.create(ssid="CoffeeShop", security_type="open")
    bundle.bssids.upsert(network_id=n1.id, bssid="aa:bb:cc:dd:ee:01", signal_dbm=-42)
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client(), (n1.id, n2.id)


def test_networks_inventory_returns_200(client):
    c, _ = client
    response = c.get("/networks")
    assert response.status_code == 200


def test_networks_inventory_lists_seed_networks(client):
    c, _ = client
    response = c.get("/networks")
    assert b"HomeWiFi" in response.data
    assert b"CoffeeShop" in response.data


def test_network_detail_returns_200_for_existing_network(client):
    c, (n1_id, _) = client
    response = c.get(f"/networks/{n1_id}")
    assert response.status_code == 200
    assert b"HomeWiFi" in response.data


def test_network_detail_shows_bssids(client):
    c, (n1_id, _) = client
    response = c.get(f"/networks/{n1_id}")
    assert b"aa:bb:cc:dd:ee:01" in response.data


def test_network_detail_returns_404_for_missing_network(client):
    c, _ = client
    response = c.get("/networks/99999")
    assert response.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add routes to `mjolnir/ui/web/routes.py`**

Append inside `register_routes`:

```python
    @app.route("/networks")
    def networks_inventory():
        conn, bundle = _get_bundle(app)
        try:
            networks = bundle.networks.list_eligible_for_processing()
            return render_template("networks.html", networks=networks)
        finally:
            conn.close()

    @app.route("/networks/<int:network_id>")
    def network_detail(network_id: int):
        conn, bundle = _get_bundle(app)
        try:
            network = bundle.networks.get_by_id(network_id)
            if network is None:
                return "Network not found", 404
            bssids = bundle.bssids.list_for_network(network_id)
            actions = bundle.action_log.list_for_network(network_id, limit=50)
            return render_template(
                "network_detail.html",
                network=network,
                bssids=bssids,
                actions=actions,
            )
        finally:
            conn.close()
```

- [ ] **Step 4: Create `mjolnir/ui/web/templates/networks.html`**

```html
{% extends "base.html" %}
{% block title %}mjolnir — Networks{% endblock %}
{% block content %}
<h1>Networks</h1>
{% if networks %}
<table>
    <tr>
        <th>SSID</th><th>Disambiguator</th><th>Security</th>
        <th>Scope</th><th>Last Seen</th><th>Stage</th><th>Exhausted</th>
    </tr>
    {% for net in networks %}
    <tr>
        <td><a href="/networks/{{ net.id }}">{{ net.ssid }}</a></td>
        <td>#{{ net.disambiguator }}</td>
        <td>{{ net.security_type or "unknown" }}</td>
        <td>{{ net.scope_state }}</td>
        <td>{{ net.last_seen or "never" }}</td>
        <td>{{ net.current_stage or "—" }}</td>
        <td>{% if net.exhausted %}yes{% else %}no{% endif %}</td>
    </tr>
    {% endfor %}
</table>
{% else %}
<p class="muted">No networks discovered yet.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Create `mjolnir/ui/web/templates/network_detail.html`**

```html
{% extends "base.html" %}
{% block title %}mjolnir — {{ network.ssid }}{% endblock %}
{% block content %}
<h1>{{ network.ssid }}{% if network.disambiguator > 1 %} #{{ network.disambiguator }}{% endif %}</h1>

<p>
    <strong>Security:</strong> {{ network.security_type or "unknown" }}<br>
    <strong>Scope:</strong> {{ network.scope_state }}<br>
    <strong>First seen:</strong> {{ network.first_seen }}<br>
    <strong>Last seen:</strong> {{ network.last_seen or "never" }}<br>
    <strong>Current stage:</strong> {{ network.current_stage or "—" }}<br>
    <strong>Exhausted:</strong> {% if network.exhausted %}yes ({{ network.exhausted_reason }}){% else %}no{% endif %}
</p>

<h2>BSSIDs ({{ bssids|length }})</h2>
{% if bssids %}
<table>
    <tr><th>BSSID</th><th>Channel</th><th>Signal (dBm)</th><th>Last Seen</th></tr>
    {% for b in bssids %}
    <tr>
        <td>{{ b.bssid }}</td>
        <td>{{ b.channel or "—" }}</td>
        <td>{{ b.last_signal_dbm or "—" }}</td>
        <td>{{ b.last_seen }}</td>
    </tr>
    {% endfor %}
</table>
{% else %}
<p class="muted">No BSSIDs recorded.</p>
{% endif %}

<h2>Recent Actions (this network)</h2>
{% if actions %}
<table>
    <tr><th>Time</th><th>Action</th><th>Outcome</th><th>Scope Basis</th></tr>
    {% for a in actions %}
    <tr>
        <td>{{ a.timestamp }}</td>
        <td>{{ a.action_type }}</td>
        <td>{{ a.outcome }}</td>
        <td>{{ a.scope_basis }}</td>
    </tr>
    {% endfor %}
</table>
{% else %}
<p class="muted">No actions for this network.</p>
{% endif %}

<div class="danger-zone">
    <h2>Persistence Authorization</h2>
    <p class="muted">
        Persistence modifies target systems. Requires both network-level
        and (for specific hosts) host-level authorization.
    </p>
    <form method="post" action="/networks/{{ network.id }}/persistence">
        {% if network.persistence_authorized %}
            <p>Network persistence is <strong>authorized</strong> by {{ network.persistence_authorized_by }} at {{ network.persistence_authorized_at }}.</p>
            <button type="submit" class="danger" name="action" value="revoke">Revoke Network Authorization</button>
        {% else %}
            <p>Network persistence is <strong>not authorized</strong>.</p>
            <label>Confirm by typing the SSID "{{ network.ssid }}":
                <input type="text" name="confirm_ssid" required>
            </label>
            <button type="submit" name="action" value="grant">Authorize Persistence on This Network</button>
        {% endif %}
    </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Run tests to verify pass**

```bash
pytest tests/unit/ui/web/test_routes_networks.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add mjolnir/ui/web/routes.py mjolnir/ui/web/templates/networks.html mjolnir/ui/web/templates/network_detail.html tests/unit/ui/web/test_routes_networks.py
git commit -m "feat(ui): networks inventory + detail routes

Networks inventory lists all eligible networks. Network detail shows
BSSIDs, recent actions, and the persistence authorization danger
zone with two-tier confirmation flow.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 3: Settings (mode toggle + kill switch)

### Task 3.1: Settings route with mode/kill-switch controls

**Files:**
- Modify: `mjolnir/ui/web/routes.py`
- Create: `mjolnir/ui/web/templates/settings.html`
- Test: `tests/unit/ui/web/test_routes_settings.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/web/test_routes_settings.py
"""Tests for the settings route (mode toggle + kill switch)."""
import pytest

from mjolnir.ui.web.app import create_app
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def client(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client()


def test_settings_get_returns_200(client):
    response = client.get("/settings")
    assert response.status_code == 200


def test_settings_shows_current_mode(client):
    response = client.get("/settings")
    # Default mode is view_only
    assert b"view" in response.data.lower()


def test_toggle_mode_to_active_persists(client, tmp_path):
    response = client.post("/settings/mode", data={"mode": "active"})
    assert response.status_code in (200, 302)  # 302 if redirect, 200 if HTMX partial

    # Verify mode persisted in DB
    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    assert bundle.system_state.get_global_mode() == "active"
    conn.close()


def test_toggle_mode_to_invalid_value_rejected(client):
    response = client.post("/settings/mode", data={"mode": "bogus"})
    assert response.status_code == 400


def test_toggle_mode_writes_audit_log(client, tmp_path):
    client.post("/settings/mode", data={"mode": "active"})
    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    rows = bundle.action_log.list_recent(limit=5)
    assert any(r.action_type == "mode_transition" for r in rows)
    conn.close()


def test_engage_kill_switch(client, tmp_path):
    response = client.post("/settings/kill_switch", data={"action": "engage"})
    assert response.status_code in (200, 302)
    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    assert bundle.system_state.is_kill_switch_engaged() is True
    conn.close()


def test_release_kill_switch(client, tmp_path):
    client.post("/settings/kill_switch", data={"action": "engage"})
    client.post("/settings/kill_switch", data={"action": "release"})
    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    assert bundle.system_state.is_kill_switch_engaged() is False
    conn.close()
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add routes to `mjolnir/ui/web/routes.py`**

```python
    from flask import request, redirect, url_for

    @app.route("/settings")
    def settings():
        conn, bundle = _get_bundle(app)
        try:
            return render_template(
                "settings.html",
                global_mode=bundle.system_state.get_global_mode(),
                kill_switch_engaged=bundle.system_state.is_kill_switch_engaged(),
            )
        finally:
            conn.close()

    @app.route("/settings/mode", methods=["POST"])
    def toggle_mode():
        new_mode = request.form.get("mode")
        if new_mode not in ("view_only", "active"):
            return "invalid mode", 400

        conn, bundle = _get_bundle(app)
        try:
            from mjolnir.audit.logger import AuditLogger, ScopeBasis
            audit = AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)
            old_mode = bundle.system_state.get_global_mode()
            bundle.system_state.set_global_mode(new_mode)
            audit.log_mode_transition(old_mode, new_mode,
                                       scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE)
        finally:
            conn.close()
        return redirect(url_for("settings"))

    @app.route("/settings/kill_switch", methods=["POST"])
    def toggle_kill_switch():
        action = request.form.get("action")
        if action not in ("engage", "release"):
            return "invalid action", 400

        conn, bundle = _get_bundle(app)
        try:
            if action == "engage":
                bundle.system_state.engage_kill_switch()
            else:
                bundle.system_state.release_kill_switch()
        finally:
            conn.close()
        return redirect(url_for("settings"))
```

- [ ] **Step 4: Create `mjolnir/ui/web/templates/settings.html`**

```html
{% extends "base.html" %}
{% block title %}mjolnir — Settings{% endblock %}
{% block content %}
<h1>Settings</h1>

<h2>Global Mode</h2>
<p>
    Current mode:
    {% if global_mode == "active" %}
        <span class="badge badge-active">ACTIVE</span>
    {% else %}
        <span class="badge badge-view-only">VIEW-ONLY</span>
    {% endif %}
</p>
<p class="muted">
    ACTIVE mode enables offensive stages (WiFi crack, credential attacks, exploitation).
    VIEW-ONLY mode allows only passive observation. The choice persists across reboots.
</p>
<form method="post" action="/settings/mode">
    {% if global_mode == "view_only" %}
        <input type="hidden" name="mode" value="active">
        <button type="submit" class="danger">Activate (enable offensive operations)</button>
    {% else %}
        <input type="hidden" name="mode" value="view_only">
        <button type="submit">Return to View-Only</button>
    {% endif %}
</form>

<h2>Kill Switch</h2>
<p>
    Status: {% if kill_switch_engaged %}<span class="badge badge-killed">ENGAGED</span>{% else %}released{% endif %}
</p>
<p class="muted">
    Engaging the kill switch halts all in-flight offensive work within ~1 second (RF)
    or ~10 seconds (non-RF). In-flight stages save progress where possible.
</p>
<form method="post" action="/settings/kill_switch">
    {% if kill_switch_engaged %}
        <input type="hidden" name="action" value="release">
        <button type="submit">Release Kill Switch</button>
    {% else %}
        <input type="hidden" name="action" value="engage">
        <button type="submit" class="danger">Engage Kill Switch</button>
    {% endif %}
</form>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/ui/web/test_routes_settings.py -v
```
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/ui/web/routes.py mjolnir/ui/web/templates/settings.html tests/unit/ui/web/test_routes_settings.py
git commit -m "feat(ui): settings route (mode toggle + kill switch)

GET /settings shows current mode and kill-switch status. POST
/settings/mode toggles view_only<->active, validates value, writes
audit log mode_transition row. POST /settings/kill_switch engages
or releases.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4: Blocklist management

### Task 4.1: Blocklist form + preemptive add

**Files:**
- Modify: `mjolnir/ui/web/routes.py`
- Create: `mjolnir/ui/web/templates/blocklist.html`
- Test: `tests/unit/ui/web/test_routes_blocklist.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/web/test_routes_blocklist.py
"""Tests for the blocklist management routes."""
import pytest

from mjolnir.ui.web.app import create_app
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def client(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    # Seed: one blocklisted, one enabled
    blocked = bundle.networks.create(ssid="MyHome", security_type="WPA2")
    bundle.networks.update_scope_state(blocked.id, "blocklisted", reason="my home", by="operator")
    enabled = bundle.networks.create(ssid="Target", security_type="WPA2")
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client(), (blocked.id, enabled.id)


def test_blocklist_get_returns_200(client):
    c, _ = client
    response = c.get("/blocklist")
    assert response.status_code == 200


def test_blocklist_lists_blocklisted_networks(client):
    c, _ = client
    response = c.get("/blocklist")
    assert b"MyHome" in response.data
    # Target is enabled, not blocklisted, so shouldn't appear in blocklist view
    assert b"Target" not in response.data


def test_blocklist_add_preemptive_creates_network(client, tmp_path):
    c, _ = client
    response = c.post("/blocklist", data={
        "ssid": "PreemptivelyBlocked",
        "reason": "do not touch",
    })
    assert response.status_code in (200, 302)

    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    matches = bundle.networks.find_by_ssid("PreemptivelyBlocked")
    assert len(matches) == 1
    assert matches[0].scope_state == "blocklisted"
    assert matches[0].blocklist_reason == "do not touch"
    conn.close()


def test_blocklist_unblock_network(client, tmp_path):
    c, (blocked_id, _) = client
    response = c.post(f"/networks/{blocked_id}/scope", data={
        "scope_state": "enabled",
    })
    assert response.status_code in (200, 302)

    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    net = bundle.networks.get_by_id(blocked_id)
    assert net.scope_state == "enabled"
    conn.close()


def test_blocklist_add_requires_ssid(client):
    c, _ = client
    response = c.post("/blocklist", data={"reason": "no ssid"})
    assert response.status_code == 400
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add routes to `mjolnir/ui/web/routes.py`**

```python
    @app.route("/blocklist")
    def blocklist():
        conn, bundle = _get_bundle(app)
        try:
            # All networks with scope_state = 'blocklisted'
            from mjolnir.db.repositories.networks import Network
            cursor = bundle.networks.conn.execute(
                "SELECT * FROM networks WHERE scope_state = 'blocklisted' ORDER BY ssid"
            )
            blocked = [Network.from_row(r) for r in cursor.fetchall()]
            return render_template("blocklist.html", blocked=blocked)
        finally:
            conn.close()

    @app.route("/blocklist", methods=["POST"])
    def blocklist_add():
        ssid = request.form.get("ssid", "").strip()
        reason = request.form.get("reason", "").strip() or None
        if not ssid:
            return "ssid is required", 400

        conn, bundle = _get_bundle(app)
        try:
            net = bundle.networks.create(ssid=ssid)
            bundle.networks.update_scope_state(net.id, "blocklisted", reason=reason, by="operator")
        finally:
            conn.close()
        return redirect(url_for("blocklist"))

    @app.route("/networks/<int:network_id>/scope", methods=["POST"])
    def update_network_scope(network_id: int):
        new_state = request.form.get("scope_state")
        if new_state not in ("enabled", "disabled", "blocklisted"):
            return "invalid scope_state", 400

        conn, bundle = _get_bundle(app)
        try:
            bundle.networks.update_scope_state(network_id, new_state, by="operator")
        finally:
            conn.close()
        return redirect(url_for("network_detail", network_id=network_id))
```

- [ ] **Step 4: Create `mjolnir/ui/web/templates/blocklist.html`**

```html
{% extends "base.html" %}
{% block title %}mjolnir — Blocklist{% endblock %}
{% block content %}
<h1>Blocklist</h1>

<h2>Add Network to Blocklist</h2>
<p class="muted">Preemptively add a network by SSID so mjolnir never attempts offensive operations against it, even if discovered.</p>
<form method="post" action="/blocklist">
    <label>SSID: <input type="text" name="ssid" required></label>
    <label>Reason: <input type="text" name="reason"></label>
    <button type="submit">Add to Blocklist</button>
</form>

<h2>Blocklisted Networks ({{ blocked|length }})</h2>
{% if blocked %}
<table>
    <tr><th>SSID</th><th>Reason</th><th>Added</th><th>Actions</th></tr>
    {% for net in blocked %}
    <tr>
        <td>{{ net.ssid }}{% if net.disambiguator > 1 %} #{{ net.disambiguator }}{% endif %}</td>
        <td>{{ net.blocklist_reason or "—" }}</td>
        <td>{{ net.scope_changed_at or "—" }}</td>
        <td>
            <form method="post" action="/networks/{{ net.id }}/scope" style="display:inline">
                <input type="hidden" name="scope_state" value="enabled">
                <button type="submit">Unblock</button>
            </form>
        </td>
    </tr>
    {% endfor %}
</table>
{% else %}
<p class="muted">No blocklisted networks.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/ui/web/test_routes_blocklist.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/ui/web/routes.py mjolnir/ui/web/templates/blocklist.html tests/unit/ui/web/test_routes_blocklist.py
git commit -m "feat(ui): blocklist management routes

GET /blocklist lists blocklisted networks. POST /blocklist preemptively
adds a network by SSID. POST /networks/<id>/scope changes scope_state
(enabled/disabled/blocklisted) for any network.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 5: Audit log view

### Task 5.1: Audit log route

**Files:**
- Modify: `mjolnir/ui/web/routes.py`
- Create: `mjolnir/ui/web/templates/audit.html`
- Test: `tests/unit/ui/web/test_routes_audit.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/web/test_routes_audit.py
"""Tests for the audit log route."""
import pytest

from mjolnir.ui.web.app import create_app
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.audit.logger import AuditLogger, ScopeBasis


@pytest.fixture
def client(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    # Seed some audit entries
    audit = AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)
    audit.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE,
        action_type="passive_scan.started",
        outcome="started",
    )
    audit.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE,
        action_type="passive_scan.succeeded",
        outcome="completed",
        details={"observations_count": "3"},
    )
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client()


def test_audit_get_returns_200(client):
    response = client.get("/audit")
    assert response.status_code == 200


def test_audit_shows_logged_actions(client):
    response = client.get("/audit")
    assert b"passive_scan.started" in response.data
    assert b"passive_scan.succeeded" in response.data


def test_audit_shows_scope_basis(client):
    response = client.get("/audit")
    assert b"operator-confirmed-active-mode" in response.data
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add route to `mjolnir/ui/web/routes.py`**

```python
    @app.route("/audit")
    def audit_log():
        conn, bundle = _get_bundle(app)
        try:
            actions = bundle.action_log.list_recent(limit=200)
            return render_template("audit.html", actions=actions)
        finally:
            conn.close()
```

- [ ] **Step 4: Create `mjolnir/ui/web/templates/audit.html`**

```html
{% extends "base.html" %}
{% block title %}mjolnir — Audit Log{% endblock %}
{% block content %}
<h1>Audit Log (last 200)</h1>
{% if actions %}
<table>
    <tr>
        <th>Timestamp</th><th>Mode</th><th>Action</th><th>Outcome</th>
        <th>Scope Basis</th><th>Network</th><th>Details</th>
    </tr>
    {% for a in actions %}
    <tr>
        <td>{{ a.timestamp }}</td>
        <td>{{ a.global_mode }}</td>
        <td>{{ a.action_type }}</td>
        <td>{{ a.outcome }}</td>
        <td>{{ a.scope_basis }}</td>
        <td>{% if a.target_network_id %}<a href="/networks/{{ a.target_network_id }}">{{ a.target_network_id }}</a>{% else %}—{% endif %}</td>
        <td class="muted" style="font-family: monospace; font-size: 0.85rem;">{{ a.details_json or "" }}</td>
    </tr>
    {% endfor %}
</table>
{% else %}
<p class="muted">No actions logged.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/unit/ui/web/test_routes_audit.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add mjolnir/ui/web/routes.py mjolnir/ui/web/templates/audit.html tests/unit/ui/web/test_routes_audit.py
git commit -m "feat(ui): audit log route

GET /audit lists last 200 audit actions with timestamp, mode, action,
outcome, scope_basis, target network, and details_json.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 6: Persistence authorization handler

### Task 6.1: Two-tier persistence authorization POST handler

**Files:**
- Modify: `mjolnir/ui/web/routes.py`
- Test: `tests/unit/ui/web/test_routes_persistence.py`

The form is already in `network_detail.html` (Phase 2). This task adds the POST handler.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/ui/web/test_routes_persistence.py
"""Tests for the two-tier persistence authorization handler."""
import pytest

from mjolnir.ui.web.app import create_app
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def client(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    net = bundle.networks.create(ssid="TargetNet", security_type="WPA2")
    conn.close()

    cfg = BjornConfig(
        paths=PathsConfig(data_dir=tmp_path, log_dir=tmp_path / "logs"),
        db=DbConfig(data_dir=tmp_path, filename="x.db"),
    )
    return create_app(cfg).test_client(), net.id


def test_persistence_grant_requires_typed_ssid_confirmation(client):
    c, net_id = client
    # Wrong SSID → should fail
    response = c.post(f"/networks/{net_id}/persistence", data={
        "action": "grant",
        "confirm_ssid": "WrongNet",
    })
    assert response.status_code == 400


def test_persistence_grant_with_correct_ssid_authorizes(client, tmp_path):
    c, net_id = client
    response = c.post(f"/networks/{net_id}/persistence", data={
        "action": "grant",
        "confirm_ssid": "TargetNet",
    })
    assert response.status_code in (200, 302)

    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    net = bundle.networks.get_by_id(net_id)
    assert net.persistence_authorized == 1
    assert net.persistence_authorized_by == "operator"
    conn.close()


def test_persistence_revoke_clears_authorization(client, tmp_path):
    c, net_id = client
    # Grant first
    c.post(f"/networks/{net_id}/persistence", data={
        "action": "grant", "confirm_ssid": "TargetNet",
    })
    # Revoke
    c.post(f"/networks/{net_id}/persistence", data={"action": "revoke"})

    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    net = bundle.networks.get_by_id(net_id)
    assert net.persistence_authorized == 0
    conn.close()


def test_persistence_grant_writes_audit_log(client, tmp_path):
    c, net_id = client
    c.post(f"/networks/{net_id}/persistence", data={
        "action": "grant", "confirm_ssid": "TargetNet",
    })
    conn = ConnectionFactory(db_path=tmp_path / "x.db").connect()
    bundle = bundle_for(conn)
    rows = bundle.action_log.list_for_network(net_id, limit=10)
    assert any("persistence" in r.action_type.lower() for r in rows)
    conn.close()
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add route to `mjolnir/ui/web/routes.py`**

```python
    @app.route("/networks/<int:network_id>/persistence", methods=["POST"])
    def network_persistence(network_id: int):
        action = request.form.get("action")
        if action not in ("grant", "revoke"):
            return "invalid action", 400

        conn, bundle = _get_bundle(app)
        try:
            network = bundle.networks.get_by_id(network_id)
            if network is None:
                return "network not found", 404

            if action == "grant":
                confirm = request.form.get("confirm_ssid", "")
                if confirm != network.ssid:
                    return f"confirmation failed: you must type the SSID '{network.ssid}' exactly", 400
                bundle.networks.authorize_persistence(network_id, by="operator")
                bundle.action_log.insert(
                    global_mode=bundle.system_state.get_global_mode(),
                    scope_basis="operator-authorized-network-persistence",
                    action_type=f"persistence.authorized.network.{network_id}",
                    target_network_id=network_id,
                    outcome="completed",
                    details={"ssid": network.ssid},
                )
            else:  # revoke
                bundle.networks.revoke_persistence_authorization(network_id)
                bundle.action_log.insert(
                    global_mode=bundle.system_state.get_global_mode(),
                    scope_basis="operator-revoked-network-persistence",
                    action_type=f"persistence.revoked.network.{network_id}",
                    target_network_id=network_id,
                    outcome="completed",
                )
        finally:
            conn.close()
        return redirect(url_for("network_detail", network_id=network_id))
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/unit/ui/web/test_routes_persistence.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add mjolnir/ui/web/routes.py tests/unit/ui/web/test_routes_persistence.py
git commit -m "feat(ui): two-tier persistence authorization handler

POST /networks/<id>/persistence with action=grant requires the
operator to type the SSID exactly (confirmation). action=revoke
clears immediately. Both write to audit log with explicit
scope_basis strings.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 7: Integration with main.py + acceptance

### Task 7.1: Start Flask in daemon mode

**Files:**
- Modify: `mjolnir/main.py`

The daemon (Plan 2b) currently runs the NLM loop only. Extend `run_daemon` to start Flask in a background thread.

- [ ] **Step 1: Modify `mjolnir/main.py`'s `run_daemon` function**

Replace the existing `run_daemon` body with a version that also starts the Flask app. Add this import at the top:

```python
from mjolnir.ui.web.app import create_app
```

Replace `run_daemon`:

```python
def run_daemon(config: BjornConfig) -> int:
    """Run the NLM main loop + Flask WebUI until shutdown is requested."""
    _install_signal_handlers()
    _shutdown_requested.clear()

    kill_switch_event = mp.Event()
    mgr = NetworkLifecycleManager(
        db_path=config.db.path,
        config=config,
        registry=default_registry,
        kill_switch_event=kill_switch_event,
    )

    # Start Flask WebUI in a background thread
    web_app = create_app(config)
    web_thread = threading.Thread(
        target=lambda: web_app.run(
            host=config.web.bind_interface,
            port=config.web.port,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    )
    web_thread.start()

    while not _shutdown_requested.is_set():
        try:
            mgr.run_once()
        except Exception as e:
            print(f"warning: NLM iteration failed: {e}", file=sys.stderr)
        for _ in range(config.nlm.scan_interval_seconds * 10):
            if _shutdown_requested.is_set():
                break
            time.sleep(0.1)

    return 0
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```
Expected: all existing tests still pass (no new tests for this wiring; the existing `test_main_runs_daemon_loop_until_shutdown` covers it).

- [ ] **Step 3: Commit**

```bash
git add mjolnir/main.py
git commit -m "feat(main): start Flask WebUI alongside NLM daemon

run_daemon now spawns the Flask app in a daemon thread so the WebUI
is reachable on config.web.bind_interface:port while the NLM loop
runs in the foreground.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 7.2: Full suite + tag

- [ ] **Step 1: Run the entire test suite**

```bash
pytest tests/ -v
```
Expected: ~200 tests pass (177 from Plan 2b + ~24 WebUI tests). Hardware tests deselected.

- [ ] **Step 2: Verify clean working tree and tag**

```bash
git status
git tag -a v0.4.0-plan3a -m "Plan 3a of sub-project #0 complete: Flask WebUI

- Flask app factory + dashboard route
- Networks inventory + detail (BSSIDs, actions, persistence danger zone)
- Settings: mode toggle (view_only<->active) + kill switch
- Blocklist management (preemptive add by SSID, scope_state changes)
- Audit log view (last 200 actions)
- Two-tier persistence authorization with typed-SSID confirmation
- Daemon now starts Flask in background thread
- ~24 new tests, all using Flask test client (no browser needed)

Every operator action in the spec is now reachable via HTTP.
Plan 3b (EPD display) is next; Plan 4 (migration + systemd + final
acceptance) ships sub-project #0."
```

---

## Plan 3a acceptance criteria

1. ✅ All Plan 2b tests still pass (177)
2. ✅ All ~24 WebUI tests pass
3. ✅ `GET /` returns dashboard with current mode, kill switch, networks, recent actions
4. ✅ `GET /networks` lists all eligible networks
5. ✅ `GET /networks/<id>` shows network detail with BSSIDs, actions, persistence zone; returns 404 for missing
6. ✅ `POST /settings/mode` toggles mode, persists, writes audit log; rejects invalid values
7. ✅ `POST /settings/kill_switch` engages/releases
8. ✅ `POST /blocklist` preemptively adds network by SSID
9. ✅ `POST /networks/<id>/scope` changes scope_state
10. ✅ `GET /audit` shows audit log entries
11. ✅ `POST /networks/<id>/persistence` grants (requires typed SSID) or revokes; writes audit log
12. ✅ Daemon starts Flask in background thread
13. ✅ Tag `v0.4.0-plan3a` exists

---

## Plan 3b preview (next plan)

Plan 3b will:
- Wrap v1's `waveshare_epd/` driver in a clean adapter
- Build the display state manager with 14 priority-ordered states
- Render each state (STARTING_UP, KILL_SWITCH_ENGAGED, ACTIVE_WORKING, etc.)
- Partial-refresh for counters; full-refresh for state transitions

Plan 3b is hardware-dependent for final verification (the e-Paper HAT) but the state manager logic is fully testable without it.
