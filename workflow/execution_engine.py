"""
workflow/execution_engine.py
─────────────────────────────
Executes a saved workflow definition node-by-node, passing a shared
context object forward, handling branching, and writing a full step
log to workflow_executions.

Phase 3: runs synchronously (test/demo mode).
Phase 4+: extract execute_workflow() into an async task queue.
"""

import time
from utils import utcnow
import models
from workflow.node_handlers import get_handler, HANDLER_REGISTRY
from agent.memory_service import record_execution_memory


# ─────────────────────────────────────────────────────────────────────
# Graph helpers
# ─────────────────────────────────────────────────────────────────────

def _build_graph(edges: list) -> dict:
    """adjacency: { (from_node_id, from_port) → to_node_id }"""
    graph = {}
    for e in edges:
        key = (e["from_node"], e.get("from_port", "default"))
        graph[key] = e["to_node"]
    return graph


def _find_start_node(nodes: list) -> dict | None:
    for n in nodes:
        if n.get("type") == "trigger.start":
            return n
    # fall back to first node if no explicit start
    return nodes[0] if nodes else None


def _node_by_id(nodes: list, node_id: str) -> dict | None:
    return next((n for n in nodes if n["id"] == node_id), None)


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────

def execute_workflow(workflow_id: str, merchant_id: str,
                     trigger_data: dict, user_id: str = None) -> dict:
    """
    Load the workflow, execute every reachable node, and return
    a serialised execution summary.

    Returns: { execution_id, status, steps, result, duration_ms }
    """
    from utils import ApiError

    workflow = models.find_workflow_by_id(merchant_id, workflow_id)
    if not workflow:
        raise ApiError("Workflow not found.", 404, code="NOT_FOUND")

    nodes = workflow.get("nodes", [])
    edges = workflow.get("edges", [])

    if not nodes:
        raise ApiError("Workflow has no nodes. Add at least a Start and End node.", 400,
                       code="EMPTY_WORKFLOW")

    # Create execution record
    execution_id = models.create_execution(workflow_id, merchant_id, trigger_data)

    graph    = _build_graph(edges)
    context  = {
        "workflow_id":   workflow_id,
        "execution_id":  execution_id,
        "merchant_id":   merchant_id,
        "trigger_data":  trigger_data,
        "variables":     dict(trigger_data),
        "step_outputs":  {},
    }

    steps         = []
    current_id    = _find_start_node(nodes)["id"] if _find_start_node(nodes) else None
    visited       = set()                    # cycle guard
    total_start   = time.time()
    final_status  = "completed"
    error_message = None

    while current_id and current_id not in visited:
        visited.add(current_id)
        node = _node_by_id(nodes, current_id)
        if not node:
            break

        node_type   = node.get("type", "")
        node_config = node.get("config", {})
        step_num    = len(steps) + 1
        step_start  = time.time()

        try:
            handler = get_handler(node_type)
            output, next_port = handler(node_config, context, merchant_id)
            context["step_outputs"][current_id] = output
            step_status = "completed"
        except Exception as exc:
            output      = {"error": str(exc)}
            next_port   = "default"
            step_status = "failed"
            final_status  = "failed"
            error_message = f"Node '{node.get('label', node_type)}' failed: {exc}"

        duration_ms = int((time.time() - step_start) * 1000)

        step = {
            "step":         step_num,
            "node_id":      current_id,
            "node_type":    node_type,
            "node_label":   node.get("label", node_type),
            "status":       step_status,
            "output":       output,
            "next_port":    next_port,
            "duration_ms":  duration_ms,
            "timestamp":    utcnow().isoformat(),
        }
        steps.append(step)

        # Stop on failure or human approval (workflow paused)
        if step_status == "failed":
            break
        if node_type == "human.approval":
            final_status = "awaiting_approval"
            break

        # Follow the edge for next_port
        current_id = graph.get((current_id, next_port)) or graph.get((current_id, "default"))

    total_ms = int((time.time() - total_start) * 1000)

    # Build final result from the last end-node output
    final_output = {}
    for step in reversed(steps):
        if step["node_type"] == "trigger.end" and step["status"] == "completed":
            final_output = step["output"]
            break
    if not final_output and steps:
        final_output = steps[-1].get("output", {})

    # Persist execution
    models.update_execution(execution_id, {
        "status":       final_status,
        "steps":        steps,
        "result":       final_output,
        "error":        error_message,
        "completed_at": utcnow(),
        "duration_ms":  total_ms,
    })

    models.log_audit("workflow_executed", user_id=user_id, merchant_id=merchant_id,
                      details={"workflow_id": workflow_id, "execution_id": execution_id,
                               "status": final_status, "steps": len(steps)})

    # Feed memory engine
    node_sequence = [s["node_type"] for s in steps]
    pattern_key   = "→".join(node_sequence)
    record_execution_memory(merchant_id, workflow_id, execution_id,
                             node_sequence, pattern_key,
                             success=(final_status == "completed"),
                             duration_ms=total_ms)

    return _serialize_execution({
        "_id":          execution_id,
        "workflow_id":  workflow_id,
        "status":       final_status,
        "trigger_data": trigger_data,
        "steps":        steps,
        "result":       final_output,
        "error":        error_message,
        "duration_ms":  total_ms,
        "started_at":   utcnow().isoformat(),
        "completed_at": utcnow().isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────
# Serialization
# ─────────────────────────────────────────────────────────────────────

def _serialize_execution(doc: dict) -> dict:
    return {
        "execution_id":  str(doc.get("_id", "")),
        "workflow_id":   str(doc.get("workflow_id", "")),
        "status":        doc.get("status"),
        "trigger_data":  doc.get("trigger_data", {}),
        "steps":         doc.get("steps", []),
        "result":        doc.get("result", {}),
        "error":         doc.get("error"),
        "duration_ms":   doc.get("duration_ms"),
        "started_at":    _iso(doc.get("started_at")),
        "completed_at":  _iso(doc.get("completed_at")),
    }


def serialize_execution_list(doc: dict) -> dict:
    return {
        "execution_id":  str(doc["_id"]),
        "workflow_id":   str(doc.get("workflow_id", "")),
        "status":        doc.get("status"),
        "step_count":    len(doc.get("steps", [])),
        "duration_ms":   doc.get("duration_ms"),
        "started_at":    _iso(doc.get("started_at")),
        "completed_at":  _iso(doc.get("completed_at")),
        "error":         doc.get("error"),
    }


def _iso(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    try:
        return val.isoformat()
    except Exception:
        return str(val)
