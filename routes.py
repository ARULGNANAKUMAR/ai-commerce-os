"""
routes.py
─────────
Two kinds of routes live here:

1. Page routes — render the HTML shell for each screen. Auth
   enforcement for these is done client-side (app.js checks for a
   valid session before rendering dashboard content); the actual
   data underneath is protected by the API routes below.

2. Protected merchant API routes (/api/merchant/*) — everything
   requires a valid access token via @jwt_required. This is the
   surface Phase 2 (AI engine, workflow builder, catalog, payments)
   will extend, not replace.
"""

from flask import Blueprint, g, render_template, request

import models
from security import jwt_required, sanitize_string
from utils import ApiError, api_response, get_client_ip

pages_bp = Blueprint("pages", __name__)
api_bp = Blueprint("merchant_api", __name__, url_prefix="/api/merchant")


# ─────────────────────────────────────────────────────────────────────
# Page routes (HTML shells)
# ─────────────────────────────────────────────────────────────────────

@pages_bp.route("/")
def index():
    return render_template("index.html")


@pages_bp.route("/login")
def login_page():
    return render_template("login.html")


@pages_bp.route("/signup")
def signup_page():
    return render_template("signup.html")


@pages_bp.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@pages_bp.route("/settings")
def settings_page():
    return render_template("settings.html")


@pages_bp.route("/products")
def products_page():
    return render_template("products.html")


@pages_bp.route("/ai-settings")
def ai_settings_page():
    return render_template("ai_settings.html")


@pages_bp.route("/permissions")
def permissions_page():
    return render_template("permissions.html")


@pages_bp.route("/workflows")
def workflows_page():
    return render_template("workflows.html")


@pages_bp.route("/builder")
@pages_bp.route("/builder/<workflow_id>")
def builder_page(workflow_id=None):
    return render_template("builder.html")


@pages_bp.route("/templates")
def templates_page():
    return render_template("workflow_templates.html")


@pages_bp.route("/executions")
def executions_page():
    return render_template("executions.html")


@pages_bp.route("/chat")
def chat_page():
    return render_template("chat.html")


@pages_bp.route("/compare")
def compare_page():
    return render_template("compare.html")


@pages_bp.route("/cart")
def cart_page():
    return render_template("cart.html")


@pages_bp.route("/approvals")
def approvals_page():
    return render_template("approvals.html")


@pages_bp.route("/copilot")
def copilot_page():
    return render_template("copilot.html")


@pages_bp.route("/payments")
def payments_page():
    return render_template("payments.html")


@pages_bp.route("/analytics")
def analytics_page():
    return render_template("analytics.html")


@pages_bp.route("/admin")
def admin_page():
    return render_template("admin.html")


# ─────────────────────────────────────────────────────────────────────
# GET /api/merchant/profile
# ─────────────────────────────────────────────────────────────────────

@api_bp.route("/profile", methods=["GET"])
@jwt_required
def get_profile():
    user = models.find_user_by_id(g.user_id)
    if not user:
        raise ApiError("Account not found.", 404, code="NOT_FOUND")
    merchant = models.find_merchant_by_user_id(g.user_id)

    return api_response(data={
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "email_verified": user["email_verified"],
            "last_login": user["last_login"].isoformat() if user.get("last_login") else None,
            "created_at": user["created_at"].isoformat(),
        },
        "merchant": _serialize_merchant(merchant),
    })


# ─────────────────────────────────────────────────────────────────────
# PUT /api/merchant/profile
# ─────────────────────────────────────────────────────────────────────

@api_bp.route("/profile", methods=["PUT"])
@jwt_required
def update_profile():
    merchant = models.find_merchant_by_user_id(g.user_id)
    if not merchant:
        raise ApiError("Merchant profile not found.", 404, code="NOT_FOUND")

    body = request.get_json(silent=True) or {}
    allowed_fields = ["company_name", "merchant_name", "phone", "business_type", "profile_photo_url"]
    updates = {}
    for field in allowed_fields:
        if field in body:
            updates[field] = sanitize_string(body[field], 300)

    if not updates:
        raise ApiError("No valid fields provided to update.", 400, code="NO_UPDATES")

    models.update_merchant_profile(str(merchant["_id"]), updates)
    models.log_audit("profile_updated", user_id=g.user_id, merchant_id=str(merchant["_id"]),
                      details={"fields": list(updates.keys())}, ip=get_client_ip())

    updated = models.find_merchant_by_id(str(merchant["_id"]))
    return api_response(data={"merchant": _serialize_merchant(updated)}, message="Profile updated.")


# ─────────────────────────────────────────────────────────────────────
# GET /api/merchant/dashboard-summary
# Empty-by-design in Phase 1: analytics/activity have no data source
# yet (AI engine + workflow builder ship in Phase 2). The shape below
# is the contract the dashboard UI already renders against, so Phase 2
# only has to populate real numbers — not redesign the screen.
# ─────────────────────────────────────────────────────────────────────

@api_bp.route("/dashboard-summary", methods=["GET"])
@jwt_required
def dashboard_summary():
    merchant = models.find_merchant_by_user_id(g.user_id)
    merchant_id = str(merchant["_id"]) if merchant else None

    recent_logs = models.get_recent_audit_logs(merchant_id, limit=8) if merchant_id else []
    product_count = models.count_products(merchant_id) if merchant_id else 0
    workflow_count = models.count_workflows(merchant_id) if merchant_id else 0

    return api_response(data={
        "metrics": {
            "conversations":   {"value": 0,              "label": "Conversations",       "unit": "count"},
            "conversion_rate": {"value": None,            "label": "Conversion rate",     "unit": "percent"},
            "revenue":         {"value": 0,               "label": "Revenue via agent",   "unit": "currency"},
            "active_agents":   {"value": workflow_count,  "label": "AI agents built",     "unit": "count"},
            "products":        {"value": product_count,   "label": "Products in catalog", "unit": "count"},
        },
        "recent_activity": [_serialize_activity(a) for a in recent_logs],
        "onboarding_complete": bool(merchant and merchant.get("onboarding_complete")),
    })


@api_bp.route("/activity", methods=["GET"])
@jwt_required
def activity_log():
    merchant = models.find_merchant_by_user_id(g.user_id)
    if not merchant:
        return api_response(data={"activity": []})

    limit = min(int(request.args.get("limit", 20)), 100)
    logs = models.get_recent_audit_logs(str(merchant["_id"]), limit=limit)
    return api_response(data={"activity": [_serialize_activity(a) for a in logs]})


# ─────────────────────────────────────────────────────────────────────
# Serialization helpers
# ─────────────────────────────────────────────────────────────────────

def _serialize_merchant(merchant: dict | None) -> dict | None:
    if not merchant:
        return None
    return {
        "id": str(merchant["_id"]),
        "company_name": merchant.get("company_name", ""),
        "merchant_name": merchant.get("merchant_name", ""),
        "phone": merchant.get("phone", ""),
        "business_type": merchant.get("business_type", ""),
        "profile_photo_url": merchant.get("profile_photo_url"),
        "onboarding_complete": merchant.get("onboarding_complete", False),
    }


def _serialize_activity(log: dict) -> dict:
    return {
        "id": str(log["_id"]),
        "action": log["action"],
        "details": log.get("details", {}),
        "timestamp": log["timestamp"].isoformat(),
    }
