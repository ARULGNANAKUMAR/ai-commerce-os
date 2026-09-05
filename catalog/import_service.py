"""
catalog/import_service.py
─────────────────────────
Handles bulk product import from CSV or JSON.

Both formats go through the same validation pipeline in
product_service.validate_product_data(). Duplicate SKUs are detected
before any insert. Invalid rows are rejected individually — valid rows
are imported even when the batch contains errors.

Returns a structured ImportResult dict, never raises on partial failure.
"""

import csv
import io
import json

import models
from catalog.product_service import validate_product_data, _sanitize_product_input
from security import sanitize_string
from config import Config
from utils import utcnow


def _parse_tags(value) -> list:
    """Accept comma-separated string or a list."""
    if isinstance(value, list):
        return [sanitize_string(str(t), 100) for t in value if str(t).strip()]
    if isinstance(value, str):
        return [sanitize_string(t.strip(), 100) for t in value.split(",") if t.strip()]
    return []


def _coerce_row(row: dict) -> dict:
    """Normalize a raw import row (keys may be arbitrary-case CSV headers)."""
    lower = {k.strip().lower(): v for k, v in row.items() if k}
    return {
        "name":         lower.get("name", ""),
        "description":  lower.get("description", ""),
        "category":     lower.get("category", ""),
        "brand":        lower.get("brand", ""),
        "price":        lower.get("price"),
        "currency":     lower.get("currency", "INR") or "INR",
        "discount":     lower.get("discount", 0) or 0,
        "stock":        lower.get("stock", 0) or 0,
        "sku":          lower.get("sku", ""),
        "availability": lower.get("availability", "in_stock") or "in_stock",
        "tags":         _parse_tags(lower.get("tags", "")),
        "images":       _parse_tags(lower.get("images", "")),
    }


def _build_result(imported, failed, errors, duplicates) -> dict:
    return {
        "imported":   imported,
        "failed":     failed,
        "duplicates": duplicates,
        "errors":     errors,
    }


def _import_rows(merchant_id: str, rows: list, user_id: str = None) -> dict:
    """Core import loop used by both CSV and JSON paths."""
    from models import log_audit

    if len(rows) > Config.MAX_IMPORT_ROWS:
        return _build_result(
            0, len(rows), [{"row": 0, "reason": f"Batch too large (max {Config.MAX_IMPORT_ROWS} rows)."}], 0
        )

    imported = 0
    failed = 0
    duplicates = 0
    errors = []
    # Track SKUs seen in this batch to catch within-batch duplicates
    batch_skus: set = set()

    for i, raw_row in enumerate(rows, start=1):
        if not raw_row:
            continue  # skip empty rows

        row = _coerce_row(raw_row) if isinstance(raw_row, dict) else {}

        # Skip completely blank rows
        if not any(str(v).strip() for v in row.values()):
            continue

        # Validate
        valid, errs = validate_product_data(row)
        if not valid:
            failed += 1
            errors.append({"row": i, "reason": "; ".join(errs)})
            continue

        # Duplicate SKU check: DB-level and within-batch
        sku = sanitize_string(row.get("sku", ""), 100)
        if sku:
            if sku in batch_skus or models.find_product_by_sku(merchant_id, sku):
                duplicates += 1
                errors.append({"row": i, "reason": f"Duplicate SKU '{sku}' — skipped."})
                continue
            batch_skus.add(sku)

        clean = _sanitize_product_input(row)
        models.create_product(merchant_id, clean)
        imported += 1

    if imported:
        log_audit(
            "product_imported", user_id=user_id, merchant_id=merchant_id,
            details={"imported": imported, "failed": failed, "duplicates": duplicates},
        )

    return _build_result(imported, failed, errors, duplicates)


# ── Public API ────────────────────────────────────────────────────────

def import_from_csv(merchant_id: str, file_bytes: bytes, user_id: str = None) -> dict:
    """Parse a CSV file and import valid rows."""
    try:
        text = file_bytes.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        return _build_result(0, 0, [{"row": 0, "reason": "File must be UTF-8 encoded."}], 0)

    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except Exception as exc:
        return _build_result(0, 0, [{"row": 0, "reason": f"Could not parse CSV: {exc}"}], 0)

    if not rows:
        return _build_result(0, 0, [{"row": 0, "reason": "CSV file is empty or has no data rows."}], 0)

    return _import_rows(merchant_id, rows, user_id=user_id)


def import_from_json(merchant_id: str, file_bytes_or_data, user_id: str = None) -> dict:
    """Parse a JSON array of product objects and import valid rows."""
    if isinstance(file_bytes_or_data, (bytes, bytearray)):
        try:
            data = json.loads(file_bytes_or_data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return _build_result(0, 0, [{"row": 0, "reason": f"Invalid JSON: {exc}"}], 0)
    else:
        data = file_bytes_or_data

    if not isinstance(data, list):
        return _build_result(0, 0, [{"row": 0, "reason": "JSON must be an array of product objects."}], 0)

    return _import_rows(merchant_id, data, user_id=user_id)
