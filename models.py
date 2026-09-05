"""
models.py
─────────
The data-access layer. Every read/write to MongoDB goes through a
function here — routes and blueprints never touch `db.<collection>`
directly. This keeps the schema in one place and makes it possible to
change storage details later without hunting through route handlers.

Collections owned by this module: users, merchants, sessions,
api_keys, audit_logs.
"""

from bson import ObjectId
from bson.errors import InvalidId

from db import get_db
from utils import utcnow


def to_object_id(id_str):
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        return None


def _strip_id(doc: dict) -> dict:
    """Convert Mongo's ObjectId to a plain string for JSON responses,
    and drop fields that should never leave the server."""
    if not doc:
        return doc
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    doc.pop("password_hash", None)
    doc.pop("verification_token", None)
    doc.pop("reset_token", None)
    doc.pop("reset_token_expires", None)
    return doc


# ─────────────────────────────────────────────────────────────────────
# users
# ─────────────────────────────────────────────────────────────────────

def create_user(email: str, password_hash: str, verification_token: str) -> str:
    db = get_db()
    doc = {
        "email": email.lower().strip(),
        "password_hash": password_hash,
        "email_verified": False,
        "verification_token": verification_token,
        "reset_token": None,
        "reset_token_expires": None,
        "created_at": utcnow(),
        "last_login": None,
    }
    result = db.users.insert_one(doc)
    return str(result.inserted_id)


def find_user_by_email(email: str) -> dict | None:
    db = get_db()
    return db.users.find_one({"email": email.lower().strip()})


def find_user_by_id(user_id: str) -> dict | None:
    db = get_db()
    oid = to_object_id(user_id)
    if not oid:
        return None
    return db.users.find_one({"_id": oid})


def find_user_by_verification_token(token: str) -> dict | None:
    db = get_db()
    return db.users.find_one({"verification_token": token})


def mark_email_verified(user_id: str) -> None:
    db = get_db()
    db.users.update_one(
        {"_id": to_object_id(user_id)},
        {"$set": {"email_verified": True, "verification_token": None}},
    )


def set_verification_token(user_id: str, token: str) -> None:
    db = get_db()
    db.users.update_one({"_id": to_object_id(user_id)}, {"$set": {"verification_token": token}})


def set_reset_token(user_id: str, token: str, expires_at) -> None:
    db = get_db()
    db.users.update_one(
        {"_id": to_object_id(user_id)},
        {"$set": {"reset_token": token, "reset_token_expires": expires_at}},
    )


def find_user_by_reset_token(token: str) -> dict | None:
    db = get_db()
    return db.users.find_one({"reset_token": token})


def update_password(user_id: str, new_password_hash: str) -> None:
    db = get_db()
    db.users.update_one(
        {"_id": to_object_id(user_id)},
        {"$set": {"password_hash": new_password_hash, "reset_token": None, "reset_token_expires": None}},
    )


def touch_last_login(user_id: str) -> None:
    db = get_db()
    db.users.update_one({"_id": to_object_id(user_id)}, {"$set": {"last_login": utcnow()}})


# ─────────────────────────────────────────────────────────────────────
# merchants
# ─────────────────────────────────────────────────────────────────────

def create_merchant(user_id: str, company_name: str, merchant_name: str,
                     phone: str = "", business_type: str = "") -> str:
    db = get_db()
    doc = {
        "user_id": to_object_id(user_id),
        "company_name": company_name,
        "merchant_name": merchant_name,
        "phone": phone,
        "business_type": business_type,
        "profile_photo_url": None,
        "onboarding_complete": bool(company_name and merchant_name),
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    result = db.merchants.insert_one(doc)
    return str(result.inserted_id)


def find_merchant_by_user_id(user_id: str) -> dict | None:
    db = get_db()
    return db.merchants.find_one({"user_id": to_object_id(user_id)})


def find_merchant_by_id(merchant_id: str) -> dict | None:
    db = get_db()
    oid = to_object_id(merchant_id)
    if not oid:
        return None
    return db.merchants.find_one({"_id": oid})


def update_merchant_profile(merchant_id: str, updates: dict) -> None:
    db = get_db()
    updates = {**updates, "updated_at": utcnow()}
    db.merchants.update_one({"_id": to_object_id(merchant_id)}, {"$set": updates})


# ─────────────────────────────────────────────────────────────────────
# sessions (refresh-token tracking → enables real logout / revocation)
# ─────────────────────────────────────────────────────────────────────

def create_session(user_id: str, refresh_token_hash: str, user_agent: str,
                    ip: str, expires_at) -> str:
    db = get_db()
    doc = {
        "user_id": to_object_id(user_id),
        "refresh_token_hash": refresh_token_hash,
        "user_agent": user_agent,
        "ip": ip,
        "created_at": utcnow(),
        "expires_at": expires_at,
        "revoked": False,
    }
    result = db.sessions.insert_one(doc)
    return str(result.inserted_id)


def find_session_by_refresh_hash(refresh_token_hash: str) -> dict | None:
    db = get_db()
    return db.sessions.find_one({"refresh_token_hash": refresh_token_hash, "revoked": False})


def revoke_session_by_refresh_hash(refresh_token_hash: str) -> None:
    db = get_db()
    db.sessions.update_one({"refresh_token_hash": refresh_token_hash}, {"$set": {"revoked": True}})


def revoke_all_sessions_for_user(user_id: str) -> None:
    db = get_db()
    db.sessions.update_many({"user_id": to_object_id(user_id)}, {"$set": {"revoked": True}})


# ─────────────────────────────────────────────────────────────────────
# api_keys — Phase 2 hook (AI provider keys, Razorpay key secret)
# Not used by any Phase 1 route. The collection + accessors exist now
# so Phase 2 can plug in without a schema migration.
# ─────────────────────────────────────────────────────────────────────

def create_api_key(merchant_id: str, provider: str, encrypted_key: str) -> str:
    db = get_db()
    doc = {
        "merchant_id": to_object_id(merchant_id),
        "provider": provider,          # e.g. "gemini", "openai", "razorpay"
        "key_encrypted": encrypted_key,
        "active": True,
        "created_at": utcnow(),
    }
    result = db.api_keys.insert_one(doc)
    return str(result.inserted_id)


def get_api_keys_for_merchant(merchant_id: str) -> list:
    db = get_db()
    return list(db.api_keys.find({"merchant_id": to_object_id(merchant_id), "active": True}))


# ─────────────────────────────────────────────────────────────────────
# audit_logs (append-only)
# ─────────────────────────────────────────────────────────────────────

def log_audit(action: str, user_id: str = None, merchant_id: str = None,
              details: dict = None, ip: str = None) -> None:
    db = get_db()
    doc = {
        "user_id": to_object_id(user_id) if user_id else None,
        "merchant_id": to_object_id(merchant_id) if merchant_id else None,
        "action": action,
        "details": details or {},
        "ip": ip,
        "timestamp": utcnow(),
    }
    db.audit_logs.insert_one(doc)


def get_recent_audit_logs(merchant_id: str, limit: int = 10) -> list:
    db = get_db()
    cursor = (
        db.audit_logs.find({"merchant_id": to_object_id(merchant_id)})
        .sort("timestamp", -1)
        .limit(limit)
    )
    return list(cursor)


# ═════════════════════════════════════════════════════════════════════
# PHASE 2 DATA ACCESS
# ═════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────
# products
# Every function requires merchant_id — the primary multi-tenant guard.
# ─────────────────────────────────────────────────────────────────────

def create_product(merchant_id: str, data: dict) -> str:
    db = get_db()
    doc = {
        "merchant_id": to_object_id(merchant_id),
        "name": data["name"],
        "description": data.get("description", ""),
        "category": data.get("category", ""),
        "brand": data.get("brand", ""),
        "price": float(data["price"]),
        "currency": data.get("currency", "INR"),
        "discount": float(data.get("discount", 0)),
        "stock": int(data.get("stock", 0)),
        "sku": data.get("sku", ""),
        "images": data.get("images", []),
        "specifications": data.get("specifications", {}),
        "tags": data.get("tags", []),
        "availability": data.get("availability", "in_stock"),
        "status": "active",
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    result = db.products.insert_one(doc)
    return str(result.inserted_id)


def find_products(merchant_id: str, filters: dict = None, skip: int = 0, limit: int = 20) -> list:
    db = get_db()
    query = _build_product_query(merchant_id, filters)
    return list(db.products.find(query).sort("created_at", -1).skip(skip).limit(limit))


def count_products(merchant_id: str, filters: dict = None) -> int:
    db = get_db()
    query = _build_product_query(merchant_id, filters)
    return db.products.count_documents(query)


def _build_product_query(merchant_id: str, filters: dict = None) -> dict:
    query = {"merchant_id": to_object_id(merchant_id), "status": {"$ne": "deleted"}}
    if not filters:
        return query
    if filters.get("keyword"):
        kw = filters["keyword"]
        query["$or"] = [
            {"name": {"$regex": kw, "$options": "i"}},
            {"description": {"$regex": kw, "$options": "i"}},
            {"category": {"$regex": kw, "$options": "i"}},
            {"brand": {"$regex": kw, "$options": "i"}},
        ]
    if filters.get("category"):
        query["category"] = {"$regex": filters["category"], "$options": "i"}
    if filters.get("min_price") is not None:
        query.setdefault("price", {})["$gte"] = float(filters["min_price"])
    if filters.get("max_price") is not None:
        query.setdefault("price", {})["$lte"] = float(filters["max_price"])
    if filters.get("availability"):
        query["availability"] = filters["availability"]
    if filters.get("in_stock_only"):
        query["stock"] = {"$gt": 0}
    if filters.get("status"):
        query["status"] = filters["status"]
    return query


def find_product_by_id(merchant_id: str, product_id: str) -> dict | None:
    db = get_db()
    oid = to_object_id(product_id)
    if not oid:
        return None
    return db.products.find_one({
        "_id": oid,
        "merchant_id": to_object_id(merchant_id),
        "status": {"$ne": "deleted"},
    })


def find_product_by_sku(merchant_id: str, sku: str) -> dict | None:
    db = get_db()
    if not sku:
        return None
    return db.products.find_one({
        "merchant_id": to_object_id(merchant_id),
        "sku": sku,
        "status": {"$ne": "deleted"},
    })


def update_product(merchant_id: str, product_id: str, updates: dict) -> bool:
    db = get_db()
    oid = to_object_id(product_id)
    if not oid:
        return False
    updates["updated_at"] = utcnow()
    result = db.products.update_one(
        {"_id": oid, "merchant_id": to_object_id(merchant_id), "status": {"$ne": "deleted"}},
        {"$set": updates},
    )
    return result.matched_count > 0


def soft_delete_product(merchant_id: str, product_id: str) -> bool:
    return update_product(merchant_id, product_id, {"status": "deleted"})


def bulk_insert_products(merchant_id: str, product_docs: list) -> list:
    """Insert a list of pre-validated product dicts. Returns list of inserted IDs."""
    inserted_ids = []
    for doc in product_docs:
        pid = create_product(merchant_id, doc)
        inserted_ids.append(pid)
    return inserted_ids


# ─────────────────────────────────────────────────────────────────────
# ai_providers — one config per merchant
# ─────────────────────────────────────────────────────────────────────

def upsert_ai_provider(merchant_id: str, updates: dict) -> dict:
    """Create or fully replace the merchant's AI provider config."""
    db = get_db()
    mid = to_object_id(merchant_id)
    updates["updated_at"] = utcnow()
    doc = db.ai_providers.find_one_and_update(
        {"merchant_id": mid},
        {"$set": updates},
        upsert=True,
        return_document=True,
    )
    # find_one_and_update may return None on first upsert with some drivers
    if doc is None:
        doc = db.ai_providers.find_one({"merchant_id": mid})
    return doc


def find_ai_provider(merchant_id: str) -> dict | None:
    db = get_db()
    return db.ai_providers.find_one({"merchant_id": to_object_id(merchant_id)})


def update_ai_provider_status(merchant_id: str, status: str, last_tested=None) -> None:
    db = get_db()
    upd = {"status": status, "updated_at": utcnow()}
    if last_tested is not None:
        upd["last_tested"] = last_tested
    db.ai_providers.update_one({"merchant_id": to_object_id(merchant_id)}, {"$set": upd})


def delete_ai_provider(merchant_id: str) -> bool:
    db = get_db()
    result = db.ai_providers.delete_one({"merchant_id": to_object_id(merchant_id)})
    return result.matched_count > 0


# ─────────────────────────────────────────────────────────────────────
# permissions — one doc per (merchant_id, capability)
# ─────────────────────────────────────────────────────────────────────

def upsert_permission(merchant_id: str, capability: str, updates: dict) -> None:
    db = get_db()
    mid = to_object_id(merchant_id)
    updates["updated_at"] = utcnow()
    db.permissions.update_one(
        {"merchant_id": mid, "capability": capability},
        {"$set": updates},
        upsert=True,
    )


def find_permission(merchant_id: str, capability: str) -> dict | None:
    db = get_db()
    return db.permissions.find_one({
        "merchant_id": to_object_id(merchant_id),
        "capability": capability,
    })


def find_all_permissions(merchant_id: str) -> list:
    db = get_db()
    return list(db.permissions.find({"merchant_id": to_object_id(merchant_id)}))


# ═════════════════════════════════════════════════════════════════════
# PHASE 3 DATA ACCESS — WORKFLOW BUILDER
# ═════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────
# workflows
# ─────────────────────────────────────────────────────────────────────

def create_workflow(merchant_id: str, data: dict) -> str:
    db = get_db()
    doc = {
        "merchant_id":  to_object_id(merchant_id),
        "name":         data.get("name", "Untitled Workflow"),
        "description":  data.get("description", ""),
        "status":       "draft",
        "version":      1,
        "nodes":        data.get("nodes", []),
        "edges":        data.get("edges", []),
        "template_id":  data.get("template_id"),
        "tags":         data.get("tags", []),
        "created_at":   utcnow(),
        "updated_at":   utcnow(),
        "published_at": None,
    }
    result = db.workflows.insert_one(doc)
    return str(result.inserted_id)


def find_workflows(merchant_id: str, skip: int = 0, limit: int = 20) -> list:
    db = get_db()
    return list(
        db.workflows
        .find({"merchant_id": to_object_id(merchant_id), "status": {"$ne": "deleted"}})
        .sort("updated_at", -1)
        .skip(skip)
        .limit(limit)
    )


def count_workflows(merchant_id: str) -> int:
    db = get_db()
    return db.workflows.count_documents(
        {"merchant_id": to_object_id(merchant_id), "status": {"$ne": "deleted"}}
    )


def find_workflow_by_id(merchant_id: str, workflow_id: str) -> dict | None:
    db = get_db()
    oid = to_object_id(workflow_id)
    if not oid:
        return None
    return db.workflows.find_one(
        {"_id": oid, "merchant_id": to_object_id(merchant_id), "status": {"$ne": "deleted"}}
    )


def update_workflow(merchant_id: str, workflow_id: str, updates: dict) -> bool:
    db = get_db()
    oid = to_object_id(workflow_id)
    if not oid:
        return False
    updates["updated_at"] = utcnow()
    result = db.workflows.update_one(
        {"_id": oid, "merchant_id": to_object_id(merchant_id), "status": {"$ne": "deleted"}},
        {"$set": updates},
    )
    return result.matched_count > 0


def soft_delete_workflow(merchant_id: str, workflow_id: str) -> bool:
    return update_workflow(merchant_id, workflow_id, {"status": "deleted"})


# ─────────────────────────────────────────────────────────────────────
# workflow_versions
# ─────────────────────────────────────────────────────────────────────

def save_workflow_version(workflow_id: str, merchant_id: str, version: int,
                           nodes: list, edges: list, name: str) -> str:
    db = get_db()
    doc = {
        "workflow_id": to_object_id(workflow_id),
        "merchant_id": to_object_id(merchant_id),
        "version":     version,
        "name":        name,
        "nodes":       nodes,
        "edges":       edges,
        "saved_at":    utcnow(),
    }
    result = db.workflow_versions.insert_one(doc)
    return str(result.inserted_id)


def find_workflow_versions(workflow_id: str, merchant_id: str) -> list:
    db = get_db()
    return list(
        db.workflow_versions
        .find({"workflow_id": to_object_id(workflow_id), "merchant_id": to_object_id(merchant_id)})
        .sort("version", -1)
    )


# ─────────────────────────────────────────────────────────────────────
# workflow_executions
# ─────────────────────────────────────────────────────────────────────

def create_execution(workflow_id: str, merchant_id: str, trigger_data: dict) -> str:
    db = get_db()
    doc = {
        "workflow_id":   to_object_id(workflow_id),
        "merchant_id":   to_object_id(merchant_id),
        "status":        "running",
        "trigger_data":  trigger_data,
        "steps":         [],
        "result":        None,
        "error":         None,
        "started_at":    utcnow(),
        "completed_at":  None,
        "duration_ms":   None,
    }
    result = db.workflow_executions.insert_one(doc)
    return str(result.inserted_id)


def update_execution(execution_id: str, updates: dict) -> None:
    db = get_db()
    db.workflow_executions.update_one(
        {"_id": to_object_id(execution_id)},
        {"$set": updates},
    )


def find_executions(merchant_id: str, workflow_id: str = None, limit: int = 20) -> list:
    db = get_db()
    query: dict = {"merchant_id": to_object_id(merchant_id)}
    if workflow_id:
        query["workflow_id"] = to_object_id(workflow_id)
    return list(
        db.workflow_executions
        .find(query)
        .sort("started_at", -1)
        .limit(limit)
    )


def find_execution_by_id(merchant_id: str, execution_id: str) -> dict | None:
    db = get_db()
    oid = to_object_id(execution_id)
    if not oid:
        return None
    return db.workflow_executions.find_one(
        {"_id": oid, "merchant_id": to_object_id(merchant_id)}
    )


# ─────────────────────────────────────────────────────────────────────
# templates (global — no merchant_id scoping)
# ─────────────────────────────────────────────────────────────────────

def upsert_template(slug: str, data: dict) -> None:
    db = get_db()
    db.templates.update_one({"slug": slug}, {"$set": data}, upsert=True)


def find_templates(category: str = None) -> list:
    db = get_db()
    query = {"category": category} if category else {}
    return list(db.templates.find(query).sort("order", 1))


def find_template_by_slug(slug: str) -> dict | None:
    db = get_db()
    return db.templates.find_one({"slug": slug})


# ─────────────────────────────────────────────────────────────────────
# ai_memory — Phase 4 foundation
# ─────────────────────────────────────────────────────────────────────

def record_memory(merchant_id: str, pattern_key: str, success: bool,
                   duration_ms: int, node_sequence: list) -> None:
    db = get_db()
    mid = to_object_id(merchant_id)
    existing = db.ai_memory.find_one({"merchant_id": mid, "pattern_key": pattern_key})
    if existing:
        inc_field = "success_count" if success else "failure_count"
        total = existing.get("success_count", 0) + existing.get("failure_count", 0)
        new_avg = int(
            (existing.get("avg_duration_ms", duration_ms) * total + duration_ms) / (total + 1)
        )
        db.ai_memory.update_one(
            {"merchant_id": mid, "pattern_key": pattern_key},
            {"$set": {"avg_duration_ms": new_avg, "last_used": utcnow()},
             "$inc": {inc_field: 1}},
        )
    else:
        db.ai_memory.update_one(
            {"merchant_id": mid, "pattern_key": pattern_key},
            {"$set": {
                "merchant_id":    mid,
                "pattern_key":    pattern_key,
                "node_sequence":  node_sequence,
                "success_count":  1 if success else 0,
                "failure_count":  0 if success else 1,
                "avg_duration_ms": duration_ms,
                "last_used":      utcnow(),
                "created_at":     utcnow(),
            }},
            upsert=True,
        )


def find_memory_insights(merchant_id: str, limit: int = 10) -> list:
    db = get_db()
    return list(
        db.ai_memory
        .find({"merchant_id": to_object_id(merchant_id)})
        .sort("success_count", -1)
        .limit(limit)
    )


# ═════════════════════════════════════════════════════════════════════
# PHASE 4 DATA ACCESS — AI COMMERCE ENGINE
# ═════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────
# customer_sessions
# ─────────────────────────────────────────────────────────────────────

def create_customer_session(merchant_id: str, session_id: str, language: str = "en") -> str:
    db = get_db()
    doc = {
        "session_id":  session_id,
        "merchant_id": to_object_id(merchant_id),
        "language":    language,
        "variables":   {},
        "cart_id":     None,
        "created_at":  utcnow(),
        "last_active": utcnow(),
    }
    db.customer_sessions.insert_one(doc)
    return session_id


def find_customer_session(merchant_id: str, session_id: str) -> dict | None:
    db = get_db()
    return db.customer_sessions.find_one({"session_id": session_id, "merchant_id": to_object_id(merchant_id)})


def update_customer_session(merchant_id: str, session_id: str, updates: dict) -> None:
    db = get_db()
    updates["last_active"] = utcnow()
    db.customer_sessions.update_one(
        {"session_id": session_id, "merchant_id": to_object_id(merchant_id)},
        {"$set": updates},
    )


# ─────────────────────────────────────────────────────────────────────
# conversations
# ─────────────────────────────────────────────────────────────────────

def append_conversation_turn(merchant_id: str, session_id: str, turn: dict) -> None:
    db = get_db()
    mid = to_object_id(merchant_id)
    existing = db.conversations.find_one({"merchant_id": mid, "session_id": session_id})
    if existing:
        messages = existing.get("messages", [])
        messages.append(turn)
        db.conversations.update_one(
            {"merchant_id": mid, "session_id": session_id},
            {"$set": {"messages": messages, "updated_at": utcnow()}},
        )
    else:
        db.conversations.update_one(
            {"merchant_id": mid, "session_id": session_id},
            {"$set": {
                "merchant_id": mid, "session_id": session_id,
                "messages": [turn], "created_at": utcnow(), "updated_at": utcnow(),
            }},
            upsert=True,
        )


def find_conversation(merchant_id: str, session_id: str) -> dict | None:
    db = get_db()
    return db.conversations.find_one({"merchant_id": to_object_id(merchant_id), "session_id": session_id})


# ─────────────────────────────────────────────────────────────────────
# carts
# ─────────────────────────────────────────────────────────────────────

def create_cart(merchant_id: str, session_id: str) -> str:
    db = get_db()
    doc = {
        "merchant_id": to_object_id(merchant_id),
        "session_id":  session_id,
        "items":       [],
        "total":       0,
        "currency":    "INR",
        "status":      "active",
        "created_at":  utcnow(),
        "updated_at":  utcnow(),
    }
    result = db.carts.insert_one(doc)
    return str(result.inserted_id)


def find_cart_by_session(merchant_id: str, session_id: str) -> dict | None:
    db = get_db()
    return db.carts.find_one({
        "merchant_id": to_object_id(merchant_id), "session_id": session_id, "status": "active",
    })


def find_cart_by_id(merchant_id: str, cart_id: str) -> dict | None:
    db = get_db()
    oid = to_object_id(cart_id)
    if not oid:
        return None
    return db.carts.find_one({"_id": oid, "merchant_id": to_object_id(merchant_id)})


def save_cart_items(merchant_id: str, cart_id: str, items: list, total: float) -> None:
    db = get_db()
    db.carts.update_one(
        {"_id": to_object_id(cart_id), "merchant_id": to_object_id(merchant_id)},
        {"$set": {"items": items, "total": total, "updated_at": utcnow()}},
    )


def update_cart_status(merchant_id: str, cart_id: str, status: str) -> None:
    db = get_db()
    db.carts.update_one(
        {"_id": to_object_id(cart_id), "merchant_id": to_object_id(merchant_id)},
        {"$set": {"status": status, "updated_at": utcnow()}},
    )


def find_all_carts(merchant_id: str, limit: int = 500) -> list:
    db = get_db()
    return list(db.carts.find({"merchant_id": to_object_id(merchant_id)}).limit(limit))


# ─────────────────────────────────────────────────────────────────────
# recommendations (event log)
# ─────────────────────────────────────────────────────────────────────

def log_recommendation(merchant_id: str, session_id: str, rec_type: str,
                        product_ids: list, reason: str = "") -> str:
    db = get_db()
    doc = {
        "merchant_id":  to_object_id(merchant_id),
        "session_id":   session_id,
        "type":         rec_type,
        "product_ids":  product_ids,
        "reason":       reason,
        "created_at":   utcnow(),
    }
    result = db.recommendations.insert_one(doc)
    return str(result.inserted_id)


def find_recommendations(merchant_id: str, session_id: str = None, limit: int = 20) -> list:
    db = get_db()
    query = {"merchant_id": to_object_id(merchant_id)}
    if session_id:
        query["session_id"] = session_id
    return list(db.recommendations.find(query).sort("created_at", -1).limit(limit))


# ─────────────────────────────────────────────────────────────────────
# approvals
# ─────────────────────────────────────────────────────────────────────

def create_approval(merchant_id: str, session_id: str, cart_id: str,
                     capability: str, amount: float, decision: str, reason: str = "") -> str:
    db = get_db()
    doc = {
        "merchant_id":  to_object_id(merchant_id),
        "session_id":   session_id,
        "cart_id":      to_object_id(cart_id) if cart_id else None,
        "capability":   capability,
        "amount":       amount,
        "status":       "pending" if decision == "REQUIRES_APPROVAL" or decision == "LIMIT_EXCEEDED" else
                        ("approved" if decision == "ALLOW" else "rejected"),
        "auto_decision": decision,
        "reason":       reason,
        "created_at":   utcnow(),
        "decided_at":   None,
        "decided_by":   None,
    }
    result = db.approvals.insert_one(doc)
    return str(result.inserted_id)


def find_approval_by_id(merchant_id: str, approval_id: str) -> dict | None:
    db = get_db()
    oid = to_object_id(approval_id)
    if not oid:
        return None
    return db.approvals.find_one({"_id": oid, "merchant_id": to_object_id(merchant_id)})


def update_approval_decision(merchant_id: str, approval_id: str, status: str,
                              decided_by: str = None) -> bool:
    db = get_db()
    result = db.approvals.update_one(
        {"_id": to_object_id(approval_id), "merchant_id": to_object_id(merchant_id)},
        {"$set": {"status": status, "decided_at": utcnow(), "decided_by": to_object_id(decided_by) if decided_by else None}},
    )
    return result.matched_count > 0


def find_approvals(merchant_id: str, status: str = None, limit: int = 50) -> list:
    db = get_db()
    query = {"merchant_id": to_object_id(merchant_id)}
    if status:
        query["status"] = status
    return list(db.approvals.find(query).sort("created_at", -1).limit(limit))


# ═════════════════════════════════════════════════════════════════════
# PHASE 5 DATA ACCESS — PAYMENTS, ORDERS, WEBHOOKS, ANALYTICS
# ═════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────
# orders
# ─────────────────────────────────────────────────────────────────────

def create_order(merchant_id: str, session_id: str, cart_id: str,
                  amount: float, currency: str = "INR") -> str:
    db = get_db()
    doc = {
        "merchant_id":       to_object_id(merchant_id),
        "session_id":        session_id,
        "cart_id":           to_object_id(cart_id) if cart_id else None,
        "amount":            amount,
        "currency":          currency,
        "status":            "created",
        "razorpay_order_id": None,
        "payment_id":        None,
        "refund_id":         None,
        "retry_count":       0,
        "created_at":        utcnow(),
        "updated_at":        utcnow(),
    }
    result = db.orders.insert_one(doc)
    return str(result.inserted_id)


def find_order(merchant_id: str, order_id: str) -> dict | None:
    db = get_db()
    oid = to_object_id(order_id)
    if not oid:
        return None
    return db.orders.find_one({"_id": oid, "merchant_id": to_object_id(merchant_id)})


def find_orders(merchant_id: str, status: str = None, limit: int = 50) -> list:
    db = get_db()
    q = {"merchant_id": to_object_id(merchant_id)}
    if status:
        q["status"] = status
    return list(db.orders.find(q).sort("created_at", -1).limit(limit))


def update_order(merchant_id: str, order_id: str, updates: dict) -> bool:
    db = get_db()
    updates["updated_at"] = utcnow()
    result = db.orders.update_one(
        {"_id": to_object_id(order_id), "merchant_id": to_object_id(merchant_id)},
        {"$set": updates},
    )
    return result.matched_count > 0


def find_order_by_razorpay_id(razorpay_order_id: str) -> dict | None:
    db = get_db()
    return db.orders.find_one({"razorpay_order_id": razorpay_order_id})


def count_orders(merchant_id: str, status: str = None) -> int:
    db = get_db()
    q = {"merchant_id": to_object_id(merchant_id)}
    if status:
        q["status"] = status
    return db.orders.count_documents(q)


# ─────────────────────────────────────────────────────────────────────
# payments
# ─────────────────────────────────────────────────────────────────────

def create_payment_record(merchant_id: str, order_id: str,
                           razorpay_payment_id: str = None, amount: float = 0) -> str:
    db = get_db()
    doc = {
        "merchant_id":        to_object_id(merchant_id),
        "order_id":           to_object_id(order_id),
        "razorpay_payment_id": razorpay_payment_id,
        "amount":             amount,
        "status":             "created",
        "signature_verified": False,
        "refunded":           False,
        "refund_amount":      0,
        "error_code":         None,
        "error_description":  None,
        "created_at":         utcnow(),
        "updated_at":         utcnow(),
    }
    result = db.payments.insert_one(doc)
    return str(result.inserted_id)


def find_payment(merchant_id: str, payment_id: str) -> dict | None:
    db = get_db()
    oid = to_object_id(payment_id)
    if not oid:
        return None
    return db.payments.find_one({"_id": oid, "merchant_id": to_object_id(merchant_id)})


def find_payments(merchant_id: str, limit: int = 50) -> list:
    db = get_db()
    return list(
        db.payments.find({"merchant_id": to_object_id(merchant_id)})
        .sort("created_at", -1).limit(limit)
    )


def update_payment_record(merchant_id: str, payment_id: str, updates: dict) -> None:
    db = get_db()
    updates["updated_at"] = utcnow()
    db.payments.update_one(
        {"_id": to_object_id(payment_id), "merchant_id": to_object_id(merchant_id)},
        {"$set": updates},
    )


def find_payment_by_razorpay_id(razorpay_payment_id: str) -> dict | None:
    db = get_db()
    return db.payments.find_one({"razorpay_payment_id": razorpay_payment_id})


# ─────────────────────────────────────────────────────────────────────
# webhooks
# ─────────────────────────────────────────────────────────────────────

def create_webhook_log(merchant_id: str, event: str, payload: dict,
                        idempotency_key: str = None, status: str = "received") -> str:
    db = get_db()
    doc = {
        "merchant_id":     to_object_id(merchant_id),
        "event":           event,
        "payload":         payload,
        "idempotency_key": idempotency_key,
        "status":          status,
        "error":           None,
        "created_at":      utcnow(),
        "processed_at":    None,
    }
    result = db.webhooks.insert_one(doc)
    return str(result.inserted_id)


def update_webhook_log(webhook_id: str, status: str, error: str = None) -> None:
    db = get_db()
    db.webhooks.update_one(
        {"_id": to_object_id(webhook_id)},
        {"$set": {"status": status, "error": error, "processed_at": utcnow()}},
    )


def find_webhooks(merchant_id: str, limit: int = 50) -> list:
    db = get_db()
    return list(
        db.webhooks.find({"merchant_id": to_object_id(merchant_id)})
        .sort("created_at", -1).limit(limit)
    )


# ─────────────────────────────────────────────────────────────────────
# analytics (daily rollup, upserted each calculation)
# ─────────────────────────────────────────────────────────────────────

def upsert_analytics(merchant_id: str, date_str: str, metrics: dict) -> None:
    db = get_db()
    metrics["merchant_id"] = to_object_id(merchant_id)
    metrics["date"] = date_str
    metrics["updated_at"] = utcnow()
    db.analytics.update_one(
        {"merchant_id": to_object_id(merchant_id), "date": date_str},
        {"$set": metrics},
        upsert=True,
    )


def find_analytics(merchant_id: str, days: int = 30) -> list:
    db = get_db()
    return list(
        db.analytics.find({"merchant_id": to_object_id(merchant_id)})
        .sort("date", -1).limit(days)
    )


# ─────────────────────────────────────────────────────────────────────
# merchant_usage
# ─────────────────────────────────────────────────────────────────────

def increment_usage(merchant_id: str, month: str, field: str, amount: int = 1) -> None:
    db = get_db()
    mid = to_object_id(merchant_id)
    db.merchant_usage.update_one(
        {"merchant_id": mid, "month": month},
        {"$set": {"merchant_id": mid, "month": month},
         "$inc": {field: amount}},
        upsert=True,
    )


def find_usage(merchant_id: str, month: str) -> dict | None:
    db = get_db()
    return db.merchant_usage.find_one(
        {"merchant_id": to_object_id(merchant_id), "month": month}
    )


def find_all_merchants() -> list:
    db = get_db()
    return list(db.merchants.find({}).sort("created_at", -1))


def find_all_merchant_usage(limit: int = 100) -> list:
    db = get_db()
    return list(db.merchant_usage.find({}).sort("month", -1).limit(limit))
