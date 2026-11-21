"""The shapes the service returns."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from gcai.constants import GLYPH_TO_ROLE, GlyphClass, Role


@dataclass(frozen=True)
class Box:
    """A bounding box in pixels."""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    def as_list(self) -> list[int]:
        return [self.x1, self.y1, self.x2, self.y2]


@dataclass(frozen=True)
class Glyph:
    """One detection."""

    glyph_class: GlyphClass
    box: Box

    @property
    def role(self) -> Role | None:
        """The role this glyph becomes, or None if the class has no mapping."""
        return GLYPH_TO_ROLE.get(self.glyph_class)


@dataclass(frozen=True)
class Detection:
    """What `POST /inference/` returned."""

    glyphs: tuple[Glyph, ...]
    annotated_png: bytes

    @classmethod
    def from_response(cls, payload: Mapping[str, Any]) -> "Detection":
        boxes = payload.get("draw_boxes") or []
        classes = payload.get("pred_classes") or []
        glyphs = tuple(
            Glyph(glyph_class=GlyphClass(name), box=Box(*(int(v) for v in box))) for name, box in zip(classes, boxes)
        )
        image = payload.get("result_image") or ""
        return cls(glyphs=glyphs, annotated_png=base64.b64decode(image) if image else b"")

    def ordered(self) -> tuple[Glyph, ...]:
        """The glyphs left to right, which is the order parts go into a design.

        The service returns them in the model's order. Sorting on the left edge
        is what the web interface does; a diagram drawn over several rows will
        interleave.
        """
        return tuple(sorted(self.glyphs, key=lambda glyph: glyph.box.x1))

    @property
    def has_predictions(self) -> bool:
        return bool(self.glyphs)

    def to_json(self) -> dict[str, Any]:
        """A record of the detection, without the annotated image."""
        return {
            "has_predictions": self.has_predictions,
            "count": len(self.glyphs),
            "glyphs": [
                {"glyph_class": glyph.glyph_class.value, "box": glyph.box.as_list()} for glyph in self.ordered()
            ],
        }


@dataclass(frozen=True)
class PartDetails:
    """One part from the bundled registry."""

    name: str
    description: str | None
    role: str | None
    sequence: str | None
    sequence_length: int | None

    @classmethod
    def from_response(cls, payload: Mapping[str, Any]) -> "PartDetails":
        length = payload.get("sequence_length")
        # The service sends an empty string rather than 0 for a part with no
        # recorded length.
        measured = int(length) if isinstance(length, (int, str)) and str(length).strip() else None
        return cls(
            name=str(payload.get("name") or payload.get("identifier") or ""),
            description=payload.get("description"),
            role=payload.get("role"),
            sequence=payload.get("sequence"),
            sequence_length=measured,
        )


@dataclass(frozen=True)
class CreateResult:
    """What `POST /file/create` returned."""

    sbol3: bytes
    structural_handle: str
    """Opaque conversion handle, valid for 24 hours."""


@dataclass(frozen=True)
class BuildResult:
    """A design generated and converted in one step."""

    sbol3: bytes
    structural_handle: str
    genbank: bytes | None = None
    fasta: bytes | None = None

    def write(self, directory: Path | str, stem: str) -> list[Path]:
        """Write every file this holds into `directory`, named after `stem`."""
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        written = []
        for suffix, data in ((".xml", self.sbol3), (".gb", self.genbank), (".fasta", self.fasta)):
            if data:
                path = target / f"{stem}{suffix}"
                path.write_bytes(data)
                written.append(path)
        return written
