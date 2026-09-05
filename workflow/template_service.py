"""
workflow/template_service.py
─────────────────────────────
Four built-in workflow templates seeded into MongoDB at app startup.
Each template is a complete node+edge layout ready to clone.
"""

import models

# ── Template node/edge definitions ────────────────────────────────────

BUILT_IN_TEMPLATES = [
    {
        "slug":        "ai_shopping_assistant",
        "name":        "AI Shopping Assistant",
        "description": "Full shopping experience: understand intent, search products, get AI-powered recommendations, and present a personalised response.",
        "category":    "sales",
        "order":       1,
        "tags":        ["recommended", "beginner"],
        "nodes": [
            {"id": "n1", "type": "trigger.start",              "label": "Start",
             "position": {"x": 80,  "y": 220},
             "config": {"description": "Customer sends a shopping query"}},
            {"id": "n2", "type": "catalog.product_search",     "label": "Search Products",
             "position": {"x": 340, "y": 220},
             "config": {"keyword": "{{customer_query}}", "max_results": 6, "category": "{{category}}"}},
            {"id": "n3", "type": "catalog.recommendation",     "label": "Rank Results",
             "position": {"x": 600, "y": 220},
             "config": {"top_n": 3, "ranking_criteria": "relevance"}},
            {"id": "n4", "type": "ai.prompt",                  "label": "Personalise Response",
             "position": {"x": 860, "y": 220},
             "config": {"prompt": "You are a friendly shopping assistant for {{merchant_name}}. The customer asked: {{customer_query}}. Budget: ₹{{budget}}. Recommend the top 3 products below and explain why each fits them. Products: {{products}}", "temperature": 0.7}},
            {"id": "n5", "type": "trigger.end",                "label": "End",
             "position": {"x": 1120, "y": 220},
             "config": {"message": "Here are the best options for you!"}},
        ],
        "edges": [
            {"id": "e1", "from_node": "n1", "from_port": "default", "to_node": "n2", "to_port": "in"},
            {"id": "e2", "from_node": "n2", "from_port": "default", "to_node": "n3", "to_port": "in"},
            {"id": "e3", "from_node": "n3", "from_port": "default", "to_node": "n4", "to_port": "in"},
            {"id": "e4", "from_node": "n4", "from_port": "default", "to_node": "n5", "to_port": "in"},
        ],
    },
    {
        "slug":        "product_comparison_agent",
        "name":        "Product Comparison Agent",
        "description": "Find products and compare them on specs, price, and availability. Delivers a structured comparison to the customer.",
        "category":    "information",
        "order":       2,
        "tags":        ["comparison", "beginner"],
        "nodes": [
            {"id": "n1", "type": "trigger.start",          "label": "Start",
             "position": {"x": 80,  "y": 220},
             "config": {"description": "Customer wants to compare products"}},
            {"id": "n2", "type": "catalog.product_search", "label": "Find Products",
             "position": {"x": 340, "y": 220},
             "config": {"keyword": "{{customer_query}}", "max_results": 4}},
            {"id": "n3", "type": "catalog.product_compare","label": "Compare",
             "position": {"x": 600, "y": 220},
             "config": {"attributes": ["price", "stock", "brand", "discount"]}},
            {"id": "n4", "type": "ai.prompt",              "label": "Write Comparison",
             "position": {"x": 860, "y": 220},
             "config": {"prompt": "Create a clear comparison summary for a customer choosing between these products: {{comparison_table}}. The customer asked: {{customer_query}}. Highlight the best value option.", "temperature": 0.5}},
            {"id": "n5", "type": "trigger.end",            "label": "End",
             "position": {"x": 1120, "y": 220},
             "config": {"message": "Here is your product comparison."}},
        ],
        "edges": [
            {"id": "e1", "from_node": "n1", "from_port": "default", "to_node": "n2", "to_port": "in"},
            {"id": "e2", "from_node": "n2", "from_port": "default", "to_node": "n3", "to_port": "in"},
            {"id": "e3", "from_node": "n3", "from_port": "default", "to_node": "n4", "to_port": "in"},
            {"id": "e4", "from_node": "n4", "from_port": "default", "to_node": "n5", "to_port": "in"},
        ],
    },
    {
        "slug":        "upsell_agent",
        "name":        "Upsell Agent",
        "description": "Search products, check if upsell is permitted, present premium alternatives with permission gating built-in.",
        "category":    "sales",
        "order":       3,
        "tags":        ["upsell", "permission-gated"],
        "nodes": [
            {"id": "n1", "type": "trigger.start",          "label": "Start",
             "position": {"x": 80,  "y": 220},
             "config": {"description": "Customer views a product"}},
            {"id": "n2", "type": "catalog.product_search", "label": "Find Base Products",
             "position": {"x": 340, "y": 220},
             "config": {"keyword": "{{customer_query}}", "max_results": 5}},
            {"id": "n3", "type": "permission.check",       "label": "Check Upsell Permission",
             "position": {"x": 600, "y": 220},
             "config": {"capability": "upsell"}},
            {"id": "n4", "type": "sales.upsell",           "label": "Suggest Upgrades",
             "position": {"x": 860, "y": 140},
             "config": {"upsell_percentage": 20, "max_suggestions": 2}},
            {"id": "n5", "type": "trigger.end",            "label": "End (Upsell)",
             "position": {"x": 1120, "y": 140},
             "config": {"message": "You might also love these premium options!"}},
            {"id": "n6", "type": "trigger.end",            "label": "End (Standard)",
             "position": {"x": 860,  "y": 320},
             "config": {"message": "Here are the best matches for you."}},
        ],
        "edges": [
            {"id": "e1", "from_node": "n1", "from_port": "default",  "to_node": "n2", "to_port": "in"},
            {"id": "e2", "from_node": "n2", "from_port": "default",  "to_node": "n3", "to_port": "in"},
            {"id": "e3", "from_node": "n3", "from_port": "allowed",  "to_node": "n4", "to_port": "in"},
            {"id": "e4", "from_node": "n4", "from_port": "default",  "to_node": "n5", "to_port": "in"},
            {"id": "e5", "from_node": "n3", "from_port": "denied",   "to_node": "n6", "to_port": "in"},
        ],
    },
    {
        "slug":        "campaign_agent",
        "name":        "Campaign Agent",
        "description": "Full-funnel commerce agent: open with AI intro, search products, recommend, upsell, and cross-sell in a single workflow.",
        "category":    "advanced",
        "order":       4,
        "tags":        ["advanced", "full-funnel"],
        "nodes": [
            {"id": "n1", "type": "trigger.start",           "label": "Start",
             "position": {"x": 80,  "y": 250},
             "config": {"description": "Campaign triggered"}},
            {"id": "n2", "type": "ai.prompt",               "label": "Opening Message",
             "position": {"x": 340, "y": 250},
             "config": {"prompt": "Write a warm, engaging opening message for a customer interested in {{category}} products. Keep it under 50 words.", "temperature": 0.8}},
            {"id": "n3", "type": "catalog.product_search",  "label": "Search Catalog",
             "position": {"x": 600, "y": 250},
             "config": {"keyword": "{{customer_query}}", "category": "{{category}}", "max_results": 8}},
            {"id": "n4", "type": "catalog.recommendation",  "label": "Top Picks",
             "position": {"x": 860, "y": 250},
             "config": {"top_n": 3, "ranking_criteria": "relevance"}},
            {"id": "n5", "type": "logic.condition",          "label": "Budget Check",
             "position": {"x": 1120, "y": 250},
             "config": {"field": "variables.budget", "operator": ">", "value": "2000"}},
            {"id": "n6", "type": "sales.upsell",             "label": "Upsell",
             "position": {"x": 1380, "y": 140},
             "config": {"upsell_percentage": 25, "max_suggestions": 2}},
            {"id": "n7", "type": "sales.cross_sell",         "label": "Cross-sell",
             "position": {"x": 1380, "y": 360},
             "config": {"max_suggestions": 2}},
            {"id": "n8", "type": "trigger.end",              "label": "End",
             "position": {"x": 1640, "y": 250},
             "config": {"message": "Your personalised campaign is ready!"}},
        ],
        "edges": [
            {"id": "e1", "from_node": "n1", "from_port": "default", "to_node": "n2", "to_port": "in"},
            {"id": "e2", "from_node": "n2", "from_port": "default", "to_node": "n3", "to_port": "in"},
            {"id": "e3", "from_node": "n3", "from_port": "default", "to_node": "n4", "to_port": "in"},
            {"id": "e4", "from_node": "n4", "from_port": "default", "to_node": "n5", "to_port": "in"},
            {"id": "e5", "from_node": "n5", "from_port": "true",   "to_node": "n6", "to_port": "in"},
            {"id": "e6", "from_node": "n5", "from_port": "false",  "to_node": "n7", "to_port": "in"},
            {"id": "e7", "from_node": "n6", "from_port": "default", "to_node": "n8", "to_port": "in"},
            {"id": "e8", "from_node": "n7", "from_port": "default", "to_node": "n8", "to_port": "in"},
        ],
    },
]


def seed_templates() -> None:
    """Idempotent: insert/update all built-in templates at app startup."""
    for t in BUILT_IN_TEMPLATES:
        models.upsert_template(t["slug"], t)


def clone_template_to_workflow(slug: str, merchant_id: str, name: str = None) -> str:
    """Create a new draft workflow from a template. Returns workflow_id."""
    from utils import ApiError
    tmpl = models.find_template_by_slug(slug)
    if not tmpl:
        raise ApiError(f"Template '{slug}' not found.", 404, code="NOT_FOUND")
    workflow_id = models.create_workflow(merchant_id, {
        "name":        name or tmpl["name"],
        "description": tmpl["description"],
        "nodes":       tmpl["nodes"],
        "edges":       tmpl["edges"],
        "template_id": slug,
        "tags":        tmpl.get("tags", []),
    })
    return workflow_id


def serialize_template(t: dict) -> dict:
    return {
        "slug":        t.get("slug"),
        "name":        t.get("name"),
        "description": t.get("description"),
        "category":    t.get("category"),
        "tags":        t.get("tags", []),
        "node_count":  len(t.get("nodes", [])),
        "nodes":       t.get("nodes", []),
        "edges":       t.get("edges", []),
    }
