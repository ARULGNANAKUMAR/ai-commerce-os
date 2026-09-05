"""
payments/webhook_service.py
────────────────────────────
Webhook dispatch system. In Phase 5 MVP, webhooks are:
  1. Logged immediately to the DB (audit trail).
  2. "Delivered" to a merchant-configured endpoint if one is set.
     Delivery is best-effort — we never block the payment flow on it.

Supported events:
  order.created | payment.success | payment.failed |
  refund.processed | approval.decided | workflow.completed
"""

import json
import urllib.request
import urllib.error
import hashlib
import hmac
import time

import models
from config import Config


SUPPORTED_EVENTS = {
    "order.created", "payment.success", "payment.failed",
    "refund.processed", "approval.decided", "workflow.completed",
    "ai.approval",
}


def dispatch_webhook(merchant_id: str, event: str, payload: dict,
                      idempotency_key: str = None) -> str:
    """Log the event and attempt delivery. Returns webhook_log_id."""
    if event not in SUPPORTED_EVENTS:
        return ""

    key = idempotency_key or f"{event}:{merchant_id}:{int(time.time() * 1000)}"
    wid = models.create_webhook_log(merchant_id, event, payload, idempotency_key=key)

    # Attempt delivery in-process (best-effort)
    merchant = models.find_merchant_by_id(merchant_id)
    endpoint = (merchant or {}).get("webhook_url")
    if endpoint:
        _deliver(wid, endpoint, event, payload, merchant_id)
    else:
        # No endpoint configured; mark as "no_endpoint" (not an error)
        models.update_webhook_log(wid, "no_endpoint")

    return wid


def _deliver(webhook_id: str, url: str, event: str, payload: dict,
              merchant_id: str) -> None:
    body = json.dumps({"event": event, "data": payload}).encode("utf-8")
    sig  = _sign(body)
    req  = urllib.request.Request(url, data=body, headers={
        "Content-Type":        "application/json",
        "X-ACOS-Event":        event,
        "X-ACOS-Signature":    sig,
        "X-ACOS-Merchant-Id":  merchant_id,
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5):
            models.update_webhook_log(webhook_id, "delivered")
    except Exception as exc:
        models.update_webhook_log(webhook_id, "failed", error=str(exc)[:300])


def _sign(body: bytes) -> str:
    secret = (Config.RAZORPAY_WEBHOOK_SECRET or "acos_webhook_secret").encode()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def verify_incoming_webhook(body_bytes: bytes, signature: str) -> bool:
    """Used by /api/payments/webhook to verify Razorpay-originated events."""
    from security_ext import verify_razorpay_webhook_signature
    return verify_razorpay_webhook_signature(body_bytes, signature)


def list_webhooks(merchant_id: str) -> list:
    rows = models.find_webhooks(merchant_id)
    return [_serialize(w) for w in rows]


def _serialize(w: dict) -> dict:
    return {
        "id":              str(w["_id"]),
        "event":           w.get("event"),
        "status":          w.get("status"),
        "error":           w.get("error"),
        "created_at":      w["created_at"].isoformat() if w.get("created_at") else None,
        "processed_at":    w["processed_at"].isoformat() if w.get("processed_at") else None,
    }
