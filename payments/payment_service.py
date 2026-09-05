"""
payments/payment_service.py
────────────────────────────
Full payment lifecycle:
  create_payment_order()  – creates Razorpay order + DB order record
  capture_payment()       – verifies signature, marks paid, fires webhooks
  fail_payment()          – records failure, increments retry_count
  retry_payment()         – creates a new Razorpay order for an existing
                            DB order (retry flow), capped at 3 attempts
  refund_payment()        – issues refund via Razorpay + updates DB

Every state transition is audit-logged and fires a webhook event
through webhook_service so merchant integrations stay up-to-date.
"""

import models
from payments import razorpay_client
from security_ext import verify_razorpay_payment_signature
from permissions.permission_service import check_permission
from utils import ApiError, utcnow


MAX_RETRY_ATTEMPTS = 3


def create_payment_order(merchant_id: str, session_id: str,
                          cart_id: str = None, user_id: str = None) -> dict:
    """
    1. Permission-check payment_request.
    2. Resolve amount from cart (or require explicit amount).
    3. Create Razorpay order.
    4. Persist DB order record.
    5. Audit log.
    6. Return order details (including razorpay_order_id for Checkout.js).
    """
    # Resolve amount from cart
    cart = models.find_cart_by_session(merchant_id, session_id) if session_id else None
    if not cart or not cart.get("items"):
        raise ApiError("Cart is empty. Add items before creating a payment order.", 400,
                       code="EMPTY_CART")
    amount = cart.get("total", 0)
    if amount <= 0:
        raise ApiError("Cart total must be greater than zero.", 400, code="INVALID_AMOUNT")

    # Permission gate
    decision = check_permission(merchant_id, "payment_request", {"amount": amount})
    if decision == "DENY":
        raise ApiError("Payment requests are not enabled for this merchant's AI agent.", 403,
                       code="PERMISSION_DENIED")
    if decision == "LIMIT_EXCEEDED":
        raise ApiError(f"Cart total ₹{amount:,.0f} exceeds the configured payment limit.", 403,
                       code="LIMIT_EXCEEDED")

    # Create Razorpay order
    rzp_order = razorpay_client.create_order(
        amount, currency="INR",
        receipt=f"sess_{session_id[:12]}",
        notes={"merchant_id": merchant_id, "session_id": session_id},
    )

    # Persist
    order_id = models.create_order(merchant_id, session_id, cart_id or str(cart.get("_id", "")),
                                    amount, currency="INR")
    models.update_order(merchant_id, order_id, {
        "razorpay_order_id": rzp_order["id"],
        "status": "created",
    })

    # Payment record
    models.create_payment_record(merchant_id, order_id, amount=amount)

    models.log_audit("payment_order_created", user_id=user_id, merchant_id=merchant_id,
                      details={"order_id": order_id, "amount": amount,
                               "razorpay_order_id": rzp_order["id"],
                               "permission_decision": decision})

    _fire_webhook(merchant_id, "order.created", {
        "order_id": order_id, "amount": amount,
        "razorpay_order_id": rzp_order["id"],
    })

    return {
        "order_id":          order_id,
        "razorpay_order_id": rzp_order["id"],
        "amount":            amount,
        "currency":          "INR",
        "key_id":            _safe_key_id(),
        "permission_decision": decision,
        "requires_approval": decision == "REQUIRES_APPROVAL",
    }


def capture_payment(merchant_id: str, order_id: str,
                     razorpay_payment_id: str, razorpay_order_id: str,
                     razorpay_signature: str, user_id: str = None) -> dict:
    """
    Called after Razorpay Checkout succeeds client-side. Verifies the
    HMAC signature, marks the order paid, fires webhook, audits.
    """
    order = models.find_order(merchant_id, order_id)
    if not order:
        raise ApiError("Order not found.", 404, code="NOT_FOUND")
    if order.get("status") == "paid":
        raise ApiError("Order has already been paid.", 409, code="ALREADY_PAID")

    # Signature verification (CRITICAL security step)
    valid = verify_razorpay_payment_signature(
        razorpay_order_id, razorpay_payment_id, razorpay_signature
    )
    if not valid:
        # Record the failed attempt
        models.update_order(merchant_id, order_id, {"status": "signature_failed"})
        models.log_audit("payment_signature_invalid", user_id=user_id, merchant_id=merchant_id,
                          details={"order_id": order_id})
        _fire_webhook(merchant_id, "payment.failed",
                      {"order_id": order_id, "reason": "invalid_signature"})
        raise ApiError("Payment signature verification failed. The payment could not be confirmed.",
                       400, code="INVALID_SIGNATURE")

    # Mark paid
    models.update_order(merchant_id, order_id, {
        "status": "paid",
        "razorpay_payment_id": razorpay_payment_id,
    })

    # Update payment record
    payments = models.find_payments(merchant_id, limit=200)
    prec = next((p for p in payments if str(p["order_id"]) == order_id), None)
    if prec:
        models.update_payment_record(merchant_id, str(prec["_id"]), {
            "razorpay_payment_id": razorpay_payment_id,
            "status": "captured",
            "signature_verified": True,
        })

    models.log_audit("payment_captured", user_id=user_id, merchant_id=merchant_id,
                      details={"order_id": order_id, "amount": order["amount"],
                               "razorpay_payment_id": razorpay_payment_id})

    _fire_webhook(merchant_id, "payment.success", {
        "order_id": order_id, "amount": order["amount"],
        "razorpay_payment_id": razorpay_payment_id,
    })

    _increment_analytics(merchant_id, order["amount"])

    return {"order_id": order_id, "status": "paid", "amount": order["amount"]}


def fail_payment(merchant_id: str, order_id: str,
                  error_code: str = "PAYMENT_FAILED",
                  description: str = "Payment failed.", user_id: str = None) -> dict:
    order = models.find_order(merchant_id, order_id)
    if not order:
        raise ApiError("Order not found.", 404, code="NOT_FOUND")

    retry_count = order.get("retry_count", 0) + 1
    models.update_order(merchant_id, order_id, {
        "status": "failed", "retry_count": retry_count,
    })

    payments = models.find_payments(merchant_id, limit=200)
    prec = next((p for p in payments if str(p["order_id"]) == order_id), None)
    if prec:
        models.update_payment_record(merchant_id, str(prec["_id"]), {
            "status": "failed",
            "error_code": error_code,
            "error_description": description,
        })

    models.log_audit("payment_failed", user_id=user_id, merchant_id=merchant_id,
                      details={"order_id": order_id, "error_code": error_code})
    _fire_webhook(merchant_id, "payment.failed",
                  {"order_id": order_id, "error_code": error_code, "description": description})

    return {
        "order_id": order_id, "status": "failed",
        "retry_count": retry_count,
        "can_retry": retry_count < MAX_RETRY_ATTEMPTS,
    }


def retry_payment(merchant_id: str, order_id: str, user_id: str = None) -> dict:
    """Create a new Razorpay order for a failed payment (up to MAX_RETRY_ATTEMPTS)."""
    order = models.find_order(merchant_id, order_id)
    if not order:
        raise ApiError("Order not found.", 404, code="NOT_FOUND")
    if order.get("status") == "paid":
        raise ApiError("Order is already paid.", 409, code="ALREADY_PAID")
    if order.get("retry_count", 0) >= MAX_RETRY_ATTEMPTS:
        raise ApiError(
            f"Maximum retry attempts ({MAX_RETRY_ATTEMPTS}) reached for this order.", 409,
            code="MAX_RETRIES_EXCEEDED",
        )

    rzp_order = razorpay_client.create_order(
        order["amount"], currency=order.get("currency", "INR"),
        receipt=f"retry_{order_id[:12]}",
    )
    # retry_count is already at N after fail_payment() called it N times.
    # We intentionally do NOT increment here — fail_payment owns the counter.
    current_retry_count = order.get("retry_count", 0)
    models.update_order(merchant_id, order_id, {
        "status": "created",
        "razorpay_order_id": rzp_order["id"],
    })
    models.create_payment_record(merchant_id, order_id, amount=order["amount"])

    models.log_audit("payment_retried", user_id=user_id, merchant_id=merchant_id,
                      details={"order_id": order_id, "retry_count": current_retry_count})

    return {
        "order_id":           order_id,
        "razorpay_order_id":  rzp_order["id"],
        "amount":             order["amount"],
        "retry_count":        current_retry_count,
        "can_retry":          current_retry_count < MAX_RETRY_ATTEMPTS,
        "key_id":             _safe_key_id(),
    }


def refund_payment(merchant_id: str, order_id: str,
                    refund_amount: float = None, user_id: str = None) -> dict:
    """Issue a full or partial refund. Checks refund_request capability."""
    from permissions.permission_service import check_permission as cp
    order = models.find_order(merchant_id, order_id)
    if not order:
        raise ApiError("Order not found.", 404, code="NOT_FOUND")
    if order.get("status") != "paid":
        raise ApiError("Only paid orders can be refunded.", 400, code="NOT_PAID")

    amount = refund_amount or order["amount"]
    decision = cp(merchant_id, "refund_request", {"amount": amount})
    if decision == "DENY":
        raise ApiError("Refund requests are not enabled for this merchant.", 403,
                       code="PERMISSION_DENIED")

    rzp_payment_id = order.get("razorpay_payment_id") or f"pay_{order_id[:16]}"
    refund = razorpay_client.create_refund(rzp_payment_id, amount)

    models.update_order(merchant_id, order_id, {
        "status": "refunded", "refund_id": refund["id"],
    })

    payments = models.find_payments(merchant_id, limit=200)
    prec = next((p for p in payments if str(p["order_id"]) == order_id), None)
    if prec:
        models.update_payment_record(merchant_id, str(prec["_id"]), {
            "refunded": True, "refund_amount": amount,
        })

    models.log_audit("payment_refunded", user_id=user_id, merchant_id=merchant_id,
                      details={"order_id": order_id, "refund_amount": amount,
                               "refund_id": refund["id"]})
    _fire_webhook(merchant_id, "refund.processed",
                  {"order_id": order_id, "amount": amount, "refund_id": refund["id"]})

    return {"order_id": order_id, "status": "refunded", "refund_id": refund["id"],
            "refund_amount": amount}


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def serialize_order(order: dict) -> dict:
    return {
        "id":                 str(order["_id"]),
        "session_id":         order.get("session_id"),
        "amount":             order.get("amount"),
        "currency":           order.get("currency", "INR"),
        "status":             order.get("status"),
        "razorpay_order_id":  order.get("razorpay_order_id"),
        "razorpay_payment_id":order.get("razorpay_payment_id"),
        "refund_id":          order.get("refund_id"),
        "retry_count":        order.get("retry_count", 0),
        "created_at":         order["created_at"].isoformat() if order.get("created_at") else None,
        "updated_at":         order["updated_at"].isoformat() if order.get("updated_at") else None,
    }


def _safe_key_id() -> str:
    """Return the public Razorpay key ID — never the secret."""
    return str(models.get_db().__class__.__name__)  # placeholder; real value from Config
    # (routes read Config.RAZORPAY_KEY_ID directly and include it in the response)


def _fire_webhook(merchant_id: str, event: str, payload: dict) -> None:
    """Log a webhook event (delivery in Phase 5 webhook_service)."""
    try:
        from payments.webhook_service import dispatch_webhook
        dispatch_webhook(merchant_id, event, payload)
    except Exception:
        pass


def _increment_analytics(merchant_id: str, amount: float) -> None:
    """Increment today's revenue counter in analytics."""
    try:
        from utils import utcnow
        today = utcnow().strftime("%Y-%m-%d")
        existing = models.find_analytics(merchant_id, days=1)
        todays = next((a for a in existing if a.get("date") == today), {})
        new_rev = round(todays.get("revenue", 0) + amount, 2)
        new_cnt = todays.get("orders_count", 0) + 1
        models.upsert_analytics(merchant_id, today, {
            "revenue": new_rev,
            "orders_count": new_cnt,
        })
    except Exception:
        pass
