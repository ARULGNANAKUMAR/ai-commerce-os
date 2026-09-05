"""
commerce/cart_service.py
──────────────────────────
Cart CRUD driven by chat or direct API calls. Every product reference
is validated against catalog.product_service so an invalid or
cross-tenant product_id can never enter a cart.
"""

import models
from catalog.product_service import get_product
from permissions.permission_service import check_permission
from utils import ApiError


def _get_or_create_cart(merchant_id: str, session_id: str) -> dict:
    cart = models.find_cart_by_session(merchant_id, session_id)
    if cart:
        return cart
    cart_id = models.create_cart(merchant_id, session_id)
    return models.find_cart_by_id(merchant_id, cart_id)


def get_cart(merchant_id: str, session_id: str) -> dict:
    cart = models.find_cart_by_session(merchant_id, session_id)
    if not cart:
        return {"items": [], "total": 0, "currency": "INR", "item_count": 0, "cart_id": None, "status": "empty"}
    return serialize_cart(cart)


def add_item(merchant_id: str, session_id: str, product_id: str, quantity: int = 1) -> dict:
    decision = check_permission(merchant_id, "cart_create")
    if decision == "DENY":
        raise ApiError("Cart creation is not enabled for this merchant's agent.", 403, code="PERMISSION_DENIED")

    if quantity < 1:
        raise ApiError("Quantity must be at least 1.", 400, code="INVALID_QUANTITY")

    product = get_product(merchant_id, product_id)
    if not product:
        raise ApiError("Product not found.", 404, code="NOT_FOUND")
    if product.get("stock", 0) < quantity:
        raise ApiError(f"Only {product.get('stock', 0)} unit(s) of '{product['name']}' available.",
                       409, code="INSUFFICIENT_STOCK")

    cart  = _get_or_create_cart(merchant_id, session_id)
    items = cart.get("items", [])

    existing = next((i for i in items if i["product_id"] == product_id), None)
    if existing:
        existing["quantity"] += quantity
    else:
        items.append({
            "product_id": product_id, "name": product["name"],
            "price": product["price"], "quantity": quantity,
        })

    total = round(sum(i["price"] * i["quantity"] for i in items), 2)
    models.save_cart_items(merchant_id, str(cart["_id"]), items, total)
    return serialize_cart(models.find_cart_by_id(merchant_id, str(cart["_id"])))


def update_item_quantity(merchant_id: str, session_id: str, product_id: str, quantity: int) -> dict:
    cart = models.find_cart_by_session(merchant_id, session_id)
    if not cart:
        raise ApiError("Cart is empty.", 404, code="EMPTY_CART")

    if quantity < 0:
        raise ApiError("Quantity cannot be negative.", 400, code="INVALID_QUANTITY")

    items = cart.get("items", [])
    item = next((i for i in items if i["product_id"] == product_id), None)
    if not item:
        raise ApiError("Product not found in cart.", 404, code="NOT_IN_CART")

    if quantity == 0:
        items = [i for i in items if i["product_id"] != product_id]
    else:
        product = get_product(merchant_id, product_id)
        if product and product.get("stock", 0) < quantity:
            raise ApiError(f"Only {product.get('stock', 0)} unit(s) available.", 409, code="INSUFFICIENT_STOCK")
        item["quantity"] = quantity

    total = round(sum(i["price"] * i["quantity"] for i in items), 2)
    models.save_cart_items(merchant_id, str(cart["_id"]), items, total)
    return serialize_cart(models.find_cart_by_id(merchant_id, str(cart["_id"])))


def remove_item(merchant_id: str, session_id: str, product_id: str) -> dict:
    cart = models.find_cart_by_session(merchant_id, session_id)
    if not cart:
        raise ApiError("Cart is empty.", 404, code="EMPTY_CART")

    items = cart.get("items", [])
    if not any(i["product_id"] == product_id for i in items):
        raise ApiError("Product not found in cart.", 404, code="NOT_IN_CART")

    items = [i for i in items if i["product_id"] != product_id]
    total = round(sum(i["price"] * i["quantity"] for i in items), 2)
    models.save_cart_items(merchant_id, str(cart["_id"]), items, total)
    return serialize_cart(models.find_cart_by_id(merchant_id, str(cart["_id"])))


def clear_cart(merchant_id: str, session_id: str) -> dict:
    cart = models.find_cart_by_session(merchant_id, session_id)
    if not cart:
        return {"items": [], "total": 0, "item_count": 0}
    models.save_cart_items(merchant_id, str(cart["_id"]), [], 0)
    return serialize_cart(models.find_cart_by_id(merchant_id, str(cart["_id"])))


def serialize_cart(cart: dict) -> dict:
    if not cart:
        return {"items": [], "total": 0, "currency": "INR", "item_count": 0, "cart_id": None, "status": "empty"}
    items = cart.get("items", [])
    return {
        "cart_id":    str(cart["_id"]),
        "items":      items,
        "total":      cart.get("total", 0),
        "currency":   cart.get("currency", "INR"),
        "item_count": sum(i["quantity"] for i in items),
        "status":     cart.get("status", "active"),
    }
