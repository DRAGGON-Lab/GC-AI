"""Storage tests against a running SBOL DB registry.

Set SBOL_DB_URL, and GCAI_URL for the test that builds a design first.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Iterator

import pytest

from gcai import GCAIClient, storage
from tests.helpers import EXAMPLES

pytestmark = pytest.mark.integration

DB_URL = os.environ.get("SBOL_DB_URL")
GCAI_URL = os.environ.get("GCAI_URL")

needs_registry = pytest.mark.skipif(not DB_URL, reason="set SBOL_DB_URL")
needs_gcai = pytest.mark.skipif(not GCAI_URL, reason="set GCAI_URL")


def example_dirs() -> list[Path]:
    return sorted((EXAMPLES.parent / "validation" / "regenerated").iterdir())


@pytest.fixture(scope="module")
def registry() -> Iterator[object]:
    with storage.client(DB_URL or "") as client:
        yield client


@needs_registry
@pytest.mark.parametrize("directory", example_dirs(), ids=lambda p: p.name)
def test_an_example_publishes_and_reads_back(registry, directory: Path) -> None:
    document = (directory / "full.xml").read_bytes()
    iri = f"https://gc-ai.test/designs/{uuid.uuid4()}"

    report = storage.publish(registry, document, document_iri=iri, name=directory.name, description="integration test")

    try:
        assert report.object_count > 0
        assert report.triple_count > 0
        assert report.validation_status == "passed"
        assert report.validation_issue_count == 0
        request = json.loads((EXAMPLES / directory.name / "request.json").read_text())
        root = request["namespace"].rstrip("/") + "/" + request["components"][0]["name"]
        rdf = storage.fetch(registry, root)
        import rdflib

        graph = rdflib.Graph().parse(data=rdf, format="xml")
        assert (rdflib.URIRef(root), rdflib.RDF.type, rdflib.URIRef("http://sbols.org/v3#Component")) in graph
    finally:
        registry.delete_graph_by_document_iri(iri)


@needs_registry
def test_the_registry_converts_to_sbol2(registry) -> None:
    document = (EXAMPLES.parent / "validation" / "regenerated" / "YES GATE" / "full.xml").read_bytes()
    iri = f"https://gc-ai.test/designs/{uuid.uuid4()}"
    storage.publish(registry, document, document_iri=iri, name="YES gate")
    try:
        sbol2 = storage.to_sbol2(registry, "http://sbols.org/unspecified_namespace/BBa_0000")
        assert "sbol" in sbol2.lower()
        assert "http://sbols.org/v3#" not in sbol2
    finally:
        registry.delete_graph_by_document_iri(iri)


@needs_registry
def test_overwrite_replaces_an_earlier_publish(registry) -> None:
    document = (EXAMPLES.parent / "validation" / "regenerated" / "YES GATE" / "full.xml").read_bytes()
    iri = f"https://gc-ai.test/designs/{uuid.uuid4()}"
    storage.publish(registry, document, document_iri=iri, name="YES gate")
    try:
        again = storage.publish(registry, document, document_iri=iri, name="YES gate", overwrite=1)
        assert again.object_count > 0
    finally:
        registry.delete_graph_by_document_iri(iri)


@needs_gcai
@needs_registry
def test_a_design_built_by_the_service_goes_straight_in(registry) -> None:
    directory = EXAMPLES / "YES GATE"
    with GCAIClient(GCAI_URL) as service:
        built = service.build(json.loads((directory / "request.json").read_text()), genbank=False, fasta=False)

    iri = f"https://gc-ai.test/designs/{uuid.uuid4()}"
    report = storage.publish(registry, built.sbol3, document_iri=iri, name="YES gate")
    try:
        assert report.object_count > 0
    finally:
        registry.delete_graph_by_document_iri(iri)
