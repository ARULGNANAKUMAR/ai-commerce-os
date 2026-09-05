"""
commerce/copilot_service.py
──────────────────────────────
Merchant-facing analytical assistant. Answers three canned question
types using real signals already captured elsewhere in the platform
(carts collection = demand proxy, ai_memory = recommendation frequency,
products = catalog state) — not invented numbers. Anything outside
those three patterns falls back to a general AI response (mock-safe,
same pattern as workflow/node_handlers.py).

No `orders` collection exists yet (checkout execution is Phase 5), so
"which products sell better" uses cart-add frequency across all carts
as the best available demand signal, and says so explicitly in the
response rather than presenting it as confirmed sales data.
"""

import re
from collections import Counter

import models
from catalog.product_service import get_products
from utils import ApiError


def _cart_item_frequency(merchant_id: str) -> Counter:
    carts = models.find_all_carts(merchant_id, limit=1000)
    freq = Counter()
    for cart in carts:
        for item in cart.get("items", []):
            freq[item["product_id"]] += item.get("quantity", 1)
    return freq


def _co_occurrence(merchant_id: str) -> Counter:
    """Count how often product pairs appear together in the same cart —
    the signal used for bundle suggestions."""
    carts = models.find_all_carts(merchant_id, limit=1000)
    pair_counts = Counter()
    for cart in carts:
        ids = sorted({i["product_id"] for i in cart.get("items", [])})
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pair_counts[(ids[i], ids[j])] += 1
    return pair_counts


def ask(merchant_id: str, question: str) -> dict:
    q = (question or "").lower()

    if any(kw in q for kw in ["sell better", "best seller", "top product", "which product"]):
        return _which_sell_better(merchant_id)

    if any(kw in q for kw in ["campaign", "need promotion", "underperform", "slow mov"]):
        return _which_need_campaigns(merchant_id)

    if any(kw in q for kw in ["bundle", "combo", "cross-sell", "cross sell", "increase revenue"]):
        return _which_bundles(merchant_id)

    return _fallback(merchant_id, question)


def _product_lookup(merchant_id: str, ids: list) -> dict:
    result = get_products(merchant_id, {"page": 1, "limit": 500})
    by_id = {p["id"]: p for p in result["products"]}
    return {pid: by_id[pid] for pid in ids if pid in by_id}


def _which_sell_better(merchant_id: str) -> dict:
    freq = _cart_item_frequency(merchant_id)
    if not freq:
        return {
            "answer": "No cart activity recorded yet, so there isn't enough data to rank products. "
                      "Once customers start adding items to their carts, I can identify your top performers.",
            "insight_type": "top_products", "data": [],
        }
    top = freq.most_common(5)
    products = _product_lookup(merchant_id, [pid for pid, _ in top])
    ranked = [{"product": products[pid], "cart_adds": count} for pid, count in top if pid in products]
    names = ", ".join(r["product"]["name"] for r in ranked[:3])
    return {
        "answer": f"Based on cart activity (the best signal available before checkout data exists), "
                  f"your most-added products are: {names}.",
        "insight_type": "top_products", "data": ranked,
    }


def _which_need_campaigns(merchant_id: str) -> dict:
    freq = _cart_item_frequency(merchant_id)
    result = get_products(merchant_id, {"page": 1, "limit": 200, "in_stock_only": True})
    all_products = result["products"]
    # High stock + low/no cart interest = campaign candidate
    candidates = sorted(
        [p for p in all_products if p.get("stock", 0) > 5],
        key=lambda p: (freq.get(p["id"], 0), -p.get("stock", 0)),
    )[:5]
    if not candidates:
        return {"answer": "Not enough catalog data to identify campaign candidates yet.",
                "insight_type": "campaign_candidates", "data": []}
    names = ", ".join(p["name"] for p in candidates[:3])
    return {
        "answer": f"These products have high stock but low cart engagement, making them good "
                  f"campaign candidates: {names}.",
        "insight_type": "campaign_candidates",
        "data": [{"product": p, "cart_adds": freq.get(p["id"], 0)} for p in candidates],
    }


def _which_bundles(merchant_id: str) -> dict:
    pairs = _co_occurrence(merchant_id)
    if not pairs:
        return {
            "answer": "No repeated product pairings in carts yet. As customers build carts with "
                      "multiple items, I'll surface which combinations to bundle.",
            "insight_type": "bundle_suggestions", "data": [],
        }
    top_pairs = pairs.most_common(3)
    ids = {pid for pair, _ in top_pairs for pid in pair}
    products = _product_lookup(merchant_id, list(ids))
    suggestions = []
    for (a, b), count in top_pairs:
        if a in products and b in products:
            suggestions.append({
                "products": [products[a], products[b]], "co_occurrences": count,
            })
    if not suggestions:
        return {"answer": "Not enough data yet to suggest bundles.", "insight_type": "bundle_suggestions", "data": []}
    first = suggestions[0]
    names = " + ".join(p["name"] for p in first["products"])
    return {
        "answer": f"Customers frequently cart {names} together — bundling them could increase "
                  f"average order value.",
        "insight_type": "bundle_suggestions", "data": suggestions,
    }


def _fallback(merchant_id: str, question: str) -> dict:
    try:
        from ai.provider_service import get_live_client
        adapter, raw_key, model = get_live_client(merchant_id)
        answer = adapter.complete(raw_key, model,
                                  f"You are a merchant analytics copilot for an e-commerce platform. "
                                  f"Answer briefly: {question}")
        raw_key = None
        if not answer:
            raise ValueError("empty")
    except Exception:
        answer = ("I can currently answer questions about top-performing products, campaign "
                  "candidates, and bundle opportunities. Try asking one of those.")
    return {"answer": answer, "insight_type": "general", "data": []}
