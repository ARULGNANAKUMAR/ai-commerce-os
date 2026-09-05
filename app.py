"""
app.py
──────
Application entry point. Uses the factory pattern so tests and future
deployment targets (gunicorn, etc.) can create isolated app instances.

Run locally with:
    python app.py

Or via flask CLI:
    export FLASK_APP=app.py
    flask run
"""

from flask import Flask

from config import Config
from db import init_db
from utils import register_error_handlers
from auth import auth_bp
from routes import pages_bp, api_bp
from catalog.product_routes import products_bp
from ai.ai_routes import ai_bp
from permissions.permission_routes import permissions_bp
from workflow.workflow_routes import (
    workflows_bp, executions_bp, templates_bp, agent_bp,
)
from workflow.template_service import seed_templates
from commerce.commerce_routes import (
    chat_bp, search_bp, compare_bp, recommend_bp, cart_bp, approval_bp, copilot_bp,
)
from payments.payment_routes import payments_bp, orders_bp
from analytics.analytics_routes import analytics_bp, embed_bp, admin_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    init_db(app)
    register_error_handlers(app)

    for bp in [pages_bp, auth_bp, api_bp,                          # Phase 1
               products_bp, ai_bp, permissions_bp,                 # Phase 2
               workflows_bp, executions_bp, templates_bp, agent_bp, # Phase 3
               chat_bp, search_bp, compare_bp, recommend_bp,       # Phase 4
               cart_bp, approval_bp, copilot_bp,
               payments_bp, orders_bp, analytics_bp,               # Phase 5
               embed_bp, admin_bp]:
        app.register_blueprint(bp)

    with app.app_context():
        seed_templates()

    @app.route("/api/health")
    def health():
        return {"success": True, "status": "ok",
                "service": "ai-commerce-os", "phase": 5}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
