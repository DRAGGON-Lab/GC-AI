"""A client for the GC-AI symbol detection and SBOL3 generation service."""

from gcai.client import DEFAULT_URL, GCAIClient
from gcai.constants import (
    GLYPH_TO_ROLE,
    IGEM_URI,
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
from gcai.design import Design, ExternalSpecies, Interaction, Operon, Part, Union, name_parts
from gcai.errors import (
    DesignValidationError,
    GCAIConnectionError,
    GCAIError,
    GCAIResponseError,
)
from gcai.models import Box, BuildResult, CreateResult, Detection, Glyph, PartDetails
from gcai.validation import Issue, validate_design

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_URL",
    "GCAIClient",
    "GLYPH_TO_ROLE",
    "IGEM_URI",
    "PARTICIPATIONS",
    "ROLE_TO_SO",
    "SEARCHABLE_ROLES",
    "SO_TO_ROLE",
    "Box",
    "BuildResult",
    "CreateResult",
    "Design",
    "DesignValidationError",
    "Detection",
    "ExternalSpecies",
    "ExternalType",
    "GCAIConnectionError",
    "GCAIError",
    "GCAIResponseError",
    "Glyph",
    "GlyphClass",
    "Interaction",
    "InteractionType",
    "Issue",
    "Operon",
    "Part",
    "PartDetails",
    "ParticipationRole",
    "Role",
    "USER_AGENT",
    "Union",
    "UnionType",
    "__version__",
    "name_parts",
    "validate_design",
]

from gcai.client import USER_AGENT  # noqa: E402
