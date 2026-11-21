"""The server's one tool."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from tests.helpers import Recorder, detection_payload, error_response, zip_bytes

pytestmark = pytest.mark.anyio

NAMESPACE = "https://example.org/designs/"


def detects(handler: Recorder, classes: list[str] | None = None, boxes: list[list[int]] | None = None) -> None:
    handler.json("POST", "/inference/", detection_payload(classes, boxes))


def builds(handler: Recorder) -> None:
    handler.route(
        "POST",
        "/file/create",
        lambda _r: httpx.Response(200, content=b"<rdf:RDF/>", headers={"file_path_structural": "/p"}),
    )

    def convert(request: httpx.Request) -> httpx.Response:
        # The service returns only the formats that were asked for.
        wanted = json.loads(request.content)
        members = {}
        if wanted.get("genbank"):
            members["d_genbank.gb"] = b"LOCUS"
        if wanted.get("fasta"):
            members["d_fasta.fasta"] = b">seq"
        return httpx.Response(200, content=zip_bytes(members))

    handler.route("POST", "/file/convert", convert)


async def call(client, **arguments):
    return await client.call_tool("design_from_image", {"name": "CIRCUIT", "namespace": NAMESPACE, **arguments})


async def test_the_server_offers_one_tool(client) -> None:
    tools = (await client.list_tools()).tools
    assert [tool.name for tool in tools] == ["design_from_image"]
    tool = tools[0]
    assert tool.description
    assert getattr(tool, "output_schema", None) or getattr(tool, "outputSchema", None)
    assert tool.annotations is not None and not tool.annotations.open_world_hint


async def test_an_image_alone_builds_a_document(client, handler: Recorder, image: Path) -> None:
    """A diagram says the roles and the order, and that is what comes back."""
    detects(handler)
    builds(handler)
    result = await call(client, image_path=str(image))

    data = result.structured_content
    assert data["built"] is True
    assert data["sbol3"] == "<rdf:RDF/>"
    assert data["parts"] == ["promoter_1", "rbs_1"], "parts are named after their roles"
    assert data["named_from_registry"] == []
    assert [(g["glyph_class"], g["role"]) for g in data["detected"]] == [
        ("promoter", "Promoter"),
        ("ribosome-entry-site", "RBS"),
    ]
    assert [type(block).__name__ for block in result.content] == ["ImageContent", "TextContent"]


async def test_unnamed_parts_are_sent_without_a_sequence(client, handler: Recorder, image: Path) -> None:
    detects(handler)
    builds(handler)
    await call(client, image_path=str(image))

    sent = next(json.loads(request.content) for request in handler.requests if request.url.path == "/file/create")
    parts = sent["components"][1:]
    assert [part["name"] for part in parts] == ["promoter_1", "rbs_1"]
    assert all(part["new"] is True for part in parts)
    assert all(part["sequence"] == "" for part in parts)


async def test_the_result_says_what_the_document_leaves_out(client, handler: Recorder, image: Path) -> None:
    detects(handler)
    builds(handler)
    data = (await call(client, image_path=str(image))).structured_content
    assert any("carry no sequence" in note for note in data["notes"])


async def test_repeated_roles_are_numbered(client, handler: Recorder, image: Path) -> None:
    detects(handler, ["promoter", "promoter", "cds"], [[0, 0, 9, 9], [20, 0, 29, 9], [40, 0, 49, 9]])
    builds(handler)
    data = (await call(client, image_path=str(image))).structured_content
    assert data["parts"] == ["promoter_1", "promoter_2", "cds_1"]


async def test_glyphs_come_back_left_to_right(client, handler: Recorder, image: Path) -> None:
    detects(handler, ["terminator", "promoter"], [[300, 0, 350, 50], [10, 0, 60, 50]])
    builds(handler)
    data = (await call(client, image_path=str(image))).structured_content
    assert [glyph["glyph_class"] for glyph in data["detected"]] == ["promoter", "terminator"]
    assert data["parts"] == ["promoter_1", "terminator_1"]


async def test_an_image_can_arrive_as_base64(client, handler: Recorder) -> None:
    detects(handler)
    builds(handler)
    data = (await call(client, image_base64=base64.b64encode(b"pretend this is a png").decode())).structured_content
    assert data["built"] is True
    assert len(data["detected"]) == 2
    sent = next(r for r in handler.requests if r.url.path == "/inference/")
    assert b"pretend this is a png" in sent.content


async def test_an_empty_name_falls_back_to_the_role(client, handler: Recorder, image: Path) -> None:
    """Name the parts you know and leave the rest to their roles."""
    detects(handler)
    builds(handler)
    data = (await call(client, image_path=str(image), part_names=["BBa_R0010", ""])).structured_content
    assert data["parts"] == ["BBa_R0010", "rbs_1"]
    assert data["named_from_registry"] == ["BBa_R0010"]


async def test_an_image_with_nothing_in_it_says_so(client, handler: Recorder, image: Path) -> None:
    detects(handler, [], [])
    data = (await call(client, image_path=str(image))).structured_content
    assert data["built"] is False
    assert "no glyphs" in data["problems"][0]


async def test_exactly_one_image_argument_is_required(client, handler: Recorder, image: Path) -> None:
    both = await call(client, image_path=str(image), image_base64="eHg=")
    assert both.is_error and "exactly one" in both.content[0].text

    neither = await call(client)
    assert neither.is_error and "exactly one" in neither.content[0].text


async def test_base64_that_is_not_base64_is_refused(client) -> None:
    result = await call(client, image_base64="not base64 at all!")
    assert result.is_error and "not valid base64" in result.content[0].text


async def test_a_path_outside_the_allowed_roots_is_refused(client, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere.png"
    outside.write_bytes(b"png")
    result = await call(client, image_path=str(outside))
    assert result.is_error and "outside the directories" in result.content[0].text


async def test_names_have_to_match_the_parts_found(client, handler: Recorder, image: Path) -> None:
    detects(handler)
    data = (await call(client, image_path=str(image), part_names=["BBa_R0010"])).structured_content
    assert data["built"] is False
    assert "1 names given for 2 detected parts" in data["problems"][0]


async def test_names_build_the_documents(client, handler: Recorder, image: Path) -> None:
    detects(handler)
    builds(handler)
    data = (await call(client, image_path=str(image), part_names=["BBa_R0010", "BBa_B0034"])).structured_content

    assert data["built"] is True
    assert data["parts"] == ["BBa_R0010", "BBa_B0034"]
    assert data["sbol3"] == "<rdf:RDF/>"
    assert data["written"] == []


async def test_the_other_formats_are_off_unless_asked_for(client, handler: Recorder, image: Path) -> None:
    detects(handler)
    builds(handler)
    data = (await call(client, image_path=str(image), part_names=["BBa_R0010", "BBa_B0034"])).structured_content
    assert data["genbank"] is None and data["fasta"] is None

    data = (
        await call(client, image_path=str(image), part_names=["BBa_R0010", "BBa_B0034"], genbank=True, fasta=True)
    ).structured_content
    assert data["genbank"] == "LOCUS" and data["fasta"] == ">seq"


async def test_the_other_formats_need_bases(client, handler: Recorder, image: Path) -> None:
    """Parts named after their role have none, and a zero-length range will not convert."""
    detects(handler)
    builds(handler)
    data = (await call(client, image_path=str(image), genbank=True, fasta=True)).structured_content

    assert data["built"] is True, "the SBOL3 is still produced"
    assert data["genbank"] is None and data["fasta"] is None
    assert any("GenBank and FASTA were not produced" in note for note in data["notes"])
    assert not any(request.url.path == "/file/convert" for request in handler.requests)


async def test_output_dir_writes_the_files_instead(client, handler: Recorder, image: Path, workdir: Path) -> None:
    detects(handler)
    builds(handler)
    out = workdir / "out"
    data = (
        await call(
            client,
            image_path=str(image),
            part_names=["BBa_R0010", "BBa_B0034"],
            output_dir=str(out),
            fasta=True,
        )
    ).structured_content

    assert data["sbol3"] is None, "the document should not also come back in the result"
    assert sorted(Path(p).name for p in data["written"]) == ["CIRCUIT.fasta", "CIRCUIT.xml"]
    assert (out / "CIRCUIT.xml").read_bytes() == b"<rdf:RDF/>"


async def test_an_output_dir_outside_the_allowed_roots_is_refused(
    client, handler: Recorder, image: Path, tmp_path: Path
) -> None:
    detects(handler)
    builds(handler)
    result = await call(
        client,
        image_path=str(image),
        part_names=["BBa_R0010", "BBa_B0034"],
        output_dir=str(tmp_path / "elsewhere"),
    )
    assert result.is_error and "outside the directories" in result.content[0].text


async def test_a_design_that_cannot_be_valid_is_reported_not_sent(client, handler: Recorder, image: Path) -> None:
    detects(handler)
    builds(handler)
    data = (await call(client, image_path=str(image), part_names=["not a displayId", "BBa_B0034"])).structured_content
    assert data["built"] is False
    assert any("displayId" in problem for problem in data["problems"])
    assert not any(request.url.path == "/file/create" for request in handler.requests)


async def test_a_service_failure_reaches_the_caller(client, handler: Recorder, image: Path) -> None:
    detects(handler)
    handler.route("POST", "/file/create", lambda _r: error_response(500, "No component data found"))
    result = await call(client, image_path=str(image), part_names=["BBa_NOPE", "BBa_B0034"])
    assert result.is_error
    assert "No component data found" in result.content[0].text


async def test_an_unreachable_service_says_so(workdir: Path, image: Path) -> None:
    from mcp import Client

    from gcai import GCAIClient
    from gcai.mcp.server import build_server

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def factory() -> GCAIClient:
        return GCAIClient("http://gcai.test", transport=httpx.MockTransport(refuse))

    server = build_server(allowed_roots=(workdir,), service_factory=factory)
    async with Client(server, raise_exceptions=False) as client:
        result = await call(client, image_path=str(image))
    assert result.is_error and "not answering" in result.content[0].text
