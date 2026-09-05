"""
agent/architecture_engine.py
──────────────────────────────
The 7-step AI Architecture Engine from the original product vision.

Phase 3: runs as a static-analysis pipeline — no LLM call required.
Phase 4+: each step can be enriched with real LLM analysis using the
          merchant's AI provider via ai/provider_service.get_live_client().

Pipeline:
  1. Task Analysis          — classify what the workflow is trying to do
  2. Structure Understanding — validate graph topology
  3. Cognitive Module Selection — map nodes → required AI capabilities
  4. Architecture Composition  — describe the execution plan
  5. Workflow Generation       — generate improvement suggestions
  6. Execution Planning        — estimate cost / timing
  7. Memory Optimisation       — check known-good patterns from ai_memory
"""

from agent.memory_service import get_insights
from workflow.node_handlers import HANDLER_REGISTRY


# ── Node type metadata ────────────────────────────────────────────────

NODE_META = {
    "trigger.start":            {"category": "trigger",     "capability": None,            "label": "Start"},
    "trigger.end":              {"category": "trigger",     "capability": None,            "label": "End"},
    "ai.prompt":                {"category": "ai",          "capability": None,            "label": "AI Prompt"},
    "catalog.product_search":   {"category": "catalog",     "capability": "product_read",  "label": "Product Search"},
    "catalog.product_compare":  {"category": "catalog",     "capability": "product_compare","label": "Compare"},
    "catalog.recommendation":   {"category": "catalog",     "capability": "recommendation","label": "Recommendation"},
    "sales.upsell":             {"category": "sales",       "capability": "upsell",        "label": "Upsell"},
    "sales.cross_sell":         {"category": "sales",       "capability": "cross_sell",    "label": "Cross-sell"},
    "logic.condition":          {"category": "logic",       "capability": None,            "label": "Condition"},
    "permission.check":         {"category": "permission",  "capability": None,            "label": "Permission Gate"},
    "human.approval":           {"category": "approval",    "capability": None,            "label": "Human Approval"},
    "commerce.cart":            {"category": "commerce",    "capability": "cart_create",   "label": "Cart"},
    "commerce.checkout_placeholder": {"category": "commerce","capability": "checkout_create","label": "Checkout"},
    "utility.delay":            {"category": "utility",     "capability": None,            "label": "Delay"},
}


# ─────────────────────────────────────────────────────────────────────
# Pipeline steps
# ─────────────────────────────────────────────────────────────────────

def _step1_task_analysis(nodes: list) -> dict:
    """Classify what the workflow is trying to accomplish."""
    types = {n.get("type") for n in nodes}
    if "sales.upsell" in types or "sales.cross_sell" in types:
        task = "sales_optimisation"
        description = "Drives additional revenue through upsell and cross-sell suggestions."
    elif "catalog.product_compare" in types:
        task = "product_comparison"
        description = "Helps customers make informed decisions by comparing products."
    elif "commerce.cart" in types or "commerce.checkout_placeholder" in types:
        task = "commerce_flow"
        description = "Guides customers from product discovery to cart creation."
    elif "ai.prompt" in types:
        task = "ai_assisted_shopping"
        description = "Uses AI to personalise the customer shopping experience."
    else:
        task = "product_discovery"
        description = "Helps customers find relevant products from the catalog."
    return {"task_type": task, "description": description}


def _step2_structure(nodes: list, edges: list) -> dict:
    """Validate the workflow graph and return structural metrics."""
    warnings = []
    has_start = any(n.get("type") == "trigger.start" for n in nodes)
    has_end   = any(n.get("type") == "trigger.end"   for n in nodes)
    if not has_start:
        warnings.append("No Start node found — add a Start node to begin the workflow.")
    if not has_end:
        warnings.append("No End node found — add an End node to finalise the workflow.")

    node_ids   = {n["id"] for n in nodes}
    orphans    = node_ids.copy()
    for e in edges:
        orphans.discard(e.get("from_node"))
        orphans.discard(e.get("to_node"))
    # remove start and end from orphan check
    for n in nodes:
        if n.get("type") in ("trigger.start", "trigger.end"):
            orphans.discard(n["id"])
    if orphans:
        warnings.append(f"{len(orphans)} node(s) are disconnected — connect all nodes with edges.")

    return {
        "node_count":   len(nodes),
        "edge_count":   len(edges),
        "has_start":    has_start,
        "has_end":      has_end,
        "is_valid":     has_start and has_end and not orphans,
        "warnings":     warnings,
    }


def _step3_module_selection(nodes: list) -> dict:
    """Map node types to the AI capabilities they require."""
    required_caps = []
    modules_used  = []
    for n in nodes:
        meta = NODE_META.get(n.get("type", ""), {})
        cap  = meta.get("capability")
        if cap and cap not in required_caps:
            required_caps.append(cap)
        label = meta.get("label", n.get("type"))
        if label not in modules_used:
            modules_used.append(label)
    needs_ai = any(n.get("type") == "ai.prompt" for n in nodes)
    return {
        "modules_used":        modules_used,
        "required_capabilities": required_caps,
        "needs_ai_provider":   needs_ai,
    }


def _step4_architecture(nodes: list, edges: list) -> dict:
    """Describe the execution sequence."""
    # Build simple ordered description from edges
    adj = {}
    for e in edges:
        adj.setdefault(e["from_node"], []).append(e["to_node"])
    node_map = {n["id"]: n for n in nodes}

    start_node = next((n for n in nodes if n.get("type") == "trigger.start"), None)
    sequence   = []
    visited    = set()
    queue      = [start_node["id"]] if start_node else []
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = node_map.get(nid)
        if node:
            meta = NODE_META.get(node.get("type", ""), {})
            sequence.append(meta.get("label", node.get("label", nid)))
        for nxt in adj.get(nid, []):
            if nxt not in visited:
                queue.append(nxt)

    has_branching = any(n.get("type") in ("logic.condition", "permission.check") for n in nodes)
    return {
        "execution_sequence": sequence,
        "has_branching":      has_branching,
        "is_linear":          not has_branching,
    }


def _step5_suggestions(nodes: list, edges: list, structure: dict) -> list:
    """Generate actionable improvement suggestions."""
    suggestions = list(structure.get("warnings", []))
    types = {n.get("type") for n in nodes}

    if "catalog.product_search" in types and "catalog.recommendation" not in types:
        suggestions.append("Add a Recommendation node after Product Search to rank results by relevance.")
    if "sales.upsell" in types and "permission.check" not in types:
        suggestions.append("Add a Permission Check node before Upsell to respect your permission settings.")
    if "ai.prompt" not in types and len(nodes) > 3:
        suggestions.append("Add an AI Prompt node to personalise the customer response using your AI provider.")
    if "trigger.end" in types and "commerce.cart" not in types and len(nodes) > 4:
        suggestions.append("Consider adding a Cart node to let the agent create carts for interested customers.")

    return suggestions


def _step6_execution_plan(nodes: list) -> dict:
    """Estimate execution time and complexity."""
    est_ms = 0
    for n in nodes:
        t = n.get("type", "")
        if t == "ai.prompt":              est_ms += 1500
        elif "catalog" in t:              est_ms += 80
        elif "sales" in t:               est_ms += 60
        elif "permission" in t:          est_ms += 20
        else:                             est_ms += 30
    complexity = "low" if len(nodes) <= 4 else ("medium" if len(nodes) <= 7 else "high")
    return {
        "estimated_duration_ms": est_ms,
        "complexity":            complexity,
        "node_count":            len(nodes),
    }


def _step7_memory_optimisation(merchant_id: str, nodes: list) -> dict:
    """Check memory for proven patterns matching this workflow."""
    insights    = get_insights(merchant_id)
    node_types  = [n.get("type") for n in nodes]
    pattern_key = "→".join(node_types)
    matching    = [i for i in insights if i["pattern"] == pattern_key]
    return {
        "pattern_found":   bool(matching),
        "pattern_key":     pattern_key,
        "past_executions": matching[0]["success_count"] if matching else 0,
        "avg_duration_ms": matching[0]["avg_duration_ms"] if matching else None,
        "top_patterns":    insights[:3],
    }


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────

def analyse_workflow(merchant_id: str, nodes: list, edges: list) -> dict:
    """Run the full 7-step pipeline and return a structured analysis."""
    step1 = _step1_task_analysis(nodes)
    step2 = _step2_structure(nodes, edges)
    step3 = _step3_module_selection(nodes)
    step4 = _step4_architecture(nodes, edges)
    step5 = _step5_suggestions(nodes, edges, step2)
    step6 = _step6_execution_plan(nodes)
    step7 = _step7_memory_optimisation(merchant_id, nodes)

    return {
        "task":              step1,
        "structure":         step2,
        "modules":           step3,
        "architecture":      step4,
        "suggestions":       step5,
        "execution_plan":    step6,
        "memory":            step7,
        "ready_to_execute":  step2["is_valid"],
    }
