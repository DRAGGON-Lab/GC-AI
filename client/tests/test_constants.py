"""The client's tables have to agree with the service's description."""

from __future__ import annotations

from pathlib import Path

import pytest

from gcai.constants import (
    PARTICIPATIONS,
    ROLE_TO_SO,
    SEARCHABLE_ROLES,
    SO_TO_ROLE,
    ExternalType,
    GlyphClass,
    InteractionType,
    ParticipationRole,
    Role,
    UnionType,
)

yaml = pytest.importorskip("yaml")
SPEC = Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"


@pytest.fixture(scope="module")
def schemas() -> dict:
    with SPEC.open() as handle:
        return dict(yaml.safe_load(handle)["components"]["schemas"])


@pytest.mark.parametrize(
    "enum, schema_name",
    [
        (Role, "ComponentRole"),
        (GlyphClass, "GlyphClass"),
        (InteractionType, "InteractionType"),
        (ParticipationRole, "ParticipationRole"),
        (ExternalType, "ExternalType"),
        (UnionType, "UnionType"),
    ],
)
def test_enum_matches_the_specification(schemas: dict, enum: type, schema_name: str) -> None:
    assert sorted(member.value for member in enum) == sorted(schemas[schema_name]["enum"])


def test_searchable_roles_match_the_specification(schemas: dict) -> None:
    assert sorted(role.value for role in SEARCHABLE_ROLES) == sorted(schemas["SearchableRole"]["enum"])


def test_mrna_is_a_role_but_not_searchable() -> None:
    assert Role.MRNA not in SEARCHABLE_ROLES
    assert Role.MRNA in set(Role)


def test_every_role_has_a_sequence_ontology_term() -> None:
    assert set(ROLE_TO_SO) == set(Role)
    assert len(SO_TO_ROLE) == len(ROLE_TO_SO), "two roles share a term"


def test_every_interaction_type_has_participation_roles() -> None:
    assert set(PARTICIPATIONS) == set(InteractionType)
    for roles in PARTICIPATIONS.values():
        assert roles, "an interaction type with no participation roles"
