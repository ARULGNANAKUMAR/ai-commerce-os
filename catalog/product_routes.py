"""
catalog/product_routes.py
─────────────────────────
Flask blueprint for /api/products.  All routes are JWT-protected.
merchant_id always comes from g (JWT), never from the request body.
"""

from flask import Blueprint, g, request

from security import jwt_required, sanitize_string
from utils import ApiError, api_response, get_client_ip
from config import Config
import models
from catalog.product_service import (
    create_product, get_products, get_product, update_product, delete_product,
)
from catalog.import_service import import_from_csv, import_from_json

products_bp = Blueprint("products", __name__, url_prefix="/api/products")


def _get_merchant_id() -> str:
    """Resolve merchant_id from JWT. Raises 403 if merchant profile is missing."""
    if g.merchant_id:
        return g.merchant_id
    # Fallback: look up from user_id (handles edge case where JWT was issued before
    # merchant profile was created)
    merchant = models.find_merchant_by_user_id(g.user_id)
    if not merchant:
        raise ApiError("Merchant profile not found.", 403, code="NO_MERCHANT")
    return str(merchant["_id"])


# ─────────────────────────────────────────────────────────────────────
# POST /api/products — create one product
# ─────────────────────────────────────────────────────────────────────

@products_bp.route("", methods=["POST"])
@jwt_required
def create():
    merchant_id = _get_merchant_id()
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        raise ApiError("Request body must be a JSON object.", 400, code="BAD_REQUEST")

    product = create_product(merchant_id, body, user_id=g.user_id)
    return api_response(data={"product": product}, message="Product created.", status=201)


# ─────────────────────────────────────────────────────────────────────
# GET /api/products — list / search products
# ─────────────────────────────────────────────────────────────────────

@products_bp.route("", methods=["GET"])
@jwt_required
def list_products():
    merchant_id = _get_merchant_id()
    result = get_products(merchant_id, request.args)
    return api_response(data=result)


# ─────────────────────────────────────────────────────────────────────
# GET /api/products/<id>
# ─────────────────────────────────────────────────────────────────────

@products_bp.route("/<product_id>", methods=["GET"])
@jwt_required
def get_one(product_id):
    merchant_id = _get_merchant_id()
    product = get_product(merchant_id, product_id)
    return api_response(data={"product": product})


# ─────────────────────────────────────────────────────────────────────
# PUT /api/products/<id>
# ─────────────────────────────────────────────────────────────────────

@products_bp.route("/<product_id>", methods=["PUT"])
@jwt_required
def update(product_id):
    merchant_id = _get_merchant_id()
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        raise ApiError("Request body must be a JSON object.", 400, code="BAD_REQUEST")

    product = update_product(merchant_id, product_id, body, user_id=g.user_id)
    return api_response(data={"product": product}, message="Product updated.")


# ─────────────────────────────────────────────────────────────────────
# DELETE /api/products/<id>  (soft delete)
# ─────────────────────────────────────────────────────────────────────

@products_bp.route("/<product_id>", methods=["DELETE"])
@jwt_required
def delete(product_id):
    merchant_id = _get_merchant_id()
    delete_product(merchant_id, product_id, user_id=g.user_id)
    return api_response(message="Product deactivated.")


# ─────────────────────────────────────────────────────────────────────
# POST /api/products/import
# Accepts multipart file (CSV or JSON) or raw JSON body.
# ─────────────────────────────────────────────────────────────────────

@products_bp.route("/import", methods=["POST"])
@jwt_required
def bulk_import():
    merchant_id = _get_merchant_id()
    content_type = request.content_type or ""

    if "multipart/form-data" in content_type or "application/octet-stream" in content_type:
        # File upload
        file = request.files.get("file")
        if not file:
            raise ApiError("No file uploaded. Use field name 'file'.", 400, code="NO_FILE")

        filename = file.filename or ""
        file_bytes = file.read(Config.MAX_IMPORT_FILE_BYTES + 1)
        if len(file_bytes) > Config.MAX_IMPORT_FILE_BYTES:
            raise ApiError(
                f"File too large (max {Config.MAX_IMPORT_FILE_BYTES // 1024 // 1024} MB).",
                413, code="FILE_TOO_LARGE",
            )

        if filename.lower().endswith(".json"):
            result = import_from_json(merchant_id, file_bytes, user_id=g.user_id)
        else:
            result = import_from_csv(merchant_id, file_bytes, user_id=g.user_id)

    elif "application/json" in content_type:
        # Raw JSON array in body
        data = request.get_json(silent=True)
        if not isinstance(data, list):
            # Check for {format, data} envelope
            if isinstance(data, dict) and isinstance(data.get("products"), list):
                data = data["products"]
            else:
                raise ApiError("JSON body must be an array of product objects.", 400, code="BAD_REQUEST")
        result = import_from_json(merchant_id, data, user_id=g.user_id)

    else:
        # Try to parse body as JSON fallback
        try:
            data = request.get_json(force=True, silent=True)
            if isinstance(data, list):
                result = import_from_json(merchant_id, data, user_id=g.user_id)
            else:
                raise ApiError("Unsupported content type. Send JSON or a multipart CSV/JSON file.", 415, code="UNSUPPORTED_MEDIA")
        except ApiError:
            raise
        except Exception:
            raise ApiError("Could not parse request body.", 400, code="BAD_REQUEST")

    status = 200 if result["imported"] > 0 else 422
    message = (
        f"Imported {result['imported']} product(s)."
        + (f" {result['failed']} failed validation." if result["failed"] else "")
        + (f" {result['duplicates']} duplicate(s) skipped." if result["duplicates"] else "")
    )
    return api_response(data=result, message=message, status=status)
