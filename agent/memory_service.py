"""
agent/memory_service.py
────────────────────────
Records successful workflow execution patterns and surfaces insights.
This is the Phase 4 foundation — the architecture_memory from the
original product vision.  In Phase 4 the memory will drive automatic
workflow optimisation suggestions.
"""

import models


def record_execution_memory(merchant_id: str, workflow_id: str, execution_id: str,
                             node_sequence: list, pattern_key: str,
                             success: bool, duration_ms: int) -> None:
    """Persist one execution result into the memory store."""
    try:
        models.record_memory(merchant_id, pattern_key, success, duration_ms, node_sequence)
    except Exception:
        pass   # memory recording is best-effort — never crash the execution


def get_insights(merchant_id: str) -> list:
    """Return top successful workflow patterns for this merchant."""
    rows = models.find_memory_insights(merchant_id, limit=10)
    return [_serialize(r) for r in rows]


def _serialize(doc: dict) -> dict:
    return {
        "pattern":       doc.get("pattern_key", ""),
        "node_sequence": doc.get("node_sequence", []),
        "success_count": doc.get("success_count", 0),
        "failure_count": doc.get("failure_count", 0),
        "avg_duration_ms": doc.get("avg_duration_ms", 0),
        "last_used":     doc["last_used"].isoformat() if doc.get("last_used") else None,
    }
