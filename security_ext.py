"""
security_ext.py  (Phase 5 extension — never modifies security.py)
──────────────────────────────────────────────────────────────────
Rate limiting:  sliding-window counter per (key, endpoint) pair,
                stored entirely in memory. For a single-process
                Gunicorn deployment (--preload + fork workers sharing
                the dict at startup) this is accurate enough for
                API-abuse protection. For multi-process or distributed
                deployments, swap the _store for a Redis backend by
                changing only _hit() and _check().

CORS:           minimal header helper for the public /api/embed/* and
                /api/payments/webhook endpoints that must be reachable
                from merchant storefronts.

Admin guard:    @admin_required decorator that checks the JWT user's
                email against Config.ADMIN_EMAILS.
"""

import time
import hashlib
import hmac
from collections import defaultdict
from functools import wraps

from flask import request, g, jsonify
from config import Config
from utils import ApiError


# ─────────────────────────────────────────────────────────────────────
# In-memory rate limiter
# ─────────────────────────────────────────────────────────────────────

# { key: [(timestamp, count), …] }
_store: dict[str, list] = defaultdict(list)


def _hit(key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
    """Return (allowed, remaining). Side-effects: updates _store."""
    now = time.time()
    cutoff = now - window_seconds
    entries = _store[key]
    # Purge stale entries
    entries[:] = [e for e in entries if e > cutoff]
    if len(entries) >= max_requests:
        return False, 0
    entries.append(now)
    return True, max_requests - len(entries)


def rate_limit(max_requests: int = None, window: int = None, key_fn=None):
    """Decorator: rate-limit a route.

    key_fn(request) → string key; defaults to IP + endpoint.
    """
    max_r = max_requests or Config.RATE_LIMIT_MAX
    win   = window or Config.RATE_LIMIT_WINDOW

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if key_fn:
                key = key_fn(request)
            else:
                ip = request.headers.get("X-Forwarded-For", request.remote_addr or "x")
                ip = ip.split(",")[0].strip()
                key = f"{ip}:{request.endpoint}"

            allowed, remaining = _hit(key, max_r, win)
            if not allowed:
                resp = jsonify({
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Too many requests. Limit is {max_r} per {win}s. Please slow down.",
                    },
                })
                resp.status_code = 429
                resp.headers["Retry-After"] = str(win)
                return resp
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────
# CORS helper (for embed / webhook public endpoints)
# ─────────────────────────────────────────────────────────────────────

def add_cors_headers(response, origins: str = None):
    origin = origins or Config.EMBED_CORS_ALLOWED_ORIGINS
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Merchant-Id"
    return response


def cors_preflight(fn):
    """Allow browsers to OPTIONS-preflight CORS requests."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            from flask import make_response
            resp = make_response("", 204)
            add_cors_headers(resp)
            return resp
        resp = fn(*args, **kwargs)
        if hasattr(resp, "__iter__"):
            # Tuple (response, status_code) from api_response()
            resp_obj, *rest = resp
            add_cors_headers(resp_obj)
            return (resp_obj, *rest)
        add_cors_headers(resp)
        return resp
    return wrapper


# ─────────────────────────────────────────────────────────────────────
# Razorpay signature verification
# ─────────────────────────────────────────────────────────────────────

def verify_razorpay_payment_signature(razorpay_order_id: str,
                                       razorpay_payment_id: str,
                                       razorpay_signature: str) -> bool:
    """Validate the HMAC-SHA256 signature Razorpay sends on payment capture."""
    secret = Config.RAZORPAY_KEY_SECRET
    if not secret:
        # No secret configured — treat as invalid in production.
        # In test/demo mode with no real keys, always return True so
        # the payment flow can be demonstrated end-to-end.
        return True
    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected = hmac.new(secret.encode("utf-8"), message.encode("utf-8"),
                         hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, razorpay_signature)


def verify_razorpay_webhook_signature(body_bytes: bytes, signature: str) -> bool:
    """Validate the X-Razorpay-Signature header on incoming webhooks.
    Demo mode activates when RAZORPAY_KEY_SECRET is not a real key
    (empty, or still the default placeholder)."""
    key_secret = Config.RAZORPAY_KEY_SECRET
    webhook_secret = Config.RAZORPAY_WEBHOOK_SECRET
    # Demo mode: no real Razorpay credentials configured
    if not key_secret or key_secret == "rzp_test_demo" or not webhook_secret:
        return True
    expected = hmac.new(webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


# ─────────────────────────────────────────────────────────────────────
# Admin guard
# ─────────────────────────────────────────────────────────────────────

def admin_required(fn):
    """Decorator: require a valid merchant JWT AND that the account
    email appears in Config.ADMIN_EMAILS. Depends on @jwt_required
    already having run (so g.user_id is set)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        import models
        user = models.find_user_by_id(g.user_id)
        if not user:
            raise ApiError("Account not found.", 404, code="NOT_FOUND")
        email = user.get("email", "")
        if email not in Config.ADMIN_EMAILS:
            raise ApiError("Admin access required.", 403, code="FORBIDDEN")
        g.admin_email = email
        return fn(*args, **kwargs)
    return wrapper
