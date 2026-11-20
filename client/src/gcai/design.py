"""A design, and the request body the service builds it from.

The objects here are what a caller works with. Instance numbering and the
`{name}_{instance}` references the service expects are derived when the payload
is built, so a caller never writes one by hand.

Parts are linked by identity, not by name: two parts may share a name and are
told apart only by which object they are. An operon or interaction therefore
has to hold the same `Part` objects that `Design.parts` holds.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from gcai.constants import (
    GLYPH_TO_ROLE,
    IGEM_URI,
    ExternalType,
    InteractionType,
    ParticipationRole,
    Role,
    UnionType,
)
from gcai.errors import DesignValidationError
from gcai.models import Detection, PartDetails


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Part:
    """One part of a design."""

    name: str
    role: Role
    new: bool = False
    """Where the part's description and sequence come from.

    False means the service reads them from the bundled registry by name, and
    ignores whatever is sent. True means the values here are used as given.
    """

    uri: str = IGEM_URI
    description: str = ""
    sequence: str = ""
    identifier: str = ""
    id: str = field(default_factory=_new_id)

    @classmethod
    def from_details(cls, details: PartDetails, role: Role) -> "Part":
        """A registry part, filled in from `GET /component/details`."""
        return cls(
            name=details.name,
            role=role,
            new=False,
            description=details.description or "",
            sequence=(details.sequence or "").lower(),
        )


@dataclass
class Union:
    """An ordering or regulatory relationship between two members of an operon."""

    source: Part
    target: Part
    type: UnionType = UnionType.ORDER
    id: str = field(default_factory=_new_id)


@dataclass
class Operon:
    """A named group of parts within the design."""

    name: str
    parts: list[Part] = field(default_factory=list)
    unions: list[Union] = field(default_factory=list)
    constitutive: bool = False
    id: str = field(default_factory=_new_id)

    def chain(self, type: UnionType = UnionType.ORDER) -> "Operon":
        """Link the members in sequence, replacing any unions already set."""
        self.unions = [Union(source=a, target=b, type=type) for a, b in zip(self.parts, self.parts[1:])]
        return self


@dataclass
class ExternalSpecies:
    """A species that takes part in interactions but is not encoded on the DNA."""

    name: str
    type: ExternalType
    uri: str = ""
    id: str = field(default_factory=_new_id)


@dataclass
class Interaction:
    """An interaction between parts and species."""

    type: InteractionType
    participants: dict[ParticipationRole, list[Part | ExternalSpecies]] = field(default_factory=dict)
    id: str = field(default_factory=_new_id)


@dataclass
class Design:
    """A circuit: a parent component, its parts, and what they do."""

    name: str
    role: Role = Role.ENGINEERED_REGION
    description: str = ""
    namespace: str = ""
    new: bool = True
    uri: str = IGEM_URI
    identifier: str = ""
    parts: list[Part] = field(default_factory=list)
    operons: list[Operon] = field(default_factory=list)
    interactions: list[Interaction] = field(default_factory=list)
    species: list[ExternalSpecies] = field(default_factory=list)

    # ------------------------------------------------------------------ build

    @classmethod
    def from_detection(cls, detection: Detection, name: str, **kwargs: Any) -> "Design":
        """A design holding one unnamed part per detected glyph, in order.

        The parts carry no names: the caller supplies them, and `validate`
        reports the ones still missing.
        """
        design = cls(name=name, **kwargs)
        for glyph in detection.ordered():
            role = GLYPH_TO_ROLE.get(glyph.glyph_class)
            if role is None:
                continue
            design.parts.append(Part(name="", role=role))
        return design

    # ------------------------------------------------------------- references

    def instance_ids(self) -> dict[int, int | None]:
        """The instance number of each part, keyed by object identity.

        Parts that share a name are numbered from 1 in list order, but only
        when every one of them has the same role. This is the rule the web
        interface applies, and the service reads the resulting references.
        """
        groups: dict[str, list[Part]] = {}
        for part in self._named_components():
            if part.name:
                groups.setdefault(part.name, []).append(part)

        numbers: dict[int, int | None] = {id(part): None for part in self.parts}
        for members in groups.values():
            if len(members) < 2:
                continue
            if len({member.role for member in members}) != 1:
                continue
            for number, member in enumerate(members, start=1):
                numbers[id(member)] = number
        return numbers

    def wire_name(self, part: Part) -> str:
        """How operons and interactions refer to `part`."""
        instance = self.instance_ids().get(id(part))
        return f"{part.name}_{instance or 1}"

    def _named_components(self) -> list[Part]:
        """The parent and the parts, which is what the web interface numbers."""
        parent = Part(name=self.name, role=self.role, new=self.new, uri=self.uri)
        return [parent, *self.parts]

    def _require_known(self, part: Part, where: str) -> None:
        if not any(part is known for known in self.parts):
            raise DesignValidationError([_stray(where, part.name or "<unnamed>")])

    # ----------------------------------------------------------------- payload

    def to_payload(self) -> dict[str, Any]:
        """The body `POST /file/create` expects."""
        numbers = self.instance_ids()

        def reference(part: Part, where: str) -> str:
            self._require_known(part, where)
            return f"{part.name}_{numbers.get(id(part)) or 1}"

        components: list[dict[str, Any]] = [
            {
                "id": "component-principal",
                "uri": self.uri,
                "new": self.new,
                "identifier": self.identifier or self.name,
                "name": self.name,
                "description": self.description,
                "role": self.role.value,
            }
        ]
        for part in self.parts:
            entry: dict[str, Any] = {
                "id": part.id,
                "uri": part.uri,
                "new": part.new,
                "identifier": part.identifier or part.name,
                "name": part.name,
                "description": part.description,
                "role": part.role.value,
                "sequence": part.sequence.lower(),
                # The web interface sends an empty string rather than 0 when a
                # part carries no sequence, which is every registry part.
                "sequence_length": len(part.sequence) if part.sequence else "",
            }
            instance = numbers.get(id(part))
            if instance is not None:
                entry["instance_id"] = instance
            components.append(entry)

        expressions = [
            {
                "id": operon.id,
                "name": operon.name,
                "constitutive": operon.constitutive,
                "components": [reference(part, f"operons[{index}]") for part in operon.parts],
                "unions": [
                    {
                        "id": union.id,
                        "type": union.type.value,
                        "from": reference(union.source, f"operons[{index}].unions"),
                        "to": reference(union.target, f"operons[{index}].unions"),
                    }
                    for union in operon.unions
                ],
            }
            for index, operon in enumerate(self.operons)
        ]

        species_names = {id(species) for species in self.species}
        interactions = []
        for index, interaction in enumerate(self.interactions):
            participants: dict[str, list[str]] = {}
            for role, members in interaction.participants.items():
                named = []
                for member in members:
                    if isinstance(member, ExternalSpecies):
                        if id(member) not in species_names:
                            raise DesignValidationError([_stray(f"interactions[{index}]", member.name)])
                        named.append(member.name)
                    else:
                        named.append(reference(member, f"interactions[{index}]"))
                participants[role.value] = named
            interactions.append({"id": interaction.id, "type": interaction.type.value, "participants": participants})

        # The service builds no functional system without operons, and ignores
        # interactions and species when there are none.
        has_system = bool(expressions)
        return {
            "namespace": self.namespace,
            "components": components,
            "expressions": expressions,
            "interactions": interactions if has_system else [],
            "eds": (
                [
                    {"id": species.id, "name": species.name, "type": species.type.value, "uri": species.uri}
                    for species in self.species
                ]
                if has_system
                else []
            ),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Design":
        """Rebuild a design from a `POST /file/create` body."""
        components = list(payload.get("components") or [])
        if not components:
            raise ValueError("a design payload needs at least the parent component")
        head, *rest = components

        design = cls(
            name=str(head.get("name") or ""),
            role=Role(head.get("role") or Role.ENGINEERED_REGION.value),
            description=str(head.get("description") or ""),
            namespace=str(payload.get("namespace") or ""),
            new=bool(head.get("new", True)),
            uri=str(head.get("uri") or IGEM_URI),
            identifier=str(head.get("identifier") or ""),
        )

        by_reference: dict[str, Part] = {}
        for entry in rest:
            part = Part(
                name=str(entry.get("name") or ""),
                role=Role(entry["role"]),
                new=bool(entry.get("new", False)),
                uri=str(entry.get("uri") or IGEM_URI),
                description=str(entry.get("description") or ""),
                sequence=str(entry.get("sequence") or ""),
                identifier=str(entry.get("identifier") or ""),
                id=str(entry.get("id") or _new_id()),
            )
            design.parts.append(part)
            by_reference[f"{part.name}_{entry.get('instance_id') or 1}"] = part

        species_by_name: dict[str, ExternalSpecies] = {}
        for entry in payload.get("eds") or []:
            species = ExternalSpecies(
                name=str(entry.get("name") or ""),
                type=ExternalType(entry["type"]),
                uri=str(entry.get("uri") or ""),
                id=str(entry.get("id") or _new_id()),
            )
            design.species.append(species)
            species_by_name[species.name] = species

        def resolve(reference: str) -> Part | ExternalSpecies:
            if reference in by_reference:
                return by_reference[reference]
            if reference in species_by_name:
                return species_by_name[reference]
            raise ValueError(f"the payload refers to {reference!r}, which it does not define")

        for entry in payload.get("expressions") or []:
            operon = Operon(
                name=str(entry.get("name") or ""),
                constitutive=bool(entry.get("constitutive", False)),
                id=str(entry.get("id") or _new_id()),
            )
            for reference in entry.get("components") or []:
                member = resolve(str(reference))
                if isinstance(member, Part):
                    operon.parts.append(member)
            for union in entry.get("unions") or []:
                source, target = resolve(str(union["from"])), resolve(str(union["to"]))
                if isinstance(source, Part) and isinstance(target, Part):
                    operon.unions.append(
                        Union(
                            source=source,
                            target=target,
                            type=UnionType(union.get("type") or UnionType.ORDER.value),
                            id=str(union.get("id") or _new_id()),
                        )
                    )
            design.operons.append(operon)

        for entry in payload.get("interactions") or []:
            participants: dict[ParticipationRole, list[Part | ExternalSpecies]] = {}
            for role, members in (entry.get("participants") or {}).items():
                participants[ParticipationRole(role)] = [resolve(str(member)) for member in members]
            design.interactions.append(
                Interaction(
                    type=InteractionType(entry["type"]),
                    participants=participants,
                    id=str(entry.get("id") or _new_id()),
                )
            )

        return design

    # -------------------------------------------------------------- validation

    def validate(self) -> "list[Any]":
        """Everything wrong with this design, worst first."""
        from gcai.validation import validate_design

        return validate_design(self)


def _stray(where: str, name: str) -> Any:
    from gcai.validation import Issue

    return Issue(
        severity="error",
        path=where,
        message=f"{name!r} is not one of this design's parts or species; " "reference the same object the design holds",
    )


def iter_parts(items: Iterable[Sequence[Part]]) -> list[Part]:
    """Flatten groups of parts, keeping order and dropping repeats by identity."""
    seen: list[Part] = []
    for group in items:
        for part in group:
            if not any(part is known for known in seen):
                seen.append(part)
    return seen
