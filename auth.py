"""
auth.py
───────
Authentication blueprint — everything under /api/auth/*.

Covers: signup, login, logout, token refresh, email verification
(structure only — sending is stubbed), and forgot/reset password
(structure only — sending is stubbed). No route here touches
merchant profile data beyond what's needed to create the initial
merchant record at signup; profile CRUD lives in routes.py.
"""

from datetime import timedelta

from flask import Blueprint, request

import models
from config import Config
from security import (
    hash_password,
    verify_password,
    validate_email_format,
    validate_password_strength,
    sanitize_string,
    generate_random_token,
    generate_access_token,
    generate_refresh_token,
    decode_refresh_token,
    hash_refresh_token,
    jwt_required,
)
from utils import ApiError, api_response, get_client_ip, utcnow
from flask import g

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ─────────────────────────────────────────────────────────────────────
# Email stub — Phase 2 hook: swap this for a real transactional email
# provider (SES/SendGrid/Postmark). Keeping a single choke point means
# that swap touches one function, not every call site.
# ─────────────────────────────────────────────────────────────────────

def _send_email(to_address: str, subject: str, body: str) -> None:
    # Structure-only for Phase 1: log instead of sending. Every call
    # site below already passes the real content a provider would need.
    print(f"[EMAIL STUB] to={to_address} subject={subject!r}\n{body}\n")


# ─────────────────────────────────────────────────────────────────────
# POST /api/auth/signup
# ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/signup", methods=["POST"])
def signup():
    body = request.get_json(silent=True) or {}

    email = sanitize_string(body.get("email"), 254)
    password = body.get("password") or ""
    company_name = sanitize_string(body.get("company_name"), 200)
    merchant_name = sanitize_string(body.get("merchant_name"), 200)
    phone = sanitize_string(body.get("phone"), 30)
    business_type = sanitize_string(body.get("business_type"), 100)

    if not validate_email_format(email):
        raise ApiError("Enter a valid email address.", 400, code="INVALID_EMAIL")

    ok, msg = validate_password_strength(password)
    if not ok:
        raise ApiError(msg, 400, code="WEAK_PASSWORD")

    if not merchant_name:
        raise ApiError("Merchant name is required.", 400, code="MISSING_FIELD")

    if models.find_user_by_email(email):
        raise ApiError("An account with this email already exists.", 409, code="EMAIL_TAKEN")

    verification_token = generate_random_token()
    password_hash = hash_password(password)
    user_id = models.create_user(email, password_hash, verification_token)
    merchant_id = models.create_merchant(user_id, company_name, merchant_name, phone, business_type)

    verify_link = f"{Config.FRONTEND_BASE_URL}/api/auth/verify-email/{verification_token}"
    _send_email(email, "Verify your AI Commerce OS account",
                f"Welcome {merchant_name}! Verify your email: {verify_link}")

    models.log_audit("signup", user_id=user_id, merchant_id=merchant_id, ip=get_client_ip())

    access_token = generate_access_token(user_id, merchant_id)
    refresh_token = generate_refresh_token(user_id)
    _persist_refresh_session(user_id, refresh_token)

    return api_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {"id": user_id, "email": email, "email_verified": False},
            "merchant": {"id": merchant_id, "company_name": company_name, "merchant_name": merchant_name},
        },
        message="Account created. Check your email to verify your address.",
        status=201,
    )


# ─────────────────────────────────────────────────────────────────────
# POST /api/auth/login
# ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    email = sanitize_string(body.get("email"), 254)
    password = body.get("password") or ""

    user = models.find_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        raise ApiError("Incorrect email or password.", 401, code="INVALID_CREDENTIALS")

    merchant = models.find_merchant_by_user_id(str(user["_id"]))
    merchant_id = str(merchant["_id"]) if merchant else None

    models.touch_last_login(str(user["_id"]))
    models.log_audit("login", user_id=str(user["_id"]), merchant_id=merchant_id, ip=get_client_ip())

    access_token = generate_access_token(str(user["_id"]), merchant_id)
    refresh_token = generate_refresh_token(str(user["_id"]))
    _persist_refresh_session(str(user["_id"]), refresh_token)

    return api_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {"id": str(user["_id"]), "email": user["email"], "email_verified": user["email_verified"]},
            "merchant": {"id": merchant_id, "company_name": merchant["company_name"] if merchant else None},
        },
        message="Logged in.",
    )


# ─────────────────────────────────────────────────────────────────────
# POST /api/auth/refresh
# ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    body = request.get_json(silent=True) or {}
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise ApiError("refresh_token is required.", 400, code="MISSING_FIELD")

    payload = decode_refresh_token(refresh_token)
    if payload.get("type") != "refresh":
        raise ApiError("Token is not a refresh token.", 401, code="TOKEN_INVALID")

    token_hash = hash_refresh_token(refresh_token)
    session = models.find_session_by_refresh_hash(token_hash)
    if not session:
        raise ApiError("Session has been revoked. Please log in again.", 401, code="SESSION_REVOKED")

    user_id = payload["sub"]
    merchant = models.find_merchant_by_user_id(user_id)
    merchant_id = str(merchant["_id"]) if merchant else None

    new_access_token = generate_access_token(user_id, merchant_id)
    return api_response(data={"access_token": new_access_token}, message="Token refreshed.")


# ─────────────────────────────────────────────────────────────────────
# POST /api/auth/logout
# ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
@jwt_required
def logout():
    body = request.get_json(silent=True) or {}
    refresh_token = body.get("refresh_token")
    if refresh_token:
        models.revoke_session_by_refresh_hash(hash_refresh_token(refresh_token))
    models.log_audit("logout", user_id=g.user_id, merchant_id=g.merchant_id, ip=get_client_ip())
    return api_response(message="Logged out.")


# ─────────────────────────────────────────────────────────────────────
# GET /api/auth/verify-email/<token>
# ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/verify-email/<token>", methods=["GET"])
def verify_email(token):
    user = models.find_user_by_verification_token(token)
    if not user:
        raise ApiError("Verification link is invalid or has already been used.", 400, code="INVALID_TOKEN")
    models.mark_email_verified(str(user["_id"]))
    models.log_audit("email_verified", user_id=str(user["_id"]))
    return api_response(message="Email verified. You can now use all features of your account.")


@auth_bp.route("/resend-verification", methods=["POST"])
@jwt_required
def resend_verification():
    user = models.find_user_by_id(g.user_id)
    if not user:
        raise ApiError("Account not found.", 404, code="NOT_FOUND")
    if user["email_verified"]:
        return api_response(message="Your email is already verified.")

    token = generate_random_token()
    models.set_verification_token(g.user_id, token)
    verify_link = f"{Config.FRONTEND_BASE_URL}/api/auth/verify-email/{token}"
    _send_email(user["email"], "Verify your AI Commerce OS account", f"Verify your email: {verify_link}")
    return api_response(message="Verification email sent.")


# ─────────────────────────────────────────────────────────────────────
# POST /api/auth/forgot-password
# ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    body = request.get_json(silent=True) or {}
    email = sanitize_string(body.get("email"), 254)
    user = models.find_user_by_email(email)

    # Always return the same response whether or not the account exists,
    # so this endpoint can't be used to enumerate registered emails.
    if user:
        token = generate_random_token()
        expires_at = utcnow() + timedelta(hours=1)
        models.set_reset_token(str(user["_id"]), token, expires_at)
        reset_link = f"{Config.FRONTEND_BASE_URL}/reset-password/{token}"
        _send_email(email, "Reset your AI Commerce OS password", f"Reset your password: {reset_link}")
        models.log_audit("password_reset_requested", user_id=str(user["_id"]))

    return api_response(message="If that email is registered, a reset link has been sent.")


@auth_bp.route("/reset-password/<token>", methods=["POST"])
def reset_password(token):
    body = request.get_json(silent=True) or {}
    new_password = body.get("password") or ""

    user = models.find_user_by_reset_token(token)
    if not user:
        raise ApiError("Reset link is invalid or has already been used.", 400, code="INVALID_TOKEN")

    expires_at = user.get("reset_token_expires")
    if not expires_at or utcnow() > expires_at:
        raise ApiError("Reset link has expired. Request a new one.", 400, code="TOKEN_EXPIRED")

    ok, msg = validate_password_strength(new_password)
    if not ok:
        raise ApiError(msg, 400, code="WEAK_PASSWORD")

    models.update_password(str(user["_id"]), hash_password(new_password))
    # Force re-login everywhere — a password reset should invalidate old sessions.
    models.revoke_all_sessions_for_user(str(user["_id"]))
    models.log_audit("password_reset_completed", user_id=str(user["_id"]))

    return api_response(message="Password updated. Please log in with your new password.")


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _persist_refresh_session(user_id: str, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    expires_at = utcnow() + timedelta(days=Config.JWT_REFRESH_EXPIRES_DAYS)
    models.create_session(
        user_id=user_id,
        refresh_token_hash=token_hash,
        user_agent=request.headers.get("User-Agent", ""),
        ip=get_client_ip(),
        expires_at=expires_at,
    )
