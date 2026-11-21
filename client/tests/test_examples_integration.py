"""The example scripts against a running GC-AI service.

Set GCAI_URL, and SBOL_DB_URL for the publishing test, then run
`pytest -m integration`.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Iterator

import image_to_sbol
import publish_to_registry
import pytest

from gcai import GCAIClient, storage
from tests.helpers import EXAMPLES

pytestmark = pytest.mark.integration

URL = os.environ.get("GCAI_URL")
DB_URL = os.environ.get("SBOL_DB_URL")
needs_service = pytest.mark.skipif(not URL, reason="set GCAI_URL to run the integration tests")
needs_registry = pytest.mark.skipif(not DB_URL, reason="set SBOL_DB_URL")

YES_GATE = EXAMPLES / "YES GATE"
NAMESPACE = "http://sbols.org/unspecified_namespace"


@pytest.fixture(scope="module")
def live() -> Iterator[GCAIClient]:
    with GCAIClient(URL) as client:
        yield client


@needs_service
def test_the_diagram_yields_a_document_with_no_names_given(live: GCAIClient, tmp_path: Path) -> None:
    summary = image_to_sbol.run(
        live,
        YES_GATE / "YES-GATE-CIRCUIT.png",
        name="YesGateFromImage",
        namespace=NAMESPACE,
        out=tmp_path,
    )

    assert summary.glyphs_found == len(summary.parts), "one part per glyph with a role"
    assert summary.without_sequence == summary.parts
    assert [path.name for path in summary.written] == ["YesGateFromImage.xml"]
    assert b"http://sbols.org/v3#" in (tmp_path / "YesGateFromImage.xml").read_bytes()


@needs_service
def test_names_bring_sequences_and_the_other_formats(live: GCAIClient, tmp_path: Path) -> None:
    summary = image_to_sbol.run(
        live,
        YES_GATE / "YES-GATE-CIRCUIT.png",
        name="YesGateNamed",
        namespace=NAMESPACE,
        names=["BBa_R0010", "BBa_B0034"],
        out=tmp_path,
    )

    assert summary.parts == ["BBa_R0010", "BBa_B0034"]
    assert summary.without_sequence == []
    assert sorted(path.name for path in summary.written) == [
        "YesGateNamed.fasta",
        "YesGateNamed.gb",
        "YesGateNamed.xml",
    ]
    fasta = (tmp_path / "YesGateNamed.fasta").read_text()
    assert sum(len(line.strip()) for line in fasta.splitlines() if not line.startswith(">")) > 100


@needs_service
@needs_registry
def test_a_document_built_from_a_diagram_publishes_and_reads_back(live: GCAIClient, tmp_path: Path) -> None:
    """The second example picks up where the first leaves off."""
    image_to_sbol.run(
        live,
        YES_GATE / "YES-GATE-CIRCUIT.png",
        name="YesGatePublished",
        namespace=NAMESPACE,
        names=["BBa_R0010", "BBa_B0034"],
        out=tmp_path,
    )
    graph = f"https://gc-ai.test/designs/{uuid.uuid4()}"

    publish_to_registry.run(
        DB_URL or "",
        tmp_path / "YesGatePublished.xml",
        iri=graph,
        design="YesGatePublished",
        namespace=NAMESPACE,
    )

    with storage.client(DB_URL or "") as registry:
        try:
            root = publish_to_registry.design_iri(NAMESPACE, "YesGatePublished")
            assert "http://sbols.org/v3#" in storage.fetch(registry, root)
        finally:
            registry.delete_graph_by_document_iri(graph)
