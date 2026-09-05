"""
analytics/analytics_service.py
────────────────────────────────
Computes all eight dashboard metrics from the live DB collections.
No pre-aggregation pipeline required for Phase 5 MVP — data volumes
are small enough for in-Python computation on each request.
Phase 6+ should move to MongoDB Aggregation Pipeline or Atlas Charts.
"""

from collections import Counter, defaultdict
import models


def compute_analytics(merchant_id: str) -> dict:
    """Return all metrics for the merchant analytics dashboard."""
    return {
        "revenue":                  _revenue(merchant_id),
        "conversion_rate":          _conversion_rate(merchant_id),
        "average_order_value":      _avg_order_value(merchant_id),
        "upsell_revenue":           _upsell_revenue(merchant_id),
        "cross_sell_revenue":       _cross_sell_revenue(merchant_id),
        "recommendation_accuracy":  _recommendation_accuracy(merchant_id),
        "workflow_success_rate":    _workflow_success_rate(merchant_id),
        "payment_success_rate":     _payment_success_rate(merchant_id),
        "payment_failure_rate":     _payment_failure_rate(merchant_id),
    }


def get_audit_timeline(merchant_id: str, limit: int = 50) -> list:
    """Visual timeline: ordered list of audit events enriched with type tags."""
    logs = models.get_recent_audit_logs(merchant_id, limit=limit)
    timeline = []
    type_map = {
        "payment_order_created":  ("💳", "Payment order created",    "payment"),
        "payment_captured":       ("✅", "Payment captured",          "payment"),
        "payment_failed":         ("❌", "Payment failed",            "payment"),
        "payment_retried":        ("🔁", "Payment retried",           "payment"),
        "payment_refunded":       ("↩️", "Refund processed",          "payment"),
        "payment_signature_invalid": ("⚠️", "Invalid signature",     "security"),
        "checkout_requested":     ("🛒", "Checkout requested",        "approval"),
        "checkout_approved":      ("👍", "Checkout approved",         "approval"),
        "checkout_rejected":      ("👎", "Checkout rejected",         "approval"),
        "workflow_executed":      ("⚡", "Workflow executed",         "workflow"),
        "permission_updated":     ("🛡",  "Permission changed",       "permission"),
        "ai_provider_tested":     ("🤖", "AI provider tested",        "ai"),
        "product_imported":       ("📦", "Products imported",         "catalog"),
    }
    for log in logs:
        action = log.get("action", "")
        icon, label, tag = type_map.get(action, ("📋", action.replace("_", " ").title(), "general"))
        timeline.append({
            "id":        str(log["_id"]),
            "action":    action,
            "label":     label,
            "icon":      icon,
            "tag":       tag,
            "details":   log.get("details", {}),
            "timestamp": log["timestamp"].isoformat() if log.get("timestamp") else None,
        })
    return timeline


# ─────────────────────────────────────────────────────────────────────
# Individual metric calculations
# ─────────────────────────────────────────────────────────────────────

def _revenue(merchant_id: str) -> dict:
    orders = models.find_orders(merchant_id, status="paid", limit=1000)
    total  = round(sum(o.get("amount", 0) for o in orders), 2)
    return {"value": total, "unit": "INR", "label": "Total revenue",
            "order_count": len(orders)}


def _conversion_rate(merchant_id: str) -> dict:
    """Paid orders / total (non-failed) orders."""
    all_orders  = models.find_orders(merchant_id, limit=1000)
    paid        = [o for o in all_orders if o.get("status") == "paid"]
    active      = [o for o in all_orders if o.get("status") not in ("failed",)]
    rate = round(len(paid) / len(active) * 100, 1) if active else 0.0
    return {"value": rate, "unit": "percent", "label": "Conversion rate",
            "paid_orders": len(paid), "total_orders": len(active)}


def _avg_order_value(merchant_id: str) -> dict:
    orders = models.find_orders(merchant_id, status="paid", limit=1000)
    if not orders:
        return {"value": 0, "unit": "INR", "label": "Average order value"}
    avg = round(sum(o.get("amount", 0) for o in orders) / len(orders), 2)
    return {"value": avg, "unit": "INR", "label": "Average order value"}


def _upsell_revenue(merchant_id: str) -> dict:
    """Proxy: revenue attributed to sessions that had an upsell recommendation."""
    recs = models.find_recommendations(merchant_id, limit=1000)
    upsell_sessions = {r["session_id"] for r in recs if r.get("type") == "upsell"}
    orders = models.find_orders(merchant_id, status="paid", limit=1000)
    upsell_rev = round(sum(
        o.get("amount", 0) for o in orders
        if o.get("session_id") in upsell_sessions
    ), 2)
    return {"value": upsell_rev, "unit": "INR", "label": "Upsell revenue",
            "sessions": len(upsell_sessions)}


def _cross_sell_revenue(merchant_id: str) -> dict:
    recs = models.find_recommendations(merchant_id, limit=1000)
    cs_sessions = {r["session_id"] for r in recs if r.get("type") == "cross_sell"}
    orders = models.find_orders(merchant_id, status="paid", limit=1000)
    cs_rev = round(sum(
        o.get("amount", 0) for o in orders
        if o.get("session_id") in cs_sessions
    ), 2)
    return {"value": cs_rev, "unit": "INR", "label": "Cross-sell revenue",
            "sessions": len(cs_sessions)}


def _recommendation_accuracy(merchant_id: str) -> dict:
    """
    % of recommendation sessions that resulted in a cart add.
    Proxy: sessions with a recommendation log AND a non-empty cart.
    """
    recs = models.find_recommendations(merchant_id, limit=1000)
    if not recs:
        return {"value": None, "unit": "percent", "label": "Recommendation accuracy",
                "note": "No recommendation data yet"}
    rec_sessions = {r["session_id"] for r in recs}
    carts = models.find_all_carts(merchant_id, limit=1000)
    cart_sessions = {c["session_id"] for c in carts if c.get("items")}
    converted = rec_sessions & cart_sessions
    acc = round(len(converted) / len(rec_sessions) * 100, 1) if rec_sessions else 0.0
    return {"value": acc, "unit": "percent", "label": "Recommendation accuracy",
            "recommended_sessions": len(rec_sessions), "converted_sessions": len(converted)}


def _workflow_success_rate(merchant_id: str) -> dict:
    execs  = models.find_executions(merchant_id, limit=1000)
    if not execs:
        return {"value": None, "unit": "percent", "label": "Workflow success rate",
                "note": "No executions yet"}
    completed = [e for e in execs if e.get("status") == "completed"]
    rate = round(len(completed) / len(execs) * 100, 1)
    return {"value": rate, "unit": "percent", "label": "Workflow success rate",
            "total": len(execs), "completed": len(completed)}


def _payment_success_rate(merchant_id: str) -> dict:
    payments = models.find_payments(merchant_id, limit=1000)
    if not payments:
        return {"value": None, "unit": "percent", "label": "Payment success rate",
                "note": "No payments yet"}
    captured = [p for p in payments if p.get("status") == "captured"]
    rate = round(len(captured) / len(payments) * 100, 1)
    return {"value": rate, "unit": "percent", "label": "Payment success rate",
            "total": len(payments), "captured": len(captured)}


def _payment_failure_rate(merchant_id: str) -> dict:
    payments = models.find_payments(merchant_id, limit=1000)
    if not payments:
        return {"value": None, "unit": "percent", "label": "Payment failure rate",
                "note": "No payments yet"}
    failed = [p for p in payments if p.get("status") == "failed"]
    rate = round(len(failed) / len(payments) * 100, 1)
    return {"value": rate, "unit": "percent", "label": "Payment failure rate",
            "total": len(payments), "failed": len(failed)}
