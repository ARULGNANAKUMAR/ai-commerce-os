"""
payments/payment_routes.py
────────────────────────────
Flask blueprint for /api/payments and /api/orders.
"""

from flask import Blueprint, g, request

from security import jwt_required
from security_ext import rate_limit, verify_razorpay_payment_signature
from utils import ApiError, api_response
from config import Config
import models
from payments.payment_service import (
    create_payment_order, capture_payment, fail_payment,
    retry_payment, refund_payment, serialize_order,
)
from payments.webhook_service import verify_incoming_webhook, dispatch_webhook, list_webhooks

payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")
orders_bp   = Blueprint("orders",   __name__, url_prefix="/api/orders")


def _mid() -> str:
    if g.merchant_id:
        return g.merchant_id
    m = models.find_merchant_by_user_id(g.user_id)
    if not m:
        raise ApiError("Merchant profile not found.", 403, code="NO_MERCHANT")
    return str(m["_id"])


# ─────────────────────────────────────────────────────────────────────
# POST /api/payments/create
# ─────────────────────────────────────────────────────────────────────

@payments_bp.route("/create", methods=["POST"])
@jwt_required
@rate_limit(max_requests=20, window=60)
def create_order_route():
    body       = request.get_json(silent=True) or {}
    session_id = body.get("session_id")
    if not session_id:
        raise ApiError("'session_id' is required.", 400, code="MISSING_FIELD")
    result = create_payment_order(
        _mid(), session_id,
        cart_id=body.get("cart_id"),
        user_id=g.user_id,
    )
    # Inject the public key_id so Checkout.js can be initialised client-side
    result["key_id"] = Config.RAZORPAY_KEY_ID
    return api_response(data=result, status=201)


# ─────────────────────────────────────────────────────────────────────
# POST /api/payments/verify  — called after Checkout.js succeeds
# ─────────────────────────────────────────────────────────────────────

@payments_bp.route("/verify", methods=["POST"])
@jwt_required
def verify_route():
    body = request.get_json(silent=True) or {}
    required = ["order_id", "razorpay_payment_id",
                "razorpay_order_id", "razorpay_signature"]
    missing  = [f for f in required if not body.get(f)]
    if missing:
        raise ApiError(f"Missing fields: {', '.join(missing)}", 400, code="MISSING_FIELD")

    result = capture_payment(
        _mid(),
        order_id=body["order_id"],
        razorpay_payment_id=body["razorpay_payment_id"],
        razorpay_order_id=body["razorpay_order_id"],
        razorpay_signature=body["razorpay_signature"],
        user_id=g.user_id,
    )
    return api_response(data=result, message="Payment captured successfully.")


# ─────────────────────────────────────────────────────────────────────
# POST /api/payments/simulate/capture  (Test Mode demo helper)
# ─────────────────────────────────────────────────────────────────────

@payments_bp.route("/simulate/capture", methods=["POST"])
@jwt_required
def simulate_capture():
    body     = request.get_json(silent=True) or {}
    order_id = body.get("order_id")
    if not order_id:
        raise ApiError("'order_id' is required.", 400, code="MISSING_FIELD")

    order = models.find_order(_mid(), order_id)
    if not order:
        raise ApiError("Order not found.", 404, code="NOT_FOUND")

    from payments.razorpay_client import simulate_payment_capture
    sim = simulate_payment_capture(order["razorpay_order_id"])

    result = capture_payment(
        _mid(), order_id,
        razorpay_payment_id=sim["razorpay_payment_id"],
        razorpay_order_id=sim["razorpay_order_id"],
        razorpay_signature=sim["razorpay_signature"],
        user_id=g.user_id,
    )
    return api_response(data={**result, "simulated": True},
                        message="Test payment captured (simulated).")


# ─────────────────────────────────────────────────────────────────────
# POST /api/payments/simulate/failure  (Test Mode demo helper)
# ─────────────────────────────────────────────────────────────────────

@payments_bp.route("/simulate/failure", methods=["POST"])
@jwt_required
def simulate_failure():
    body     = request.get_json(silent=True) or {}
    order_id = body.get("order_id")
    if not order_id:
        raise ApiError("'order_id' is required.", 400, code="MISSING_FIELD")
    result = fail_payment(
        _mid(), order_id,
        error_code=body.get("error_code", "BAD_REQUEST_ERROR"),
        description=body.get("description", "Payment declined by bank."),
        user_id=g.user_id,
    )
    return api_response(data={**result, "simulated": True},
                        message="Test payment failure simulated.")


# ─────────────────────────────────────────────────────────────────────
# POST /api/payments/retry
# ─────────────────────────────────────────────────────────────────────

@payments_bp.route("/retry", methods=["POST"])
@jwt_required
def retry_route():
    body     = request.get_json(silent=True) or {}
    order_id = body.get("order_id")
    if not order_id:
        raise ApiError("'order_id' is required.", 400, code="MISSING_FIELD")
    result = retry_payment(_mid(), order_id, user_id=g.user_id)
    return api_response(data=result, message="New payment attempt created.")


# ─────────────────────────────────────────────────────────────────────
# POST /api/payments/refund
# ─────────────────────────────────────────────────────────────────────

@payments_bp.route("/refund", methods=["POST"])
@jwt_required
def refund_route():
    body     = request.get_json(silent=True) or {}
    order_id = body.get("order_id")
    if not order_id:
        raise ApiError("'order_id' is required.", 400, code="MISSING_FIELD")
    amount = body.get("amount")
    result = refund_payment(_mid(), order_id,
                             refund_amount=float(amount) if amount else None,
                             user_id=g.user_id)
    return api_response(data=result, message="Refund processed (test mode).")


# ─────────────────────────────────────────────────────────────────────
# POST /api/payments/webhook  — Razorpay sends events here
# ─────────────────────────────────────────────────────────────────────

@payments_bp.route("/webhook", methods=["POST"])
def razorpay_webhook():
    """Public endpoint — no JWT.  Secured by Razorpay signature."""
    body      = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_incoming_webhook(body, signature):
        return {"success": False, "error": "Invalid signature"}, 400

    try:
        payload = request.get_json(force=True, silent=True) or {}
        event   = payload.get("event", "unknown")
        entity  = payload.get("payload", {})

        # Route to the appropriate merchant
        # In a real deployment the Razorpay webhook payload contains the
        # order object with our notes.merchant_id; for demo we resolve
        # from the order DB.
        order_entity = entity.get("order", {}).get("entity", {})
        rzp_order_id = order_entity.get("id")
        merchant_id  = None

        if rzp_order_id:
            order_doc = models.find_order_by_razorpay_id(rzp_order_id)
            if order_doc:
                merchant_id = str(order_doc["merchant_id"])

        if merchant_id:
            dispatch_webhook(merchant_id, event, payload)

    except Exception:
        pass  # never fail a webhook endpoint — always return 200

    return {"success": True}, 200


# ─────────────────────────────────────────────────────────────────────
# GET /api/payments/webhooks
# ─────────────────────────────────────────────────────────────────────

@payments_bp.route("/webhooks", methods=["GET"])
@jwt_required
def webhooks_list():
    return api_response(data={"webhooks": list_webhooks(_mid())})


# ─────────────────────────────────────────────────────────────────────
# ORDERS blueprint
# ─────────────────────────────────────────────────────────────────────

@orders_bp.route("", methods=["GET"])
@jwt_required
def list_orders():
    status = request.args.get("status")
    limit  = min(int(request.args.get("limit", 50)), 200)
    orders = models.find_orders(_mid(), status=status, limit=limit)
    return api_response(data={"orders": [serialize_order(o) for o in orders]})


@orders_bp.route("/<order_id>", methods=["GET"])
@jwt_required
def get_order(order_id):
    order = models.find_order(_mid(), order_id)
    if not order:
        raise ApiError("Order not found.", 404, code="NOT_FOUND")
    return api_response(data={"order": serialize_order(order)})
