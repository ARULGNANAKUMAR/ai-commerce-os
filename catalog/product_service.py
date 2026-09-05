"""
catalog/product_service.py
──────────────────────────
Business logic for the product catalog. Routes call these functions;
they never touch MongoDB directly (that stays in models.py).

Responsibilities:
  - validate_product_data()  – schema + business-rule validation
  - product CRUD with audit logging
  - search / filter orchestration (keyword, category, price, stock)
  - serialization (strip internal fields before API response)
"""

from security import sanitize_string
from utils import ApiError, utcnow
import models

# ── Allowed values ────────────────────────────────────────────────────

ALLOWED_AVAILABILITY = {"in_stock", "out_of_stock", "pre_order"}
ALLOWED_CURRENCIES = {"INR", "USD", "EUR", "GBP", "AED", "SGD"}
ALLOWED_STATUSES = {"active", "inactive"}


# ── Validation ────────────────────────────────────────────────────────

def validate_product_data(data: dict, require_name: bool = True) -> tuple[bool, list]:
    """Return (is_valid, list_of_error_messages)."""
    errors = []

    name = data.get("name", "")
    if require_name and not str(name).strip():
        errors.append("'name' is required.")
    elif name and len(str(name)) > 500:
        errors.append("'name' must be ≤ 500 characters.")

    price = data.get("price")
    if price is None and require_name:  # price required on create
        errors.append("'price' is required.")
    elif price is not None:
        try:
            p = float(price)
            if p < 0:
                errors.append("'price' must be a non-negative number.")
        except (ValueError, TypeError):
            errors.append("'price' must be a valid number.")

    stock = data.get("stock")
    if stock is not None:
        try:
            s = int(stock)
            if s < 0:
                errors.append("'stock' must be a non-negative integer.")
        except (ValueError, TypeError):
            errors.append("'stock' must be a valid integer.")

    discount = data.get("discount")
    if discount is not None:
        try:
            d = float(discount)
            if not (0 <= d <= 100):
                errors.append("'discount' must be between 0 and 100.")
        except (ValueError, TypeError):
            errors.append("'discount' must be a valid number.")

    availability = data.get("availability")
    if availability and availability not in ALLOWED_AVAILABILITY:
        errors.append(f"'availability' must be one of: {', '.join(sorted(ALLOWED_AVAILABILITY))}.")

    currency = data.get("currency")
    if currency and currency not in ALLOWED_CURRENCIES:
        errors.append(f"'currency' must be one of: {', '.join(sorted(ALLOWED_CURRENCIES))}.")

    return len(errors) == 0, errors


def _sanitize_product_input(data: dict) -> dict:
    return {
        "name":          sanitize_string(data.get("name"), 500),
        "description":   sanitize_string(data.get("description"), 5000),
        "category":      sanitize_string(data.get("category"), 200),
        "brand":         sanitize_string(data.get("brand"), 200),
        "price":         float(data["price"]),
        "currency":      sanitize_string(data.get("currency") or "INR", 10),
        "discount":      float(data.get("discount") or 0),
        "stock":         int(data.get("stock") or 0),
        "sku":           sanitize_string(data.get("sku"), 100),
        "images":        [str(u) for u in (data.get("images") or []) if u][:10],
        "specifications": dict(data.get("specifications") or {}),
        "tags":          [sanitize_string(t, 100) for t in (data.get("tags") or []) if t][:20],
        "availability":  data.get("availability") or "in_stock",
    }


# ── CRUD ──────────────────────────────────────────────────────────────

def create_product(merchant_id: str, raw_data: dict, user_id: str = None) -> dict:
    valid, errors = validate_product_data(raw_data)
    if not valid:
        raise ApiError("; ".join(errors), 400, code="VALIDATION_ERROR")

    # Duplicate SKU check
    sku = sanitize_string(raw_data.get("sku"), 100)
    if sku and models.find_product_by_sku(merchant_id, sku):
        raise ApiError(f"A product with SKU '{sku}' already exists.", 409, code="DUPLICATE_SKU")

    clean = _sanitize_product_input(raw_data)
    product_id = models.create_product(merchant_id, clean)

    models.log_audit(
        "product_created", user_id=user_id, merchant_id=merchant_id,
        details={"product_id": product_id, "name": clean["name"]},
    )
    return serialize_product(models.find_product_by_id(merchant_id, product_id))


def get_products(merchant_id: str, query_params: dict) -> dict:
    filters = {
        "keyword":      sanitize_string(query_params.get("keyword"), 200) or None,
        "category":     sanitize_string(query_params.get("category"), 200) or None,
        "availability": query_params.get("availability") or None,
        "status":       query_params.get("status") or None,
        "in_stock_only": query_params.get("in_stock_only") in ("1", "true", True),
    }
    try:
        if query_params.get("min_price") is not None:
            filters["min_price"] = float(query_params["min_price"])
        if query_params.get("max_price") is not None:
            filters["max_price"] = float(query_params["max_price"])
    except (ValueError, TypeError):
        pass

    page  = max(1, int(query_params.get("page", 1)))
    limit = min(int(query_params.get("limit", 20)), 100)
    skip  = (page - 1) * limit

    total   = models.count_products(merchant_id, filters)
    records = models.find_products(merchant_id, filters, skip=skip, limit=limit)

    return {
        "products": [serialize_product(p) for p in records],
        "pagination": {
            "total": total, "page": page, "limit": limit,
            "pages": max(1, (total + limit - 1) // limit),
        },
    }


def get_product(merchant_id: str, product_id: str) -> dict:
    product = models.find_product_by_id(merchant_id, product_id)
    if not product:
        raise ApiError("Product not found.", 404, code="NOT_FOUND")
    return serialize_product(product)


def update_product(merchant_id: str, product_id: str, raw_data: dict, user_id: str = None) -> dict:
    if not models.find_product_by_id(merchant_id, product_id):
        raise ApiError("Product not found.", 404, code="NOT_FOUND")

    valid, errors = validate_product_data(raw_data, require_name=False)
    if not valid:
        raise ApiError("; ".join(errors), 400, code="VALIDATION_ERROR")

    # SKU uniqueness if being changed
    new_sku = sanitize_string(raw_data.get("sku"), 100)
    if new_sku:
        existing = models.find_product_by_sku(merchant_id, new_sku)
        if existing and str(existing["_id"]) != product_id:
            raise ApiError(f"A product with SKU '{new_sku}' already exists.", 409, code="DUPLICATE_SKU")

    # Build update dict from only provided fields
    allowed = ["name", "description", "category", "brand", "price", "currency",
               "discount", "stock", "sku", "images", "specifications", "tags",
               "availability", "status"]
    updates = {}
    for field in allowed:
        if field in raw_data:
            if field == "price":
                updates[field] = float(raw_data[field])
            elif field in ("stock",):
                updates[field] = int(raw_data[field])
            elif field in ("images", "tags"):
                updates[field] = list(raw_data[field])
            elif field == "specifications":
                updates[field] = dict(raw_data[field])
            else:
                updates[field] = sanitize_string(str(raw_data[field]), 5000)

    if not updates:
        raise ApiError("No valid fields provided to update.", 400, code="NO_UPDATES")

    models.update_product(merchant_id, product_id, updates)
    models.log_audit(
        "product_updated", user_id=user_id, merchant_id=merchant_id,
        details={"product_id": product_id, "fields": list(updates.keys())},
    )
    return serialize_product(models.find_product_by_id(merchant_id, product_id))


def delete_product(merchant_id: str, product_id: str, user_id: str = None) -> None:
    if not models.find_product_by_id(merchant_id, product_id):
        raise ApiError("Product not found.", 404, code="NOT_FOUND")
    models.soft_delete_product(merchant_id, product_id)
    models.log_audit(
        "product_deleted", user_id=user_id, merchant_id=merchant_id,
        details={"product_id": product_id},
    )


# ── Serialization ─────────────────────────────────────────────────────

def serialize_product(product: dict) -> dict:
    if not product:
        return {}
    return {
        "id":            str(product["_id"]),
        "name":          product.get("name", ""),
        "description":   product.get("description", ""),
        "category":      product.get("category", ""),
        "brand":         product.get("brand", ""),
        "price":         product.get("price", 0),
        "currency":      product.get("currency", "INR"),
        "discount":      product.get("discount", 0),
        "stock":         product.get("stock", 0),
        "sku":           product.get("sku", ""),
        "images":        product.get("images", []),
        "specifications": product.get("specifications", {}),
        "tags":          product.get("tags", []),
        "availability":  product.get("availability", "in_stock"),
        "status":        product.get("status", "active"),
        "created_at":    product["created_at"].isoformat() if product.get("created_at") else None,
        "updated_at":    product["updated_at"].isoformat() if product.get("updated_at") else None,
    }
