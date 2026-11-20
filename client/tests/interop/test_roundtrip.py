"""Comparing detected glyphs with encoded parts."""

from __future__ import annotations

from pathlib import Path

import pytest

from gcai.constants import GlyphClass, Role
from gcai.errors import GCAIError
from gcai.interop import check_order, encoded_parts
from gcai.models import Box, Detection, Glyph
from tests.interop.helpers import detection_from_record

pytest.importorskip("sbol3", reason="install gc-ai-client[sbol]")

YES_GATE_ROLES = [
    Role.PROMOTER,
    Role.RBS,
    Role.CDS,
    Role.TERMINATOR,
    Role.PROMOTER,
    Role.RBS,
    Role.CDS,
    Role.TERMINATOR,
]


def detection_of(*classes: GlyphClass) -> Detection:
    """A detection holding these classes, left to right."""
    return Detection(
        glyphs=tuple(
            Glyph(glyph_class=cls, box=Box(index * 100, 0, index * 100 + 50, 50)) for index, cls in enumerate(classes)
        ),
        annotated_png=b"",
    )


def test_parts_come_back_in_five_to_three_order(yes_gate: bytes) -> None:
    parts = encoded_parts(yes_gate)
    assert [part.role for part in parts] == YES_GATE_ROLES
    assert [part.display_id for part in parts][:3] == ["BBa_J23100", "BBa_B0034", "BBa_C0012"]


def test_parts_carry_their_locations(yes_gate: bytes) -> None:
    parts = encoded_parts(yes_gate)
    starts = [part.start for part in parts]
    assert starts == sorted(starts), "parts should be ordered by where they sit"
    assert parts[0].start == 1


def test_the_order_survives_without_locations(yes_gate: bytes) -> None:
    """With the Ranges stripped, the `meets` chain gives the same order."""
    rdflib = pytest.importorskip("rdflib")
    graph = rdflib.Graph().parse(data=yes_gate.decode(), format="xml", publicID="")
    sbol = rdflib.Namespace("http://sbols.org/v3#")
    for subject, predicate, obj in list(graph.triples((None, sbol.hasLocation, None))):
        graph.remove((subject, predicate, obj))
    stripped = graph.serialize(format="xml").encode()

    parts = encoded_parts(stripped)

    assert [part.role for part in parts] == YES_GATE_ROLES
    assert all(part.start is None for part in parts)


def test_a_document_the_order_cannot_be_read_from_is_reported(yes_gate: bytes) -> None:
    """Locations that disagree with the constraints are raised, not guessed at."""
    rdflib = pytest.importorskip("rdflib")
    graph = rdflib.Graph().parse(data=yes_gate.decode(), format="xml", publicID="")
    sbol = rdflib.Namespace("http://sbols.org/v3#")
    starts = sorted(graph.triples((None, sbol.start, None)), key=lambda t: int(t[2]))
    # Swap the first two start positions, so the locations contradict the chain.
    (s1, p1, o1), (s2, p2, o2) = starts[0], starts[1]
    graph.remove((s1, p1, o1))
    graph.remove((s2, p2, o2))
    graph.add((s1, p1, o2))
    graph.add((s2, p2, o1))

    with pytest.raises(GCAIError, match="disagree about the order"):
        encoded_parts(graph.serialize(format="xml").encode())


def test_a_matching_detection_round_trips(yes_gate: bytes) -> None:
    detection = detection_of(
        GlyphClass.PROMOTER,
        GlyphClass.RIBOSOME_ENTRY_SITE,
        GlyphClass.CDS,
        GlyphClass.TERMINATOR,
        GlyphClass.PROMOTER,
        GlyphClass.RIBOSOME_ENTRY_SITE,
        GlyphClass.CDS,
        GlyphClass.TERMINATOR,
    )
    report = check_order(detection, yes_gate)
    assert report.ok, report.format()
    assert len(report.encoded) == 8


def test_cds_arrow_counts_as_a_coding_sequence(yes_gate: bytes) -> None:
    detection = detection_of(
        GlyphClass.PROMOTER,
        GlyphClass.RIBOSOME_ENTRY_SITE,
        GlyphClass.CDS_ARROW,
        GlyphClass.TERMINATOR,
        GlyphClass.PROMOTER,
        GlyphClass.RIBOSOME_ENTRY_SITE,
        GlyphClass.CDS_ARROW,
        GlyphClass.TERMINATOR,
    )
    assert check_order(detection, yes_gate).ok


def test_a_part_the_image_did_not_show_is_reported_as_an_insert(yes_gate: bytes) -> None:
    detection = detection_of(GlyphClass.PROMOTER, GlyphClass.RIBOSOME_ENTRY_SITE)
    report = check_order(detection, yes_gate)
    assert not report.ok
    kinds = {mismatch.kind for mismatch in report.mismatches}
    assert kinds == {"insert"}
    assert "not detected" in str(report.mismatches[0])


def test_a_glyph_the_document_does_not_hold_is_reported_as_a_delete(yes_gate: bytes) -> None:
    detection = detection_of(
        GlyphClass.PROMOTER,
        GlyphClass.RIBOSOME_ENTRY_SITE,
        GlyphClass.CDS,
        GlyphClass.TERMINATOR,
        GlyphClass.OPERATOR,
        GlyphClass.PROMOTER,
        GlyphClass.RIBOSOME_ENTRY_SITE,
        GlyphClass.CDS,
        GlyphClass.TERMINATOR,
    )
    report = check_order(detection, yes_gate)
    assert not report.ok
    assert any(mismatch.kind == "delete" for mismatch in report.mismatches)


def test_a_different_glyph_is_reported_as_a_replacement(yes_gate: bytes) -> None:
    detection = detection_of(
        GlyphClass.PROMOTER,
        GlyphClass.RIBOSOME_ENTRY_SITE,
        GlyphClass.OPERATOR,
        GlyphClass.TERMINATOR,
        GlyphClass.PROMOTER,
        GlyphClass.RIBOSOME_ENTRY_SITE,
        GlyphClass.CDS,
        GlyphClass.TERMINATOR,
    )
    report = check_order(detection, yes_gate)
    assert [mismatch.kind for mismatch in report.mismatches] == ["replace"]
    assert report.mismatches[0].index == 2


def test_the_committed_examples_hold_more_than_was_detected(example: Path) -> None:
    """Detection proposes some parts; the rest of a design is entered by hand."""
    document = next(example.glob("*.xml")).read_bytes()
    report = check_order(detection_from_record(example), document)
    assert not report.ok
    assert all(mismatch.kind == "insert" for mismatch in report.mismatches), report.format()
    assert len(report.encoded) > len(report.detected)
