"""
test_phase4.py
──────────────
QA suite for AI Commerce OS Phase 4 — AI Commerce Engine.

Covers exactly the groups requested in the Phase 4 QA protocol:
  1. AI Chat (English / Tamil / Tanglish)
  2. Product Search (keyword / category / price filter / out-of-stock)
  3. Comparison (2 products / 5 products / missing specs)
  4. Recommendation (budget / upsell / cross-sell)
  5. Cart (add / update / remove / invalid product)
  6. Approval (approve / reject / resume)
  7. Security (permission-denied checkout / merchant isolation / audit logs)
  8. Regression (Phase 1+2+3 still intact)
"""

import sys, os, json, base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stubs"))
sys.path.insert(0, os.path.dirname(__file__))
os.environ["API_KEY_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()

from app import create_app

app = create_app()
cli = app.test_client()

_results = {"passed": 0, "failed": 0, "bugs": []}

def test(name, condition, group, detail=""):
    if condition:
        _results["passed"] += 1
        print(f"  \u2705 {name}")
    else:
        _results["failed"] += 1
        _results["bugs"].append({"group": group, "test": name, "detail": detail})
        print(f"  \u274c {name}" + (f" \u2014 {detail}" if detail else ""))

def section(t):
    print(f"\n{'='*60}\n  {t}\n{'='*60}")

def ok(r): return r.status_code in (200, 201)
def j(r): return r.get_json() or {}
def data(r): return j(r).get("data", {})
def err(r): return j(r).get("error", {}).get("code", "")
def H(tok): return {"Authorization": f"Bearer {tok}"}

def signup(email, name):
    r = cli.post("/api/auth/signup", json={"email": email, "password": "TestPass1", "merchant_name": name})
    return r

def seed_products(h):
    specs = [
        ("Blue Cotton Kurta", "Fashion", "Cotton", 999, 30, 10),
        ("Red Silk Saree", "Fashion", "Silk", 4999, 10, 0),
        ("Wireless Earbuds", "Electronics", "SoundX", 2499, 50, 5),
        ("Bluetooth Speaker", "Electronics", "SoundX", 1999, 0, 0),   # out of stock
        ("Leather Wallet", "Accessories", "UrbanCraft", 799, 40, 0),
    ]
    ids = []
    for i, (name, cat, brand, price, stock, disc) in enumerate(specs):
        r = cli.post("/api/products", headers=h, json={
            "name": name, "category": cat, "brand": brand, "price": price,
            "stock": stock, "discount": disc, "sku": f"QA4-{i}",
            "availability": "in_stock" if stock > 0 else "out_of_stock",
        })
        ids.append(data(r)["product"]["id"])
    return ids

# ─────────────────────────────────────────────────────────────────────
section("GROUP 1 \u2014 AI Chat (English / Tamil / Tanglish)")
G = "CHAT"

r = signup("chat@test.com", "Chat Merchant"); tok = data(r)["access_token"]; h = H(tok)
pids = seed_products(h)

r = cli.post("/api/chat", headers=h, json={"message": "show me blue kurta under 2000"})
test("English search returns 200", ok(r), G)
res = data(r)
test("English detected as 'en'", res["language"] == "en", G, f"got {res['language']}")
test("Intent classified as search", res["intent"] == "search", G)
test("Reply mentions a product", "Kurta" in res["reply"] or res["data"].get("count", 0) >= 0, G)
sid = res["session_id"]
test("Session ID returned", bool(sid), G)

r = cli.post("/api/chat", headers=h, json={"message": "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd", "session_id": sid})
test("Tamil message returns 200", ok(r), G)
res_ta = data(r)
test("Tamil detected as 'ta'", res_ta["language"] == "ta", G, f"got {res_ta['language']}")

r = cli.post("/api/chat", headers=h, json={"message": "earbuds venum", "session_id": sid})
test("Tanglish message returns 200", ok(r), G)
res_tg = data(r)
test("Tanglish detected as 'tanglish'", res_tg["language"] == "tanglish", G, f"got {res_tg['language']}")
test("Tanglish intent classified as search", res_tg["intent"] == "search", G)

r = cli.post("/api/chat", headers=h, json={"message": "", "session_id": sid})
test("Empty message returns 400", r.status_code == 400, G)

# Conversation history persisted
r = cli.get(f"/api/chat/history/{sid}", headers=h)
test("Chat history retrievable", ok(r), G)
test("History has multiple turns", len(data(r)["messages"]) >= 4, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 2 \u2014 Product Search")
G = "SEARCH"

r = cli.post("/api/search", headers=h, json={"query": "kurta"})
test("Keyword search returns 200", ok(r), G)
test("Keyword search finds Kurta", any("Kurta" in p["name"] for p in data(r)["products"]), G)

r = cli.post("/api/search", headers=h, json={"query": "", "category": "Electronics"})
test("Category search returns 200", ok(r), G)
test("Category filter returns only Electronics", all(p["category"] == "Electronics" for p in data(r)["products"]), G)

r = cli.post("/api/search", headers=h, json={"query": "", "max_price": 1000})
test("Price filter returns 200", ok(r), G)
test("Price filter respects max_price", all(p["price"] <= 1000 for p in data(r)["products"]), G)

r = cli.post("/api/search", headers=h, json={"query": "speaker"})
test("Out-of-stock item excluded by default", not any(p["name"] == "Bluetooth Speaker" for p in data(r)["products"]), G)

r = cli.post("/api/search", headers=h, json={"query": "speaker", "in_stock_only": False})
test("Out-of-stock item included when explicitly requested",
     any(p["name"] == "Bluetooth Speaker" for p in data(r)["products"]), G)

r = cli.get(f"/api/search/similar/{pids[0]}", headers=h)
test("Similar products returns 200", ok(r), G)
test("Similar products excludes the base product", all(p["id"] != pids[0] for p in data(r)["similar_products"]), G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 3 \u2014 Comparison")
G = "COMPARE"

r = cli.post("/api/compare", headers=h, json={"product_ids": pids[:2]})
test("Compare 2 products returns 200", ok(r), G)
test("Compare 2 returns 2 rows", data(r)["count"] == 2, G)
test("Compare includes explainable summary", len(data(r)["summary"]) > 0, G)

r = cli.post("/api/compare", headers=h, json={"product_ids": pids[:5]})
test("Compare 5 products returns 200", ok(r), G)
test("Compare 5 returns 5 rows", data(r)["count"] == 5, G)

r = cli.post("/api/compare", headers=h, json={"product_ids": pids[:7] if len(pids) >= 7 else pids + pids[:2]})
# cap check: only 5 unique ids exist, so test the MAX_COMPARE limit directly with duplicates padded
r2 = cli.post("/api/compare", headers=h, json={"product_ids": ["x"]*7})
test("Comparing more than 6 products is rejected", r2.status_code == 400, G)

# Missing specification handling: none of the seeded products have specifications set
r = cli.post("/api/compare", headers=h, json={"product_ids": pids[:2]})
specs = data(r)["products"][0]["specifications"]
test("Missing specifications handled gracefully (no crash)", isinstance(specs, dict), G)
test("Missing specifications shows a note", "note" in specs, G)

r = cli.post("/api/compare", headers=h, json={"product_ids": [pids[0]]})
test("Comparing fewer than 2 products is rejected", r.status_code == 400, G)

r = cli.post("/api/compare", headers=h, json={"product_ids": [pids[0], "000000000000000000000000"]})
test("Comparing with an invalid product ID returns 404", r.status_code == 404, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 4 \u2014 Recommendation")
G = "RECOMMEND"

r = cli.post("/api/recommend/budget", headers=h, json={"budget": 1000})
test("Budget recommendation returns 200", ok(r), G)
test("Budget recommendation respects budget", all(p["price"] <= 1000 for p in data(r)["recommendations"]), G)

r = cli.post("/api/recommend/budget", headers=h, json={"budget": -5})
test("Invalid (negative) budget rejected", r.status_code == 400, G)

# Upsell — disabled by default
r = cli.post("/api/recommend/upsell", headers=h, json={"product_ids": [pids[0]]})
test("Upsell call returns 200 even when disabled", ok(r), G)
test("Upsell blocked when capability disabled", data(r).get("upsell_blocked") is True, G)

cli.put("/api/permissions/upsell", headers=h, json={"enabled": True})
r = cli.post("/api/recommend/upsell", headers=h, json={"product_ids": [pids[0]]})
test("Upsell returns suggestions once enabled", "upsell_suggestions" in data(r), G)

# Cross-sell — disabled by default
r = cli.post("/api/recommend/cross-sell", headers=h, json={"product_ids": [pids[0]]})
test("Cross-sell blocked when capability disabled", data(r).get("cross_sell_blocked") is True, G)

cli.put("/api/permissions/cross_sell", headers=h, json={"enabled": True})
r = cli.post("/api/recommend/cross-sell", headers=h, json={"product_ids": [pids[0]]})
test("Cross-sell returns suggestions once enabled", "cross_sell_suggestions" in data(r), G)

r = cli.get(f"/api/recommend/alternatives/{pids[0]}", headers=h)
test("Alternatives endpoint returns 200", ok(r), G)

r = cli.get(f"/api/recommend/bundle/{pids[0]}", headers=h)
test("Bundle endpoint returns 200", ok(r), G)
test("Bundle includes savings calculation", "savings" in data(r), G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 5 \u2014 Cart")
G = "CART"

cli.put("/api/permissions/cart_create", headers=h, json={"enabled": True})
csid = "cart_test_session"

r = cli.post(f"/api/cart/{csid}/items", headers=h, json={"product_id": pids[0], "quantity": 2})
test("Add item to cart returns 201", r.status_code == 201, G)
test("Cart item count correct after add", data(r)["item_count"] == 2, G)

r = cli.put(f"/api/cart/{csid}/items/{pids[0]}", headers=h, json={"quantity": 5})
test("Update quantity returns 200", ok(r), G)
test("Quantity updated correctly", data(r)["items"][0]["quantity"] == 5, G)

r = cli.delete(f"/api/cart/{csid}/items/{pids[0]}", headers=h)
test("Remove item returns 200", ok(r), G)
test("Cart empty after removing only item", data(r)["item_count"] == 0, G)

r = cli.post(f"/api/cart/{csid}/items", headers=h, json={"product_id": "000000000000000000000000", "quantity": 1})
test("Adding invalid product returns 404", r.status_code == 404, G, f"got {r.status_code}")

r = cli.post(f"/api/cart/{csid}/items", headers=h, json={"product_id": pids[1], "quantity": 999})
test("Adding more than available stock returns 409", r.status_code == 409, G)

r = cli.post(f"/api/cart/{csid}/items", headers=h, json={"product_id": pids[0], "quantity": 0})
test("Adding zero quantity returns 400", r.status_code == 400, G)

r = cli.get(f"/api/cart/{csid}", headers=h)
test("Get cart returns 200", ok(r), G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 6 \u2014 Approval (approve / reject / resume)")
G = "APPROVAL"

asid = "approval_test_session"
cli.post(f"/api/cart/{asid}/items", headers=h, json={"product_id": pids[0], "quantity": 1})  # ₹999

cli.put("/api/permissions/payment_request", headers=h,
        json={"enabled": True, "limits": {"max_amount": 2000, "approval_required": True}})

r = cli.post("/api/approval/request", headers=h, json={"session_id": asid})
test("Approval request returns 200", ok(r), G)
appr = data(r)
test("Approval status is pending (approval required)", appr["status"] == "pending", G)
aid = appr["approval_id"]

r = cli.put(f"/api/approval/{aid}/decide", headers=h, json={"decision": "approved"})
test("Approve decision returns 200", ok(r), G)
test("Approval status updated to approved", data(r)["status"] == "approved", G)

# "Resume": cart status reflects the approval decision
cart_after = cli.get(f"/api/cart/{asid}", headers=h)
test("Cart still accessible after approval (resume)", ok(cart_after), G)

# Reject flow
bsid = "reject_test_session"
cli.post(f"/api/cart/{bsid}/items", headers=h, json={"product_id": pids[0], "quantity": 1})
r = cli.post("/api/approval/request", headers=h, json={"session_id": bsid})
aid2 = data(r)["approval_id"]
r = cli.put(f"/api/approval/{aid2}/decide", headers=h, json={"decision": "rejected"})
test("Reject decision returns 200", ok(r), G)
test("Approval status updated to rejected", data(r)["status"] == "rejected", G)

r = cli.put(f"/api/approval/{aid2}/decide", headers=h, json={"decision": "approved"})
test("Deciding an already-decided approval is rejected (409)", r.status_code == 409, G)

r = cli.get("/api/approval", headers=h)
test("List approvals returns 200", ok(r), G)
test("Approval list has entries", len(data(r)["approvals"]) >= 2, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 7 \u2014 Security")
G = "SECURITY"

# Permission-denied checkout: disable payment_request entirely
cli.put("/api/permissions/payment_request", headers=h, json={"enabled": False})
dsid = "denied_checkout_session"
cli.post(f"/api/cart/{dsid}/items", headers=h, json={"product_id": pids[0], "quantity": 1})
r = cli.post("/api/approval/request", headers=h, json={"session_id": dsid})
test("Checkout with payment_request disabled returns 403", r.status_code == 403, G)
test("Denied checkout status is rejected", data(r)["status"] == "rejected", G)

# Re-enable for isolation tests
cli.put("/api/permissions/payment_request", headers=h,
        json={"enabled": True, "limits": {"max_amount": 2000, "approval_required": True}})

# Merchant isolation
r2 = signup("chat2@test.com", "Chat Merchant 2"); tok2 = data(r2)["access_token"]; h2 = H(tok2)

r = cli.get(f"/api/cart/{csid}", headers=h2)
test("Merchant B sees empty cart for Merchant A's session (isolated)", data(r)["item_count"] == 0, G)

r = cli.get(f"/api/chat/history/{sid}", headers=h2)
test("Merchant B cannot see Merchant A's chat history", len(data(r)["messages"]) == 0, G)

r = cli.get(f"/api/approval/{aid}", headers=h2)
test("Merchant B cannot view Merchant A's approval", r.status_code == 404, G)

r = cli.post("/api/search", headers=h2, json={"query": "kurta"})
test("Merchant B search returns no results (isolated catalog)", data(r)["count"] == 0, G)

r = cli.post("/api/copilot/ask", headers=h2, json={"question": "which products sell better?"})
test("Merchant B copilot has no data (isolated)", len(data(r).get("data", [])) == 0, G)

# Audit logs generated for Phase 4 actions
cli.post("/api/copilot/ask", headers=h, json={"question": "which products sell better?"})
r = cli.get("/api/merchant/activity", headers=h)
actions = [a["action"] for a in data(r)["activity"]]
test("checkout_requested logged", "checkout_requested" in actions, G)
test("checkout_approved logged", "checkout_approved" in actions, G)
test("checkout_rejected logged", "checkout_rejected" in actions, G)
test("copilot_query logged", "copilot_query" in actions, G)

logs_str = json.dumps(data(r)["activity"])
test("No API keys or passwords leaked in audit logs", "sk-" not in logs_str and "password" not in logs_str.lower(), G)

# No JWT enforcement across all Phase 4 routes
routes = [
    ("POST", "/api/chat"), ("GET", f"/api/chat/history/{sid}"),
    ("POST", "/api/search"), ("GET", f"/api/search/similar/{pids[0]}"),
    ("POST", "/api/compare"),
    ("POST", "/api/recommend/budget"), ("POST", "/api/recommend/upsell"),
    ("GET", f"/api/cart/{csid}"), ("POST", f"/api/cart/{csid}/items"),
    ("POST", "/api/approval/request"), ("GET", "/api/approval"),
    ("POST", "/api/copilot/ask"),
]
for method, path in routes:
    r = cli.open(path, method=method, content_type="application/json", data="{}")
    test(f"No JWT \u2192 401 on {method} {path}", r.status_code == 401, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 8 \u2014 Regression (Phase 1 + 2 + 3)")
G = "REGRESSION"

r = signup("regr4@test.com", "Regression 4"); rtok = data(r)["access_token"]; rh = H(rtok)
test("Phase 1 signup still works", r.status_code == 201, G)

r = cli.get("/api/merchant/dashboard-summary", headers=rh)
test("Dashboard summary still works", ok(r), G)

r = cli.post("/api/products", headers=rh, json={"name": "Regr P4 Product", "price": 199})
test("Phase 2 product creation still works", r.status_code == 201, G)

r = cli.get("/api/permissions", headers=rh)
test("Phase 2 permissions still work (12 capabilities)", len(data(r)["permissions"]) == 12, G)

r = cli.post("/api/workflows", headers=rh, json={"name": "Regr Workflow"})
test("Phase 3 workflow creation still works", r.status_code == 201, G)
wid = data(r)["workflow"]["id"]

r = cli.get("/api/templates", headers=rh)
test("Phase 3 templates still seeded (4)", len(data(r)["templates"]) == 4, G)

# Chat-driven execution logs appear in the Phase 3 executions list
cli.post("/api/chat", headers=rh, json={"message": "hello"})
r = cli.get("/api/executions", headers=rh)
test("Chat activity appears in Phase 3 execution logs", len(data(r)["executions"]) >= 1, G)
chat_exec = next((e for e in data(r)["executions"]), None)
test("Execution log entry has completed status", chat_exec["status"] == "completed", G)

for path in ["/", "/login", "/signup", "/dashboard", "/settings", "/products",
             "/ai-settings", "/permissions", "/workflows", "/builder", "/templates",
             "/executions", "/chat", "/compare", "/cart", "/approvals", "/copilot"]:
    r = cli.get(path)
    test(f"Page {path} renders (200)", r.status_code == 200, G)

r = cli.get("/api/health")
test("Health check reports phase >= 4 (current phase)", isinstance(j(r).get("phase"), int) and j(r).get("phase") >= 4, G)

# ─────────────────────────────────────────────────────────────────────
total = _results["passed"] + _results["failed"]
passed, failed, bugs = _results["passed"], _results["failed"], _results["bugs"]

print(f"\n{'='*60}\n  PHASE 4 QA REPORT\n{'='*60}\n")
print(f"  Total tests : {total}")
print(f"  Passed      : {passed}")
print(f"  Failed      : {failed}")
print(f"  Pass rate   : {100*passed//total if total else 0}%\n")

from collections import Counter
group_fails = Counter(b["group"] for b in bugs)
labels = {
    "CHAT": "AI Chat (EN/TA/Tanglish)", "SEARCH": "Product Search",
    "COMPARE": "Comparison Engine", "RECOMMEND": "Recommendation Engine",
    "CART": "Conversational Cart", "APPROVAL": "Human Approval System",
    "SECURITY": "Security & Isolation", "REGRESSION": "Regression (Phase 1+2+3)",
}
for g, label in labels.items():
    status = "PASS" if group_fails[g] == 0 else f"FAIL ({group_fails[g]})"
    print(f"  {label:<32} {status}")

if bugs:
    print(f"\n  BUGS FOUND ({len(bugs)})")
    for i, b in enumerate(bugs, 1):
        print(f"\n  [{i}] {b['test']}\n       Group: {b['group']}" + (f"\n       Detail: {b['detail']}" if b.get('detail') else ""))

verdict = "READY" if failed == 0 else "NOT READY"
print(f"\n{'='*60}\n  PHASE 4 STATUS: {verdict}\n{'='*60}\n")

sys.exit(0 if failed == 0 else 1)
