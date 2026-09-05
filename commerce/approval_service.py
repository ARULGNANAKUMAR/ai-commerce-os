"""
commerce/approval_service.py
────────────────────────────────
Before checkout, every cart's total is run through the Phase 2
permission engine for the 'payment_request' capability. The outcome
maps directly onto an approval record:

    ALLOW              → auto-approved, checkout may proceed immediately
    DENY                → rejected immediately (capability disabled)
    REQUIRES_APPROVAL   → pending; a human must approve or reject
    LIMIT_EXCEEDED      → pending; flagged as over the configured limit

This is the same decision vocabulary used by the Phase 3 workflow
engine's permission.check node — chat-driven checkout and the visual
builder share one source of truth for what "allowed" means.
"""

import models
from commerce.cart_service import serialize_cart, get_cart
from permissions.permission_service import check_permission
from utils import ApiError, utcnow


def request_checkout_approval(merchant_id: str, session_id: str, user_id: str = None) -> dict:
    cart = models.find_cart_by_session(merchant_id, session_id)
    if not cart or not cart.get("items"):
        raise ApiError("Cart is empty — add items before checkout.", 400, code="EMPTY_CART")

    total = cart.get("total", 0)
    decision = check_permission(merchant_id, "payment_request", {"amount": total})

    reason_map = {
        "ALLOW": "Within auto-approval limits.",
        "DENY": "Payment requests are not enabled for this merchant's AI agent.",
        "REQUIRES_APPROVAL": "This merchant requires human approval for AI-initiated payments.",
        "LIMIT_EXCEEDED": "Cart total exceeds the configured auto-approval limit.",
    }
    approval_id = models.create_approval(
        merchant_id, session_id, str(cart["_id"]), "payment_request", total,
        decision, reason=reason_map.get(decision, ""),
    )

    models.log_audit("checkout_requested", user_id=user_id, merchant_id=merchant_id,
                      details={"session_id": session_id, "amount": total, "decision": decision})

    approval = models.find_approval_by_id(merchant_id, approval_id)

    # Auto-approved carts can move straight to "approved" cart status
    if decision == "ALLOW":
        models.update_cart_status(merchant_id, str(cart["_id"]), "approved")

    return serialize_approval(approval, cart=serialize_cart(cart))


def decide_approval(merchant_id: str, approval_id: str, decision: str, user_id: str = None) -> dict:
    """Human decides on a pending approval. decision: 'approved' | 'rejected'."""
    if decision not in ("approved", "rejected"):
        raise ApiError("Decision must be 'approved' or 'rejected'.", 400, code="INVALID_DECISION")

    approval = models.find_approval_by_id(merchant_id, approval_id)
    if not approval:
        raise ApiError("Approval request not found.", 404, code="NOT_FOUND")
    if approval.get("status") not in ("pending",):
        raise ApiError(f"This approval has already been {approval.get('status')}.", 409, code="ALREADY_DECIDED")

    models.update_approval_decision(merchant_id, approval_id, decision, decided_by=user_id)

    cart_id = approval.get("cart_id")
    if cart_id:
        new_cart_status = "approved" if decision == "approved" else "rejected"
        models.update_cart_status(merchant_id, str(cart_id), new_cart_status)

    models.log_audit(f"checkout_{decision}", user_id=user_id, merchant_id=merchant_id,
                      details={"approval_id": approval_id, "amount": approval.get("amount")})

    updated = models.find_approval_by_id(merchant_id, approval_id)
    return serialize_approval(updated)


def get_approval(merchant_id: str, approval_id: str) -> dict:
    approval = models.find_approval_by_id(merchant_id, approval_id)
    if not approval:
        raise ApiError("Approval request not found.", 404, code="NOT_FOUND")
    return serialize_approval(approval)


def list_approvals(merchant_id: str, status: str = None) -> list:
    rows = models.find_approvals(merchant_id, status=status)
    return [serialize_approval(a) for a in rows]


def serialize_approval(a: dict, cart: dict = None) -> dict:
    return {
        "approval_id":   str(a["_id"]),
        "session_id":    a.get("session_id"),
        "capability":    a.get("capability"),
        "amount":        a.get("amount"),
        "status":        a.get("status"),
        "auto_decision": a.get("auto_decision"),
        "reason":        a.get("reason"),
        "created_at":    a["created_at"].isoformat() if a.get("created_at") else None,
        "decided_at":    a["decided_at"].isoformat() if a.get("decided_at") else None,
        "cart":          cart,
    }
