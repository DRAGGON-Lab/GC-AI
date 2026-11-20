"""Comparing what was detected with what was encoded.

A design starts as glyphs in an image and ends as parts in a document. This
compares the two sequences, which is how you find out whether the document says
what the diagram said, without rendering anything.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from gcai.constants import ROLE_TO_GLYPHS, SO_TO_ROLE, GlyphClass, Role
from gcai.errors import GCAIError
from gcai.interop._doc import load, parent_component, require_sbol3, term
from gcai.models import Detection

if TYPE_CHECKING:  # pragma: no cover
    import sbol3

SBOL_MEETS = "http://sbols.org/v3#meets"


@dataclass(frozen=True)
class EncodedPart:
    """One part as the document records it."""

    display_id: str
    name: str | None
    role: Role | None
    so_term: str | None
    start: int | None
    end: int | None


@dataclass(frozen=True)
class Mismatch:
    """One place where the detected and encoded sequences disagree."""

    kind: Literal["replace", "delete", "insert"]
    index: int
    detected: tuple[GlyphClass, ...]
    encoded: tuple[Role | None, ...]

    def __str__(self) -> str:
        detected = ", ".join(glyph.value for glyph in self.detected) or "-"
        encoded = ", ".join(role.value if role else "?" for role in self.encoded) or "-"
        if self.kind == "insert":
            return f"at {self.index}: the document has {encoded}, which was not detected"
        if self.kind == "delete":
            return f"at {self.index}: {detected} was detected but is not in the document"
        return f"at {self.index}: detected {detected}, but the document has {encoded}"


@dataclass(frozen=True)
class RoundTripReport:
    """How the detected glyphs compare with the encoded parts."""

    detected: tuple[GlyphClass, ...]
    encoded: tuple[EncodedPart, ...]
    mismatches: tuple[Mismatch, ...]

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def format(self) -> str:
        lines = [
            f"detected {len(self.detected)} glyphs, document holds {len(self.encoded)} parts",
        ]
        if self.ok:
            lines.append("they agree")
        else:
            lines += [f"  {mismatch}" for mismatch in self.mismatches]
        return "\n".join(lines)


def encoded_parts(document: bytes | str, *, parent: str | None = None) -> tuple[EncodedPart, ...]:
    """The design's parts in 5'-to-3' order.

    The service records that order twice: a Range location on each part, and a
    chain of `meets` constraints. Ranges are used when every part has one, and
    the chain otherwise. If both are present and disagree, the document is
    malformed and that is raised rather than guessed at.
    """
    sbol3 = require_sbol3()
    doc = load(document)
    component = parent_component(doc, parent)
    subcomponents = [f for f in component.features if isinstance(f, sbol3.SubComponent)]
    if not subcomponents:
        return ()

    by_range = _order_by_range(subcomponents)
    by_chain = _order_by_constraints(component, subcomponents)

    if by_range is not None and by_chain is not None and by_range != by_chain:
        ranges = ", ".join(f.display_id for f in by_range)
        chain = ", ".join(f.display_id for f in by_chain)
        raise GCAIError(
            "the document's locations and constraints disagree about the order of its parts: "
            f"locations give {ranges}, constraints give {chain}"
        )

    ordered = by_range or by_chain or subcomponents
    return tuple(_describe(feature) for feature in ordered)


def _order_by_range(subcomponents: list["sbol3.SubComponent"]) -> list["sbol3.SubComponent"] | None:
    starts: list[tuple[int, "sbol3.SubComponent"]] = []
    for feature in subcomponents:
        location = feature.locations[0] if feature.locations else None
        start = getattr(location, "start", None)
        if start is None:
            return None
        starts.append((int(start), feature))
    return [feature for _, feature in sorted(starts, key=lambda row: row[0])]


def _order_by_constraints(
    component: "sbol3.Component", subcomponents: list["sbol3.SubComponent"]
) -> list["sbol3.SubComponent"] | None:
    """Walk the chain of `meets` constraints from the feature nothing precedes."""
    known = {feature.identity: feature for feature in subcomponents}
    follows: dict[str, str] = {}
    for constraint in component.constraints:
        if str(constraint.restriction) != SBOL_MEETS:
            continue
        subject, obj = str(constraint.subject), str(constraint.object)
        if subject in known and obj in known:
            if subject in follows:  # a fork is not a chain
                return None
            follows[subject] = obj
    if len(follows) != len(subcomponents) - 1:
        return None

    targets = set(follows.values())
    heads = [identity for identity in known if identity not in targets]
    if len(heads) != 1:
        return None

    ordered: list["sbol3.SubComponent"] = []
    current: str | None = heads[0]
    while current is not None:
        ordered.append(known[current])
        current = follows.get(current)
    return ordered if len(ordered) == len(subcomponents) else None


def _describe(feature: "sbol3.SubComponent") -> EncodedPart:
    definition = feature.instance_of.lookup()
    so_term = None
    role = None
    for candidate in getattr(definition, "roles", []):
        mapped = SO_TO_ROLE.get(term(candidate))
        if mapped is not None:
            so_term, role = term(candidate), mapped
            break
    location = feature.locations[0] if feature.locations else None
    return EncodedPart(
        display_id=getattr(definition, "display_id", ""),
        name=feature.name,
        role=role,
        so_term=so_term,
        start=getattr(location, "start", None),
        end=getattr(location, "end", None),
    )


def check_order(detection: Detection, document: bytes | str, *, parent: str | None = None) -> RoundTripReport:
    """Compare the detected glyphs with the parts the document encodes.

    A design is usually completed by hand after detection, so a report that is
    not `ok` is not necessarily a fault: it says the document holds something
    the image did not, which is exactly what adding a part looks like.
    """
    detected = tuple(glyph.glyph_class for glyph in detection.ordered())
    encoded = encoded_parts(document, parent=parent)

    # Compare on roles, so that a glyph class and the role it becomes match:
    # cds and cds-arrow are both a CDS.
    left = [glyph.role.value if glyph.role else f"?{glyph.glyph_class.value}" for glyph in detection.ordered()]
    right = [part.role.value if part.role else f"?{part.display_id}" for part in encoded]

    mismatches = []
    for kind, i1, i2, j1, j2 in difflib.SequenceMatcher(a=left, b=right, autojunk=False).get_opcodes():
        if kind == "equal":
            continue
        mismatches.append(
            Mismatch(
                kind=kind,
                index=i1,
                detected=detected[i1:i2],
                encoded=tuple(part.role for part in encoded[j1:j2]),
            )
        )
    return RoundTripReport(detected=detected, encoded=encoded, mismatches=tuple(mismatches))


def glyphs_for(role: Role) -> frozenset[GlyphClass]:
    """Which detected classes become `role`."""
    return ROLE_TO_GLYPHS.get(role, frozenset())
