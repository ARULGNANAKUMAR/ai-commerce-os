"""
config.py
─────────
Central, environment-driven configuration for AI Commerce OS.

Every setting is read from the environment (via python-dotenv locally),
never hardcoded, so the exact same codebase runs unmodified across
local dev, staging, and production. Phase 2+ modules (AI providers,
Razorpay) should add their config keys here, not scatter os.environ
calls through the codebase.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # ── Core Flask ────────────────────────────────────────────────
    ENV = os.environ.get("FLASK_ENV", "development")
    DEBUG = ENV == "development"
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # ── MongoDB ───────────────────────────────────────────────────
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "ai_commerce_os")

    # ── JWT ───────────────────────────────────────────────────────
    JWT_ACCESS_SECRET = os.environ.get("JWT_ACCESS_SECRET", "dev-access-secret-change-me")
    JWT_REFRESH_SECRET = os.environ.get("JWT_REFRESH_SECRET", "dev-refresh-secret-change-me")
    JWT_ACCESS_EXPIRES_MINUTES = int(os.environ.get("JWT_ACCESS_EXPIRES_MINUTES", 15))
    JWT_REFRESH_EXPIRES_DAYS = int(os.environ.get("JWT_REFRESH_EXPIRES_DAYS", 7))
    JWT_ALGORITHM = "HS256"

    # ── Encryption (Phase 2 hook: AI provider keys, Razorpay secret) ─
    API_KEY_ENCRYPTION_KEY = os.environ.get("API_KEY_ENCRYPTION_KEY", "")

    # ── App URLs ──────────────────────────────────────────────────
    FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:5000")

    # ── Password policy ───────────────────────────────────────────
    PASSWORD_MIN_LENGTH = 8

    # ── Feature flags ─────────────────────────────────────────────
    FEATURE_AI_ENGINE_ENABLED = _get_bool("FEATURE_AI_ENGINE_ENABLED", False)
    FEATURE_PAYMENTS_ENABLED = _get_bool("FEATURE_PAYMENTS_ENABLED", False)
    FEATURE_WORKFLOW_BUILDER_ENABLED = _get_bool("FEATURE_WORKFLOW_BUILDER_ENABLED", False)

    # ── Phase 2: Product catalog ──────────────────────────────────
    MAX_PRODUCTS_PER_MERCHANT = int(os.environ.get("MAX_PRODUCTS_PER_MERCHANT", 5000))
    MAX_IMPORT_ROWS = int(os.environ.get("MAX_IMPORT_ROWS", 500))
    MAX_IMPORT_FILE_BYTES = int(os.environ.get("MAX_IMPORT_FILE_BYTES", 5 * 1024 * 1024))  # 5 MB

    # ── Phase 2: AI providers ─────────────────────────────────────
    SUPPORTED_AI_PROVIDERS = {
        "gemini": {
            "label": "Google Gemini",
            "models": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"],
            "default_model": "gemini-1.5-flash",
        },
        "openai": {
            "label": "OpenAI",
            "models": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
            "default_model": "gpt-4o-mini",
        },
    }
    AI_TEST_TIMEOUT_SECONDS = int(os.environ.get("AI_TEST_TIMEOUT_SECONDS", 10))

    # ── Phase 2: Permission defaults ──────────────────────────────
    DEFAULT_MAX_PAYMENT_AMOUNT = int(os.environ.get("DEFAULT_MAX_PAYMENT_AMOUNT", 2000))
    DEFAULT_MAX_REFUND_AMOUNT = int(os.environ.get("DEFAULT_MAX_REFUND_AMOUNT", 500))

    # ── Phase 5: Razorpay (Test Mode only) ──────────────────────────
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_demo")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "webhook_secret_demo")
    RAZORPAY_API_BASE = "https://api.razorpay.com/v1"

    # ── Phase 5: Admin ───────────────────────────────────────────────
    ADMIN_EMAILS: set = {
        e.strip().lower()
        for e in os.environ.get("ADMIN_EMAILS", "admin@aicommerceos.com").split(",")
        if e.strip()
    }

    # ── Phase 5: CORS ────────────────────────────────────────────────
    EMBED_CORS_ALLOWED_ORIGINS = os.environ.get("EMBED_CORS_ALLOWED_ORIGINS", "*")

    # ── Phase 5: Rate limiting ────────────────────────────────────────
    RATE_LIMIT_MAX = int(os.environ.get("RATE_LIMIT_MAX", 60))
    RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", 60))

    # ── Phase 5: Deployment ───────────────────────────────────────────
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")
    GUNICORN_WORKERS = int(os.environ.get("GUNICORN_WORKERS", 4))
