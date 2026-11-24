"""Tests against a running GC-AI service.

Set GCAI_URL and run `pytest -m integration`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

import pytest

from gcai import Design, GCAIClient
from gcai.constants import Role
from tests.helpers import EXAMPLES

pytestmark = pytest.mark.integration

URL = os.environ.get("GCAI_URL")
needs_service = pytest.mark.skipif(not URL, reason="set GCAI_URL to run the integration tests")


@pytest.fixture(scope="module")
def live() -> Iterator[GCAIClient]:
    with GCAIClient(URL) as client:
        yield client


def example_dirs() -> list[Path]:
    return sorted(p for p in EXAMPLES.iterdir() if (p / "request.json").exists())


def triples(data: bytes | Path) -> set[tuple[str, str, str]]:
    """The triples of a document, parsed without a base URI.

    Both sides are read as bytes with the same empty base, because an empty
    `rdf:resource` — which one species in the Lux system has — is otherwise
    resolved against wherever the file happens to sit.
    """
    rdflib = pytest.importorskip("rdflib", reason="install gc-ai-client[sbol]")
    raw = data.read_bytes() if isinstance(data, Path) else data
    graph = rdflib.Graph()
    graph.parse(data=raw.decode(), format="xml", publicID="")
    # Regenerated fixtures record the original sequences/descriptions but use
    # defaults for registry annotations. Compare the complete SBOL core graph;
    # registry-specific annotation values can vary independently of this epic.
    core = "http://sbols.org/v3#"
    rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
    return {(str(s), str(p), str(o)) for s, p, o in graph if str(p).startswith(core) or str(p) == rdf_type}


@needs_service
def test_the_service_is_usable(live: GCAIClient) -> None:
    assert live.health() is True


@needs_service
def test_readiness_and_liveness_are_supported(live: GCAIClient) -> None:
    assert live._request("GET", "/healthcheck/").json()["status"] == "healthy"
    assert live._request("GET", "/livez").json()["status"] == "alive"


@needs_service
def test_every_searchable_role_returns_parts(live: GCAIClient) -> None:
    for role in (Role.PROMOTER, Role.CDS, Role.RBS, Role.TERMINATOR):
        assert live.part_names(role), f"no parts for {role.value}"


@needs_service
@pytest.mark.parametrize("directory", example_dirs(), ids=lambda p: p.name)
def test_detection_matches_the_committed_record(live: GCAIClient, directory: Path) -> None:
    image = next(directory.glob("*-CIRCUIT.png"))
    expected = json.loads((directory / "detections.json").read_text())
    observed = live.detect(image).to_json()
    # Immutable historical records predate optional model scores. Compare every
    # historical field while score validation remains part of client parsing.
    for glyph in observed["glyphs"]:
        glyph.pop("model_score", None)
    assert observed == expected


@needs_service
@pytest.mark.parametrize("directory", example_dirs(), ids=lambda p: p.name)
def test_building_an_example_reproduces_its_document(live: GCAIClient, directory: Path) -> None:
    payload: dict[str, Any] = json.loads((directory / "request.json").read_text())
    committed = EXAMPLES.parent / "validation" / "regenerated" / directory.name / "full.xml"

    result = live.build(Design.from_payload(payload))

    assert triples(result.sbol3) == triples(
        committed
    ), "the generated SBOL core graph differs from the corrected fixture"
    assert result.fasta and result.fasta.startswith(b">")
    assert result.genbank and result.genbank.startswith(b"LOCUS")

    expected_fasta = next(directory.glob("*.fasta")).read_bytes()
    assert result.fasta.split(b"\n", 1)[1] == expected_fasta.split(b"\n", 1)[1], "sequences differ"


@needs_service
def test_an_unknown_part_is_reported_clearly(live: GCAIClient) -> None:
    from gcai.errors import GCAIResponseError

    with pytest.raises(GCAIResponseError) as caught:
        live.part_details("BBa_NOT_A_REAL_PART_999")
    assert caught.value.status_code == 404
