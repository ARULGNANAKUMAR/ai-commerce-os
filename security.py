"""
security.py
───────────
All cryptographic and validation primitives live here, in one place,
so the rest of the codebase never touches bcrypt/jwt/Fernet directly.

Contents:
    - Password hashing (bcrypt)
    - JWT issuing + verification (access & refresh tokens)
    - @jwt_required route-protection decorator
    - Symmetric encryption helpers for third-party secrets
      (Phase 2 hook: merchant AI keys, Razorpay key secret)
    - Input validation helpers
"""

import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken
from flask import request, g

from config import Config
from utils import ApiError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ─────────────────────────────────────────────────────────────────────
# Password hashing
# ─────────────────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt. Returns a utf-8 string
    safe to store directly in MongoDB."""
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time verification of a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ─────────────────────────────────────────────────────────────────────
# JWT — access & refresh tokens
# ─────────────────────────────────────────────────────────────────────

def _encode(payload: dict, secret: str) -> str:
    return jwt.encode(payload, secret, algorithm=Config.JWT_ALGORITHM)


def generate_access_token(user_id: str, merchant_id: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "merchant_id": merchant_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=Config.JWT_ACCESS_EXPIRES_MINUTES),
    }
    return _encode(payload, Config.JWT_ACCESS_SECRET)


def generate_refresh_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        # random jti prevents refresh-token collisions when issued in the same second
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(days=Config.JWT_REFRESH_EXPIRES_DAYS),
    }
    return _encode(payload, Config.JWT_REFRESH_SECRET)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, Config.JWT_ACCESS_SECRET, algorithms=[Config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ApiError("Access token expired.", 401, code="TOKEN_EXPIRED")
    except jwt.InvalidTokenError:
        raise ApiError("Invalid access token.", 401, code="TOKEN_INVALID")


def decode_refresh_token(token: str) -> dict:
    try:
        return jwt.decode(token, Config.JWT_REFRESH_SECRET, algorithms=[Config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ApiError("Refresh token expired. Please log in again.", 401, code="TOKEN_EXPIRED")
    except jwt.InvalidTokenError:
        raise ApiError("Invalid refresh token.", 401, code="TOKEN_INVALID")


def hash_refresh_token(token: str) -> str:
    """We never store raw refresh tokens in MongoDB — only a hash of them,
    so a database read alone can never yield a usable session token."""
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────
# Route protection
# ─────────────────────────────────────────────────────────────────────

def get_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise ApiError("Missing or malformed Authorization header.", 401, code="AUTH_MISSING")
    return auth_header.split(" ", 1)[1].strip()


def jwt_required(fn):
    """Decorator that validates the access token on incoming requests
    and attaches g.user_id / g.merchant_id for downstream handlers.

    Any route decorated with this is automatically part of the platform's
    protected surface — Phase 2+ modules should reuse this decorator
    rather than reimplementing auth checks.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = get_bearer_token()
        payload = decode_access_token(token)
        if payload.get("type") != "access":
            raise ApiError("Token is not an access token.", 401, code="TOKEN_INVALID")
        g.user_id = payload["sub"]
        g.merchant_id = payload.get("merchant_id")
        return fn(*args, **kwargs)

    return wrapper


# ─────────────────────────────────────────────────────────────────────
# Symmetric encryption — Phase 2 hook for AI provider / Razorpay keys
# ─────────────────────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    key = Config.API_KEY_ENCRYPTION_KEY
    if not key:
        raise ApiError(
            "API_KEY_ENCRYPTION_KEY is not configured on the server.",
            500,
            code="ENCRYPTION_NOT_CONFIGURED",
        )
    return Fernet(key.encode("utf-8"))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a third-party secret (AI provider key, Razorpay key secret)
    for storage in the `api_keys` collection. Not used by any Phase 1
    feature yet — exists so Phase 2 can persist merchant AI/Razorpay
    credentials without a schema or security-model change."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ApiError("Could not decrypt stored secret.", 500, code="DECRYPTION_FAILED")


# ─────────────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────────────

def validate_email_format(email: str) -> bool:
    return bool(email) and bool(EMAIL_RE.match(email.strip()))


def validate_password_strength(password: str) -> tuple[bool, str]:
    if not password or len(password) < Config.PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {Config.PASSWORD_MIN_LENGTH} characters."
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must include at least one letter."
    if not re.search(r"[0-9]", password):
        return False, "Password must include at least one number."
    return True, ""


def sanitize_string(value, max_length: int = 500) -> str:
    """Trim, cap length, and strip control characters from user-supplied
    text before it touches the database."""
    if value is None:
        return ""
    value = str(value).strip()
    value = "".join(ch for ch in value if ch.isprintable())
    return value[:max_length]


def generate_random_token() -> str:
    """URL-safe random token used for email verification / password reset links."""
    return secrets.token_urlsafe(32)
