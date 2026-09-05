"""
commerce/search_service.py
─────────────────────────────
Product search built on top of catalog.product_service.

"Semantic search" here is implemented as token-overlap relevance
scoring across name/description/category/brand/tags — no vector DB
required (Phase 2's product catalog explicitly deferred vector search;
this keeps that architecture decision intact while still being far
better than a plain substring match). Swapping in real embeddings
later only touches _score_product() and stays a drop-in change.
"""

import re
from catalog.product_service import get_products, get_product
from utils import ApiError

STOPWORDS = {"a", "an", "the", "show", "me", "find", "search", "for", "i", "want", "need",
             "looking", "do", "you", "have", "under", "below", "budget", "please", "some"}


def _tokenize(text: str) -> set:
    words = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def _score_product(query_tokens: set, product: dict) -> float:
    hay = " ".join([
        product.get("name", ""), product.get("description", ""),
        product.get("category", ""), product.get("brand", ""),
        " ".join(product.get("tags", [])),
    ])
    hay_tokens = _tokenize(hay)
    if not query_tokens or not hay_tokens:
        return 0.0
    overlap = query_tokens & hay_tokens
    score = len(overlap) / len(query_tokens)
    # Boost exact name-token matches
    name_tokens = _tokenize(product.get("name", ""))
    if query_tokens & name_tokens:
        score += 0.5
    # Small boost for in-stock, discount
    if product.get("availability") == "in_stock":
        score += 0.1
    if product.get("discount", 0) > 0:
        score += 0.05
    return score


def search_products(merchant_id: str, query: str, category: str = None,
                     brand: str = None, min_price: float = None, max_price: float = None,
                     in_stock_only: bool = True, limit: int = 10) -> dict:
    """Semantic-ish relevance search with structured filters, inventory-aware by default."""
    params = {"page": 1, "limit": 200}  # pull a wide candidate set, then rank
    if category:
        params["category"] = category
    if min_price is not None:
        params["min_price"] = min_price
    if max_price is not None:
        params["max_price"] = max_price
    if in_stock_only:
        params["in_stock_only"] = True

    result = get_products(merchant_id, params)
    candidates = result["products"]

    if brand:
        b = brand.lower()
        candidates = [p for p in candidates if b in (p.get("brand") or "").lower()]

    query_tokens = _tokenize(query)
    if query_tokens:
        scored = [(p, _score_product(query_tokens, p)) for p in candidates]
        scored = [s for s in scored if s[1] > 0]
        scored.sort(key=lambda s: s[1], reverse=True)
        ranked = [p for p, _ in scored]
    else:
        ranked = candidates

    return {
        "products":     ranked[:limit],
        "count":        len(ranked[:limit]),
        "total_candidates": len(candidates),
        "query":        query,
        "filters": {
            "category": category, "brand": brand,
            "min_price": min_price, "max_price": max_price,
            "in_stock_only": in_stock_only,
        },
    }


def find_similar_products(merchant_id: str, product_id: str, limit: int = 5) -> dict:
    base = get_product(merchant_id, product_id)
    if not base:
        raise ApiError("Product not found.", 404, code="NOT_FOUND")

    params = {"page": 1, "limit": 100, "category": base.get("category") or None}
    result = get_products(merchant_id, params)
    candidates = [p for p in result["products"] if p["id"] != product_id]

    # Score by category match (already filtered) + price proximity + shared tags
    base_price = base.get("price", 0)
    base_tags  = set(base.get("tags", []))

    def _sim_score(p):
        score = 1.0  # same category baseline
        price_diff = abs(p.get("price", 0) - base_price)
        score -= min(price_diff / (base_price + 1), 1.0) * 0.5
        shared_tags = base_tags & set(p.get("tags", []))
        score += len(shared_tags) * 0.2
        if p.get("brand") == base.get("brand"):
            score += 0.3
        return score

    candidates.sort(key=_sim_score, reverse=True)
    return {"base_product": base, "similar_products": candidates[:limit], "count": len(candidates[:limit])}
