"""The MCP tool against a running GC-AI service.

Set GCAI_URL and run `pytest -m integration`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.helpers import EXAMPLES

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

GCAI_URL = os.environ.get("GCAI_URL")
needs_service = pytest.mark.skipif(not GCAI_URL, reason="set GCAI_URL")

YES_GATE = EXAMPLES / "YES GATE"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def live_client(tmp_path: Path):
    from mcp import Client

    from gcai.mcp.server import build_server

    server = build_server(base_url=GCAI_URL, allowed_roots=(EXAMPLES, tmp_path))
    async with Client(server, raise_exceptions=False) as client:
        yield client


@needs_service
async def test_an_example_image_reports_its_glyphs(live_client) -> None:
    result = await live_client.call_tool(
        "design_from_image",
        {
            "name": "YES_GATE",
            "namespace": "https://example.org/designs/",
            "image_path": str(YES_GATE / "YES-GATE-CIRCUIT.png"),
        },
    )
    data = result.structured_content
    assert data["built"] is False
    assert data["detected"], "the detector found nothing in the example image"
    assert [type(block).__name__ for block in result.content][0] == "ImageContent"


@needs_service
async def test_names_build_a_real_document(live_client, tmp_path: Path) -> None:
    first = await live_client.call_tool(
        "design_from_image",
        {
            "name": "YES_GATE",
            "namespace": "https://example.org/designs/",
            "image_path": str(YES_GATE / "YES-GATE-CIRCUIT.png"),
        },
    )
    roles = [glyph["role"] for glyph in first.structured_content["detected"]]
    names = {"Promoter": "BBa_R0010", "RBS": "BBa_B0034", "CDS": "BBa_E0040", "Terminator": "BBa_B0015"}
    part_names = [names[role] for role in roles]

    result = await live_client.call_tool(
        "design_from_image",
        {
            "name": "YES_GATE",
            "namespace": "https://example.org/designs/",
            "image_path": str(YES_GATE / "YES-GATE-CIRCUIT.png"),
            "part_names": part_names,
            "output_dir": str(tmp_path / "out"),
            "fasta": True,
        },
    )
    data = result.structured_content
    assert data["built"] is True, data.get("problems")
    written = {Path(path).suffix for path in data["written"]}
    assert written == {".xml", ".fasta"}
    document = Path(data["written"][0]).read_bytes()
    assert document.startswith(b"<?xml")
    assert b"http://sbols.org/v3#" in document


@needs_service
async def test_a_part_the_service_does_not_know_is_reported(live_client) -> None:
    first = await live_client.call_tool(
        "design_from_image",
        {
            "name": "YES_GATE",
            "namespace": "https://example.org/designs/",
            "image_path": str(YES_GATE / "YES-GATE-CIRCUIT.png"),
        },
    )
    count = len(first.structured_content["detected"])
    result = await live_client.call_tool(
        "design_from_image",
        {
            "name": "YES_GATE",
            "namespace": "https://example.org/designs/",
            "image_path": str(YES_GATE / "YES-GATE-CIRCUIT.png"),
            # Distinct, so local validation passes and the service is the one
            # that refuses them.
            "part_names": [f"BBa_NOT_A_REAL_PART_{i}" for i in range(count)],
        },
    )
    assert result.is_error
    assert "No component data found" in result.content[0].text
