"""
commerce/comparison_service.py
─────────────────────────────────
Compares 2–6 products across price, rating, specifications, features,
stock, discount, and a mock delivery estimate. Produces an
"explainable" summary — a plain-English sentence per criterion stating
which product wins and why, not just a raw table.

Rating: the product schema (Phase 2) has no rating field, so a
deterministic synthetic rating is derived from availability + discount
as a stand-in until a real reviews system exists — clearly labelled
as such in the output so it's never mistaken for real customer data.
"""

from catalog.product_service import get_product
from utils import ApiError

MAX_COMPARE = 6
MIN_COMPARE = 2


def _synthetic_rating(product: dict) -> float:
    """Deterministic stand-in rating (out of 5) until real reviews exist."""
    base = 3.5
    if product.get("availability") == "in_stock":
        base += 0.5
    base += min(product.get("discount", 0) / 100, 0.5)
    if product.get("stock", 0) > 20:
        base += 0.3
    return round(min(base, 5.0), 1)


def _delivery_estimate(product: dict) -> str:
    if product.get("availability") == "out_of_stock":
        return "Currently unavailable"
    if product.get("availability") == "pre_order":
        return "Pre-order — ships in 2-3 weeks"
    stock = product.get("stock", 0)
    if stock > 20:
        return "1-2 business days"
    if stock > 0:
        return "2-4 business days"
    return "Currently unavailable"


def compare_products(merchant_id: str, product_ids: list, attributes: list = None) -> dict:
    if not product_ids or len(product_ids) < MIN_COMPARE:
        raise ApiError(f"Provide at least {MIN_COMPARE} product IDs to compare.", 400, code="TOO_FEW_PRODUCTS")
    if len(product_ids) > MAX_COMPARE:
        raise ApiError(f"You can compare at most {MAX_COMPARE} products at once.", 400, code="TOO_MANY_PRODUCTS")

    products = []
    missing = []
    for pid in product_ids:
        p = get_product(merchant_id, pid)
        if p:
            products.append(p)
        else:
            missing.append(pid)

    if len(products) < MIN_COMPARE:
        if missing:
            _raise_missing(missing)
        raise ApiError("Not enough valid products found to compare.", 404, code="NOT_FOUND")

    attrs = attributes or ["price", "rating", "specifications", "features", "stock", "discount", "delivery"]

    rows = []
    for p in products:
        row = {"id": p["id"], "name": p["name"], "brand": p.get("brand", "N/A")}
        if "price" in attrs:
            row["price"] = p.get("price", None)
        if "rating" in attrs:
            row["rating"] = _synthetic_rating(p)
            row["rating_note"] = "estimated (no review data yet)"
        if "specifications" in attrs:
            row["specifications"] = p.get("specifications") or {"note": "No specifications provided"}
        if "features" in attrs:
            row["features"] = p.get("tags") or []
        if "stock" in attrs:
            row["stock"] = p.get("stock", 0)
        if "discount" in attrs:
            row["discount"] = p.get("discount", 0)
        if "delivery" in attrs:
            row["delivery_estimate"] = _delivery_estimate(p)
        rows.append(row)

    summary = _build_explanation(rows, attrs)

    return {
        "products":        rows,
        "count":            len(rows),
        "missing_ids":      missing,
        "compared_attributes": attrs,
        "summary":          summary,
    }


def _raise_missing(missing):
    raise ApiError(f"Product(s) not found: {', '.join(missing)}", 404, code="NOT_FOUND")


def _build_explanation(rows: list, attrs: list) -> list:
    """Generate plain-English explainable comparison points."""
    lines = []

    if "price" in attrs:
        priced = [r for r in rows if r.get("price") is not None]
        if priced:
            cheapest = min(priced, key=lambda r: r["price"])
            lines.append(f"{cheapest['name']} is the most affordable at ₹{cheapest['price']:,.0f}.")

    if "rating" in attrs:
        top_rated = max(rows, key=lambda r: r.get("rating", 0))
        lines.append(f"{top_rated['name']} has the highest estimated rating ({top_rated['rating']}/5).")

    if "stock" in attrs:
        in_stock = [r for r in rows if r.get("stock", 0) > 0]
        if len(in_stock) < len(rows):
            out = [r["name"] for r in rows if r.get("stock", 0) == 0]
            lines.append(f"{', '.join(out)} {'is' if len(out)==1 else 'are'} currently out of stock.")

    if "discount" in attrs:
        discounted = [r for r in rows if r.get("discount", 0) > 0]
        if discounted:
            best_deal = max(discounted, key=lambda r: r["discount"])
            lines.append(f"{best_deal['name']} has the biggest discount at {best_deal['discount']}% off.")

    if "delivery" in attrs:
        fastest = [r for r in rows if "1-2" in r.get("delivery_estimate", "")]
        if fastest:
            lines.append(f"{fastest[0]['name']} ships fastest ({fastest[0]['delivery_estimate']}).")

    if not lines:
        lines.append("Products are broadly comparable across the selected attributes.")

    return lines
