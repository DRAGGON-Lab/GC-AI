"""Local checks on a design.

The service builds a document and reports whether it could write it; it does
not check a design beyond what it needs to do that. These checks cover the
rest, so a caller learns what is wrong before sending a request, and learns
about the things the service accepts but should not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

from gcai.constants import DISPLAY_ID, IUPAC_DNA, PARTICIPATIONS, RNA_ROLES

if TYPE_CHECKING:  # pragma: no cover
    from gcai.design import Design, ExternalSpecies, Part

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    """One thing wrong with a design."""

    severity: Severity
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.path}: {self.message}"


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_design(design: "Design") -> list[Issue]:
    """Everything wrong with `design`, errors before warnings."""
    issues: list[Issue] = []
    issues += _check_namespace(design)
    issues += _check_component(design.name, design.role.value, design.uri, "design", is_parent=True)
    issues += _check_parts(design)
    issues += _check_operons(design)
    issues += _check_species(design)
    issues += _check_interactions(design)
    issues += _check_shape(design)
    return sorted(issues, key=lambda issue: 0 if issue.severity == "error" else 1)


def _check_namespace(design: "Design") -> list[Issue]:
    if not design.namespace:
        return [
            Issue(
                "error",
                "namespace",
                "set a namespace: the service applies it process-wide, so a request without one "
                "is built under whatever namespace the previous request set",
            )
        ]
    if not _is_http_url(design.namespace):
        return [Issue("error", "namespace", f"{design.namespace!r} is not an http or https URL")]
    return []


def _check_component(name: str, role: str, uri: str, path: str, *, is_parent: bool) -> list[Issue]:
    issues: list[Issue] = []
    if not name:
        issues.append(Issue("error", f"{path}.name", "a name is required"))
    elif not DISPLAY_ID.match(name):
        issues.append(
            Issue(
                "error",
                f"{path}.name",
                f"{name!r} is not a valid SBOL displayId; it has to match {DISPLAY_ID.pattern}",
            )
        )
    if not uri:
        issues.append(Issue("error", f"{path}.uri", "a URI is required"))
    elif not _is_http_url(uri):
        issues.append(Issue("error", f"{path}.uri", f"{uri!r} is not an http or https URL"))
    elif not is_parent and not uri.endswith(("/", "#")):
        issues.append(
            Issue(
                "error",
                f"{path}.uri",
                f"{uri!r} has to end in '/' or '#': it prefixes the part's annotation namespace",
            )
        )
    return issues


def _check_parts(design: "Design") -> list[Issue]:
    issues: list[Issue] = []
    if not design.parts:
        issues.append(Issue("error", "parts", "a design needs at least one part"))

    for index, part in enumerate(design.parts):
        path = f"parts[{index}]"
        issues += _check_component(part.name, part.role.value, part.uri, path, is_parent=False)

        if part.new:
            if not part.sequence:
                # The service accepts this: the document records the part's
                # role and its place in the order, with no bases. It is what a
                # diagram on its own can say.
                issues.append(
                    Issue(
                        "warning",
                        f"{path}.sequence",
                        "no sequence, so the document will record this part's role and position " "but no bases",
                    )
                )
            else:
                bad = sorted(set(part.sequence.lower()) - IUPAC_DNA)
                if bad:
                    issues.append(Issue("error", f"{path}.sequence", f"not IUPAC DNA: {''.join(bad)!r}"))
        if part.role in RNA_ROLES:
            issues.append(
                Issue(
                    "warning",
                    f"{path}.role",
                    f"{part.role.value} is an RNA role; its sequence is still concatenated into the "
                    "parent's DNA sequence, which the service accepts without complaint",
                )
            )
        if part.name == design.name:
            issues.append(Issue("error", f"{path}.name", "a part cannot have the same name as the design"))

    by_name: dict[str, set[str]] = {}
    for part in design.parts:
        if part.name:
            by_name.setdefault(part.name.lower(), set()).add(part.role.value)
    for name, roles in by_name.items():
        if len(roles) > 1:
            issues.append(
                Issue(
                    "error",
                    "parts",
                    f"{name!r} is used with more than one role ({', '.join(sorted(roles))}); "
                    "parts that share a name have to share a role, or they cannot be told apart",
                )
            )
    return issues


def _check_operons(design: "Design") -> list[Issue]:
    issues: list[Issue] = []
    known = design.parts
    for index, operon in enumerate(design.operons):
        path = f"operons[{index}]"
        if not operon.name:
            issues.append(Issue("error", f"{path}.name", "a name is required"))
        if not operon.parts:
            issues.append(Issue("error", f"{path}.parts", "an operon needs at least one part"))
        for part in operon.parts:
            if not any(part is candidate for candidate in known):
                issues.append(Issue("error", f"{path}.parts", f"{part.name!r} is not one of this design's parts"))
        if not operon.unions:
            issues.append(
                Issue(
                    "warning",
                    f"{path}.unions",
                    "no unions: the web interface requires at least one, though the service does not",
                )
            )
        for union in operon.unions:
            for end, part in (("from", union.source), ("to", union.target)):
                if not any(part is candidate for candidate in operon.parts):
                    issues.append(
                        Issue(
                            "error",
                            f"{path}.unions.{end}",
                            f"{part.name!r} is not a member of this operon",
                        )
                    )
    return issues


def _check_species(design: "Design") -> list[Issue]:
    issues: list[Issue] = []
    for index, species in enumerate(design.species):
        path = f"species[{index}]"
        if not species.name:
            issues.append(Issue("error", f"{path}.name", "a name is required"))
        if species.uri:
            if species.uri != species.uri.strip():
                issues.append(
                    Issue(
                        "error",
                        f"{path}.uri",
                        "the URI has leading or trailing whitespace; the service writes it through "
                        "unchanged, and a URI containing a space cannot be canonicalised",
                    )
                )
            elif not _is_http_url(species.uri):
                issues.append(Issue("error", f"{path}.uri", f"{species.uri!r} is not an http or https URL"))
        else:
            issues.append(
                Issue(
                    "warning",
                    f"{path}.uri",
                    "no URI: an empty definition is resolved against the document's own location "
                    "when it is read back",
                )
            )
    return issues


def _check_interactions(design: "Design") -> list[Issue]:
    issues: list[Issue] = []
    for index, interaction in enumerate(design.interactions):
        path = f"interactions[{index}]"
        expected = PARTICIPATIONS[interaction.type]
        if not interaction.participants:
            issues.append(Issue("error", f"{path}.participants", "an interaction needs participants"))
        for role, members in interaction.participants.items():
            if role not in expected:
                issues.append(
                    Issue(
                        "error",
                        f"{path}.participants.{role.value}",
                        f"{role.value} is not a participation role of {interaction.type.value} "
                        f"(expected {', '.join(r.value for r in expected)}); the service accepts it "
                        "and writes the wrong term",
                    )
                )
            if not members:
                issues.append(Issue("error", f"{path}.participants.{role.value}", "no participants for this role"))
            for member in members:
                if not _is_known(design, member):
                    issues.append(
                        Issue(
                            "error",
                            f"{path}.participants.{role.value}",
                            f"{member.name!r} is not one of this design's parts or species",
                        )
                    )
    return issues


def _is_known(design: "Design", member: "Part | ExternalSpecies") -> bool:
    from gcai.design import ExternalSpecies

    pool = design.species if isinstance(member, ExternalSpecies) else design.parts
    return any(member is candidate for candidate in pool)


def _check_shape(design: "Design") -> list[Issue]:
    if design.operons:
        return []
    issues = []
    if design.interactions:
        issues.append(
            Issue(
                "warning",
                "interactions",
                "a design with no operons gets no functional system, so its interactions are dropped",
            )
        )
    if design.species:
        issues.append(
            Issue(
                "warning",
                "species",
                "a design with no operons gets no functional system, so its species are dropped",
            )
        )
    return issues
