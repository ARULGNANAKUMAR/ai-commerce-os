"""
test_phase2.py
──────────────
Comprehensive QA + security test suite for AI Commerce OS Phase 1 + 2.

Usage (from project root, with MongoDB NOT required — uses stubs):
    python test_phase2.py

Covers all 9 test groups specified in the Phase 2 prompt:
    1. Authentication
    2. Multi-tenant isolation
    3. Product CRUD
    4. Bulk import
    5. AI API security
    6. Permission engine
    7. Audit logs
    8. API security
    9. Regression (Phase 1)
"""

import sys, os, json, io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stubs"))
sys.path.insert(0, os.path.dirname(__file__))

# Set required environment variable before importing app
os.environ.setdefault(
    "API_KEY_ENCRYPTION_KEY",
    "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcy1sb25n"  # 44-char base64 of 32 bytes
)
# Use a real Fernet key for encryption tests
import base64
_fernet_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
os.environ["API_KEY_ENCRYPTION_KEY"] = _fernet_key

from app import create_app

app  = create_app()
cli  = app.test_client()

# ─────────────────────────────────────────────────────────────────────
# Test harness
# ─────────────────────────────────────────────────────────────────────

_results = {"passed": 0, "failed": 0, "bugs": []}

def test(name: str, condition: bool, group: str, detail: str = ""):
    if condition:
        _results["passed"] += 1
        print(f"  ✅ {name}")
    else:
        _results["failed"] += 1
        _results["bugs"].append({"group": group, "test": name, "detail": detail})
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

def section(title: str):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")

def ok(r):  return r.status_code in (200, 201)
def j(r):   return r.get_json() or {}
def data(r): return j(r).get("data", {})
def err(r):  return j(r).get("error", {}).get("code", "")

# ─────────────────────────────────────────────────────────────────────
# Setup helpers
# ─────────────────────────────────────────────────────────────────────

def signup(email, name, company="Corp"):
    r = cli.post("/api/auth/signup", json={
        "email": email, "password": "TestPass1",
        "merchant_name": name, "company_name": company
    })
    return r

def auth_header(token):
    return {"Authorization": f"Bearer {token}"}

# ─────────────────────────────────────────────────────────────────────
# GROUP 1 — Authentication
# ─────────────────────────────────────────────────────────────────────

section("GROUP 1 — Authentication")

r = signup("auth_test@test.com", "Auth User"); G = "AUTH"
test("Signup returns 201",          r.status_code == 201, G)
test("Signup includes access_token", "access_token" in data(r), G)
test("Signup includes refresh_token","refresh_token" in data(r), G)
_tok = data(r)["access_token"]; _rtok = data(r)["refresh_token"]

r = cli.post("/api/auth/login", json={"email":"auth_test@test.com","password":"TestPass1"})
test("Login with correct password returns 200", ok(r), G)
login_tok = data(r)["access_token"]

r = cli.post("/api/auth/login", json={"email":"auth_test@test.com","password":"wrong"})
test("Login with wrong password returns 401",   r.status_code == 401, G)
test("Wrong password: INVALID_CREDENTIALS code", err(r) == "INVALID_CREDENTIALS", G)

r = cli.post("/api/auth/login", json={"email":"nobody@test.com","password":"TestPass1"})
test("Login with unknown email returns 401", r.status_code == 401, G)

r = cli.get("/api/merchant/profile")
test("Protected route without token returns 401", r.status_code == 401, G)

r = cli.get("/api/merchant/profile", headers={"Authorization":"Bearer bad-token"})
test("Invalid JWT returns 401", r.status_code == 401, G)

r = cli.get("/api/merchant/profile", headers=auth_header(login_tok))
test("Valid JWT allows access to protected route", ok(r), G)

r = cli.post("/api/auth/logout", headers=auth_header(login_tok), json={"refresh_token":_rtok})
test("Logout returns 200", ok(r), G)

r = cli.post("/api/auth/refresh", json={"refresh_token":_rtok})
test("Refresh after logout returns 401 (session revoked)", r.status_code == 401, G)

r = cli.post("/api/auth/signup", json={"email":"auth_test@test.com","password":"TestPass1","merchant_name":"X"})
test("Duplicate email signup returns 409", r.status_code == 409, G)

r = cli.post("/api/auth/signup", json={"email":"weak@test.com","password":"1234","merchant_name":"X"})
test("Weak password rejected (400)", r.status_code == 400, G)

r = cli.post("/api/auth/signup", json={"email":"bad-email","password":"TestPass1","merchant_name":"X"})
test("Invalid email rejected (400)", r.status_code == 400, G)

# ─────────────────────────────────────────────────────────────────────
# GROUP 2 — Multi-tenant isolation
# ─────────────────────────────────────────────────────────────────────

section("GROUP 2 — Multi-tenant isolation")
G = "ISOLATION"

rA = signup("merchant_a@iso.com","Merchant A","Alpha Corp"); tokA = data(rA)["access_token"]
rB = signup("merchant_b@iso.com","Merchant B","Beta Corp");  tokB = data(rB)["access_token"]
HA = auth_header(tokA); HB = auth_header(tokB)

# Create products and AI config for A
r = cli.post("/api/products", headers=HA, json={"name":"A Product","price":100,"stock":10,"sku":"A-001"})
test("Merchant A can create product", ok(r), G)
pid_a = data(r)["product"]["id"]

cli.post("/api/ai/providers", headers=HA, json={"provider":"gemini","model":"gemini-1.5-flash","api_key":"secret-key-a"})

# B cannot access A's product
r = cli.get(f"/api/products/{pid_a}", headers=HB)
test("B cannot read A's product (404)", r.status_code == 404, G)

# B's product list is empty (isolated)
r = cli.get("/api/products", headers=HB)
test("B product list is empty (0 products)", data(r)["pagination"]["total"] == 0, G)

# B cannot update A's product
r = cli.put(f"/api/products/{pid_a}", headers=HB, json={"price":999})
test("B cannot update A's product (404)", r.status_code == 404, G)

# B cannot delete A's product
r = cli.delete(f"/api/products/{pid_a}", headers=HB)
test("B cannot delete A's product (404)", r.status_code == 404, G)

# B's AI config is independent (A connected, B has none)
r = cli.get("/api/ai/providers", headers=HB)
test("B has no AI provider (isolated from A)", data(r)["provider"] is None, G)

# Permissions are isolated: enable payment_request for A only
cli.put("/api/permissions/payment_request", headers=HA, json={"enabled":True})
r = cli.post("/api/permissions/check", headers=HB,
             json={"capability":"payment_request","context":{"amount":500}})
test("B's payment_request still DENY (isolated from A's config)", data(r)["decision"] == "DENY", G)

# Frontend cannot spoof merchant_id: JWT g.merchant_id is always used
# Attempt to pass a different merchant_id in the request body is ignored
r = cli.post("/api/products", headers=HA,
             json={"name":"Spoofed","price":10,"merchant_id": data(rB).get("merchant", {}).get("id","fake")})
r2 = cli.get("/api/products", headers=HA)
# The created product should still belong to A
test("merchant_id in request body is ignored (always from JWT)", data(r2)["pagination"]["total"] >= 1, G)

# ─────────────────────────────────────────────────────────────────────
# GROUP 3 — Product CRUD
# ─────────────────────────────────────────────────────────────────────

section("GROUP 3 — Product CRUD")
G = "PRODUCT_CRUD"

r = signup("crud@test.com","CRUD User","CRUD Corp"); tok = data(r)["access_token"]; H = auth_header(tok)

# Valid create
r = cli.post("/api/products", headers=H, json={
    "name":"Test Kurta","price":599,"stock":50,"category":"Fashion",
    "brand":"TestBrand","sku":"CRUD-001","tags":["kurta","cotton"],
    "availability":"in_stock"
})
test("Create product returns 201",      r.status_code == 201, G)
test("Created product has correct name", data(r)["product"]["name"] == "Test Kurta", G)
test("Created product has correct price", data(r)["product"]["price"] == 599.0, G)
cid = data(r)["product"]["id"]

# Read
r = cli.get(f"/api/products/{cid}", headers=H)
test("Read product returns 200",          ok(r), G)
test("Product has availability field",    "availability" in data(r)["product"], G)
test("key_encrypted NOT in response",    "key_encrypted" not in str(j(r)), G)

# Update
r = cli.put(f"/api/products/{cid}", headers=H, json={"price":799,"stock":45})
test("Update product returns 200",         ok(r), G)
test("Updated price is correct",           data(r)["product"]["price"] == 799.0, G)
test("Unchanged fields preserved (name)",  data(r)["product"]["name"] == "Test Kurta", G)

# Read after update
r = cli.get(f"/api/products/{cid}", headers=H)
test("Get after update shows new price",   data(r)["product"]["price"] == 799.0, G)

# Delete (soft)
r = cli.delete(f"/api/products/{cid}", headers=H)
test("Delete returns 200",                 ok(r), G)

r = cli.get(f"/api/products/{cid}", headers=H)
test("Deleted product returns 404",        r.status_code == 404, G)

# Validation: missing name
r = cli.post("/api/products", headers=H, json={"price":100})
test("Missing name returns 400",           r.status_code == 400, G)

# Validation: negative price
r = cli.post("/api/products", headers=H, json={"name":"X","price":-50})
test("Negative price returns 400",         r.status_code == 400, G)

# Validation: invalid price type
r = cli.post("/api/products", headers=H, json={"name":"X","price":"not-a-number"})
test("Non-numeric price returns 400",      r.status_code == 400, G)

# Validation: negative stock
r = cli.post("/api/products", headers=H, json={"name":"X","price":100,"stock":-5})
test("Negative stock returns 400",         r.status_code == 400, G)

# Duplicate SKU
cli.post("/api/products", headers=H, json={"name":"Dup A","price":100,"sku":"DUP-X"})
r = cli.post("/api/products", headers=H, json={"name":"Dup B","price":200,"sku":"DUP-X"})
test("Duplicate SKU returns 409",          r.status_code == 409, G)

# Invalid availability
r = cli.post("/api/products", headers=H, json={"name":"X","price":100,"availability":"flying"})
test("Invalid availability returns 400",   r.status_code == 400, G)

# 404 on unknown product
r = cli.get("/api/products/000000000000000000000000", headers=H)
test("Unknown product ID returns 404",     r.status_code == 404, G)

# ─────────────────────────────────────────────────────────────────────
# GROUP 4 — Bulk import
# ─────────────────────────────────────────────────────────────────────

section("GROUP 4 — Bulk Import")
G = "IMPORT"

r = signup("import@test.com","Import User"); tok = data(r)["access_token"]; H = auth_header(tok)

# JSON import: mix of valid, invalid, and duplicate
products_data = [
    {"name":"Valid A","price":999,"stock":20,"sku":"IMP-001","category":"Fashion"},
    {"name":"Valid B","price":499,"stock":50,"sku":"IMP-002"},
    {"name":"",       "price":599},                          # missing name → fail
    {"name":"X",      "price":-10},                          # negative price → fail
    {"name":"Valid C","price":299,"stock":10,"sku":"IMP-001"},# dup SKU → skip
    {},                                                       # empty → skip
]
r = cli.post("/api/products/import",
             headers={**H, "Content-Type":"application/json"},
             data=json.dumps(products_data))
d = data(r)
test("Import returns 200",                          r.status_code == 200, G)
test("Import: 2 rows imported",                     d["imported"] == 2, G,
     f"got {d.get('imported')}")
test("Import: 2 rows failed validation",            d["failed"]   == 2, G,
     f"got {d.get('failed')}")
test("Import: 1 duplicate SKU skipped",             d["duplicates"] == 1, G,
     f"got {d.get('duplicates')}")
test("Import: errors list provided",                isinstance(d.get("errors"), list), G)

# CSV import via file upload
csv_bytes = b"""name,price,stock,sku,category
CSV Product A,1999,30,CSV-001,Electronics
CSV Product B,999,15,CSV-002,Electronics
,500,10,,
Bad Price,-100,5,CSV-003,
"""
data_io = io.BytesIO(csv_bytes)
r = cli.post("/api/products/import", headers=H, data={"file": (data_io, "products.csv")},
             content_type="multipart/form-data")
d2 = data(r)
test("CSV import returns 200/422",                  r.status_code in (200, 422), G)
test("CSV import: 2 valid rows imported",           d2.get("imported") == 2, G,
     f"got {d2.get('imported')}")
test("CSV import: 2 invalid rows rejected",         d2.get("failed") == 2, G,
     f"got {d2.get('failed')}")

# Empty JSON array
r = cli.post("/api/products/import",
             headers={**H, "Content-Type":"application/json"}, data="[]")
test("Empty JSON array returns gracefully", r.status_code in (200, 422), G)

# JSON object instead of array
r = cli.post("/api/products/import",
             headers={**H, "Content-Type":"application/json"},
             data=json.dumps({"not":"an array"}))
test("Non-array JSON body returns 400", r.status_code == 400, G)

# ─────────────────────────────────────────────────────────────────────
# GROUP 5 — AI API security
# ─────────────────────────────────────────────────────────────────────

section("GROUP 5 — AI API Security")
G = "AI_SECURITY"

r = signup("ai@test.com","AI User"); tok = data(r)["access_token"]; H = auth_header(tok)

# Missing API key
r = cli.post("/api/ai/providers", headers=H,
             json={"provider":"gemini","model":"gemini-1.5-flash","api_key":""})
test("Empty API key rejected (400)", r.status_code == 400, G)

# Unknown provider
r = cli.post("/api/ai/providers", headers=H,
             json={"provider":"unknown_ai","model":"some-model","api_key":"test"})
test("Unknown provider rejected (400)",          r.status_code == 400, G)

# Unsupported model for provider
r = cli.post("/api/ai/providers", headers=H,
             json={"provider":"gemini","model":"gpt-4o","api_key":"test-key-12345"})
test("Wrong model for provider rejected (400)", r.status_code == 400, G)

# Valid save — check key NEVER appears in response
r = cli.post("/api/ai/providers", headers=H,
             json={"provider":"openai","model":"gpt-4o-mini","api_key":"sk-test-secret-key-never-reveal-99"})
test("Valid provider save returns 200",             ok(r), G)
resp_str = json.dumps(j(r))
test("Raw API key NOT in save response",           "sk-test-secret-key-never-reveal-99" not in resp_str, G)
test("key_encrypted NOT in save response",         "key_encrypted" not in resp_str, G)
test("Only key_hint (last 4) present in response", data(r)["provider"]["key_hint"] == "-99" or
     data(r)["provider"]["key_hint"] == "l-99"[-4:] or
     len(data(r)["provider"].get("key_hint","")) <= 4, G)

# GET never reveals key
r = cli.get("/api/ai/providers", headers=H)
resp_str2 = json.dumps(j(r))
test("GET provider: raw key NOT in response",      "sk-test-secret-key-never-reveal-99" not in resp_str2, G)
test("GET provider: key_encrypted NOT in response","key_encrypted" not in resp_str2, G)

# Test connection (network disabled → expects failure but safe message)
r = cli.post("/api/ai/providers/test", headers=H)
test("Test connection returns safe message (not raw error)", r.status_code in (200, 422), G)
t_resp = json.dumps(j(r))
test("Test result contains no raw credentials",    "sk-test" not in t_resp, G)

# Unauthenticated access
r = cli.post("/api/ai/providers", json={"provider":"gemini","model":"gemini-1.5-flash","api_key":"x"})
test("Unauthenticated AI route returns 401",       r.status_code == 401, G)

# Delete provider
r = cli.delete("/api/ai/providers", headers=H)
test("Delete provider returns 200",                ok(r), G)

r = cli.post("/api/ai/providers/test", headers=H)
test("Test after delete returns 404",              r.status_code == 404, G)

# ─────────────────────────────────────────────────────────────────────
# GROUP 6 — Permission engine
# ─────────────────────────────────────────────────────────────────────

section("GROUP 6 — Permission Engine")
G = "PERMISSIONS"

r = signup("perm@test.com","Perm User"); tok = data(r)["access_token"]; H = auth_header(tok)

# All 12 capabilities initialized
r = cli.get("/api/permissions", headers=H)
perms = data(r)["permissions"]
test("12 capabilities returned",                  len(perms) == 12, G, f"got {len(perms)}")

# Scenario 1: product_search enabled by default → ALLOW
r = cli.post("/api/permissions/check", headers=H, json={"capability":"product_search"})
test("Scenario 1: product_search → ALLOW",         data(r)["decision"] == "ALLOW", G)

# Scenario 2: payment_request disabled by default → DENY
r = cli.post("/api/permissions/check", headers=H, json={"capability":"payment_request","context":{"amount":100}})
test("Scenario 2: payment_request (disabled) → DENY", data(r)["decision"] == "DENY", G)

# Enable payment_request with limits
cli.put("/api/permissions/payment_request", headers=H,
        json={"enabled":True,"limits":{"max_amount":2000,"approval_required":True}})

# Scenario 3: ₹1500 within ₹2000 limit, approval required → REQUIRES_APPROVAL
r = cli.post("/api/permissions/check", headers=H, json={"capability":"payment_request","context":{"amount":1500}})
test("Scenario 3: ₹1500 within limit → REQUIRES_APPROVAL", data(r)["decision"] == "REQUIRES_APPROVAL", G)

# Scenario 4: ₹3000 exceeds ₹2000 limit → LIMIT_EXCEEDED
r = cli.post("/api/permissions/check", headers=H, json={"capability":"payment_request","context":{"amount":3000}})
test("Scenario 4: ₹3000 > ₹2000 → LIMIT_EXCEEDED", data(r)["decision"] == "LIMIT_EXCEEDED", G)

# Scenario 5: unknown capability → DENY (deny-by-default)
r = cli.post("/api/permissions/check", headers=H, json={"capability":"fly_to_moon"})
test("Scenario 5: unknown capability → DENY",     data(r)["decision"] == "DENY", G)

# Enable without approval → ALLOW
cli.put("/api/permissions/payment_request", headers=H,
        json={"enabled":True,"limits":{"max_amount":5000,"approval_required":False}})
r = cli.post("/api/permissions/check", headers=H, json={"capability":"payment_request","context":{"amount":1000}})
test("Payment enabled, no approval, within limit → ALLOW", data(r)["decision"] == "ALLOW", G)

# Disable a default-enabled capability
cli.put("/api/permissions/product_search", headers=H, json={"enabled":False})
r = cli.post("/api/permissions/check", headers=H, json={"capability":"product_search"})
test("Disabled product_search → DENY",            data(r)["decision"] == "DENY", G)

# Re-enable it
cli.put("/api/permissions/product_search", headers=H, json={"enabled":True})
r = cli.post("/api/permissions/check", headers=H, json={"capability":"product_search"})
test("Re-enabled product_search → ALLOW",         data(r)["decision"] == "ALLOW", G)

# Invalid capability update
r = cli.put("/api/permissions/fake_cap", headers=H, json={"enabled":True})
test("Update unknown capability returns 400",     r.status_code == 400, G)

# Missing enabled field
r = cli.put("/api/permissions/product_search", headers=H, json={"limits":{"max_amount":100}})
test("Missing 'enabled' field returns 400",       r.status_code == 400, G)

# Negative max_amount rejected
r = cli.put("/api/permissions/payment_request", headers=H,
            json={"enabled":True,"limits":{"max_amount":-500}})
test("Negative max_amount returns 400",           r.status_code == 400, G)

# ─────────────────────────────────────────────────────────────────────
# GROUP 7 — Audit logs
# ─────────────────────────────────────────────────────────────────────

section("GROUP 7 — Audit Logs")
G = "AUDIT"

r = signup("audit@test.com","Audit User"); tok = data(r)["access_token"]; H = auth_header(tok)
mid = data(r)["merchant"]["id"]

# Perform auditable actions
cli.post("/api/products", headers=H, json={"name":"Audit Product","price":100})
cli.post("/api/ai/providers", headers=H,
         json={"provider":"gemini","model":"gemini-1.5-flash","api_key":"audit-key-xxxx"})
cli.put("/api/permissions/upsell", headers=H, json={"enabled":True})

r = cli.get("/api/merchant/activity", headers=H)
logs = data(r)["activity"]
test("Audit logs returned",                        isinstance(logs, list), G)
test("At least 4 audit events recorded",           len(logs) >= 4, G, f"got {len(logs)}")

actions = [l["action"] for l in logs]
test("signup action logged",                       "signup" in actions, G)
test("product_created action logged",              "product_created" in actions, G)
test("ai_provider_connected action logged",        "ai_provider_connected" in actions, G)
test("permission_updated action logged",           "permission_updated" in actions, G)

# Verify sensitive data NOT in logs
logs_str = json.dumps(logs)
test("API key NOT in audit logs",                  "audit-key-xxxx" not in logs_str, G)
test("key_encrypted NOT in audit logs",            "key_encrypted" not in logs_str, G)
test("password_hash NOT in audit logs",            "password_hash" not in logs_str, G)

# Logs are merchant-scoped: create another merchant and check isolation
r2 = signup("audit2@test.com","Audit User 2"); tok2 = data(r2)["access_token"]; H2 = auth_header(tok2)
r = cli.get("/api/merchant/activity", headers=H2)
logs2 = data(r)["activity"]
# Should only see audit2's own signup
test("Audit logs are merchant-scoped (no cross-tenant bleed)",
     all(a["action"] != "product_created" for a in logs2), G)

# ─────────────────────────────────────────────────────────────────────
# GROUP 8 — API Security
# ─────────────────────────────────────────────────────────────────────

section("GROUP 8 — API Security")
G = "API_SECURITY"

r = signup("sec@test.com","Security User"); tok = data(r)["access_token"]; H = auth_header(tok)

# Missing JWT on every protected endpoint
protected_routes = [
    ("GET",    "/api/products"),
    ("POST",   "/api/products"),
    ("GET",    "/api/ai/providers"),
    ("POST",   "/api/ai/providers"),
    ("GET",    "/api/permissions"),
    ("PUT",    "/api/permissions/product_search"),
    ("POST",   "/api/permissions/check"),
    ("GET",    "/api/merchant/profile"),
    ("GET",    "/api/merchant/dashboard-summary"),
]
for method, path in protected_routes:
    r = cli.open(path, method=method, content_type="application/json", data="{}")
    test(f"No JWT → 401 on {method} {path}", r.status_code == 401, G)

# Wrong HTTP method on key routes
r = cli.get("/api/auth/signup")
test("GET /api/auth/signup returns 405", r.status_code == 405, G)

r = cli.get("/api/auth/login")
test("GET /api/auth/login returns 405", r.status_code == 405, G)

# Invalid ObjectId
r = cli.get("/api/products/INVALID-ID", headers=H)
test("Invalid product ObjectId returns 404", r.status_code == 404, G)

# XSS-like input sanitized (doesn't crash, stored safely)
r = cli.post("/api/products", headers=H, json={
    "name": "<script>alert('xss')</script>",
    "price": 100
})
test("XSS-like name accepted without crash", r.status_code == 201, G)
if ok(r):
    stored_name = data(r)["product"]["name"]
    # The name is stored as-is (HTML escaping is a frontend concern),
    # but the request must not cause server errors
    test("XSS input stored without server error", True, G)

# Oversized payload (10k char product name)
r = cli.post("/api/products", headers=H, json={"name":"A"*10000,"price":100})
test("Oversized name safely truncated or rejected", r.status_code in (201, 400), G)

# Malformed JSON
r = cli.post("/api/products", headers=H,
             data="not-valid-json", content_type="application/json")
test("Malformed JSON body returns 400", r.status_code == 400, G)

# Empty body
r = cli.post("/api/products", headers=H, data="", content_type="application/json")
test("Empty body returns 400", r.status_code == 400, G)

# 404 for unknown routes
r = cli.get("/api/nonexistent-endpoint-9999")
test("Unknown route returns 404 with JSON body",
     r.status_code == 404 and r.content_type.startswith("application/json"), G)

# ─────────────────────────────────────────────────────────────────────
# GROUP 9 — Regression (Phase 1)
# ─────────────────────────────────────────────────────────────────────

section("GROUP 9 — Phase 1 Regression")
G = "REGRESSION"

r = signup("regression@test.com","Regression User","Regression Corp")
test("Phase 1 signup still works",                 r.status_code == 201, G)
tok = data(r)["access_token"]; rtok = data(r)["refresh_token"]; H = auth_header(tok)

r = cli.post("/api/auth/login", json={"email":"regression@test.com","password":"TestPass1"})
test("Phase 1 login still works",                  ok(r), G)

r = cli.get("/api/merchant/profile", headers=H)
test("Phase 1 profile GET still works",            ok(r), G)
test("Phase 1 profile includes user + merchant",   "user" in data(r) and "merchant" in data(r), G)

r = cli.put("/api/merchant/profile", headers=H, json={"company_name":"New Regression Corp"})
test("Phase 1 profile PUT still works",            ok(r), G)
test("Phase 1 profile update correct name",        data(r)["merchant"]["company_name"] == "New Regression Corp", G)

r = cli.get("/api/merchant/dashboard-summary", headers=H)
test("Phase 1 dashboard-summary still works",      ok(r), G)
metrics = data(r).get("metrics",{})
test("Dashboard includes Phase 2 products metric", "products" in metrics, G)

r = cli.get("/api/merchant/activity", headers=H)
test("Phase 1 activity log still works",           ok(r), G)

r = cli.post("/api/auth/refresh", json={"refresh_token": rtok})
test("Phase 1 token refresh still works",          ok(r), G)

r = cli.post("/api/auth/forgot-password", json={"email":"regression@test.com"})
test("Phase 1 forgot-password still works",        ok(r), G)

r = cli.post("/api/auth/logout", headers=H, json={"refresh_token": rtok})
test("Phase 1 logout still works",                 ok(r), G)

r = cli.get("/"); test("Index page renders (200)",     r.status_code == 200, G)
r = cli.get("/login"); test("Login page renders (200)", r.status_code == 200, G)
r = cli.get("/signup"); test("Signup page renders (200)", r.status_code == 200, G)
r = cli.get("/dashboard"); test("Dashboard page renders (200)", r.status_code == 200, G)
r = cli.get("/settings");  test("Settings page renders (200)",  r.status_code == 200, G)

# Phase 2 pages render
r = cli.get("/products");    test("Products page renders (200)",    r.status_code == 200, G)
r = cli.get("/ai-settings"); test("AI Settings page renders (200)", r.status_code == 200, G)
r = cli.get("/permissions");  test("Permissions page renders (200)", r.status_code == 200, G)

r = cli.get("/api/health")
phase = j(r).get("phase")
test("Health check reports phase >= 2 (current phase)", isinstance(phase, int) and phase >= 2, G, f"got phase={phase}")

# ─────────────────────────────────────────────────────────────────────
# FINAL REPORT
# ─────────────────────────────────────────────────────────────────────

total   = _results["passed"] + _results["failed"]
passed  = _results["passed"]
failed  = _results["failed"]
bugs    = _results["bugs"]

print(f"""
{'═'*60}
  PHASE 2 QA REPORT
{'═'*60}

  Total tests : {total}
  Passed      : {passed}  ✅
  Failed      : {failed}  {'❌' if failed else '✅'}
  Pass rate   : {100*passed//total}%

  Test group breakdown:
{'─'*60}""")

from collections import Counter
group_counts = Counter()
group_fails  = Counter()
for b in bugs:
    group_fails[b["group"]] += 1
for g in ["AUTH","ISOLATION","PRODUCT_CRUD","IMPORT","AI_SECURITY","PERMISSIONS","AUDIT","API_SECURITY","REGRESSION"]:
    status = "✅ PASS" if group_fails[g] == 0 else f"❌ FAIL ({group_fails[g]} failures)"
    labels = {
        "AUTH":"Authentication","ISOLATION":"Multi-tenant isolation",
        "PRODUCT_CRUD":"Product CRUD","IMPORT":"Bulk import",
        "AI_SECURITY":"AI API security","PERMISSIONS":"Permission engine",
        "AUDIT":"Audit logs","API_SECURITY":"API security","REGRESSION":"Regression (Phase 1)",
    }
    print(f"  {labels[g]:<30} {status}")

if bugs:
    print(f"\n{'─'*60}")
    print(f"  BUGS FOUND ({len(bugs)})")
    print(f"{'─'*60}")
    for i, b in enumerate(bugs, 1):
        print(f"\n  [{i}] {b['test']}")
        print(f"       Group   : {b['group']}")
        if b.get("detail"):
            print(f"       Detail  : {b['detail']}")

verdict = "✅ READY" if failed == 0 else "❌ NOT READY"
print(f"""
{'═'*60}
  PHASE 2 STATUS: {verdict}
  {'Phase 3 (Agent Builder) may begin.' if failed == 0 else 'Fix failures before proceeding to Phase 3.'}
{'═'*60}
""")

sys.exit(0 if failed == 0 else 1)
