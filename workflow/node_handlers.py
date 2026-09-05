"""
workflow/node_handlers.py
──────────────────────────
One handler function per node type. Each handler:
    (config: dict, context: dict, merchant_id: str) → (output: dict, next_port: str)

`next_port` is "default" for most nodes; "true"/"false" for condition;
"allowed"/"denied" for permission.check.

Variable interpolation via resolve_var() uses {{key}} syntax throughout.
AI nodes fall back to a structured mock when the AI provider is not connected
or the network is unavailable — ensuring the demo always runs.
"""

import re
import time
from utils import ApiError


# ─────────────────────────────────────────────────────────────────────
# Variable interpolation
# ─────────────────────────────────────────────────────────────────────

def resolve_var(template: str, context: dict) -> str:
    """Replace {{key}} and {{a.b}} placeholders from context variables."""
    variables = {}
    variables.update(context.get("trigger_data", {}))
    variables.update(context.get("variables", {}))
    # flatten step_outputs one level for convenience
    for nid, output in context.get("step_outputs", {}).items():
        if isinstance(output, dict):
            for k, v in output.items():
                if k not in variables:
                    variables[k] = v

    def _get_nested(key: str):
        parts = key.strip().split(".")
        cur = variables
        for p in parts:
            if isinstance(cur, dict):
                cur = cur.get(p)
            elif isinstance(cur, list) and p.isdigit():
                cur = cur[int(p)]
            else:
                return None
        return cur

    def replacer(m):
        val = _get_nested(m.group(1))
        if val is None:
            return m.group(0)   # leave placeholder intact
        if isinstance(val, (list, dict)):
            import json
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return re.sub(r"\{\{([^}]+)\}\}", replacer, str(template or ""))


# ─────────────────────────────────────────────────────────────────────
# Mock AI response (fallback when provider not connected / network off)
# ─────────────────────────────────────────────────────────────────────

def _mock_ai_response(context: dict, prompt: str) -> str:
    product_count = 0
    for output in context.get("step_outputs", {}).values():
        if isinstance(output, dict) and "products" in output:
            product_count = len(output["products"])
    query = context.get("variables", {}).get("customer_query", "your query")
    return (
        f"Based on your search for '{query}', I found {product_count} matching products. "
        f"The top picks offer excellent value, quality, and availability. "
        f"I recommend starting with the highest-rated option that best fits your budget. "
        f"[AI mock — connect a provider in Settings for live responses]"
    )


# ─────────────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────────────

def handle_start(config: dict, context: dict, merchant_id: str):
    return {
        "triggered":   True,
        "description": config.get("description", "Workflow started"),
        "variables":   context.get("trigger_data", {}),
    }, "default"


def handle_ai_prompt(config: dict, context: dict, merchant_id: str):
    prompt_template = config.get("prompt", "Summarise the current context.")
    prompt = resolve_var(prompt_template, context)
    used_mock = False

    try:
        from ai.provider_service import get_live_client
        adapter, raw_key, model = get_live_client(merchant_id)
        response = adapter.complete(raw_key, model, prompt)
        raw_key = None
        if not response:
            raise ValueError("Empty response")
    except Exception:
        response = _mock_ai_response(context, prompt)
        model    = "mock"
        used_mock = True

    return {
        "response":     response,
        "prompt_used":  prompt,
        "model":        model if not used_mock else "mock",
        "used_mock":    used_mock,
    }, "default"


def handle_product_search(config: dict, context: dict, merchant_id: str):
    from catalog.product_service import get_products
    keyword     = resolve_var(config.get("keyword", ""), context)
    category    = resolve_var(config.get("category", ""), context)
    max_results = int(config.get("max_results", 5))
    min_price   = config.get("min_price")
    max_price   = config.get("max_price")
    params: dict = {"keyword": keyword, "category": category,
                    "limit": max_results, "page": 1}
    if min_price:
        params["min_price"] = float(min_price)
    if max_price:
        params["max_price"] = float(max_price)
    result   = get_products(merchant_id, params)
    products = result.get("products", [])
    return {"products": products, "count": len(products), "query": keyword}, "default"


def handle_product_compare(config: dict, context: dict, merchant_id: str):
    attributes = config.get("attributes", ["price", "stock", "brand", "discount"])
    # Gather products from the nearest upstream product_search output
    products = []
    for output in context.get("step_outputs", {}).values():
        if isinstance(output, dict) and "products" in output:
            products = output["products"]
            break

    table = []
    for p in products[:6]:
        row = {"name": p.get("name"), "id": p.get("id")}
        for attr in attributes:
            row[attr] = p.get(attr)
        table.append(row)

    return {
        "comparison_table": table,
        "products":         products[:6],
        "attributes":       attributes,
        "count":            len(table),
    }, "default"


def handle_recommendation(config: dict, context: dict, merchant_id: str):
    top_n    = int(config.get("top_n", 3))
    criteria = config.get("ranking_criteria", "relevance")
    products = []
    for output in context.get("step_outputs", {}).values():
        if isinstance(output, dict) and "products" in output:
            products = output["products"]
            break

    # Simple ranking heuristic — no AI call needed
    if criteria == "price":
        ranked = sorted(products, key=lambda p: p.get("price", 0))
    elif criteria == "stock":
        ranked = sorted(products, key=lambda p: p.get("stock", 0), reverse=True)
    else:
        # "relevance": in-stock first, then by discount desc, then by price asc
        ranked = sorted(products,
                        key=lambda p: (p.get("availability") != "in_stock",
                                       -p.get("discount", 0),
                                       p.get("price", 0)))

    return {
        "recommendations":   ranked[:top_n],
        "count":             min(top_n, len(ranked)),
        "ranking_criteria":  criteria,
        "products":          ranked[:top_n],
    }, "default"


def handle_upsell(config: dict, context: dict, merchant_id: str):
    from permissions.permission_service import check_permission
    decision = check_permission(merchant_id, "upsell")
    if decision == "DENY":
        return {"upsell_blocked": True, "reason": "upsell capability not enabled"}, "default"

    pct  = float(config.get("upsell_percentage", 20))
    maxs = int(config.get("max_suggestions", 2))
    products = []
    for output in context.get("step_outputs", {}).values():
        if isinstance(output, dict) and "products" in output:
            products = output["products"]
            break

    min_price = min((p.get("price", 0) for p in products), default=0)
    threshold = min_price * (1 + pct / 100)

    from catalog.product_service import get_products
    result  = get_products(merchant_id, {"min_price": threshold, "limit": maxs, "page": 1})
    upsells = result.get("products", [])

    return {
        "upsell_suggestions": upsells,
        "count":              len(upsells),
        "base_price":         min_price,
        "upsell_threshold":   threshold,
        "products":           upsells,
    }, "default"


def handle_cross_sell(config: dict, context: dict, merchant_id: str):
    from permissions.permission_service import check_permission
    decision = check_permission(merchant_id, "cross_sell")
    if decision == "DENY":
        return {"cross_sell_blocked": True, "reason": "cross_sell capability not enabled"}, "default"

    maxs = int(config.get("max_suggestions", 2))
    products = []
    for output in context.get("step_outputs", {}).values():
        if isinstance(output, dict) and "products" in output:
            products = output["products"]
            break
    categories = {p.get("category") for p in products if p.get("category")}

    from catalog.product_service import get_products
    result  = get_products(merchant_id, {"limit": maxs + len(products), "page": 1})
    all_p   = result.get("products", [])
    existing_ids = {p.get("id") for p in products}
    cross   = [p for p in all_p
               if p.get("id") not in existing_ids and p.get("category") not in categories][:maxs]

    return {
        "cross_sell_suggestions": cross,
        "count":                  len(cross),
        "products":               cross,
    }, "default"


def handle_condition(config: dict, context: dict, merchant_id: str):
    field_path = config.get("field", "")
    operator   = config.get("operator", "==")
    value      = config.get("value", "")

    # Resolve the field
    def _get(path):
        parts = path.strip().split(".")
        cur   = {**context.get("variables", {}), **context.get("trigger_data", {}),
                 "step_outputs": context.get("step_outputs", {})}
        for p in parts:
            if isinstance(cur, dict):
                cur = cur.get(p)
            elif isinstance(cur, list) and p.isdigit():
                cur = cur[int(p)]
            else:
                return None
        return cur

    actual = _get(field_path)

    try:
        a = float(actual) if actual is not None else 0
        v = float(value)
        if operator == ">":  result = a > v
        elif operator == "<": result = a < v
        elif operator == ">=": result = a >= v
        elif operator == "<=": result = a <= v
        elif operator == "!=": result = a != v
        else:                  result = a == v
    except (TypeError, ValueError):
        result = str(actual) == str(value)

    return {
        "condition_met":    result,
        "field":            field_path,
        "actual_value":     actual,
        "operator":         operator,
        "expected_value":   value,
    }, "true" if result else "false"


def handle_permission_check(config: dict, context: dict, merchant_id: str):
    from permissions.permission_service import check_permission
    capability = config.get("capability", "product_search")
    amount_field = config.get("context_amount_field", "")
    ctx = {}
    if amount_field:
        from utils import utcnow
        ctx["amount"] = context.get("variables", {}).get(amount_field, 0)
    decision = check_permission(merchant_id, capability, ctx)
    allowed  = decision in ("ALLOW", "REQUIRES_APPROVAL")
    return {
        "decision":   decision,
        "capability": capability,
        "allowed":    allowed,
    }, "allowed" if allowed else "denied"


def handle_human_approval(config: dict, context: dict, merchant_id: str):
    message = resolve_var(config.get("message", "Approval required for this action."), context)
    return {
        "status":   "awaiting_approval",
        "message":  message,
        "paused":   True,
    }, "default"   # execution continues but marks as awaiting


def handle_cart(config: dict, context: dict, merchant_id: str):
    from permissions.permission_service import check_permission
    decision = check_permission(merchant_id, "cart_create")
    if decision == "DENY":
        return {"cart_blocked": True, "reason": "cart_create not enabled"}, "default"

    products = []
    for output in context.get("step_outputs", {}).values():
        if isinstance(output, dict) and "products" in output:
            products = output["products"]
            break

    cart_items = [{"product_id": p.get("id"), "name": p.get("name"),
                   "price": p.get("price"), "quantity": 1} for p in products[:5]]
    total = sum(i["price"] for i in cart_items if i["price"])

    return {
        "cart": {"items": cart_items, "total": total, "currency": "INR", "item_count": len(cart_items)},
        "total": total,
        "permission_decision": decision,
    }, "default"


def handle_checkout_placeholder(config: dict, context: dict, merchant_id: str):
    from permissions.permission_service import check_permission
    decision = check_permission(merchant_id, "checkout_create")
    cart = {}
    for output in context.get("step_outputs", {}).values():
        if isinstance(output, dict) and "cart" in output:
            cart = output["cart"]
            break
    return {
        "checkout_placeholder": True,
        "cart":                 cart,
        "note":                 config.get("note", "Razorpay checkout connects in Phase 4."),
        "permission_decision":  decision,
    }, "default"


def handle_delay(config: dict, context: dict, merchant_id: str):
    delay_s = int(config.get("delay_seconds", 1))
    return {
        "delay_seconds": delay_s,
        "note":          f"Simulated {delay_s}s delay (instant in test mode).",
    }, "default"


def handle_end(config: dict, context: dict, merchant_id: str):
    message = resolve_var(config.get("message", "Workflow completed."), context)
    # Collect final outputs from all steps
    all_products = []
    ai_response  = None
    for output in context.get("step_outputs", {}).values():
        if isinstance(output, dict):
            if "products" in output and not all_products:
                all_products = output["products"]
            if "response" in output and not ai_response:
                ai_response = output["response"]

    return {
        "completed":    True,
        "message":      message,
        "products":     all_products,
        "ai_response":  ai_response,
        "summary":      f"Workflow completed. Products found: {len(all_products)}.",
    }, "default"


# ─────────────────────────────────────────────────────────────────────
# Handler registry — keyed by node type string
# ─────────────────────────────────────────────────────────────────────

HANDLER_REGISTRY = {
    "trigger.start":            handle_start,
    "ai.prompt":                handle_ai_prompt,
    "catalog.product_search":   handle_product_search,
    "catalog.product_compare":  handle_product_compare,
    "catalog.recommendation":   handle_recommendation,
    "sales.upsell":             handle_upsell,
    "sales.cross_sell":         handle_cross_sell,
    "logic.condition":          handle_condition,
    "permission.check":         handle_permission_check,
    "human.approval":           handle_human_approval,
    "commerce.cart":            handle_cart,
    "commerce.checkout_placeholder": handle_checkout_placeholder,
    "utility.delay":            handle_delay,
    "trigger.end":              handle_end,
}


def get_handler(node_type: str):
    handler = HANDLER_REGISTRY.get(node_type)
    if not handler:
        raise ValueError(f"No handler registered for node type '{node_type}'.")
    return handler
