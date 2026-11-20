"""Reading the service's responses."""

from __future__ import annotations

from conftest import PNG, detection_payload

from gcai.constants import GlyphClass, Role
from gcai.models import Detection, PartDetails


def test_detection_reads_boxes_and_classes() -> None:
    detection = Detection.from_response(detection_payload())
    assert detection.has_predictions
    assert [glyph.glyph_class for glyph in detection.glyphs] == [
        GlyphClass.PROMOTER,
        GlyphClass.RIBOSOME_ENTRY_SITE,
    ]
    assert detection.glyphs[0].box.as_list() == [55, 164, 110, 234]
    assert detection.glyphs[0].box.width == 55
    assert detection.annotated_png == PNG


def test_detection_orders_glyphs_left_to_right() -> None:
    detection = Detection.from_response(
        detection_payload(["terminator", "promoter"], [[300, 0, 350, 50], [10, 0, 60, 50]])
    )
    assert [glyph.glyph_class.value for glyph in detection.ordered()] == ["promoter", "terminator"]


def test_detection_with_nothing_found() -> None:
    detection = Detection.from_response(
        {"status": "success", "result_image": "", "draw_boxes": [], "pred_classes": [], "has_predictions": False}
    )
    assert not detection.has_predictions
    assert detection.to_json() == {"has_predictions": False, "count": 0, "glyphs": []}


def test_cds_arrow_is_a_coding_sequence() -> None:
    detection = Detection.from_response(detection_payload(["cds-arrow"], [[0, 0, 10, 10]]))
    assert detection.glyphs[0].role is Role.CDS


def test_detection_record_leaves_out_the_image() -> None:
    record = Detection.from_response(detection_payload()).to_json()
    assert record["count"] == 2
    assert "result_image" not in record
    assert record["glyphs"][0]["glyph_class"] == "promoter"


def test_part_details_reads_an_empty_length() -> None:
    details = PartDetails.from_response(
        {"name": "BBa_R0010", "description": None, "role": None, "sequence": None, "sequence_length": ""}
    )
    assert details.sequence_length is None
    assert details.name == "BBa_R0010"
