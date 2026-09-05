"""
ai/provider_service.py
──────────────────────
Business logic layer for AI provider configuration.

Critical security invariants (enforced here, not just in routes):
  - API keys are NEVER returned to any caller; only key_hint is exposed.
  - Decryption happens in-memory, within this request lifecycle only.
  - Logs never contain key material.
"""

from security import encrypt_secret, decrypt_secret, sanitize_string
from utils import ApiError, utcnow
from config import Config
from ai.provider_adapters import get_adapter, get_provider_models, ADAPTER_REGISTRY
import models


# ── Public interface ──────────────────────────────────────────────────

def save_provider(merchant_id: str, provider: str, model: str,
                  api_key: str, user_id: str = None) -> dict:
    """Persist (or update) an AI provider config. Encrypts the key."""
    if provider not in Config.SUPPORTED_AI_PROVIDERS:
        raise ApiError(f"Provider '{provider}' is not supported.", 400, code="UNSUPPORTED_PROVIDER")

    supported_models = Config.SUPPORTED_AI_PROVIDERS[provider]["models"]
    if model not in supported_models:
        raise ApiError(
            f"Model '{model}' is not available for {provider}. Choose from: {', '.join(supported_models)}.",
            400, code="UNSUPPORTED_MODEL",
        )

    api_key = api_key.strip()
    if not api_key:
        raise ApiError("API key cannot be empty.", 400, code="MISSING_KEY")

    # key_hint: last 4 chars only, for display — never store raw key
    key_hint = api_key[-4:] if len(api_key) >= 4 else "****"
    key_encrypted = encrypt_secret(api_key)

    doc = models.upsert_ai_provider(merchant_id, {
        "provider": provider,
        "model": model,
        "key_encrypted": key_encrypted,
        "key_hint": key_hint,
        "status": "disconnected",   # status set to connected only after test
        "last_tested": None,
    })

    models.log_audit(
        "ai_provider_connected", user_id=user_id, merchant_id=merchant_id,
        details={"provider": provider, "model": model},
        # NEVER log key_hint or any part of the key
    )

    return serialize_provider(models.find_ai_provider(merchant_id))


def test_provider(merchant_id: str, user_id: str = None) -> dict:
    """Run a live connection test against the stored provider config."""
    config = models.find_ai_provider(merchant_id)
    if not config:
        raise ApiError("No AI provider configured. Add one first.", 404, code="NO_PROVIDER")

    provider = config["provider"]
    model = config["model"]

    # Decrypt key in-memory; it never leaves this function
    try:
        raw_key = decrypt_secret(config["key_encrypted"])
    except ApiError:
        models.update_ai_provider_status(merchant_id, "error")
        raise ApiError("Could not decrypt stored key. Re-enter your API key.", 500, code="KEY_DECRYPT_ERROR")

    adapter = get_adapter(provider)
    success, message = adapter.test_connection(raw_key, model)
    raw_key = None  # explicitly clear from local scope

    status = "connected" if success else "error"
    models.update_ai_provider_status(merchant_id, status, last_tested=utcnow())
    models.log_audit(
        "ai_provider_tested", user_id=user_id, merchant_id=merchant_id,
        details={"provider": provider, "success": success},
    )

    return {
        "success": success,
        "status": status,
        "message": message,
        "provider": provider,
        "model": model,
    }


def get_provider_config(merchant_id: str) -> dict | None:
    """Return the sanitized provider config (no key material)."""
    config = models.find_ai_provider(merchant_id)
    if not config:
        return None
    return serialize_provider(config)


def remove_provider(merchant_id: str, user_id: str = None) -> None:
    config = models.find_ai_provider(merchant_id)
    if not config:
        raise ApiError("No AI provider configured.", 404, code="NO_PROVIDER")
    models.delete_ai_provider(merchant_id)
    models.log_audit(
        "ai_provider_disconnected", user_id=user_id, merchant_id=merchant_id,
        details={"provider": config.get("provider")},
    )


def get_supported_providers() -> dict:
    """Return provider metadata for the frontend (no keys)."""
    result = {}
    for pid, meta in Config.SUPPORTED_AI_PROVIDERS.items():
        result[pid] = {
            "label":         meta["label"],
            "models":        meta["models"],
            "default_model": meta["default_model"],
        }
    return result


# Phase 3 hook: called by the agent engine during inference.
# Kept here so it's the only place key decryption happens.
def get_live_client(merchant_id: str):
    """Return (adapter, raw_key, model) for use by the AI engine.
    Callers MUST NOT log or persist the returned raw_key."""
    config = models.find_ai_provider(merchant_id)
    if not config or config.get("status") != "connected":
        raise ApiError("AI provider is not connected or not configured.", 503, code="PROVIDER_UNAVAILABLE")
    raw_key = decrypt_secret(config["key_encrypted"])
    adapter = get_adapter(config["provider"])
    return adapter, raw_key, config["model"]


# ── Serialization — NEVER include key_encrypted or raw key ───────────

def serialize_provider(doc: dict) -> dict:
    if not doc:
        return {}
    return {
        "id":          str(doc["_id"]),
        "provider":    doc.get("provider", ""),
        "model":       doc.get("model", ""),
        "key_hint":    doc.get("key_hint", "****"),   # e.g. "k2a9"
        "status":      doc.get("status", "disconnected"),
        "last_tested": doc["last_tested"].isoformat() if doc.get("last_tested") else None,
        "created_at":  doc["created_at"].isoformat() if doc.get("created_at") else None,
        "updated_at":  doc["updated_at"].isoformat() if doc.get("updated_at") else None,
    }
    # key_encrypted: intentionally absent
