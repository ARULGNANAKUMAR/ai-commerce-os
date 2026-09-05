"""
commerce/recommendation_service.py
─────────────────────────────────────
Personalized, budget-based, alternative, and bundle recommendations.

Upsell / cross-sell reuse the exact same permission-gated logic as the
Phase 3 workflow nodes (sales.upsell / sales.cross_sell) — this module
calls into workflow.node_handlers so there is exactly one implementation
of "what counts as an upsell" across chat and the visual builder.
"""

import models
from catalog.product_service import get_products
from permissions.permission_service import check_permission
from utils import ApiError


def recommend_personalized(merchant_id: str, session_id: str, limit: int = 5) -> dict:
    """Use the customer session's remembered context (category/tags from
    past searches in this conversation) to rank recommendations."""
    session = models.find_customer_session(merchant_id, session_id) if session_id else None
    variables = (session or {}).get("variables", {})
    category  = variables.get("last_category")

    params = {"page": 1, "limit": limit, "in_stock_only": True}
    if category:
        params["category"] = category
    result = get_products(merchant_id, params)
    products = result["products"]
    # Prefer in-stock, higher discount first (proxy for "recommended")
    products.sort(key=lambda p: (-p.get("discount", 0), p.get("price", 0)))

    models.log_recommendation(merchant_id, session_id or "anon", "personalized",
                              [p["id"] for p in products[:limit]],
                              reason=f"Based on interest in {category}" if category else "General top picks")
    return {"recommendations": products[:limit], "count": len(products[:limit]),
            "basis": f"category:{category}" if category else "general"}


def recommend_by_budget(merchant_id: str, budget: float, category: str = None, limit: int = 5) -> dict:
    if budget is None or budget <= 0:
        raise ApiError("A positive budget amount is required.", 400, code="INVALID_BUDGET")

    params = {"page": 1, "limit": 50, "max_price": budget, "in_stock_only": True}
    if category:
        params["category"] = category
    result = get_products(merchant_id, params)
    products = result["products"]
    # Best value: highest discount, then closest to budget without exceeding it
    products.sort(key=lambda p: (-p.get("discount", 0), -p.get("price", 0)))

    return {"recommendations": products[:limit], "count": len(products[:limit]), "budget": budget}


def recommend_alternatives(merchant_id: str, product_id: str, limit: int = 4) -> dict:
    from catalog.product_service import get_product
    base = get_product(merchant_id, product_id)
    if not base:
        raise ApiError("Product not found.", 404, code="NOT_FOUND")

    params = {"page": 1, "limit": 50, "category": base.get("category") or None, "in_stock_only": True}
    result = get_products(merchant_id, params)
    alts = [p for p in result["products"] if p["id"] != product_id]
    alts.sort(key=lambda p: abs(p.get("price", 0) - base.get("price", 0)))
    return {"base_product": base, "alternatives": alts[:limit], "count": len(alts[:limit])}


def recommend_bundle(merchant_id: str, product_id: str, bundle_size: int = 2, limit: int = 3) -> dict:
    """Suggest complementary products (different category) to bundle with the base product."""
    from catalog.product_service import get_product
    base = get_product(merchant_id, product_id)
    if not base:
        raise ApiError("Product not found.", 404, code="NOT_FOUND")

    result = get_products(merchant_id, {"page": 1, "limit": 100, "in_stock_only": True})
    candidates = [p for p in result["products"]
                  if p["id"] != product_id and p.get("category") != base.get("category")]
    candidates.sort(key=lambda p: (-p.get("discount", 0), p.get("price", 0)))
    bundle_items = candidates[:max(bundle_size - 1, 1)][:limit]

    bundle_total = base.get("price", 0) + sum(p.get("price", 0) for p in bundle_items)
    bundle_discount_pct = 5  # simple flat bundle incentive
    bundle_price = round(bundle_total * (1 - bundle_discount_pct / 100), 2)

    return {
        "base_product":   base,
        "bundle_items":   bundle_items,
        "bundle_total":   bundle_total,
        "bundle_price":   bundle_price,
        "bundle_discount_pct": bundle_discount_pct,
        "savings":        round(bundle_total - bundle_price, 2),
    }


def recommend_upsell(merchant_id: str, product_ids: list, session_id: str = None) -> dict:
    from workflow.node_handlers import handle_upsell
    decision = check_permission(merchant_id, "upsell")
    context = {"step_outputs": {"_seed": {"products": _resolve_products(merchant_id, product_ids)}}}
    output, _ = handle_upsell({"upsell_percentage": 20, "max_suggestions": 3}, context, merchant_id)
    if session_id and output.get("products"):
        models.log_recommendation(merchant_id, session_id, "upsell",
                                  [p["id"] for p in output["products"]], reason="upsell")
    return {**output, "permission_decision": decision}


def recommend_cross_sell(merchant_id: str, product_ids: list, session_id: str = None) -> dict:
    from workflow.node_handlers import handle_cross_sell
    decision = check_permission(merchant_id, "cross_sell")
    context = {"step_outputs": {"_seed": {"products": _resolve_products(merchant_id, product_ids)}}}
    output, _ = handle_cross_sell({"max_suggestions": 3}, context, merchant_id)
    if session_id and output.get("products"):
        models.log_recommendation(merchant_id, session_id, "cross_sell",
                                  [p["id"] for p in output["products"]], reason="cross_sell")
    return {**output, "permission_decision": decision}


def _resolve_products(merchant_id: str, product_ids: list) -> list:
    from catalog.product_service import get_product
    out = []
    for pid in product_ids or []:
        p = get_product(merchant_id, pid)
        if p:
            out.append(p)
    return out
