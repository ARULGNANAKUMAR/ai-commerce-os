"""
payments/razorpay_client.py
────────────────────────────
Thin HTTP client for Razorpay's REST API — no SDK dependency.
All calls target Test Mode credentials and never touch live money.

Real HTTP calls are attempted when RAZORPAY_KEY_ID / KEY_SECRET are
configured. When credentials are absent (sandbox testing, CI), a
deterministic mock response is returned so the full payment flow can
be exercised without network access or a live Razorpay account.
"""

import json
import urllib.request
import urllib.error
import base64
import secrets
import time
from config import Config
from utils import ApiError


def _auth_header() -> str:
    credentials = f"{Config.RAZORPAY_KEY_ID}:{Config.RAZORPAY_KEY_SECRET}"
    return "Basic " + base64.b64encode(credentials.encode()).decode()


def _post(path: str, payload: dict) -> dict:
    url  = f"{Config.RAZORPAY_API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type":  "application/json",
            "Authorization": _auth_header(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read())
        except Exception:
            pass
        code = body.get("error", {}).get("code", "RAZORPAY_ERROR")
        desc = body.get("error", {}).get("description", f"HTTP {e.code}")
        raise ApiError(f"Razorpay: {desc}", 502, code=code)
    except urllib.error.URLError:
        raise ApiError("Could not reach Razorpay API. Check server internet access.", 502,
                       code="RAZORPAY_UNREACHABLE")


def _mock_order_id() -> str:
    return f"order_{secrets.token_hex(10)}"


def _mock_payment_id() -> str:
    return f"pay_{secrets.token_hex(10)}"


def _is_demo() -> bool:
    """True when no real key secret is configured → use mock responses."""
    return not bool(Config.RAZORPAY_KEY_SECRET)


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def create_order(amount_inr: float, currency: str = "INR",
                  receipt: str = None, notes: dict = None) -> dict:
    """
    Create a Razorpay order. amount_inr is in ₹; Razorpay expects paise.
    Returns the Razorpay order object.
    """
    amount_paise = int(amount_inr * 100)
    if amount_paise <= 0:
        raise ApiError("Order amount must be greater than zero.", 400, code="INVALID_AMOUNT")

    if _is_demo():
        return {
            "id":       _mock_order_id(),
            "entity":   "order",
            "amount":   amount_paise,
            "currency": currency,
            "receipt":  receipt or f"rcpt_{int(time.time())}",
            "status":   "created",
            "notes":    notes or {},
        }

    payload = {
        "amount":   amount_paise,
        "currency": currency,
        "receipt":  receipt or f"rcpt_{int(time.time())}",
        "notes":    notes or {},
    }
    return _post("/orders", payload)


def simulate_payment_capture(razorpay_order_id: str, amount_paise: int = None) -> dict:
    """
    Simulate a successful payment capture. In real usage the customer
    completes Razorpay Checkout in the browser and we receive a webhook —
    this helper lets us simulate that server-side for test mode demos.
    """
    payment_id = _mock_payment_id()
    return {
        "razorpay_order_id":   razorpay_order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature":  _mock_signature(razorpay_order_id, payment_id),
        "status":              "captured",
    }


def simulate_payment_failure(razorpay_order_id: str, error_code: str = "BAD_REQUEST_ERROR",
                              description: str = "Payment declined by bank.") -> dict:
    return {
        "razorpay_order_id": razorpay_order_id,
        "status":            "failed",
        "error_code":        error_code,
        "error_description": description,
    }


def create_refund(razorpay_payment_id: str, amount_inr: float) -> dict:
    """Simulate or create a real Razorpay refund."""
    amount_paise = int(amount_inr * 100)
    if _is_demo():
        return {
            "id":         f"rfnd_{secrets.token_hex(8)}",
            "payment_id": razorpay_payment_id,
            "amount":     amount_paise,
            "status":     "processed",
            "entity":     "refund",
        }
    return _post(f"/payments/{razorpay_payment_id}/refund", {"amount": amount_paise})


def _mock_signature(order_id: str, payment_id: str) -> str:
    """Generate a valid HMAC signature using the configured secret,
    or a deterministic test string when in demo mode."""
    import hmac, hashlib
    secret = Config.RAZORPAY_KEY_SECRET or "demo_secret"
    message = f"{order_id}|{payment_id}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
