"""Helpers for the interop tests."""

from __future__ import annotations

import json
from pathlib import Path

from gcai.models import Detection

EXAMPLES = Path(__file__).resolve().parents[3] / "docs" / "examples"


def detection_from_record(directory: Path) -> Detection:
    """The committed detection record, as a Detection."""
    record = json.loads((directory / "detections.json").read_text())
    return Detection.from_response(
        {
            "draw_boxes": [glyph["box"] for glyph in record["glyphs"]],
            "pred_classes": [glyph["glyph_class"] for glyph in record["glyphs"]],
            "result_image": "",
            "has_predictions": record["has_predictions"],
        }
    )
