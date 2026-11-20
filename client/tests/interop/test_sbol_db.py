"""Publishing to an SBOL DB registry, over a mock transport."""

from __future__ import annotations

import httpx
import pytest

from gcai.errors import GCAIError
from gcai.interop import PublishResult, SbolDb

pytest.importorskip("sbol_db", reason="install gc-ai-client[db]")

IMPORT_REPORT = {
    "graph_id": "g-123",
    "object_count": 15,
    "triple_count": 546,
    "validation_status": "valid",
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
def db(registry: Registry) -> SbolDb:
    return SbolDb("http://registry.test", transport=httpx.MockTransport(registry))


def test_publishing_sends_the_document_as_rdf_xml(db: SbolDb, registry: Registry) -> None:
    registry.add("POST", "/graphs", httpx.Response(200, json=IMPORT_REPORT))

    result = db.publish(
        b"<rdf:RDF/>",
        document_iri="https://example.org/designs/yes-gate",
        name="YES gate",
        description="a circuit",
        namespace="https://example.org/designs/",
    )

    assert isinstance(result, PublishResult)
    assert result.graph_id == "g-123"
    assert result.object_count == 15
    assert result.valid

    request = registry.last
    assert request.headers["content-type"] == "application/rdf+xml"
    assert request.url.params["format"] == "rdfxml"
    assert request.url.params["version"] == "sbol3", "the document is SBOL3, not converted first"
    assert request.url.params["document_iri"] == "https://example.org/designs/yes-gate"
    assert request.content == b"<rdf:RDF/>"


def test_a_publish_the_registry_rejects_becomes_a_gcai_error(db: SbolDb, registry: Registry) -> None:
    registry.add("POST", "/graphs", httpx.Response(400, json={"error": "document_iri already exists"}))
    with pytest.raises(GCAIError, match="could not publish"):
        db.publish(b"<rdf:RDF/>", document_iri="https://example.org/taken")


def test_a_document_the_registry_finds_invalid_is_not_valid(db: SbolDb, registry: Registry) -> None:
    registry.add(
        "POST",
        "/graphs",
        httpx.Response(200, json={**IMPORT_REPORT, "validation_status": "invalid", "validation_issue_count": 3}),
    )
    result = db.publish(b"<rdf:RDF/>", document_iri="https://example.org/x")
    assert not result.valid
    assert "3 issues" in str(result)


def test_overwrite_is_passed_through(db: SbolDb, registry: Registry) -> None:
    registry.add("POST", "/graphs", httpx.Response(200, json=IMPORT_REPORT))
    db.publish(b"<rdf:RDF/>", document_iri="https://example.org/x", overwrite=1)
    assert registry.last.url.params["overwrite"] == "1"


def test_fetching_sbol2_asks_the_registry_to_convert(db: SbolDb, registry: Registry) -> None:
    registry.add("GET", "/objects/neighborhood.rdf", httpx.Response(200, text="<sbol2/>"))

    data = db.to_sbol2("https://example.org/designs/yes-gate")

    assert data == b"<sbol2/>"
    assert registry.last.url.params["version"] == "sbol2"
    assert registry.last.url.params["format"] == "rdfxml"


def test_fetching_defaults_to_sbol3(db: SbolDb, registry: Registry) -> None:
    registry.add("GET", "/objects/neighborhood.rdf", httpx.Response(200, text="<sbol3/>"))
    db.fetch("https://example.org/x")
    assert registry.last.url.params["version"] == "sbol3"


def test_search_maps_roles_to_gcai_roles(db: SbolDb, registry: Registry) -> None:
    registry.add(
        "GET",
        "/search",
        httpx.Response(
            200,
            json={
                "objects": [
                    {
                        "iri": "https://example.org/BBa_R0010",
                        "sbol_class": "Component",
                        "display_id": "BBa_R0010",
                        "name": "BBa_R0010",
                        "description": "promoter",
                        "roles": ["https://identifiers.org/SO:0000167"],
                    }
                ],
                "total": 1,
            },
        ),
    )

    found = db.search("BBa_R0010")

    assert registry.last.url.params["q"] == "BBa_R0010"
    assert registry.last.url.params["object_type"] == "Component"
    assert len(found) == 1
    assert found[0].display_id == "BBa_R0010"
    assert found[0].role is not None and found[0].role.value == "Promoter"


def test_from_env_needs_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SBOL_DB_URL", raising=False)
    with pytest.raises(GCAIError, match="SBOL_DB_URL"):
        SbolDb.from_env()


def test_from_env_reads_the_url_and_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SBOL_DB_URL", "http://registry.test")
    monkeypatch.setenv("SBOL_DB_USER", "curator")
    monkeypatch.setenv("SBOL_DB_PASSWORD", "secret")
    with SbolDb.from_env() as db:
        assert db.url == "http://registry.test"
