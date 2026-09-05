"""
utils.py
────────
Cross-cutting helpers used by every layer of the app:
    - ApiError: a single exception type that carries an HTTP status +
      machine-readable code, so every failure path (auth, validation,
      db) produces the same JSON error shape.
    - api_response(): standard success envelope.
    - register_error_handlers(): wires ApiError + generic exceptions
      into consistent JSON responses instead of Flask's default HTML
      error pages.
    - get_client_ip(): best-effort client IP extraction for audit logs.
"""

from datetime import datetime, timezone

from flask import jsonify, request


class ApiError(Exception):
    """Raise this anywhere in the app to produce a clean JSON error
    response. Keeps error handling consistent instead of every route
    inventing its own failure shape."""

    def __init__(self, message: str, status_code: int = 400, code: str = "ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code

    def to_dict(self) -> dict:
        return {"success": False, "error": {"code": self.code, "message": self.message}}


def api_response(data=None, message: str = "", status: int = 200):
    """Standard success envelope used across all API endpoints:

        { "success": true, "message": "...", "data": {...} }
    """
    body = {"success": True, "message": message, "data": data}
    return jsonify(body), status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err: ApiError):
        response = jsonify(err.to_dict())
        response.status_code = err.status_code
        return response

    @app.errorhandler(404)
    def handle_404(_err):
        return jsonify({
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "The requested resource was not found."},
        }), 404

    @app.errorhandler(405)
    def handle_405(_err):
        return jsonify({
            "success": False,
            "error": {"code": "METHOD_NOT_ALLOWED", "message": "That method is not allowed on this route."},
        }), 405

    @app.errorhandler(500)
    def handle_500(_err):
        app.logger.exception("Unhandled server error")
        return jsonify({
            "success": False,
            "error": {"code": "INTERNAL_ERROR", "message": "Something went wrong on our end. Please try again."},
        }), 500


def get_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
