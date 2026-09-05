"""
commerce/commerce_routes.py
──────────────────────────────
All Phase 4 blueprints in one file, mirroring the pattern used for
Phase 3's workflow_routes.py. Every route requires a merchant JWT
(the merchant operating the agent) except none — customer-facing chat
in a real deployment would run through a public, domain-scoped agent
token (documented in Section 8 of the Phase 1 architecture doc as a
future surface). For Phase 4, all endpoints are exercised by the
merchant's own authenticated session, matching how the merchant
dashboard test-drives the agent before publishing it.
"""

from flask import Blueprint, g, request

from security import jwt_required
from utils import ApiError, api_response
import models

from commerce import chat_service, search_service, comparison_service, \
    recommendation_service, cart_service, approval_service, copilot_service

chat_bp       = Blueprint("chat",       __name__, url_prefix="/api/chat")
search_bp     = Blueprint("search",     __name__, url_prefix="/api/search")
compare_bp    = Blueprint("compare",    __name__, url_prefix="/api/compare")
recommend_bp  = Blueprint("recommend",  __name__, url_prefix="/api/recommend")
cart_bp       = Blueprint("cart",       __name__, url_prefix="/api/cart")
approval_bp   = Blueprint("approval",   __name__, url_prefix="/api/approval")
copilot_bp    = Blueprint("copilot",    __name__, url_prefix="/api/copilot")


def _mid() -> str:
    if g.merchant_id:
        return g.merchant_id
    m = models.find_merchant_by_user_id(g.user_id)
    if not m:
        raise ApiError("Merchant profile not found.", 403, code="NO_MERCHANT")
    return str(m["_id"])


# ═════════════════════════════════════════════════════════════════════
# CHAT — AI Shopping Agent / AI Buyer Mode
# ═════════════════════════════════════════════════════════════════════

@chat_bp.route("", methods=["POST"])
@jwt_required
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        raise ApiError("'message' is required.", 400, code="MISSING_FIELD")
    session_id = body.get("session_id")
    result = chat_service.process_message(_mid(), message, session_id=session_id, user_id=g.user_id)
    return api_response(data=result)


@chat_bp.route("/history/<session_id>", methods=["GET"])
@jwt_required
def chat_history(session_id):
    convo = models.find_conversation(_mid(), session_id)
    messages = convo.get("messages", []) if convo else []
    return api_response(data={"session_id": session_id, "messages": messages})


# ═════════════════════════════════════════════════════════════════════
# SEARCH — Product Search Engine
# ═════════════════════════════════════════════════════════════════════

@search_bp.route("", methods=["POST"])
@jwt_required
def search():
    body = request.get_json(silent=True) or {}
    query = body.get("query", "")
    result = search_service.search_products(
        _mid(), query,
        category=body.get("category"), brand=body.get("brand"),
        min_price=body.get("min_price"), max_price=body.get("max_price"),
        in_stock_only=body.get("in_stock_only", True),
        limit=int(body.get("limit", 10)),
    )
    return api_response(data=result)


@search_bp.route("/similar/<product_id>", methods=["GET"])
@jwt_required
def similar(product_id):
    limit = int(request.args.get("limit", 5))
    result = search_service.find_similar_products(_mid(), product_id, limit=limit)
    return api_response(data=result)


# ═════════════════════════════════════════════════════════════════════
# COMPARE — Product Comparison Engine
# ═════════════════════════════════════════════════════════════════════

@compare_bp.route("", methods=["POST"])
@jwt_required
def compare():
    body = request.get_json(silent=True) or {}
    product_ids = body.get("product_ids", [])
    attributes  = body.get("attributes")
    result = comparison_service.compare_products(_mid(), product_ids, attributes=attributes)
    return api_response(data=result)


# ═════════════════════════════════════════════════════════════════════
# RECOMMEND — AI Recommendation Engine
# ═════════════════════════════════════════════════════════════════════

@recommend_bp.route("/personalized", methods=["POST"])
@jwt_required
def recommend_personalized():
    body = request.get_json(silent=True) or {}
    result = recommendation_service.recommend_personalized(
        _mid(), body.get("session_id"), limit=int(body.get("limit", 5)))
    return api_response(data=result)


@recommend_bp.route("/budget", methods=["POST"])
@jwt_required
def recommend_budget():
    body = request.get_json(silent=True) or {}
    result = recommendation_service.recommend_by_budget(
        _mid(), body.get("budget"), category=body.get("category"), limit=int(body.get("limit", 5)))
    return api_response(data=result)


@recommend_bp.route("/alternatives/<product_id>", methods=["GET"])
@jwt_required
def recommend_alternatives(product_id):
    result = recommendation_service.recommend_alternatives(_mid(), product_id)
    return api_response(data=result)


@recommend_bp.route("/bundle/<product_id>", methods=["GET"])
@jwt_required
def recommend_bundle(product_id):
    result = recommendation_service.recommend_bundle(_mid(), product_id)
    return api_response(data=result)


@recommend_bp.route("/upsell", methods=["POST"])
@jwt_required
def recommend_upsell():
    body = request.get_json(silent=True) or {}
    result = recommendation_service.recommend_upsell(
        _mid(), body.get("product_ids", []), session_id=body.get("session_id"))
    return api_response(data=result)


@recommend_bp.route("/cross-sell", methods=["POST"])
@jwt_required
def recommend_cross_sell():
    body = request.get_json(silent=True) or {}
    result = recommendation_service.recommend_cross_sell(
        _mid(), body.get("product_ids", []), session_id=body.get("session_id"))
    return api_response(data=result)


# ═════════════════════════════════════════════════════════════════════
# CART — Conversational Cart
# ═════════════════════════════════════════════════════════════════════

@cart_bp.route("/<session_id>", methods=["GET"])
@jwt_required
def get_cart(session_id):
    return api_response(data=cart_service.get_cart(_mid(), session_id))


@cart_bp.route("/<session_id>/items", methods=["POST"])
@jwt_required
def add_item(session_id):
    body = request.get_json(silent=True) or {}
    product_id = body.get("product_id")
    if not product_id:
        raise ApiError("'product_id' is required.", 400, code="MISSING_FIELD")
    quantity = int(body.get("quantity", 1))
    result = cart_service.add_item(_mid(), session_id, product_id, quantity)
    return api_response(data=result, message="Item added to cart.", status=201)


@cart_bp.route("/<session_id>/items/<product_id>", methods=["PUT"])
@jwt_required
def update_item(session_id, product_id):
    body = request.get_json(silent=True) or {}
    if "quantity" not in body:
        raise ApiError("'quantity' is required.", 400, code="MISSING_FIELD")
    result = cart_service.update_item_quantity(_mid(), session_id, product_id, int(body["quantity"]))
    return api_response(data=result, message="Cart updated.")


@cart_bp.route("/<session_id>/items/<product_id>", methods=["DELETE"])
@jwt_required
def remove_item(session_id, product_id):
    result = cart_service.remove_item(_mid(), session_id, product_id)
    return api_response(data=result, message="Item removed from cart.")


@cart_bp.route("/<session_id>", methods=["DELETE"])
@jwt_required
def clear_cart(session_id):
    result = cart_service.clear_cart(_mid(), session_id)
    return api_response(data=result, message="Cart cleared.")


# ═════════════════════════════════════════════════════════════════════
# APPROVAL — Human Approval System
# ═════════════════════════════════════════════════════════════════════

@approval_bp.route("/request", methods=["POST"])
@jwt_required
def request_approval():
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id")
    if not session_id:
        raise ApiError("'session_id' is required.", 400, code="MISSING_FIELD")
    result = approval_service.request_checkout_approval(_mid(), session_id, user_id=g.user_id)
    status = 200 if result["status"] in ("approved", "pending") else 403
    return api_response(data=result, status=status)


@approval_bp.route("/<approval_id>/decide", methods=["PUT"])
@jwt_required
def decide(approval_id):
    body = request.get_json(silent=True) or {}
    decision = body.get("decision")
    if decision not in ("approved", "rejected"):
        raise ApiError("'decision' must be 'approved' or 'rejected'.", 400, code="INVALID_DECISION")
    result = approval_service.decide_approval(_mid(), approval_id, decision, user_id=g.user_id)
    return api_response(data=result, message=f"Checkout {decision}.")


@approval_bp.route("/<approval_id>", methods=["GET"])
@jwt_required
def get_approval(approval_id):
    return api_response(data=approval_service.get_approval(_mid(), approval_id))


@approval_bp.route("", methods=["GET"])
@jwt_required
def list_approvals():
    status = request.args.get("status")
    return api_response(data={"approvals": approval_service.list_approvals(_mid(), status=status)})


# ═════════════════════════════════════════════════════════════════════
# COPILOT — Merchant AI Copilot
# ═════════════════════════════════════════════════════════════════════

@copilot_bp.route("/ask", methods=["POST"])
@jwt_required
def ask():
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        raise ApiError("'question' is required.", 400, code="MISSING_FIELD")
    result = copilot_service.ask(_mid(), question)
    models.log_audit("copilot_query", user_id=g.user_id, merchant_id=_mid(),
                      details={"question": question, "insight_type": result.get("insight_type")})
    return api_response(data=result)
