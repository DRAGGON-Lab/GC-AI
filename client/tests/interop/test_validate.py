"""Validating generated documents."""

from __future__ import annotations

from pathlib import Path

import pytest

from gcai.errors import GCAIError
from gcai.interop import validate
from gcai.interop._doc import load, parent_component

pytest.importorskip("sbol3", reason="install gc-ai-client[sbol]")


def test_every_committed_example_validates(example: Path) -> None:
    document = next(example.glob("*.xml")).read_bytes()
    assert validate(document) == []


def test_a_document_holding_no_sbol_objects_is_reported() -> None:
    """It parses as RDF and has nothing to find, so it would look valid."""
    issues = validate(b'<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>')
    assert [issue.severity for issue in issues] == ["warning"]
    assert "no SBOL objects" in issues[0].message


def test_the_parent_component_is_the_one_holding_parts(yes_gate: bytes) -> None:
    component = parent_component(load(yes_gate))
    assert component.display_id == "BBa_0000"


def test_naming_a_component_that_is_not_there_is_an_error(yes_gate: bytes) -> None:
    with pytest.raises(GCAIError, match="no parent component"):
        parent_component(load(yes_gate), "NOT_A_COMPONENT")


def test_an_empty_species_uri_does_not_pick_up_a_file_path() -> None:
    """A document is parsed from memory so an empty definition stays empty."""
    lux = Path(__file__).resolve().parents[3] / "docs" / "examples" / "Lux System (BBa_I13263)"
    document = (lux / "BBa_I13263.xml").read_bytes()
    assert validate(document) == []
    assert b"file://" not in document
