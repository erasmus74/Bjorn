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
