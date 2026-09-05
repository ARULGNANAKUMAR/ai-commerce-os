"""
permissions/permission_routes.py
─────────────────────────────────
Flask blueprint for /api/permissions.

POST /api/permissions/check is the Phase 3 integration point — the
workflow engine calls it before every agent action.
"""

from flask import Blueprint, g, request

from security import jwt_required
from utils import ApiError, api_response
import models
from permissions.permission_service import (
    get_all_permissions, update_permission, check_permission,
)

permissions_bp = Blueprint("permissions", __name__, url_prefix="/api/permissions")


def _get_merchant_id() -> str:
    if g.merchant_id:
        return g.merchant_id
    merchant = models.find_merchant_by_user_id(g.user_id)
    if not merchant:
        raise ApiError("Merchant profile not found.", 403, code="NO_MERCHANT")
    return str(merchant["_id"])


# ─────────────────────────────────────────────────────────────────────
# GET /api/permissions — all capabilities + current state
# ─────────────────────────────────────────────────────────────────────

@permissions_bp.route("", methods=["GET"])
@jwt_required
def list_permissions():
    merchant_id = _get_merchant_id()
    perms = get_all_permissions(merchant_id)
    return api_response(data={"permissions": perms})


# ─────────────────────────────────────────────────────────────────────
# PUT /api/permissions/<capability>
# Body: { enabled: bool, limits?: { max_amount?, approval_required? } }
# ─────────────────────────────────────────────────────────────────────

@permissions_bp.route("/<capability>", methods=["PUT"])
@jwt_required
def update(capability):
    merchant_id = _get_merchant_id()
    body = request.get_json(silent=True) or {}

    if "enabled" not in body:
        raise ApiError("'enabled' (boolean) is required.", 400, code="MISSING_FIELD")

    enabled = body["enabled"]
    if not isinstance(enabled, bool):
        raise ApiError("'enabled' must be true or false.", 400, code="VALIDATION_ERROR")

    limits = body.get("limits")
    result = update_permission(merchant_id, capability, enabled, limits, user_id=g.user_id)
    return api_response(data={"permission": result}, message="Permission updated.")


# ─────────────────────────────────────────────────────────────────────
# POST /api/permissions/check
# Body: { capability: str, context?: { amount?: number, ... } }
# Used by Phase 3 workflow engine and by the merchant UI sandbox tester.
# ─────────────────────────────────────────────────────────────────────

@permissions_bp.route("/check", methods=["POST"])
@jwt_required
def check():
    merchant_id = _get_merchant_id()
    body = request.get_json(silent=True) or {}

    capability = str(body.get("capability") or "").strip()
    if not capability:
        raise ApiError("'capability' is required.", 400, code="MISSING_FIELD")

    context = body.get("context") or {}
    decision = check_permission(merchant_id, capability, context)

    return api_response(data={
        "capability": capability,
        "decision":   decision,
        "context":    context,
    })
