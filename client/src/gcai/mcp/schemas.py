"""What the tool returns."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Glyph(BaseModel):
    """One glyph the detector found."""

    index: int
    glyph_class: str
    role: str | None = Field(default=None, description="The component role this glyph becomes")
    box: list[int] = Field(description="x1, y1, x2, y2 in pixels")
    model_score: float | None = Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Optional model score, not a calibrated probability",
    )


class Result(BaseModel):
    """What came of an image.

    The document is built on the one call. It is returned here, or written to
    disk when `output_dir` was given.
    """

    detected: list[Glyph] = Field(description="Glyphs found, left to right, which is 5' to 3'")
    unmapped: list[str] = Field(default_factory=list, description="Classes the detector found that have no role")
    built: bool = False
    parts: list[str] = Field(default_factory=list, description="The parts that went into the design")
    named_from_registry: list[str] = Field(default_factory=list, description="Those bound to a part the service knows")
    notes: list[str] = Field(default_factory=list, description="What the document does and does not say")
    sbol3: str | None = Field(default=None, description="The SBOL3 document, when nothing was written")
    genbank: str | None = None
    fasta: str | None = None
    written: list[str] = Field(default_factory=list, description="Files written, when output_dir was given")
    problems: list[str] = Field(default_factory=list, description="Why the design was not built")
    next_step: str = ""
