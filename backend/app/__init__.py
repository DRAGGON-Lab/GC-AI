from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from app.utils.custom_error import CustomError
from app.routes.file_routes import file_blueprint
from app.routes.component_routes import component_blueprint
import sys
import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger(__name__)


def create_app(test_config=None):
    app = Flask(__name__)
    if test_config:
        app.config.update(test_config)
    CORS(app, origins="*", expose_headers=["file_path_structural"])

    if not app.config.get("TESTING"):
        from app.routes.inference_routes import inference_blueprint
        from app.routes.healthcheck_routes import healthcheck_blueprint

        app.register_blueprint(inference_blueprint, url_prefix="/inference")
        app.register_blueprint(healthcheck_blueprint, url_prefix="/healthcheck")
    app.register_blueprint(file_blueprint, url_prefix="/file")
    app.register_blueprint(component_blueprint, url_prefix="/component")

    # The factory may be called repeatedly by test and WSGI runners.
    if not any(getattr(h, "_gcai", False) for h in app.logger.handlers):
        file_handler = RotatingFileHandler(
            "gc-ai-backend.log", maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setLevel(logging.WARNING)
        file_handler._gcai = True
        app.logger.addHandler(file_handler)

    def handle_general_exception(e):
        """
        Global error handler to catch all exceptions and return a JSON response.
        """
        status_code = 500
        if isinstance(e, HTTPException):
            status_code = e.code
            message = e.description
        elif isinstance(e, CustomError):
            status_code = e.status_code
            message = e.message
        else:
            message = "An unexpected error occurred."

        response = {
            "status_code": status_code,
            "error": message if status_code < 500 else "An unexpected error occurred.",
            "code": (
                getattr(e, "code", None)
                if isinstance(e, CustomError)
                else ("invalid_request" if status_code < 500 else "internal_error")
            ),
        }
        if isinstance(e, CustomError):
            response.update(e.details())
        app.logger.error(
            f"Error: {message}, Status Code: {status_code}, Details: {str(e)}"
        )
        return jsonify(response), status_code

    app.register_error_handler(Exception, handle_general_exception)

    return app
