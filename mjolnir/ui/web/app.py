"""Flask app factory for mjolnir's WebUI.

Single-user, trusted-context app. No auth in sub-project #0 (bind to
127.0.0.1, SSH port-forward access). Reads NLM state via repository
bundle from Plan 1; writes via same repositories.
"""
from flask import Flask

from mjolnir.config import BjornConfig


def create_app(config: BjornConfig) -> Flask:
    app = Flask(__name__)
    app.config["MJOLNIR_CONFIG"] = config
    app.config["MJOLNIR_DB_PATH"] = str(config.db.path)

    from mjolnir.ui.web.routes import register_routes
    register_routes(app)

    return app
