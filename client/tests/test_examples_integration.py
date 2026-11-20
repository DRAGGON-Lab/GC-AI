"""The example scripts against a running GC-AI service.

Set GCAI_URL and run `pytest -m integration`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

import image_to_sbol
from gcai import GCAIClient
from tests.helpers import EXAMPLES

pytestmark = pytest.mark.integration

URL = os.environ.get("GCAI_URL")
needs_service = pytest.mark.skipif(not URL, reason="set GCAI_URL to run the integration tests")

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
