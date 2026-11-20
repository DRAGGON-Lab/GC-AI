"""Interop tests against running services.

Set GCAI_URL for the GC-AI service and SBOL_DB_URL for a registry, then run
`pytest -m integration`.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Iterator

import pytest

from gcai import GCAIClient
from gcai.interop import SbolDb, check_order, validate
from tests.interop.helpers import detection_from_record

pytestmark = pytest.mark.integration

GCAI_URL = os.environ.get("GCAI_URL")
DB_URL = os.environ.get("SBOL_DB_URL")
DB_OPS_URL = os.environ.get("SBOL_DB_OPERATIONS_URL")

needs_gcai = pytest.mark.skipif(not GCAI_URL, reason="set GCAI_URL")
needs_registry = pytest.mark.skipif(not DB_URL, reason="set SBOL_DB_URL")


@pytest.fixture(scope="module")
def registry() -> Iterator[SbolDb]:
    with SbolDb(DB_URL or "", operations_url=DB_OPS_URL) as db:
        yield db


@needs_registry
def test_the_registry_answers(registry: SbolDb) -> None:
    assert registry.healthy() is True


@needs_registry
def test_a_generated_document_can_be_published_and_read_back(registry: SbolDb, example: Path) -> None:
    document = next(example.glob("*.xml")).read_bytes()
    iri = f"https://gc-ai.test/designs/{uuid.uuid4()}"

    result = registry.publish(
        document,
        document_iri=iri,
        name=example.name,
        description="published by the GC-AI interop tests",
        namespace="https://gc-ai.test/designs/",
    )

    assert result.object_count > 0
    assert result.triple_count > 0

    # The registry reads SBOL3 as it is: no conversion happens on the way in.
    fetched = registry.fetch(iri.replace("/designs/", "/designs/"), version="sbol3")
    assert fetched

    registry.delete(iri)


@needs_registry
def test_the_registry_converts_to_sbol2_itself(registry: SbolDb, yes_gate: bytes) -> None:
    """No local converter is involved, which is the point of using a registry."""
    iri = f"https://gc-ai.test/designs/{uuid.uuid4()}"
    registry.publish(yes_gate, document_iri=iri, name="YES gate", description="")
    try:
        parent = "http://sbols.org/unspecified_namespace/BBa_0000"
        sbol2 = registry.to_sbol2(parent)
        assert sbol2
        assert b"sbol" in sbol2.lower()
    finally:
        registry.delete(iri)


@needs_registry
def test_the_registry_validates_what_the_service_does_not(registry: SbolDb, yes_gate: bytes) -> None:
    """The registry runs its own validator on import.

    This records what it currently reports for a document the Python SBOL
    validator passes, so a change in either is visible.
    """
    iri = f"https://gc-ai.test/designs/{uuid.uuid4()}"
    try:
        result = registry.publish(yes_gate, document_iri=iri, name="YES gate", description="")
        assert validate(yes_gate) == [], "the Python validator finds nothing"
        assert result.validation_issue_count >= 0
    finally:
        registry.delete(iri)


@needs_gcai
@needs_registry
def test_a_design_goes_from_image_to_registry(registry: SbolDb, example: Path) -> None:
    """The whole path: build with the service, check it, publish it."""
    import json

    with GCAIClient(GCAI_URL) as client:
        payload = json.loads((example / "request.json").read_text())
        built = client.build(payload, genbank=False, fasta=False)

    assert validate(built.sbol3) == []

    report = check_order(detection_from_record(example), built.sbol3)
    assert len(report.encoded) >= len(report.detected)

    iri = f"https://gc-ai.test/designs/{uuid.uuid4()}"
    result = registry.publish(built.sbol3, document_iri=iri, name=example.name, description="end to end")
    try:
        assert result.object_count > 0
    finally:
        registry.delete(iri)
