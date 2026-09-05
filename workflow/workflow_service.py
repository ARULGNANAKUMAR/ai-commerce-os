"""
workflow/workflow_service.py
─────────────────────────────
Business logic for workflow CRUD. Routes never touch models directly.
"""

from security import sanitize_string
from utils import ApiError, utcnow
import models


ALLOWED_STATUSES = {"draft", "published", "archived"}


def create_workflow(merchant_id: str, data: dict, user_id: str = None) -> dict:
    name = sanitize_string(data.get("name") or "Untitled Workflow", 300)
    wid  = models.create_workflow(merchant_id, {
        "name":        name,
        "description": sanitize_string(data.get("description", ""), 1000),
        "nodes":       data.get("nodes", []),
        "edges":       data.get("edges", []),
        "tags":        [sanitize_string(t, 100) for t in (data.get("tags") or [])],
        "template_id": data.get("template_id"),
    })
    models.log_audit("workflow_created", user_id=user_id, merchant_id=merchant_id,
                      details={"workflow_id": wid, "name": name})
    return serialize_workflow(models.find_workflow_by_id(merchant_id, wid))


def get_workflows(merchant_id: str, page: int = 1, limit: int = 20) -> dict:
    limit = min(limit, 100)
    skip  = (page - 1) * limit
    total = models.count_workflows(merchant_id)
    rows  = models.find_workflows(merchant_id, skip=skip, limit=limit)
    return {
        "workflows":  [serialize_workflow(w) for w in rows],
        "pagination": {"total": total, "page": page, "limit": limit,
                       "pages": max(1, (total + limit - 1) // limit)},
    }


def get_workflow(merchant_id: str, workflow_id: str) -> dict:
    w = models.find_workflow_by_id(merchant_id, workflow_id)
    if not w:
        raise ApiError("Workflow not found.", 404, code="NOT_FOUND")
    return serialize_workflow(w)


def update_workflow(merchant_id: str, workflow_id: str, data: dict,
                     user_id: str = None) -> dict:
    w = models.find_workflow_by_id(merchant_id, workflow_id)
    if not w:
        raise ApiError("Workflow not found.", 404, code="NOT_FOUND")

    updates = {}
    if "name"        in data: updates["name"]        = sanitize_string(data["name"], 300)
    if "description" in data: updates["description"] = sanitize_string(data["description"], 1000)
    if "nodes"       in data: updates["nodes"]       = data["nodes"]
    if "edges"       in data: updates["edges"]       = data["edges"]
    if "tags"        in data: updates["tags"]        = data["tags"]

    if not updates:
        raise ApiError("Nothing to update.", 400, code="NO_UPDATES")

    # Auto-increment version and save a snapshot whenever nodes/edges change
    if "nodes" in updates or "edges" in updates:
        new_version = int(w.get("version", 1)) + 1
        updates["version"] = new_version
        models.save_workflow_version(
            workflow_id, merchant_id, new_version,
            updates.get("nodes", w["nodes"]),
            updates.get("edges", w["edges"]),
            updates.get("name",  w["name"]),
        )

    models.update_workflow(merchant_id, workflow_id, updates)
    models.log_audit("workflow_updated", user_id=user_id, merchant_id=merchant_id,
                      details={"workflow_id": workflow_id, "fields": list(updates.keys())})
    return serialize_workflow(models.find_workflow_by_id(merchant_id, workflow_id))


def publish_workflow(merchant_id: str, workflow_id: str, user_id: str = None) -> dict:
    w = models.find_workflow_by_id(merchant_id, workflow_id)
    if not w:
        raise ApiError("Workflow not found.", 404, code="NOT_FOUND")
    if not w.get("nodes"):
        raise ApiError("Cannot publish an empty workflow.", 400, code="EMPTY_WORKFLOW")

    models.update_workflow(merchant_id, workflow_id,
                            {"status": "published", "published_at": utcnow()})
    models.log_audit("workflow_published", user_id=user_id, merchant_id=merchant_id,
                      details={"workflow_id": workflow_id})
    return serialize_workflow(models.find_workflow_by_id(merchant_id, workflow_id))


def delete_workflow(merchant_id: str, workflow_id: str, user_id: str = None) -> None:
    w = models.find_workflow_by_id(merchant_id, workflow_id)
    if not w:
        raise ApiError("Workflow not found.", 404, code="NOT_FOUND")
    models.soft_delete_workflow(merchant_id, workflow_id)
    models.log_audit("workflow_deleted", user_id=user_id, merchant_id=merchant_id,
                      details={"workflow_id": workflow_id})


def clone_workflow(merchant_id: str, workflow_id: str,
                    name: str = None, user_id: str = None) -> dict:
    w = models.find_workflow_by_id(merchant_id, workflow_id)
    if not w:
        raise ApiError("Workflow not found.", 404, code="NOT_FOUND")
    new_name = sanitize_string(name or f"Copy of {w['name']}", 300)
    new_id   = models.create_workflow(merchant_id, {
        "name":        new_name,
        "description": w.get("description", ""),
        "nodes":       w.get("nodes", []),
        "edges":       w.get("edges", []),
        "tags":        w.get("tags", []),
        "template_id": w.get("template_id"),
    })
    models.log_audit("workflow_cloned", user_id=user_id, merchant_id=merchant_id,
                      details={"source_id": workflow_id, "new_id": new_id})
    return serialize_workflow(models.find_workflow_by_id(merchant_id, new_id))


def get_versions(merchant_id: str, workflow_id: str) -> list:
    w = models.find_workflow_by_id(merchant_id, workflow_id)
    if not w:
        raise ApiError("Workflow not found.", 404, code="NOT_FOUND")
    versions = models.find_workflow_versions(workflow_id, merchant_id)
    return [_serialize_version(v) for v in versions]


def serialize_workflow(w: dict) -> dict:
    if not w:
        return {}
    return {
        "id":          str(w["_id"]),
        "name":        w.get("name", ""),
        "description": w.get("description", ""),
        "status":      w.get("status", "draft"),
        "version":     w.get("version", 1),
        "nodes":       w.get("nodes", []),
        "edges":       w.get("edges", []),
        "tags":        w.get("tags", []),
        "template_id": w.get("template_id"),
        "node_count":  len(w.get("nodes", [])),
        "edge_count":  len(w.get("edges", [])),
        "created_at":  w["created_at"].isoformat()  if w.get("created_at")  else None,
        "updated_at":  w["updated_at"].isoformat()  if w.get("updated_at")  else None,
        "published_at":w["published_at"].isoformat() if w.get("published_at") else None,
    }


def _serialize_version(v: dict) -> dict:
    return {
        "id":         str(v["_id"]),
        "version":    v.get("version"),
        "name":       v.get("name"),
        "node_count": len(v.get("nodes", [])),
        "saved_at":   v["saved_at"].isoformat() if v.get("saved_at") else None,
    }
