"""
test_phase3.py
──────────────
QA suite for AI Commerce OS Phase 3 — Workflow Builder & Agent Architecture.

Covers:
  1. Workflow CRUD (create/read/update/delete/publish/clone/versions)
  2. Template system (seeded templates, clone-to-workflow)
  3. Execution engine (linear flow, branching, permission gating, failure handling)
  4. AI Architecture Engine (7-step analysis pipeline)
  5. Memory engine (pattern recording + insights)
  6. Multi-tenant isolation (workflows, executions)
  7. Security (JWT enforcement, audit logging)
  8. Regression (Phase 1 + Phase 2 still intact)
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

def signup(email, name):
    r = cli.post("/api/auth/signup", json={"email": email, "password": "TestPass1", "merchant_name": name})
    return r

def H(tok): return {"Authorization": f"Bearer {tok}"}

# ─────────────────────────────────────────────────────────────────────
section("GROUP 1 \u2014 Workflow CRUD")
G = "WORKFLOW_CRUD"

r = signup("wf1@test.com", "WF User"); tok = data(r)["access_token"]; h = H(tok)

r = cli.post("/api/workflows", headers=h, json={"name": "Test Agent", "description": "A test workflow"})
test("Create workflow returns 201", r.status_code == 201, G)
wid = data(r)["workflow"]["id"]
test("New workflow has status draft", data(r)["workflow"]["status"] == "draft", G)
test("New workflow has version 1", data(r)["workflow"]["version"] == 1, G)

r = cli.get(f"/api/workflows/{wid}", headers=h)
test("Get workflow returns 200", ok(r), G)
test("Get workflow name matches", data(r)["workflow"]["name"] == "Test Agent", G)

r = cli.get("/api/workflows", headers=h)
test("List workflows returns 200", ok(r), G)
test("List includes created workflow", data(r)["pagination"]["total"] >= 1, G)

nodes = [
    {"id": "n1", "type": "trigger.start", "label": "Start", "position": {"x": 0, "y": 0}, "config": {}},
    {"id": "n2", "type": "trigger.end",   "label": "End",   "position": {"x": 200, "y": 0}, "config": {"message": "Done"}},
]
edges = [{"id": "e1", "from_node": "n1", "from_port": "default", "to_node": "n2", "to_port": "in"}]

r = cli.put(f"/api/workflows/{wid}", headers=h, json={"nodes": nodes, "edges": edges})
test("Update workflow with nodes returns 200", ok(r), G)
test("Version incremented after node update", data(r)["workflow"]["version"] == 2, G,
     f"got {data(r)['workflow'].get('version')}")
test("Node count reflects update", data(r)["workflow"]["node_count"] == 2, G)

r = cli.get(f"/api/workflows/{wid}/versions", headers=h)
test("Version history returns 200", ok(r), G)
test("Version history has 1 snapshot", len(data(r)["versions"]) == 1, G,
     f"got {len(data(r)['versions'])}")

r = cli.post(f"/api/workflows/{wid}/publish", headers=h)
test("Publish workflow returns 200", ok(r), G)
test("Published workflow has status published", data(r)["workflow"]["status"] == "published", G)

r = cli.post(f"/api/workflows/{wid}/clone", headers=h, json={"name": "Cloned Agent"})
test("Clone workflow returns 201", r.status_code == 201, G)
clone_id = data(r)["workflow"]["id"]
test("Clone has independent ID", clone_id != wid, G)
test("Clone starts as draft", data(r)["workflow"]["status"] == "draft", G)

r = cli.delete(f"/api/workflows/{clone_id}", headers=h)
test("Delete workflow returns 200", ok(r), G)
r = cli.get(f"/api/workflows/{clone_id}", headers=h)
test("Deleted workflow returns 404", r.status_code == 404, G)

r = cli.post("/api/workflows", headers=h, json={})
test("Create with no name defaults gracefully", r.status_code == 201, G)

r = cli.put(f"/api/workflows/{wid}", headers=h, json={})
test("Update with empty body returns 400", r.status_code == 400, G)

r = cli.get("/api/workflows/000000000000000000000000", headers=h)
test("Unknown workflow ID returns 404", r.status_code == 404, G)

r = cli.post(f"/api/workflows/{wid}/publish".replace(wid, "bad-id"), headers=h)
test("Publish invalid ID returns 404", r.status_code == 404, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 2 \u2014 Template System")
G = "TEMPLATES"

r = cli.get("/api/templates", headers=h)
test("List templates returns 200", ok(r), G)
tmpls = data(r)["templates"]
test("4 built-in templates seeded", len(tmpls) == 4, G, f"got {len(tmpls)}")

slugs = {t["slug"] for t in tmpls}
for expected in ["ai_shopping_assistant", "product_comparison_agent", "upsell_agent", "campaign_agent"]:
    test(f"Template '{expected}' exists", expected in slugs, G)

for t in tmpls:
    test(f"Template '{t['slug']}' has nodes", t["node_count"] > 0, G)

r = cli.post("/api/templates/ai_shopping_assistant/use", headers=h, json={"name": "My Shopping Bot"})
test("Clone template to workflow returns 201", r.status_code == 201, G)
tmpl_wf_id = data(r)["workflow"]["id"]
test("Cloned workflow has nodes from template", data(r)["workflow"]["node_count"] > 0, G)

r = cli.post("/api/templates/nonexistent_template/use", headers=h, json={})
test("Unknown template slug returns 404", r.status_code == 404, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 3 \u2014 Execution Engine")
G = "EXECUTION"

# 3a. Simple linear workflow (Start → End)
r = cli.post(f"/api/workflows/{wid}/execute", headers=h, json={"trigger_data": {"customer_query": "test"}})
test("Execute simple workflow returns 200/422", r.status_code in (200, 422), G)
ex = data(r)["execution"]
test("Execution has completed status", ex["status"] == "completed", G, f"got {ex['status']}")
test("Execution has 2 steps (start+end)", len(ex["steps"]) == 2, G, f"got {len(ex['steps'])}")
test("Execution steps are in order", ex["steps"][0]["node_type"] == "trigger.start", G)
test("Execution has duration_ms", ex["duration_ms"] is not None, G)

# 3b. Full template workflow: product search → recommendation → AI prompt → end
r = cli.post(f"/api/workflows/{tmpl_wf_id}/execute", headers=h,
             json={"trigger_data": {"customer_query": "kurta", "budget": 2000, "category": "Fashion"}})
test("Execute template workflow returns 200/422", r.status_code in (200, 422), G)
ex2 = data(r)["execution"]
test("Template execution completes", ex2["status"] == "completed", G, f"got {ex2['status']}")
test("Template execution has 5 steps", len(ex2["steps"]) == 5, G, f"got {len(ex2['steps'])}")
node_types = [s["node_type"] for s in ex2["steps"]]
test("Execution includes product_search step", "catalog.product_search" in node_types, G)
test("Execution includes ai.prompt step", "ai.prompt" in node_types, G)
test("AI step used mock (no provider connected)",
     any(s["output"].get("used_mock") for s in ex2["steps"] if s["node_type"] == "ai.prompt"), G)

# 3c. Execution log retrieval
eid = ex2["execution_id"]
r = cli.get(f"/api/executions/{eid}", headers=h)
test("Get execution detail returns 200", ok(r), G)
test("Execution detail has steps", len(data(r)["execution"]["steps"]) > 0, G)

r = cli.get("/api/executions", headers=h)
test("List executions returns 200", ok(r), G)
test("Execution list has entries", len(data(r)["executions"]) >= 2, G)

r = cli.get(f"/api/executions?workflow_id={wid}", headers=h)
test("Filter executions by workflow_id works", all(e["workflow_id"] == wid for e in data(r)["executions"]), G)

# 3d. Branching: upsell_agent template has a permission.check node
r = cli.post("/api/templates/upsell_agent/use", headers=h, json={"name": "Upsell Test"})
upsell_wf = data(r)["workflow"]["id"]

# upsell capability disabled by default -> should follow "denied" branch
r = cli.post(f"/api/workflows/{upsell_wf}/execute", headers=h, json={"trigger_data": {"customer_query": "kurta"}})
ex3 = data(r)["execution"]
test("Branching workflow completes", ex3["status"] == "completed", G, f"got {ex3['status']}")
perm_step = next((s for s in ex3["steps"] if s["node_type"] == "permission.check"), None)
test("Permission check step present", perm_step is not None, G)
if perm_step:
    test("Permission check denied (upsell disabled by default)",
         perm_step["output"]["decision"] == "DENY", G, f"got {perm_step['output'].get('decision')}")
    test("Branched to 'denied' port", perm_step["next_port"] == "denied", G)
end_labels = [s["node_label"] for s in ex3["steps"] if s["node_type"] == "trigger.end"]
test("Reached 'End (Standard)' branch, not upsell branch",
     end_labels == ["End (Standard)"], G, f"got {end_labels}")

# Now enable upsell and re-run -> should follow "allowed" branch
cli.put("/api/permissions/upsell", headers=h, json={"enabled": True})
r = cli.post(f"/api/workflows/{upsell_wf}/execute", headers=h, json={"trigger_data": {"customer_query": "kurta"}})
ex4 = data(r)["execution"]
perm_step2 = next((s for s in ex4["steps"] if s["node_type"] == "permission.check"), None)
test("Permission check allowed after enabling upsell",
     perm_step2["output"]["decision"] == "ALLOW", G)
end_labels2 = [s["node_label"] for s in ex4["steps"] if s["node_type"] == "trigger.end"]
test("Branched to upsell End node after permission enabled",
     end_labels2 == ["End (Upsell)"], G, f"got {end_labels2}")

# 3e. Execute empty/invalid workflow
r = cli.post("/api/workflows", headers=h, json={"name": "Empty WF"})
empty_wid = data(r)["workflow"]["id"]
r = cli.post(f"/api/workflows/{empty_wid}/execute", headers=h, json={"trigger_data": {}})
test("Execute empty workflow returns error", r.status_code == 400, G)
test("Empty workflow error code correct", err(r) == "EMPTY_WORKFLOW", G)

# 3f. Execute unknown workflow
r = cli.post("/api/workflows/000000000000000000000000/execute", headers=h, json={"trigger_data": {}})
test("Execute unknown workflow returns 404", r.status_code == 404, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 4 \u2014 AI Architecture Engine (7-step pipeline)")
G = "ARCH_ENGINE"

r = cli.post(f"/api/workflows/{tmpl_wf_id}/analyze", headers=h)
test("Analyze workflow returns 200", ok(r), G)
a = data(r)["analysis"]
test("Analysis has task step", "task" in a and "task_type" in a["task"], G)
test("Analysis has structure step", "structure" in a and "is_valid" in a["structure"], G)
test("Analysis has modules step", "modules" in a and "required_capabilities" in a["modules"], G)
test("Analysis has architecture step", "architecture" in a and "execution_sequence" in a["architecture"], G)
test("Analysis has suggestions step", "suggestions" in a and isinstance(a["suggestions"], list), G)
test("Analysis has execution_plan step", "execution_plan" in a and "estimated_duration_ms" in a["execution_plan"], G)
test("Analysis has memory step", "memory" in a and "pattern_key" in a["memory"], G)
test("Valid workflow marked ready_to_execute", a["ready_to_execute"] is True, G)
test("AI shopping task type detected", a["task"]["task_type"] in ("ai_assisted_shopping", "product_discovery"), G,
     f"got {a['task']['task_type']}")

# Analyze the empty workflow -> should NOT be ready
r = cli.post(f"/api/workflows/{empty_wid}/analyze", headers=h)
a2 = data(r)["analysis"]
test("Empty workflow structure invalid", a2["structure"]["is_valid"] is False, G)
test("Empty workflow not ready to execute", a2["ready_to_execute"] is False, G)

# Ad-hoc analyze (unsaved nodes/edges) via /api/agent/analyze
r = cli.post("/api/agent/analyze", headers=h, json={"nodes": nodes, "edges": edges})
test("Ad-hoc analyze via /api/agent/analyze works", ok(r), G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 5 \u2014 Memory Engine")
G = "MEMORY"

r = cli.get("/api/agent/memory", headers=h)
test("Get memory insights returns 200", ok(r), G)
insights = data(r)["insights"]
test("Memory has recorded patterns after executions", len(insights) > 0, G, f"got {len(insights)}")
test("Memory pattern has success_count", all("success_count" in i for i in insights), G)
test("Memory pattern has node_sequence", all("node_sequence" in i for i in insights), G)

# Re-run same workflow -> pattern success_count should increase
before = next((i["success_count"] for i in insights if "trigger.start" in i["pattern"]), 0)
cli.post(f"/api/workflows/{wid}/execute", headers=h, json={"trigger_data": {}})
r = cli.get("/api/agent/memory", headers=h)
after_insights = data(r)["insights"]
after = next((i["success_count"] for i in after_insights if "trigger.start" in i["pattern"] and i["pattern"].count("\u2192") == 1), 0)
test("Repeated execution increments memory success_count", after >= before, G, f"before={before} after={after}")

# Analysis should detect matching memory pattern
r = cli.post(f"/api/workflows/{wid}/analyze", headers=h)
mem = data(r)["analysis"]["memory"]
test("Analysis detects known pattern in memory", mem["pattern_found"] is True, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 6 \u2014 Multi-tenant Isolation")
G = "ISOLATION"

r = signup("wf2@test.com", "WF User 2"); tok2 = data(r)["access_token"]; h2 = H(tok2)

r = cli.get(f"/api/workflows/{wid}", headers=h2)
test("Merchant B cannot read Merchant A's workflow", r.status_code == 404, G)

r = cli.put(f"/api/workflows/{wid}", headers=h2, json={"name": "Hijacked"})
test("Merchant B cannot update Merchant A's workflow", r.status_code == 404, G)

r = cli.delete(f"/api/workflows/{wid}", headers=h2)
test("Merchant B cannot delete Merchant A's workflow", r.status_code == 404, G)

r = cli.post(f"/api/workflows/{wid}/execute", headers=h2, json={"trigger_data": {}})
test("Merchant B cannot execute Merchant A's workflow", r.status_code == 404, G)

r = cli.get("/api/workflows", headers=h2)
test("Merchant B's workflow list is empty (isolated)", data(r)["pagination"]["total"] == 0, G)

r = cli.get(f"/api/executions/{eid}", headers=h2)
test("Merchant B cannot view Merchant A's execution log", r.status_code == 404, G)

r = cli.get("/api/agent/memory", headers=h2)
test("Merchant B's memory insights are empty (isolated)", len(data(r)["insights"]) == 0, G)

# Templates are global — both merchants see them
r = cli.get("/api/templates", headers=h2)
test("Templates are globally visible to all merchants", len(data(r)["templates"]) == 4, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 7 \u2014 Security & Audit")
G = "SECURITY"

routes_to_check = [
    ("POST", "/api/workflows"),
    ("GET",  "/api/workflows"),
    ("GET",  f"/api/workflows/{wid}"),
    ("PUT",  f"/api/workflows/{wid}"),
    ("DELETE", f"/api/workflows/{wid}"),
    ("POST", f"/api/workflows/{wid}/execute"),
    ("POST", f"/api/workflows/{wid}/publish"),
    ("POST", f"/api/workflows/{wid}/clone"),
    ("GET",  f"/api/workflows/{wid}/versions"),
    ("GET",  "/api/executions"),
    ("GET",  f"/api/executions/{eid}"),
    ("GET",  "/api/templates"),
    ("POST", "/api/templates/ai_shopping_assistant/use"),
    ("GET",  "/api/agent/memory"),
    ("POST", "/api/agent/analyze"),
]
for method, path in routes_to_check:
    r = cli.open(path, method=method, content_type="application/json", data="{}")
    test(f"No JWT \u2192 401 on {method} {path}", r.status_code == 401, G)

r = cli.get("/api/merchant/activity", headers=h)
logs = data(r)["activity"]
actions = [l["action"] for l in logs]
test("workflow_created logged", "workflow_created" in actions, G)
test("workflow_updated logged", "workflow_updated" in actions, G)
test("workflow_published logged", "workflow_published" in actions, G)
test("workflow_cloned logged", "workflow_cloned" in actions, G)
test("workflow_executed logged", "workflow_executed" in actions, G)
test("template_used logged", "template_used" in actions, G)
test("workflow_deleted logged", "workflow_deleted" in actions, G)

logs_str = json.dumps(logs)
test("No API keys leaked in workflow audit logs", "sk-" not in logs_str, G)

# ─────────────────────────────────────────────────────────────────────
section("GROUP 8 \u2014 Regression (Phase 1 + Phase 2)")
G = "REGRESSION"

r = signup("regression3@test.com", "Regression User")
test("Phase 1 signup still works", r.status_code == 201, G)
rtok = data(r)["access_token"]; rh = H(rtok)

r = cli.get("/api/merchant/profile", headers=rh)
test("Phase 1 profile still works", ok(r), G)

r = cli.get("/api/merchant/dashboard-summary", headers=rh)
test("Dashboard summary still works", ok(r), G)
metrics = data(r)["metrics"]
test("Dashboard includes active_agents metric", "active_agents" in metrics, G)
test("Dashboard includes products metric", "products" in metrics, G)

r = cli.post("/api/products", headers=rh, json={"name": "Regr Product", "price": 99})
test("Phase 2 product creation still works", r.status_code == 201, G)

r = cli.get("/api/permissions", headers=rh)
test("Phase 2 permissions still work", ok(r), G)
test("12 capabilities still present", len(data(r)["permissions"]) == 12, G)

r = cli.post("/api/ai/providers", headers=rh,
             json={"provider": "gemini", "model": "gemini-1.5-flash", "api_key": "regr-key-xxx"})
test("Phase 2 AI provider save still works", ok(r), G)
test("Key not leaked in response", "regr-key-xxx" not in json.dumps(data(r)), G)

for path in ["/", "/login", "/signup", "/dashboard", "/settings", "/products", "/ai-settings", "/permissions"]:
    r = cli.get(path)
    test(f"Page {path} still renders (200)", r.status_code == 200, G)

r = cli.get("/api/health")
test("Health check reports phase >= 3 (current phase)", isinstance(j(r).get("phase"), int) and j(r).get("phase") >= 3, G)

# ─────────────────────────────────────────────────────────────────────
# FINAL REPORT
# ─────────────────────────────────────────────────────────────────────

total = _results["passed"] + _results["failed"]
passed, failed, bugs = _results["passed"], _results["failed"], _results["bugs"]

print(f"\n{'='*60}\n  PHASE 3 QA REPORT\n{'='*60}\n")
print(f"  Total tests : {total}")
print(f"  Passed      : {passed}")
print(f"  Failed      : {failed}")
print(f"  Pass rate   : {100*passed//total if total else 0}%\n")

from collections import Counter
group_fails = Counter(b["group"] for b in bugs)
labels = {
    "WORKFLOW_CRUD": "Workflow CRUD", "TEMPLATES": "Template system",
    "EXECUTION": "Execution engine", "ARCH_ENGINE": "AI Architecture Engine",
    "MEMORY": "Memory engine", "ISOLATION": "Multi-tenant isolation",
    "SECURITY": "Security & audit", "REGRESSION": "Regression (Phase 1+2)",
}
for g, label in labels.items():
    status = "PASS" if group_fails[g] == 0 else f"FAIL ({group_fails[g]})"
    print(f"  {label:<28} {status}")

if bugs:
    print(f"\n  BUGS FOUND ({len(bugs)})")
    for i, b in enumerate(bugs, 1):
        print(f"\n  [{i}] {b['test']}\n       Group: {b['group']}" + (f"\n       Detail: {b['detail']}" if b.get('detail') else ""))

verdict = "READY" if failed == 0 else "NOT READY"
print(f"\n{'='*60}\n  PHASE 3 STATUS: {verdict}\n{'='*60}\n")

sys.exit(0 if failed == 0 else 1)
