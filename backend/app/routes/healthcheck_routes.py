"""Readiness consumes dependency probes; liveness is dependency independent."""

from flask import Blueprint, jsonify

from app.config import get_db_connection, get_model
from app.utils.custom_error import CustomError

healthcheck_blueprint = Blueprint("healthcheck", __name__)


@healthcheck_blueprint.route("/", methods=["GET"])
def healthcheck():
    try:
        if get_model() is None:
            raise RuntimeError("Detector unavailable")
        connection = get_db_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise RuntimeError("Database probe returned an unexpected result")
            finally:
                cursor.close()
        finally:
            connection.close()
    except Exception:
        # Dependency diagnostics and credentials never belong in public errors.
        raise CustomError(
            "Application dependencies are unavailable", 503, code="not_ready"
        ) from None
    return jsonify({"status": "healthy", "message": "Application is running correctly"})


def liveness():
    return jsonify({"status": "dead"})
