"""Assembling a design and turning it into a request."""

from __future__ import annotations

from typing import Any

import pytest

from gcai.constants import ExternalType, InteractionType, ParticipationRole, Role, UnionType
from gcai.design import Design, ExternalSpecies, Interaction, Operon, Part
from gcai.errors import DesignValidationError
from gcai.models import Detection
from tests.helpers import detection_payload


def design_with(*parts: Part) -> Design:
    design = Design(name="CIRCUIT", namespace="https://example.org/")
    design.parts.extend(parts)
    return design


def test_instance_numbers_are_absent_when_names_are_unique() -> None:
    design = design_with(
        Part(name="BBa_R0010", role=Role.PROMOTER),
        Part(name="BBa_B0034", role=Role.RBS),
    )
    assert set(design.instance_ids().values()) == {None}
    assert design.wire_name(design.parts[0]) == "BBa_R0010_1"


def test_parts_sharing_a_name_and_role_are_numbered_in_order() -> None:
    first = Part(name="BBa_B0034", role=Role.RBS)
    second = Part(name="BBa_B0034", role=Role.RBS)
    third = Part(name="BBa_B0034", role=Role.RBS)
    design = design_with(first, second, third)
    assert [design.wire_name(p) for p in (first, second, third)] == [
        "BBa_B0034_1",
        "BBa_B0034_2",
        "BBa_B0034_3",
    ]


def test_parts_sharing_a_name_with_different_roles_are_not_numbered() -> None:
    first = Part(name="SAME", role=Role.RBS)
    second = Part(name="SAME", role=Role.CDS)
    design = design_with(first, second)
    assert set(design.instance_ids().values()) == {None}


def test_the_parent_counts_towards_numbering() -> None:
    design = Design(name="SHARED", namespace="https://example.org/")
    part = Part(name="SHARED", role=Role.ENGINEERED_REGION)
    design.parts.append(part)
    assert design.instance_ids()[id(part)] == 2


def test_payload_puts_the_design_first_and_keeps_part_order() -> None:
    design = design_with(
        Part(name="BBa_R0010", role=Role.PROMOTER),
        Part(name="BBa_B0034", role=Role.RBS),
    )
    payload = design.to_payload()
    assert payload["components"][0]["id"] == "component-principal"
    assert payload["components"][0]["name"] == "CIRCUIT"
    assert [c["name"] for c in payload["components"][1:]] == ["BBa_R0010", "BBa_B0034"]


def test_payload_lowercases_sequences_and_sets_the_length() -> None:
    design = design_with(Part(name="NEW_PART", role=Role.CDS, new=True, sequence="ATGC"))
    entry = design.to_payload()["components"][1]
    assert entry["sequence"] == "atgc"
    assert entry["sequence_length"] == 4


def test_payload_refers_to_species_by_name_and_parts_by_instance() -> None:
    promoter = Part(name="BBa_R0010", role=Role.PROMOTER)
    design = design_with(promoter)
    species = ExternalSpecies(name="LacI", type=ExternalType.PROTEIN)
    design.species.append(species)
    design.operons.append(Operon(name="Operon 1", parts=[promoter]).chain())
    design.interactions.append(
        Interaction(
            type=InteractionType.INHIBITION,
            participants={
                ParticipationRole.INHIBITOR: [species],
                ParticipationRole.INHIBITED: [promoter],
            },
        )
    )
    participants = design.to_payload()["interactions"][0]["participants"]
    assert participants == {"Inhibitor": ["LacI"], "Inhibited": ["BBa_R0010_1"]}


def test_a_design_without_operons_drops_interactions_and_species() -> None:
    promoter = Part(name="BBa_R0010", role=Role.PROMOTER)
    design = design_with(promoter)
    design.species.append(ExternalSpecies(name="LacI", type=ExternalType.PROTEIN))
    design.interactions.append(
        Interaction(type=InteractionType.DEGRADATION, participants={ParticipationRole.REACTANT: [promoter]})
    )
    payload = design.to_payload()
    assert payload["interactions"] == []
    assert payload["eds"] == []


def test_chain_links_operon_members_in_sequence() -> None:
    a, b, c = (Part(name=f"P{i}", role=Role.CDS) for i in range(3))
    operon = Operon(name="Operon", parts=[a, b, c]).chain(UnionType.REGULATE)
    assert [(u.source.name, u.target.name, u.type) for u in operon.unions] == [
        ("P0", "P1", UnionType.REGULATE),
        ("P1", "P2", UnionType.REGULATE),
    ]


def test_referring_to_a_part_the_design_does_not_hold_is_refused() -> None:
    design = design_with(Part(name="BBa_R0010", role=Role.PROMOTER))
    stranger = Part(name="BBa_B0034", role=Role.RBS)
    design.operons.append(Operon(name="Operon", parts=[stranger]))
    with pytest.raises(DesignValidationError, match="not one of this design's parts"):
        design.to_payload()


def test_from_detection_keeps_order_and_leaves_names_empty() -> None:
    detection = Detection.from_response(
        detection_payload(["terminator", "promoter"], [[300, 0, 350, 50], [10, 0, 60, 50]])
    )
    design = Design.from_detection(detection, name="CIRCUIT")
    assert [part.role for part in design.parts] == [Role.PROMOTER, Role.TERMINATOR]
    assert all(part.name == "" for part in design.parts)


def strip_ids(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop the client-side keys, which the service does not read."""
    cleaned = {key: value for key, value in payload.items()}
    cleaned["components"] = [{k: v for k, v in c.items() if k != "id"} for c in payload["components"]]
    cleaned["expressions"] = [
        {
            **{k: v for k, v in e.items() if k not in {"id", "unions"}},
            "unions": [{k: v for k, v in u.items() if k != "id"} for u in e["unions"]],
        }
        for e in payload["expressions"]
    ]
    cleaned["interactions"] = [{k: v for k, v in i.items() if k != "id"} for i in payload["interactions"]]
    cleaned["eds"] = [{k: v for k, v in d.items() if k != "id"} for d in payload["eds"]]
    return cleaned


def test_round_trip_reproduces_each_committed_request(example_request: dict[str, Any]) -> None:
    rebuilt = Design.from_payload(example_request).to_payload()
    assert strip_ids(rebuilt) == strip_ids(example_request)
