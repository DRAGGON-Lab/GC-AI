"""Application boundaries shared by development, tests and WSGI."""

import os

from flask import Flask, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from app.utils.custom_error import CustomError
from app.routes.file_routes import file_blueprint
from app.routes.component_routes import component_blueprint


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=int(os.getenv("GCAI_MAX_REQUEST_BYTES", 12 * 1024 * 1024)),
        MAX_IMAGE_BYTES=int(os.getenv("GCAI_MAX_IMAGE_BYTES", 10 * 1024 * 1024)),
        MAX_IMAGE_PIXELS=int(os.getenv("GCAI_MAX_IMAGE_PIXELS", 16_000_000)),
        MAX_IMAGE_DIMENSION=int(os.getenv("GCAI_MAX_IMAGE_DIMENSION", 8192)),
        INFERENCE_RETRY_AFTER=1,
        TRUSTED_ORIGINS=[
            o
            for o in os.getenv(
                "GCAI_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if o
        ],
    )
    if test_config:
        app.config.update(test_config)
    CORS(
        app,
        origins=app.config["TRUSTED_ORIGINS"],
        expose_headers=["X-GCAI-Structural-Handle", "Retry-After"],
        supports_credentials=True,
    )

    @app.before_request
    def enforce_browser_origin():
        origin = request.headers.get("Origin")
        if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
            if origin not in app.config["TRUSTED_ORIGINS"]:
                raise CustomError(
                    "Browser origin is not trusted", 403, code="untrusted_origin"
                )

    from app.routes.inference_routes import inference_blueprint
    from app.routes.healthcheck_routes import healthcheck_blueprint, liveness

    app.register_blueprint(inference_blueprint, url_prefix="/inference")
    app.register_blueprint(healthcheck_blueprint, url_prefix="/healthcheck")
    app.add_url_rule("/livez", view_func=liveness)
    app.register_blueprint(file_blueprint, url_prefix="/file")
    app.register_blueprint(component_blueprint, url_prefix="/component")

    def handle_general_exception(error):
        if isinstance(error, HTTPException):
            response = error.get_response()
            status = error.code
            message = error.description
            code = "invalid_request" if status < 500 else "internal_error"
        else:
            status = error.status_code if isinstance(error, CustomError) else 500
            response = app.response_class(status=status)
            message = (
                error.message
                if isinstance(error, CustomError)
                else "An unexpected error occurred."
            )
            code = error.code if isinstance(error, CustomError) else "internal_error"
        body = {
            "status_code": status,
            "error": message if status < 500 else "An unexpected error occurred.",
            "code": code,
        }
        # Internal validation findings can contain filesystem paths and dependency secrets.
        if isinstance(error, CustomError):
            response.headers.update(error.headers)
            if status < 500 and error.issues:
                body.update(error.details())
        if status >= 500:
            app.logger.error("Request failed (%s)", type(error).__name__)
        response.set_data(
            app.json.dumps(body)
            if hasattr(app, "json")
            else __import__("json").dumps(body)
        )
        response.content_type = "application/json"
        return response

    app.register_error_handler(Exception, handle_general_exception)
    return app
