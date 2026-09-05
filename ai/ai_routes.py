"""
ai/ai_routes.py
───────────────
Flask blueprint for /api/ai — AI provider configuration.

Security rules enforced here:
  - merchant_id always from JWT (g.merchant_id), never from body
  - API keys accepted only via POST body over HTTPS, never via GET params
  - Responses never contain key_encrypted or any key material
  - Error messages safe enough to return to the merchant UI
"""

from flask import Blueprint, g, request

from security import jwt_required
from utils import ApiError, api_response
from config import Config
import models
from ai.provider_service import (
    save_provider, test_provider, get_provider_config,
    remove_provider, get_supported_providers,
)

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


def _get_merchant_id() -> str:
    if g.merchant_id:
        return g.merchant_id
    merchant = models.find_merchant_by_user_id(g.user_id)
    if not merchant:
        raise ApiError("Merchant profile not found.", 403, code="NO_MERCHANT")
    return str(merchant["_id"])


# ─────────────────────────────────────────────────────────────────────
# GET /api/ai/providers/meta — available providers + model lists
# ─────────────────────────────────────────────────────────────────────

@ai_bp.route("/providers/meta", methods=["GET"])
@jwt_required
def provider_meta():
    return api_response(data={"providers": get_supported_providers()})


# ─────────────────────────────────────────────────────────────────────
# GET /api/ai/providers — current provider config (no key)
# ─────────────────────────────────────────────────────────────────────

@ai_bp.route("/providers", methods=["GET"])
@jwt_required
def get_provider():
    merchant_id = _get_merchant_id()
    config = get_provider_config(merchant_id)
    return api_response(data={"provider": config})


# ─────────────────────────────────────────────────────────────────────
# POST /api/ai/providers — save / update provider config
# Body: { provider, model, api_key }
# ─────────────────────────────────────────────────────────────────────

@ai_bp.route("/providers", methods=["POST"])
@jwt_required
def save():
    merchant_id = _get_merchant_id()
    body = request.get_json(silent=True) or {}

    provider = str(body.get("provider") or "").strip().lower()
    model    = str(body.get("model")    or "").strip()
    api_key  = str(body.get("api_key")  or "").strip()

    if not provider:
        raise ApiError("'provider' is required.", 400, code="MISSING_FIELD")
    if not model:
        raise ApiError("'model' is required.", 400, code="MISSING_FIELD")
    if not api_key:
        raise ApiError("'api_key' is required.", 400, code="MISSING_KEY")

    result = save_provider(merchant_id, provider, model, api_key, user_id=g.user_id)
    return api_response(data={"provider": result}, message="AI provider saved. Click 'Test connection' to verify.")


# ─────────────────────────────────────────────────────────────────────
# POST /api/ai/providers/test — live connection test
# ─────────────────────────────────────────────────────────────────────

@ai_bp.route("/providers/test", methods=["POST"])
@jwt_required
def test_connection():
    merchant_id = _get_merchant_id()
    result = test_provider(merchant_id, user_id=g.user_id)
    status = 200 if result["success"] else 422
    return api_response(
        data=result,
        message=result["message"],
        status=status,
    )


# ─────────────────────────────────────────────────────────────────────
# DELETE /api/ai/providers — remove provider config
# ─────────────────────────────────────────────────────────────────────

@ai_bp.route("/providers", methods=["DELETE"])
@jwt_required
def remove():
    merchant_id = _get_merchant_id()
    remove_provider(merchant_id, user_id=g.user_id)
    return api_response(message="AI provider disconnected.")
