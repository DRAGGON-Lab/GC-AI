"""Exercise the public framework boundary and header preservation."""

import pytest
from flask import abort
from werkzeug.exceptions import Unauthorized
from app import create_app
from app.utils.custom_error import CustomError


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "TRUSTED_ORIGINS": ["https://gcai.example"]})

    @app.route("/failure")
    def failure():
        raise CustomError(
            "secret /private/checkpoint password", 500, issues=[{"message": "secret"}]
        )

    @app.route("/auth")
    def auth():
        from werkzeug.datastructures import WWWAuthenticate

        raise Unauthorized(
            www_authenticate=WWWAuthenticate("basic", {"realm": "GC-AI"})
        )

    return app


@pytest.mark.parametrize(
    "body,content_type",
    [("oops", "application/json"), ("[]", "application/json"), ("{}", "text/plain")],
)
def test_invalid_json_is_400(app, body, content_type):
    r = app.test_client().post("/file/create", data=body, content_type=content_type)
    assert r.status_code == 400
    assert {"status_code", "error", "code"} <= r.json.keys()


def test_method_header_survives(app):
    r = app.test_client().get("/file/create")
    assert r.status_code == 405 and "POST" in r.headers["Allow"]


def test_auth_header_survives(app):
    r = app.test_client().get("/auth")
    assert r.status_code == 401 and "Basic" in r.headers["WWW-Authenticate"]


def test_internal_details_do_not_escape(app):
    r = app.test_client().get("/failure")
    assert r.status_code == 500 and "issues" not in r.json
    assert b"secret" not in r.data and b"private" not in r.data


@pytest.mark.parametrize("route", ["/file/create", "/inference/"])
def test_unsafe_untrusted_origin_rejected_before_route(app, route):
    r = app.test_client().post(route, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json["code"] == "untrusted_origin"
    assert "Access-Control-Allow-Origin" not in r.headers


def test_preflight_explicit_origin(app):
    r = app.test_client().options(
        "/file/create",
        headers={
            "Origin": "https://gcai.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert r.headers["Access-Control-Allow-Origin"] == "https://gcai.example"
    assert "*" not in r.headers["Access-Control-Allow-Origin"]
