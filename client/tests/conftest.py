"""Fixtures shared by the client tests."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
import pytest

from gcai import GCAIClient

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "docs" / "examples"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def detection_payload(classes: list[str] | None = None, boxes: list[list[int]] | None = None) -> dict[str, Any]:
    classes = ["promoter", "ribosome-entry-site"] if classes is None else classes
    boxes = [[55, 164, 110, 234], [115, 186, 163, 230]] if boxes is None else boxes
    return {
        "status": "success",
        "result_image": base64.b64encode(PNG).decode(),
        "draw_boxes": boxes,
        "pred_classes": classes,
        "has_predictions": bool(classes),
    }


def zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def error_response(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"status_code": status, "error": message})


@pytest.fixture
def handler() -> "Recorder":
    return Recorder()


class Recorder:
    """A mock transport that records requests and answers from a routing table."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}

    def route(self, method: str, path: str, responder: Callable[[httpx.Request], httpx.Response]) -> None:
        self.routes[(method.upper(), path)] = responder

    def json(self, method: str, path: str, payload: Any, status: int = 200) -> None:
        self.route(method, path, lambda _request: httpx.Response(status, json=payload))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        responder = self.routes.get((request.method, request.url.path))
        if responder is None:
            return error_response(404, f"no route for {request.method} {request.url.path}")
        return responder(request)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> Any:
        return json.loads(self.last.content)


@pytest.fixture
def client(handler: Recorder) -> Iterator[GCAIClient]:
    with GCAIClient("http://gcai.test", transport=httpx.MockTransport(handler)) as instance:
        yield instance


@pytest.fixture(params=sorted(p.name for p in EXAMPLES.iterdir() if (p / "request.json").exists()))
def example_request(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Each committed example request, one per test run."""
    with (EXAMPLES / request.param / "request.json").open() as handle:
        payload: dict[str, Any] = json.load(handle)
    return payload
