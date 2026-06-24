"""HTTP routes for mjolnir's WebUI."""
from flask import Flask, render_template

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
