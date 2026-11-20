"""Talking to the service, over a mock transport."""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import Recorder, detection_payload, error_response, zip_bytes

from gcai import GCAIClient
from gcai.constants import InteractionType, ParticipationRole, Role
from gcai.design import Design, Part
from gcai.errors import DesignValidationError, GCAIConnectionError, GCAIError, GCAIResponseError


def promoter_names(handler: Recorder, names: list[str] | None = None) -> None:
    handler.json("GET", "/component/names", names if names is not None else ["BBa_R0010"])


def test_health_is_true_when_a_part_lookup_works(client: GCAIClient, handler: Recorder) -> None:
    promoter_names(handler)
    assert client.health() is True
    assert handler.last.url.path == "/component/names"
    assert handler.last.url.params["role"] == "Promoter"


def test_health_is_false_when_the_service_fails(client: GCAIClient, handler: Recorder) -> None:
    handler.route("GET", "/component/names", lambda _r: error_response(500, "database down"))
    assert client.health() is False


def test_health_raises_when_the_service_cannot_be_reached() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with GCAIClient("http://gcai.test", transport=httpx.MockTransport(refuse)) as client:
        with pytest.raises(GCAIConnectionError, match="cannot reach"):
            client.health()


def test_detect_posts_the_image_as_multipart(client: GCAIClient, handler: Recorder, tmp_path) -> None:
    handler.json("POST", "/inference/", detection_payload())
    image = tmp_path / "circuit.png"
    image.write_bytes(b"not really a png")

    detection = client.detect(image)

    assert len(detection.glyphs) == 2
    body = handler.last.content
    assert b'name="image"' in body
    assert b"circuit.png" in body
    assert b"not really a png" in body


def test_detect_accepts_raw_bytes(client: GCAIClient, handler: Recorder) -> None:
    handler.json("POST", "/inference/", detection_payload())
    client.detect(b"bytes", filename="given.png")
    assert b"given.png" in handler.last.content


def test_part_names_and_details(client: GCAIClient, handler: Recorder) -> None:
    promoter_names(handler, ["BBa_R0010", "BBa_J23100"])
    handler.json(
        "GET",
        "/component/details",
        {
            "identifier": "BBa_R0010",
            "name": "BBa_R0010",
            "description": "promoter",
            "role": "Promoter",
            "sequence": "caatacg",
            "sequence_length": 7,
        },
    )
    assert client.part_names(Role.PROMOTER) == ["BBa_R0010", "BBa_J23100"]
    details = client.part_details("BBa_R0010", Role.PROMOTER)
    assert details.sequence == "caatacg"
    assert handler.last.url.params["component_name"] == "BBa_R0010"


def test_participations(client: GCAIClient, handler: Recorder) -> None:
    handler.json("GET", "/component/interactions", ["Inhibitor", "Inhibited"])
    assert client.participations(InteractionType.INHIBITION) == [
        ParticipationRole.INHIBITOR,
        ParticipationRole.INHIBITED,
    ]
    assert handler.last.url.params["interaction_type"] == "Inhibition"


def test_fill_parts_reads_registry_parts_only(client: GCAIClient, handler: Recorder) -> None:
    handler.json(
        "GET",
        "/component/details",
        {
            "name": "BBa_R0010",
            "description": "promoter",
            "role": "Promoter",
            "sequence": "CAATACG",
            "sequence_length": 7,
        },
    )
    design = Design(name="CIRCUIT", namespace="https://example.org/")
    registry = Part(name="BBa_R0010", role=Role.PROMOTER)
    mine = Part(name="MINE", role=Role.CDS, new=True, sequence="atgc", description="kept")
    design.parts.extend([registry, mine])

    client.fill_parts(design)

    assert registry.sequence == "caatacg"
    assert registry.description == "promoter"
    assert mine.description == "kept", "a part marked new is left alone"
    assert len(handler.requests) == 1


def create_route(handler: Recorder, *, header: bool = True) -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        headers = {"file_path_structural": "/app/files/structural.xml"} if header else {}
        return httpx.Response(200, content=b"<rdf:RDF/>", headers=headers)

    handler.route("POST", "/file/create", respond)


def test_create_returns_the_document_and_the_structural_path(client: GCAIClient, handler: Recorder) -> None:
    create_route(handler)
    design = Design(name="CIRCUIT", namespace="https://example.org/")
    design.parts.append(Part(name="BBa_R0010", role=Role.PROMOTER))

    result = client.create(design)

    assert result.sbol3 == b"<rdf:RDF/>"
    assert result.structural_path == "/app/files/structural.xml"
    assert json.loads(handler.last.content)["components"][0]["name"] == "CIRCUIT"


def test_create_without_the_header_is_an_error(client: GCAIClient, handler: Recorder) -> None:
    create_route(handler, header=False)
    design = Design(name="CIRCUIT", namespace="https://example.org/")
    design.parts.append(Part(name="BBa_R0010", role=Role.PROMOTER))
    with pytest.raises(GCAIError, match="file_path_structural"):
        client.create(design)


def test_create_sends_a_mapping_unchanged(client: GCAIClient, handler: Recorder) -> None:
    create_route(handler)
    payload = {"namespace": "x", "components": [{"name": "AS_IS"}], "expressions": [], "interactions": [], "eds": []}
    client.create(payload)
    assert json.loads(handler.last.content) == payload


def test_create_refuses_an_invalid_design(client: GCAIClient, handler: Recorder) -> None:
    create_route(handler)
    design = Design(name="CIRCUIT")  # no namespace, no parts
    with pytest.raises(DesignValidationError) as caught:
        client.create(design)
    assert any(issue.path == "namespace" for issue in caught.value.issues)
    assert handler.requests == []


def test_create_can_skip_validation(client: GCAIClient, handler: Recorder) -> None:
    create_route(handler)
    design = Design(name="CIRCUIT")
    design.parts.append(Part(name="BBa_R0010", role=Role.PROMOTER))
    client.create(design, validate=False)
    assert handler.requests


def test_convert_unpacks_the_archive(client: GCAIClient, handler: Recorder) -> None:
    archive = zip_bytes({"design_genbank.gb": b"LOCUS", "design_fasta.fasta": b">seq"})
    handler.route("POST", "/file/convert", lambda _r: httpx.Response(200, content=archive))

    out = client.convert("/app/files/structural.xml")

    assert out == {"genbank": b"LOCUS", "fasta": b">seq"}
    assert json.loads(handler.last.content) == {
        "file_path": "/app/files/structural.xml",
        "genbank": True,
        "fasta": True,
    }


def test_convert_with_one_format(client: GCAIClient, handler: Recorder) -> None:
    handler.route("POST", "/file/convert", lambda _r: httpx.Response(200, content=zip_bytes({"d_fasta.fasta": b">s"})))
    assert client.convert("/p", genbank=False) == {"fasta": b">s"}


def test_build_creates_then_converts(client: GCAIClient, handler: Recorder, tmp_path) -> None:
    create_route(handler)
    handler.route(
        "POST",
        "/file/convert",
        lambda _r: httpx.Response(200, content=zip_bytes({"d_genbank.gb": b"LOCUS", "d_fasta.fasta": b">seq"})),
    )
    design = Design(name="CIRCUIT", namespace="https://example.org/")
    design.parts.append(Part(name="BBa_R0010", role=Role.PROMOTER))

    result = client.build(design)

    assert result.sbol3 == b"<rdf:RDF/>"
    assert result.genbank == b"LOCUS"
    written = result.write(tmp_path, "circuit")
    assert sorted(p.name for p in written) == ["circuit.fasta", "circuit.gb", "circuit.xml"]


def test_build_skips_conversion_when_no_format_is_wanted(client: GCAIClient, handler: Recorder) -> None:
    create_route(handler)
    design = Design(name="CIRCUIT", namespace="https://example.org/")
    design.parts.append(Part(name="BBa_R0010", role=Role.PROMOTER))
    result = client.build(design, genbank=False, fasta=False)
    assert result.genbank is None and result.fasta is None
    assert [r.url.path for r in handler.requests] == ["/file/create"]


def test_the_error_envelope_becomes_a_response_error(client: GCAIClient, handler: Recorder) -> None:
    handler.route("GET", "/component/details", lambda _r: error_response(404, "Component not found"))
    with pytest.raises(GCAIResponseError) as caught:
        client.part_details("NOPE")
    assert caught.value.status_code == 404
    assert caught.value.message == "Component not found"


def test_a_response_that_is_not_json_still_raises(client: GCAIClient, handler: Recorder) -> None:
    handler.route("GET", "/component/names", lambda _r: httpx.Response(502, text="<html>gateway</html>"))
    with pytest.raises(GCAIResponseError) as caught:
        client.part_names(Role.PROMOTER)
    assert caught.value.status_code == 502
    assert "gateway" in caught.value.message


def test_requests_identify_the_client(client: GCAIClient, handler: Recorder) -> None:
    promoter_names(handler)
    client.part_names(Role.PROMOTER)
    assert handler.last.headers["user-agent"].startswith("gcai-client/")
