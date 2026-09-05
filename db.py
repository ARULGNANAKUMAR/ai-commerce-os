"""
db.py
─────
Single source of truth for the MongoDB connection.

Phase 1 collections:
    users        - auth identity (email, password hash, verification state)
    merchants    - business profile data, 1:1 with users
    sessions     - refresh-token sessions (enables logout / revocation)
    api_keys     - encrypted third-party keys (Phase 2 hook: AI + Razorpay)
    audit_logs   - append-only activity trail

Every collection is created lazily by MongoDB on first write; indexes
are declared explicitly here so they exist before the app takes traffic.
"""

from pymongo import MongoClient, ASCENDING
from pymongo.database import Database

from config import Config

_client: MongoClient | None = None
_db: Database | None = None


def init_db(app=None) -> Database:
    """Initialize the MongoDB client + database and ensure indexes exist.

    Safe to call multiple times (idempotent) — used both at app startup
    and defensively by get_db() if init hasn't happened yet.
    """
    global _client, _db

    if _db is not None:
        return _db

    _client = MongoClient(Config.MONGO_URI)
    _db = _client[Config.MONGO_DB_NAME]
    _create_indexes(_db)

    if app is not None:
        app.logger.info("MongoDB connected: db=%s", Config.MONGO_DB_NAME)

    return _db


def get_db() -> Database:
    """Return the active database handle, initializing it if needed."""
    if _db is None:
        return init_db()
    return _db


def _create_indexes(db: Database) -> None:
    # users — email is the login identity, must be unique
    db.users.create_index("email", unique=True)
    db.users.create_index("verification_token", sparse=True)
    db.users.create_index("reset_token", sparse=True)

    # merchants — one profile per user
    db.merchants.create_index("user_id", unique=True)

    # sessions — refresh-token lookups + auto-expiry cleanup
    db.sessions.create_index("user_id")
    db.sessions.create_index("refresh_token_hash", unique=True)
    db.sessions.create_index("expires_at", expireAfterSeconds=0)

    # api_keys — encrypted third-party keys
    db.api_keys.create_index([("merchant_id", ASCENDING), ("provider", ASCENDING)])

    # audit_logs — queried by merchant, ordered by time
    db.audit_logs.create_index([("merchant_id", ASCENDING), ("timestamp", ASCENDING)])

    # ── Phase 2 collections ────────────────────────────────────────

    # products — scoped by merchant; SKU unique per merchant
    db.products.create_index([("merchant_id", ASCENDING), ("status", ASCENDING)])
    db.products.create_index([("merchant_id", ASCENDING), ("sku", ASCENDING)], sparse=True)
    db.products.create_index([("merchant_id", ASCENDING), ("category", ASCENDING)])
    db.products.create_index([("merchant_id", ASCENDING), ("created_at", ASCENDING)])
    # Text index hint for future full-text search (Phase 3+)
    # db.products.create_index([("name","text"),("description","text"),("tags","text")])

    # ai_providers — one active config per merchant
    db.ai_providers.create_index("merchant_id", unique=True)

    # permissions — one doc per (merchant, capability) pair
    db.permissions.create_index(
        [("merchant_id", ASCENDING), ("capability", ASCENDING)], unique=True
    )

    # ── Phase 3: Workflow Builder ──────────────────────────────────────

    # workflows — draft/published/archived per merchant
    db.workflows.create_index([("merchant_id", ASCENDING), ("status", ASCENDING)])
    db.workflows.create_index([("merchant_id", ASCENDING), ("updated_at", ASCENDING)])

    # workflow_versions — one per (workflow_id, version_number)
    db.workflow_versions.create_index(
        [("workflow_id", ASCENDING), ("version", ASCENDING)], unique=True
    )

    # workflow_executions — queryable by merchant + workflow
    db.workflow_executions.create_index([("merchant_id", ASCENDING), ("workflow_id", ASCENDING)])
    db.workflow_executions.create_index([("merchant_id", ASCENDING), ("started_at", ASCENDING)])
    db.workflow_executions.create_index("workflow_id")

    # templates — global shared library, keyed by slug
    db.templates.create_index("slug", unique=True)
    db.templates.create_index("category")

    # ai_memory — pattern → success statistics per merchant
    db.ai_memory.create_index(
        [("merchant_id", ASCENDING), ("pattern_key", ASCENDING)], unique=True
    )

    # ── Phase 4: AI Commerce Engine ─────────────────────────────────────

    # carts — one active cart per (merchant, session) typically
    db.carts.create_index([("merchant_id", ASCENDING), ("session_id", ASCENDING)])
    db.carts.create_index([("merchant_id", ASCENDING), ("status", ASCENDING)])

    # conversations — chat history per session
    db.conversations.create_index([("merchant_id", ASCENDING), ("session_id", ASCENDING)], unique=True)

    # recommendations — cached/logged recommendation events
    db.recommendations.create_index([("merchant_id", ASCENDING), ("session_id", ASCENDING)])
    db.recommendations.create_index([("merchant_id", ASCENDING), ("created_at", ASCENDING)])

    # approvals — human approval queue for checkout / financial actions
    db.approvals.create_index([("merchant_id", ASCENDING), ("status", ASCENDING)])
    db.approvals.create_index([("merchant_id", ASCENDING), ("session_id", ASCENDING)])

    # customer_sessions — chat session state (language, context variables)
    db.customer_sessions.create_index("session_id", unique=True)
    db.customer_sessions.create_index([("merchant_id", ASCENDING), ("last_active", ASCENDING)])

    # ── Phase 5: Payments, Orders, Webhooks, Analytics, Admin ──────────

    # orders
    db.orders.create_index([("merchant_id", ASCENDING), ("status", ASCENDING)])
    db.orders.create_index([("merchant_id", ASCENDING), ("created_at", ASCENDING)])
    db.orders.create_index("razorpay_order_id", sparse=True)
    db.orders.create_index([("merchant_id", ASCENDING), ("session_id", ASCENDING)])

    # payments
    db.payments.create_index([("merchant_id", ASCENDING), ("order_id", ASCENDING)])
    db.payments.create_index("razorpay_payment_id", sparse=True)
    db.payments.create_index([("merchant_id", ASCENDING), ("status", ASCENDING)])
    db.payments.create_index([("merchant_id", ASCENDING), ("created_at", ASCENDING)])

    # webhooks
    db.webhooks.create_index([("merchant_id", ASCENDING), ("event", ASCENDING)])
    db.webhooks.create_index([("merchant_id", ASCENDING), ("status", ASCENDING)])
    db.webhooks.create_index([("merchant_id", ASCENDING), ("created_at", ASCENDING)])
    db.webhooks.create_index("idempotency_key", unique=True, sparse=True)

    # analytics  — one daily-rollup doc per merchant
    db.analytics.create_index(
        [("merchant_id", ASCENDING), ("date", ASCENDING)], unique=True
    )

    # merchant_usage — AI token / execution counts
    db.merchant_usage.create_index(
        [("merchant_id", ASCENDING), ("month", ASCENDING)], unique=True
    )
