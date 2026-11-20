"""Storing designs in an SBOL DB registry."""

from __future__ import annotations

import httpx
import pytest

from gcai import storage
from gcai.errors import GCAIError

pytest.importorskip("sbol_db", reason="install gc-ai-client[db]")

IMPORT_REPORT = {
    "graph_id": "g-123",
    "object_count": 82,
    "triple_count": 546,
    "validation_status": "passed",
    "validation_issue_count": 0,
}


class Registry:
    """Records requests and answers from a routing table."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], httpx.Response] = {}

    def add(self, method: str, path: str, response: httpx.Response) -> None:
        self.routes[(method.upper(), path)] = response

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.routes.get((request.method, request.url.path))
        if response is None:
            return httpx.Response(404, json={"error": f"no route for {request.url.path}"})
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


@pytest.fixture
def registry() -> Registry:
    return Registry()


@pytest.fixture
def db(registry: Registry):
    with storage.client("http://registry.test", transport=httpx.MockTransport(registry)) as client:
        yield client


def test_publish_sends_rdf_xml_as_sbol3(db, registry: Registry) -> None:
    registry.add("POST", "/graphs", httpx.Response(200, json=IMPORT_REPORT))

    report = storage.publish(
        db,
        b"<rdf:RDF/>",
        document_iri="https://example.org/designs/yes-gate",
        name="YES gate",
        description="a circuit",
        namespace="https://example.org/designs/",
    )

    assert report.object_count == 82
    assert report.triple_count == 546
    assert report.validation_issue_count == 0

    request = registry.last
    assert request.headers["content-type"] == "application/rdf+xml"
    assert request.url.params["format"] == "rdfxml"
    assert request.url.params["version"] == "sbol3"
    assert request.url.params["document_iri"] == "https://example.org/designs/yes-gate"
    assert request.content == b"<rdf:RDF/>"


def test_publish_accepts_text_as_well_as_bytes(db, registry: Registry) -> None:
    registry.add("POST", "/graphs", httpx.Response(200, json=IMPORT_REPORT))
    storage.publish(db, "<rdf:RDF/>", document_iri="https://example.org/x")
    assert registry.last.content == b"<rdf:RDF/>"


def test_publish_passes_overwrite_through(db, registry: Registry) -> None:
    registry.add("POST", "/graphs", httpx.Response(200, json=IMPORT_REPORT))
    storage.publish(db, b"<rdf:RDF/>", document_iri="https://example.org/x", overwrite=1)
    assert registry.last.url.params["overwrite"] == "1"


def test_the_report_carries_the_registry_validation(db, registry: Registry) -> None:
    registry.add(
        "POST",
        "/graphs",
        httpx.Response(200, json={**IMPORT_REPORT, "validation_status": "failed", "validation_issue_count": 13}),
    )
    report = storage.publish(db, b"<rdf:RDF/>", document_iri="https://example.org/x")
    assert report.validation_status == "failed"
    assert report.validation_issue_count == 13


def test_a_rejected_publish_raises_the_registry_error(db, registry: Registry) -> None:
    from sbol_db import SbolDbError

    registry.add("POST", "/graphs", httpx.Response(400, json={"error": "document_iri already exists"}))
    with pytest.raises(SbolDbError):
        storage.publish(db, b"<rdf:RDF/>", document_iri="https://example.org/taken")


def test_fetch_asks_for_sbol3_rdf_xml(db, registry: Registry) -> None:
    registry.add("GET", "/objects/neighborhood.rdf", httpx.Response(200, text="<sbol3/>"))
    assert storage.fetch(db, "https://example.org/x") == "<sbol3/>"
    assert registry.last.url.params["version"] == "sbol3"
    assert registry.last.url.params["format"] == "rdfxml"


def test_to_sbol2_asks_the_registry_to_convert(db, registry: Registry) -> None:
    registry.add("GET", "/objects/neighborhood.rdf", httpx.Response(200, text="<sbol2/>"))
    assert storage.to_sbol2(db, "https://example.org/x") == "<sbol2/>"
    assert registry.last.url.params["version"] == "sbol2"


def test_client_explains_a_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def refuse(name: str, *args: object, **kwargs: object):
        if name == "sbol_db":
            raise ImportError("no sbol_db")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(GCAIError, match=r"gc-ai-client\[db\]"):
        storage.client("http://registry.test")
