"""Local checks, one test per rule."""

from __future__ import annotations

from gcai.constants import ExternalType, InteractionType, ParticipationRole, Role
from gcai.design import Design, ExternalSpecies, Interaction, Operon, Part, Union


def issues_for(design: Design, path: str) -> list[str]:
    return [issue.message for issue in design.validate() if issue.path == path]


def severities(design: Design, path: str) -> set[str]:
    return {issue.severity for issue in design.validate() if issue.path == path}


def minimal() -> Design:
    design = Design(name="CIRCUIT", namespace="https://example.org/")
    design.parts.append(Part(name="BBa_R0010", role=Role.PROMOTER))
    return design


def test_a_minimal_design_is_valid() -> None:
    assert minimal().validate() == []


def test_a_missing_namespace_is_an_error() -> None:
    design = minimal()
    design.namespace = ""
    assert severities(design, "namespace") == {"error"}
    assert "namespace" in issues_for(design, "namespace")[0]


def test_a_namespace_that_is_not_a_url_is_an_error() -> None:
    design = minimal()
    design.namespace = "example.org"
    assert severities(design, "namespace") == {"error"}


def test_a_name_that_is_not_a_display_id_is_an_error() -> None:
    design = minimal()
    design.parts[0].name = "BBa R0010"
    assert "displayId" in issues_for(design, "parts[0].name")[0]


def test_a_part_uri_without_a_separator_is_an_error() -> None:
    design = minimal()
    design.parts[0].uri = "http://parts.igem.org"
    assert "has to end in" in issues_for(design, "parts[0].uri")[0]


def test_a_new_part_without_a_sequence_is_a_warning() -> None:
    """The service builds it: the document gets the role and the order, no bases."""
    design = minimal()
    design.parts[0].new = True
    assert severities(design, "parts[0].sequence") == {"warning"}
    assert "no bases" in issues_for(design, "parts[0].sequence")[0]


def test_a_sequence_that_is_not_dna_is_an_error() -> None:
    design = minimal()
    design.parts[0].new = True
    design.parts[0].sequence = "atgzx"
    assert "not IUPAC DNA" in issues_for(design, "parts[0].sequence")[0]


def test_one_name_with_two_roles_is_an_error() -> None:
    design = minimal()
    design.parts.append(Part(name="BBa_R0010", role=Role.CDS))
    assert any("more than one role" in message for message in issues_for(design, "parts"))


def test_a_part_named_after_the_design_is_an_error() -> None:
    design = minimal()
    design.parts[0].name = "CIRCUIT"
    assert severities(design, "parts[0].name") == {"error"}


def test_an_rna_role_is_an_error() -> None:
    design = minimal()
    design.parts[0].role = Role.NCRNA
    assert severities(design, "parts[0].role") == {"error"}


def test_an_operon_holding_a_foreign_part_is_an_error() -> None:
    design = minimal()
    design.operons.append(Operon(name="Operon", parts=[Part(name="OTHER", role=Role.CDS)]))
    assert any("not one of this design's parts" in m for m in issues_for(design, "operons[0].parts"))


def test_an_operon_without_unions_is_valid() -> None:
    design = minimal()
    design.operons.append(Operon(name="Operon", parts=[design.parts[0]]))
    assert severities(design, "operons[0].unions") == set()


def test_a_union_endpoint_outside_the_operon_is_an_error() -> None:
    design = minimal()
    outsider = Part(name="BBa_B0034", role=Role.RBS)
    design.parts.append(outsider)
    operon = Operon(name="Operon", parts=[design.parts[0]])
    operon.unions.append(Union(source=design.parts[0], target=outsider))
    design.operons.append(operon)
    assert severities(design, "operons[0].unions.to") == {"error"}


def test_a_participation_role_wrong_for_its_type_is_an_error() -> None:
    design = minimal()
    design.operons.append(Operon(name="Operon", parts=[design.parts[0]]).chain())
    design.interactions.append(
        Interaction(
            type=InteractionType.INHIBITION,
            participants={ParticipationRole.STIMULATOR: [design.parts[0]]},
        )
    )
    message = issues_for(design, "interactions[0].participants.Stimulator")[0]
    assert "is not a participation role of Inhibition" in message


def test_a_species_uri_with_whitespace_is_an_error() -> None:
    design = minimal()
    design.species.append(ExternalSpecies(name="LacI", type=ExternalType.PROTEIN, uri="https://example.org/laci "))
    assert "whitespace" in issues_for(design, "species[0].uri")[0]


def test_a_local_species_without_a_uri_is_valid() -> None:
    design = minimal()
    design.species.append(ExternalSpecies(name="LacI", type=ExternalType.PROTEIN))
    assert severities(design, "species[0].uri") == set()


def test_interactions_without_operons_are_valid() -> None:
    design = minimal()
    design.interactions.append(
        Interaction(type=InteractionType.DEGRADATION, participants={ParticipationRole.REACTANT: [design.parts[0]]})
    )
    assert severities(design, "interactions") == set()


def test_errors_sort_before_warnings() -> None:
    design = minimal()
    design.namespace = ""
    design.parts[0].role = Role.NCRNA
    assert [issue.severity for issue in design.validate()][0] == "error"
