"""
commerce/chat_service.py
──────────────────────────
The AI Shopping Agent / "AI Buyer Mode" orchestrator.

Every incoming message is: language-detected → intent-classified →
routed to the matching commerce service (search / compare / recommend /
cart / checkout) → logged as a conversation turn → logged as a
synthetic execution in the Phase 3 workflow_executions collection so
chat-driven agent activity shows up in the same Execution Logs screen
as visual-builder runs. This is the concrete bridge the Phase 4 spec
asks for ("execution logs connect to Phase 3 workflow engine") without
duplicating the execution-log infrastructure.

Context memory: customer_sessions.variables carries state across turns
within one conversation (last search results, last category, budget),
enough for "add the first one" / "compare them" style follow-ups.
"""

import re
import time
import secrets

import models
from commerce.language_service import detect_language, detect_intent, extract_budget
from commerce import search_service, comparison_service, recommendation_service, cart_service
from commerce.approval_service import request_checkout_approval
from utils import utcnow

ORDINAL_WORDS = {"first": 0, "1st": 0, "one": 0, "second": 1, "2nd": 1, "two": 1,
                 "third": 2, "3rd": 2, "three": 2, "fourth": 3, "4th": 3}

# Reserved sentinel ObjectId (all-zero) representing the virtual
# "AI Buyer chat" pseudo-workflow — valid in real MongoDB, unlike an
# arbitrary string, so create_execution() never silently drops it.
CHAT_WORKFLOW_ID = "000000000000000000000000"


def _resolve_ordinal(text: str) -> int | None:
    lowered = text.lower()
    for word, idx in ORDINAL_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            return idx
    return None


def start_session(merchant_id: str, language: str = "en") -> str:
    session_id = f"sess_{secrets.token_urlsafe(12)}"
    models.create_customer_session(merchant_id, session_id, language)
    return session_id


def _get_or_create_session(merchant_id: str, session_id: str | None, language: str) -> str:
    if session_id:
        existing = models.find_customer_session(merchant_id, session_id)
        if existing:
            return session_id
    return start_session(merchant_id, language)


def process_message(merchant_id: str, message: str, session_id: str = None,
                     user_id: str = None) -> dict:
    t0 = time.time()
    language = detect_language(message)
    session_id = _get_or_create_session(merchant_id, session_id, language)
    session = models.find_customer_session(merchant_id, session_id) or {}
    variables = session.get("variables", {})

    intent = detect_intent(message, language)
    reply_text, response_data = _dispatch(merchant_id, session_id, message, intent, variables, user_id)

    # Persist conversation turn
    models.append_conversation_turn(merchant_id, session_id, {
        "role": "user", "content": message, "intent": intent, "language": language,
        "timestamp": utcnow().isoformat(),
    })
    models.append_conversation_turn(merchant_id, session_id, {
        "role": "assistant", "content": reply_text, "intent": intent,
        "timestamp": utcnow().isoformat(),
    })
    models.update_customer_session(merchant_id, session_id, {"variables": variables, "language": language})

    duration_ms = int((time.time() - t0) * 1000)
    _log_chat_execution(merchant_id, session_id, intent, message, response_data, duration_ms)

    return {
        "session_id": session_id,
        "language":   language,
        "intent":     intent,
        "reply":      reply_text,
        "data":       response_data,
    }


def _resolve_cart_target(merchant_id: str, message: str, variables: dict) -> str | None:
    """Figure out which product the customer means: by name mentioned in the
    message, by ordinal ('the first one'), or by running a fresh search if
    neither matches the cached last_search_results."""
    ids = variables.get("last_search_results", [])
    from catalog.product_service import get_product
    cached = [p for p in (get_product(merchant_id, pid) for pid in ids) if p]

    lowered = message.lower()
    # 1. Direct name-token match against cached results
    msg_tokens = set(re.findall(r"[a-zA-Z0-9]+", lowered))
    for p in cached:
        name_tokens = set(re.findall(r"[a-zA-Z0-9]+", p["name"].lower()))
        if name_tokens & msg_tokens - {"add", "cart", "the", "to", "a", "buy"}:
            return p["id"]

    # 2. Ordinal reference ("the first one")
    idx = _resolve_ordinal(message)
    if idx is not None and idx < len(ids):
        return ids[idx]

    # 3. Fall back to a fresh search using the message text
    fresh = search_service.search_products(merchant_id, message, limit=1)
    if fresh["products"]:
        variables["last_search_results"] = [fresh["products"][0]["id"]]
        return fresh["products"][0]["id"]

    # 4. Last resort: first cached result
    return ids[0] if ids else None


def _dispatch(merchant_id, session_id, message, intent, variables, user_id):
    if intent == "greeting":
        return "Hi! I can help you search, compare, and recommend products, and check out when you're ready.", {}

    if intent == "search":
        budget = extract_budget(message)
        result = search_service.search_products(merchant_id, message, max_price=budget, limit=5)
        products = result["products"]
        variables["last_search_results"] = [p["id"] for p in products]
        if products:
            variables["last_category"] = products[0].get("category")
        names = ", ".join(p["name"] for p in products[:3]) or "no matching products"
        reply = f"I found {result['count']} product(s): {names}." if products else \
                "I couldn't find any matching products. Try a different search."
        return reply, result

    if intent == "compare":
        ids = variables.get("last_search_results", [])[:4]
        if len(ids) < 2:
            return "Search for a few products first, then ask me to compare them.", {}
        result = comparison_service.compare_products(merchant_id, ids)
        return " ".join(result["summary"]), result

    if intent == "recommend":
        budget = extract_budget(message)
        if budget:
            result = recommendation_service.recommend_by_budget(merchant_id, budget,
                                                                 category=variables.get("last_category"))
            reply = f"Within ₹{budget:,.0f}, I'd suggest: " + \
                    ", ".join(p["name"] for p in result["recommendations"][:3])
        else:
            result = recommendation_service.recommend_personalized(merchant_id, session_id)
            reply = "Here are some picks for you: " + \
                    ", ".join(p["name"] for p in result["recommendations"][:3])
        return reply, result

    if intent == "add_to_cart":
        target_id = _resolve_cart_target(merchant_id, message, variables)
        if not target_id:
            return "I couldn't find that product. Try searching for it first, then ask me to add it.", {}
        result = cart_service.add_item(merchant_id, session_id, target_id, quantity=1)
        item_name = next((i["name"] for i in result["items"] if i["product_id"] == target_id), "item")
        return f"Added {item_name} to your cart. Cart total: ₹{result['total']:,.0f}.", result

    if intent == "remove_from_cart":
        cart = cart_service.get_cart(merchant_id, session_id)
        if not cart["items"]:
            return "Your cart is already empty.", cart
        idx = _resolve_ordinal(message) or 0
        idx = min(idx, len(cart["items"]) - 1)
        pid = cart["items"][idx]["product_id"]
        result = cart_service.remove_item(merchant_id, session_id, pid)
        return f"Removed item from your cart. New total: ₹{result['total']:,.0f}.", result

    if intent == "update_cart":
        cart = cart_service.get_cart(merchant_id, session_id)
        if not cart["items"]:
            return "Your cart is empty — nothing to update.", cart
        qty_match = re.search(r"(\d+)", message)
        qty = int(qty_match.group(1)) if qty_match else 1
        idx = _resolve_ordinal(message) or 0
        idx = min(idx, len(cart["items"]) - 1)
        pid = cart["items"][idx]["product_id"]
        result = cart_service.update_item_quantity(merchant_id, session_id, pid, qty)
        return f"Updated quantity. New total: ₹{result['total']:,.0f}.", result

    if intent == "view_cart":
        cart = cart_service.get_cart(merchant_id, session_id)
        if not cart["items"]:
            return "Your cart is empty.", cart
        summary = ", ".join(f"{i['name']} x{i['quantity']}" for i in cart["items"])
        return f"Your cart: {summary}. Total: ₹{cart['total']:,.0f}.", cart

    if intent == "checkout":
        try:
            approval = request_checkout_approval(merchant_id, session_id, user_id=user_id)
        except Exception as exc:
            return str(exc), {}
        status = approval["status"]
        if status == "approved":
            reply = f"Your order for ₹{approval['amount']:,.0f} is approved and ready for checkout!"
        elif status == "pending":
            reply = f"Your order for ₹{approval['amount']:,.0f} needs merchant approval before it can proceed."
        else:
            reply = f"Sorry, checkout couldn't proceed: {approval.get('reason', 'not permitted')}."
        return reply, approval

    # Unknown intent — best-effort AI response, mock-safe
    try:
        from ai.provider_service import get_live_client
        adapter, raw_key, model = get_live_client(merchant_id)
        reply = adapter.complete(raw_key, model,
                                 f"You are a helpful shopping assistant. Respond briefly to: {message}")
        raw_key = None
        if not reply:
            raise ValueError("empty")
    except Exception:
        reply = "I can help you search, compare, and recommend products, manage your cart, and check out."
    return reply, {}


def _log_chat_execution(merchant_id, session_id, intent, message, response_data, duration_ms):
    """Bridge chat activity into the Phase 3 execution log so AI Buyer
    actions are visible alongside visual-builder workflow runs."""
    try:
        execution_id = models.create_execution(CHAT_WORKFLOW_ID, merchant_id,
                                                {"message": message, "session_id": session_id})
        step = {
            "step": 1, "node_id": "chat_turn", "node_type": f"chat.{intent}",
            "node_label": f"AI Buyer: {intent}", "status": "completed",
            "output": {k: v for k, v in (response_data or {}).items() if k in
                       ("count", "total", "status", "reply", "amount")},
            "next_port": "default", "duration_ms": duration_ms,
            "timestamp": utcnow().isoformat(),
        }
        models.update_execution(execution_id, {
            "status": "completed", "steps": [step], "result": {"intent": intent},
            "completed_at": utcnow(), "duration_ms": duration_ms,
        })
    except Exception:
        pass  # logging is best-effort — never break the chat response
