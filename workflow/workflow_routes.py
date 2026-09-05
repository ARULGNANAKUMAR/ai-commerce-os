"""
workflow/workflow_routes.py  +  workflow/execution_routes.py
─────────────────────────────────────────────────────────────
Keeping both blueprints in one file for conciseness; registered
separately in app.py so URL prefixes remain clean.
"""

from flask import Blueprint, g, request

from security import jwt_required
from utils import ApiError, api_response
import models
from workflow.workflow_service import (
    create_workflow, get_workflows, get_workflow, update_workflow,
    publish_workflow, delete_workflow, clone_workflow, get_versions, serialize_workflow,
)
from workflow.execution_engine import execute_workflow, serialize_execution_list
from workflow.template_service import (
    serialize_template, clone_template_to_workflow, seed_templates,
)
from agent.architecture_engine import analyse_workflow
from agent.memory_service import get_insights

workflows_bp  = Blueprint("workflows",  __name__, url_prefix="/api/workflows")
executions_bp = Blueprint("executions", __name__, url_prefix="/api/executions")
templates_bp  = Blueprint("wf_templates", __name__, url_prefix="/api/templates")
agent_bp      = Blueprint("agent",      __name__, url_prefix="/api/agent")


def _mid() -> str:
    if g.merchant_id:
        return g.merchant_id
    m = models.find_merchant_by_user_id(g.user_id)
    if not m:
        raise ApiError("Merchant profile not found.", 403, code="NO_MERCHANT")
    return str(m["_id"])


# ═════════════════════════════════════════════════════════════════════
# WORKFLOWS
# ═════════════════════════════════════════════════════════════════════

@workflows_bp.route("", methods=["POST"])
@jwt_required
def wf_create():
    body = request.get_json(silent=True) or {}
    w    = create_workflow(_mid(), body, user_id=g.user_id)
    return api_response(data={"workflow": w}, message="Workflow created.", status=201)


@workflows_bp.route("", methods=["GET"])
@jwt_required
def wf_list():
    page  = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    return api_response(data=get_workflows(_mid(), page, limit))


@workflows_bp.route("/<workflow_id>", methods=["GET"])
@jwt_required
def wf_get(workflow_id):
    return api_response(data={"workflow": get_workflow(_mid(), workflow_id)})


@workflows_bp.route("/<workflow_id>", methods=["PUT"])
@jwt_required
def wf_update(workflow_id):
    body = request.get_json(silent=True) or {}
    w    = update_workflow(_mid(), workflow_id, body, user_id=g.user_id)
    return api_response(data={"workflow": w}, message="Workflow saved.")


@workflows_bp.route("/<workflow_id>", methods=["DELETE"])
@jwt_required
def wf_delete(workflow_id):
    delete_workflow(_mid(), workflow_id, user_id=g.user_id)
    return api_response(message="Workflow deleted.")


@workflows_bp.route("/<workflow_id>/publish", methods=["POST"])
@jwt_required
def wf_publish(workflow_id):
    w = publish_workflow(_mid(), workflow_id, user_id=g.user_id)
    return api_response(data={"workflow": w}, message="Workflow published.")


@workflows_bp.route("/<workflow_id>/clone", methods=["POST"])
@jwt_required
def wf_clone(workflow_id):
    body = request.get_json(silent=True) or {}
    w    = clone_workflow(_mid(), workflow_id, name=body.get("name"), user_id=g.user_id)
    return api_response(data={"workflow": w}, message="Workflow cloned.", status=201)


@workflows_bp.route("/<workflow_id>/versions", methods=["GET"])
@jwt_required
def wf_versions(workflow_id):
    return api_response(data={"versions": get_versions(_mid(), workflow_id)})


@workflows_bp.route("/<workflow_id>/execute", methods=["POST"])
@jwt_required
def wf_execute(workflow_id):
    body         = request.get_json(silent=True) or {}
    trigger_data = body.get("trigger_data", {})
    result       = execute_workflow(workflow_id, _mid(), trigger_data, user_id=g.user_id)
    status_code  = 200 if result["status"] in ("completed", "awaiting_approval") else 422
    return api_response(data={"execution": result},
                        message=f"Execution {result['status']}.",
                        status=status_code)


@workflows_bp.route("/<workflow_id>/analyze", methods=["POST"])
@jwt_required
def wf_analyze(workflow_id):
    w   = get_workflow(_mid(), workflow_id)
    analysis = analyse_workflow(_mid(), w["nodes"], w["edges"])
    return api_response(data={"analysis": analysis})


# ═════════════════════════════════════════════════════════════════════
# EXECUTIONS
# ═════════════════════════════════════════════════════════════════════

@executions_bp.route("", methods=["GET"])
@jwt_required
def ex_list():
    workflow_id = request.args.get("workflow_id")
    limit       = min(int(request.args.get("limit", 20)), 100)
    execs       = models.find_executions(_mid(), workflow_id=workflow_id, limit=limit)
    return api_response(data={"executions": [serialize_execution_list(e) for e in execs]})


@executions_bp.route("/<execution_id>", methods=["GET"])
@jwt_required
def ex_get(execution_id):
    ex = models.find_execution_by_id(_mid(), execution_id)
    if not ex:
        raise ApiError("Execution not found.", 404, code="NOT_FOUND")
    # Serialize fully
    doc = {
        "_id":          str(ex["_id"]),
        "workflow_id":  str(ex.get("workflow_id", "")),
        "status":       ex.get("status"),
        "trigger_data": ex.get("trigger_data", {}),
        "steps":        ex.get("steps", []),
        "result":       ex.get("result", {}),
        "error":        ex.get("error"),
        "duration_ms":  ex.get("duration_ms"),
        "started_at":   ex["started_at"].isoformat()   if ex.get("started_at")   else None,
        "completed_at": ex["completed_at"].isoformat()  if ex.get("completed_at")  else None,
    }
    return api_response(data={"execution": doc})


# ═════════════════════════════════════════════════════════════════════
# TEMPLATES
# ═════════════════════════════════════════════════════════════════════

@templates_bp.route("", methods=["GET"])
@jwt_required
def tmpl_list():
    category = request.args.get("category")
    tmpls    = models.find_templates(category=category)
    return api_response(data={"templates": [serialize_template(t) for t in tmpls]})


@templates_bp.route("/<slug>/use", methods=["POST"])
@jwt_required
def tmpl_use(slug):
    body    = request.get_json(silent=True) or {}
    new_id  = clone_template_to_workflow(slug, _mid(), name=body.get("name"))
    models.log_audit("template_used", user_id=g.user_id, merchant_id=_mid(),
                      details={"slug": slug, "workflow_id": new_id})
    w = serialize_workflow(models.find_workflow_by_id(_mid(), new_id))
    return api_response(data={"workflow": w}, message="Template cloned to new workflow.", status=201)


# ═════════════════════════════════════════════════════════════════════
# AGENT
# ═════════════════════════════════════════════════════════════════════

@agent_bp.route("/analyze", methods=["POST"])
@jwt_required
def ag_analyze():
    """Analyse an arbitrary node/edge definition (not necessarily saved)."""
    body  = request.get_json(silent=True) or {}
    nodes = body.get("nodes", [])
    edges = body.get("edges", [])
    return api_response(data={"analysis": analyse_workflow(_mid(), nodes, edges)})


@agent_bp.route("/memory", methods=["GET"])
@jwt_required
def ag_memory():
    return api_response(data={"insights": get_insights(_mid())})
