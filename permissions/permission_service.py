"""
permissions/permission_service.py
──────────────────────────────────
Capability-based permission engine.  Every AI agent action must pass
through check_permission() before execution (enforced by Phase 3
workflow engine).

Design:   deny-by-default.
          Unknown capability → DENY.
          Disabled capability → DENY.
          Enabled + limit check → ALLOW / REQUIRES_APPROVAL / LIMIT_EXCEEDED.

Possible results from check_permission():
    ALLOW
    DENY
    REQUIRES_APPROVAL
    LIMIT_EXCEEDED
"""

from utils import ApiError, utcnow
from config import Config
import models

# ── Capability registry ───────────────────────────────────────────────

CAPABILITIES: list[dict] = [
    # ── Information (enabled by default) ─────────────────────────────
    {
        "capability":    "product_read",
        "label":         "Read Products",
        "description":   "Allow the agent to read product data from your catalog.",
        "category":      "information",
        "default_enabled": True,
        "has_limits":    False,
        "default_limits": {},
    },
    {
        "capability":    "product_search",
        "label":         "Search Products",
        "description":   "Allow the agent to search and filter your product catalog.",
        "category":      "information",
        "default_enabled": True,
        "has_limits":    False,
        "default_limits": {},
    },
    {
        "capability":    "product_compare",
        "label":         "Compare Products",
        "description":   "Allow the agent to compare products side-by-side for customers.",
        "category":      "information",
        "default_enabled": True,
        "has_limits":    False,
        "default_limits": {},
    },
    {
        "capability":    "recommendation",
        "label":         "Recommend Products",
        "description":   "Allow the agent to make personalized product recommendations.",
        "category":      "information",
        "default_enabled": True,
        "has_limits":    False,
        "default_limits": {},
    },
    # ── Sales (disabled by default) ───────────────────────────────────
    {
        "capability":    "upsell",
        "label":         "Upsell",
        "description":   "Allow the agent to suggest higher-tier or premium alternatives.",
        "category":      "sales",
        "default_enabled": False,
        "has_limits":    False,
        "default_limits": {},
    },
    {
        "capability":    "cross_sell",
        "label":         "Cross-sell",
        "description":   "Allow the agent to suggest complementary products.",
        "category":      "sales",
        "default_enabled": False,
        "has_limits":    False,
        "default_limits": {},
    },
    {
        "capability":    "cart_create",
        "label":         "Create Cart",
        "description":   "Allow the agent to create and modify shopping carts.",
        "category":      "sales",
        "default_enabled": False,
        "has_limits":    False,
        "default_limits": {},
    },
    {
        "capability":    "checkout_create",
        "label":         "Create Checkout",
        "description":   "Allow the agent to initiate checkout flows.",
        "category":      "sales",
        "default_enabled": False,
        "has_limits":    False,
        "default_limits": {},
    },
    # ── Financial (disabled by default, with limits) ──────────────────
    {
        "capability":    "payment_request",
        "label":         "Request Payment",
        "description":   "Allow the agent to request payment from customers via Razorpay.",
        "category":      "financial",
        "default_enabled": False,
        "has_limits":    True,
        "default_limits": {
            "max_amount":         Config.DEFAULT_MAX_PAYMENT_AMOUNT,
            "approval_required":  True,
        },
    },
    {
        "capability":    "refund_request",
        "label":         "Request Refund",
        "description":   "Allow the agent to initiate refunds on behalf of customers.",
        "category":      "financial",
        "default_enabled": False,
        "has_limits":    True,
        "default_limits": {
            "max_amount":        Config.DEFAULT_MAX_REFUND_AMOUNT,
            "approval_required": True,
        },
    },
    # ── Advanced (disabled by default) ───────────────────────────────
    {
        "capability":    "campaign_create",
        "label":         "Create Campaigns",
        "description":   "Allow the agent to create discount campaigns and promotional codes.",
        "category":      "advanced",
        "default_enabled": False,
        "has_limits":    False,
        "default_limits": {},
    },
    {
        "capability":    "customer_data_read",
        "label":         "Read Customer Data",
        "description":   "Allow the agent to access customer profile and order history.",
        "category":      "advanced",
        "default_enabled": False,
        "has_limits":    False,
        "default_limits": {},
    },
]

CAPABILITY_IDS: set[str] = {c["capability"] for c in CAPABILITIES}
_CAPABILITY_META: dict[str, dict] = {c["capability"]: c for c in CAPABILITIES}


# ── Default initialization ────────────────────────────────────────────

def ensure_defaults(merchant_id: str) -> None:
    """Lazily initialize all capabilities to their defaults for a merchant.
    Idempotent — safe to call on every request."""
    existing = {p["capability"] for p in models.find_all_permissions(merchant_id)}
    for cap in CAPABILITIES:
        if cap["capability"] not in existing:
            models.upsert_permission(merchant_id, cap["capability"], {
                "enabled":    cap["default_enabled"],
                "limits":     dict(cap["default_limits"]),
                "created_at": utcnow(),
            })


# ── Permission check ──────────────────────────────────────────────────

def check_permission(merchant_id: str, capability: str, context: dict = None) -> str:
    """
    The primary decision function. Called by the Phase 3 workflow engine
    before every agent action.

    Returns one of: ALLOW | DENY | REQUIRES_APPROVAL | LIMIT_EXCEEDED
    """
    # Unknown capability → deny by default (security invariant)
    if capability not in CAPABILITY_IDS:
        return "DENY"

    perm = models.find_permission(merchant_id, capability)
    if not perm:
        # Permission row doesn't exist → use default_enabled value
        meta = _CAPABILITY_META[capability]
        return "ALLOW" if meta["default_enabled"] else "DENY"

    if not perm.get("enabled", False):
        return "DENY"

    # Evaluate financial limits if applicable
    meta = _CAPABILITY_META.get(capability, {})
    if meta.get("has_limits") and context:
        limits = perm.get("limits", {})
        amount = context.get("amount")
        if amount is not None:
            max_amount = limits.get("max_amount")
            if max_amount is not None and float(amount) > float(max_amount):
                return "LIMIT_EXCEEDED"

        approval_required = limits.get("approval_required", False)
        if approval_required:
            return "REQUIRES_APPROVAL"

    return "ALLOW"


# ── CRUD ──────────────────────────────────────────────────────────────

def get_all_permissions(merchant_id: str) -> list:
    ensure_defaults(merchant_id)
    stored = {p["capability"]: p for p in models.find_all_permissions(merchant_id)}
    result = []
    for cap in CAPABILITIES:
        cid = cap["capability"]
        perm = stored.get(cid, {})
        result.append({
            "capability":   cid,
            "label":        cap["label"],
            "description":  cap["description"],
            "category":     cap["category"],
            "has_limits":   cap["has_limits"],
            "enabled":      perm.get("enabled", cap["default_enabled"]),
            "limits":       perm.get("limits", dict(cap["default_limits"])),
            "updated_at":   perm["updated_at"].isoformat() if perm.get("updated_at") else None,
        })
    return result


def update_permission(merchant_id: str, capability: str, enabled: bool,
                      limits: dict = None, user_id: str = None) -> dict:
    if capability not in CAPABILITY_IDS:
        raise ApiError(f"Unknown capability '{capability}'.", 400, code="UNKNOWN_CAPABILITY")

    meta = _CAPABILITY_META[capability]
    updates = {"enabled": bool(enabled)}

    if meta["has_limits"] and limits is not None:
        clean_limits = {}
        if "max_amount" in limits:
            try:
                val = float(limits["max_amount"])
                if val < 0:
                    raise ApiError("max_amount must be non-negative.", 400, code="VALIDATION_ERROR")
                clean_limits["max_amount"] = val
            except (TypeError, ValueError):
                raise ApiError("max_amount must be a number.", 400, code="VALIDATION_ERROR")
        if "approval_required" in limits:
            clean_limits["approval_required"] = bool(limits["approval_required"])
        if clean_limits:
            # Merge with existing limits
            existing = models.find_permission(merchant_id, capability)
            existing_limits = existing.get("limits", {}) if existing else {}
            existing_limits.update(clean_limits)
            updates["limits"] = existing_limits

    models.upsert_permission(merchant_id, capability, {**updates, "created_at": utcnow()})
    models.log_audit(
        "permission_updated", user_id=user_id, merchant_id=merchant_id,
        details={"capability": capability, "enabled": enabled},
    )

    perm = models.find_permission(merchant_id, capability)
    return {
        "capability": capability,
        "label":      meta["label"],
        "enabled":    perm.get("enabled", False),
        "limits":     perm.get("limits", {}),
    }
