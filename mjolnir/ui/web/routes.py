"""HTTP routes for mjolnir's WebUI."""
from flask import Flask, render_template, request, redirect, url_for

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

    @app.route("/blocklist")
    def blocklist():
        conn, bundle = _get_bundle(app)
        try:
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

    @app.route("/audit")
    def audit_log():
        conn, bundle = _get_bundle(app)
        try:
            actions = bundle.action_log.list_recent(limit=200)
            return render_template("audit.html", actions=actions)
        finally:
            conn.close()
