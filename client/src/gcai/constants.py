"""The enumerated values the GC-AI service accepts.

Each table mirrors one in the service, named in the comment above it. The
`test_constants` tests check every table against `docs/openapi.yaml`, so the
service's description and this module cannot drift apart.
"""

from __future__ import annotations

import re
from enum import Enum


# backend/app/data_configs/glyphs.yaml
class GlyphClass(str, Enum):
    """A class the detection model can emit."""

    APTAMER = "aptamer"
    CDS = "cds"
    CDS_ARROW = "cds-arrow"
    ENGINEERED_REGION = "engineered-region"
    INERT_DNA_SPACER = "inert-dna-spacer"
    NCRNA = "ncrna"
    OPERATOR = "operator"
    ORIGIN_OF_REPLICATION = "origin-of-replication"
    ORIGIN_OF_TRANSFER = "origin-of-transfer"
    POLYA = "polyA"
    PRIMER_BINDING_SITE = "primer-binding-site"
    PROMOTER = "promoter"
    RIBOSOME_ENTRY_SITE = "ribosome-entry-site"
    TERMINATOR = "terminator"


# backend/app/utils/file.py, component_map
class Role(str, Enum):
    """A role a component in a design may take."""

    PROMOTER = "Promoter"
    RBS = "RBS"
    CDS = "CDS"
    TERMINATOR = "Terminator"
    OPERATOR = "Operator"
    ENGINEERED_REGION = "Engineered-Region"
    APTAMER_DNA = "Aptamer-DNA"
    APTAMER_RNA = "Aptamer-RNA"
    INERT_DNA_SPACER = "Inert-DNA-Spacer"
    NCRNA = "Ncrna"
    POLYA_SITE = "PolyA-Site"
    PRIMER_BINDING_SITE = "Primer-Binding-Site"
    ORIGIN_OF_TRANSFER = "Origin-Of-Transfer"
    ORIGIN_OF_REPLICATION = "Origin-Of-Replication"
    MRNA = "mRNA"


# backend/app/routes/component_routes.py, part_type_map
SEARCHABLE_ROLES: frozenset[Role] = frozenset(set(Role) - {Role.MRNA})
"""The roles the bundled registry can be searched by.

`mRNA` is a valid component role but no registry part type maps to it, so
`GET /component/names` rejects it.
"""


class UnionType(str, Enum):
    """The relationship a union asserts between two features.

    Both are written as a `meets` constraint, so they are indistinguishable in
    a generated document.
    """

    ORDER = "Order"
    REGULATE = "Regulate"


# backend/app/utils/file.py, interaction_mapping
class InteractionType(str, Enum):
    INHIBITION = "Inhibition"
    STIMULATION = "Stimulation"
    BIOCHEMICAL_REACTION = "Biochemical Reaction"
    NON_COVALENT_BINDING = "Non-Covalent Binding"
    DEGRADATION = "Degradation"
    CONTROL = "Control"
    GENETIC_PRODUCTION = "Genetic Production"


# backend/app/utils/file.py, role_mapping
class ParticipationRole(str, Enum):
    INHIBITOR = "Inhibitor"
    INHIBITED = "Inhibited"
    STIMULATOR = "Stimulator"
    STIMULATED = "Stimulated"
    REACTANT = "Reactant"
    PRODUCT = "Product"
    MODIFIER = "Modifier"
    MODIFIED = "Modified"
    TEMPLATE = "Template"
    PROMOTER = "Promoter"


# backend/app/utils/file.py, ed_mapping
class ExternalType(str, Enum):
    SIMPLE_CHEMICAL = "Simple Chemical"
    PROTEIN = "Protein"
    RESTRICTION_ENZYME = "Restriction Enzyme"


# backend/app/routes/component_routes.py, participation_map
PARTICIPATIONS: dict[InteractionType, tuple[ParticipationRole, ...]] = {
    InteractionType.INHIBITION: (ParticipationRole.INHIBITOR, ParticipationRole.INHIBITED),
    InteractionType.STIMULATION: (ParticipationRole.STIMULATOR, ParticipationRole.STIMULATED),
    InteractionType.BIOCHEMICAL_REACTION: (
        ParticipationRole.REACTANT,
        ParticipationRole.MODIFIER,
        ParticipationRole.PRODUCT,
    ),
    InteractionType.NON_COVALENT_BINDING: (ParticipationRole.REACTANT, ParticipationRole.PRODUCT),
    InteractionType.DEGRADATION: (ParticipationRole.REACTANT,),
    InteractionType.CONTROL: (ParticipationRole.MODIFIER, ParticipationRole.MODIFIED),
    InteractionType.GENETIC_PRODUCTION: (
        ParticipationRole.PROMOTER,
        ParticipationRole.TEMPLATE,
        ParticipationRole.PRODUCT,
    ),
}
"""The participation roles that are meaningful for each interaction type.

The service does not enforce this: it accepts any `ParticipationRole` on any
interaction type and writes the matching SBO term. `validate_design` reports a
mismatch, because the service will not.
"""

# frontend/src/utils/PredictionUtils.jsx, with cds-arrow added.
GLYPH_TO_ROLE: dict[GlyphClass, Role] = {
    GlyphClass.PROMOTER: Role.PROMOTER,
    GlyphClass.RIBOSOME_ENTRY_SITE: Role.RBS,
    GlyphClass.CDS: Role.CDS,
    GlyphClass.CDS_ARROW: Role.CDS,
    GlyphClass.TERMINATOR: Role.TERMINATOR,
    GlyphClass.OPERATOR: Role.OPERATOR,
    GlyphClass.ENGINEERED_REGION: Role.ENGINEERED_REGION,
    GlyphClass.APTAMER: Role.APTAMER_DNA,
    GlyphClass.INERT_DNA_SPACER: Role.INERT_DNA_SPACER,
    GlyphClass.NCRNA: Role.NCRNA,
    GlyphClass.POLYA: Role.POLYA_SITE,
    GlyphClass.PRIMER_BINDING_SITE: Role.PRIMER_BINDING_SITE,
    GlyphClass.ORIGIN_OF_TRANSFER: Role.ORIGIN_OF_TRANSFER,
    GlyphClass.ORIGIN_OF_REPLICATION: Role.ORIGIN_OF_REPLICATION,
}
"""Which role each detected glyph class becomes.

`cds-arrow` maps to CDS here. The web interface leaves it unmapped, which
produces a component whose role the service rejects.
"""

ROLE_TO_GLYPHS: dict[Role, frozenset[GlyphClass]] = {}
for _glyph, _role in GLYPH_TO_ROLE.items():
    ROLE_TO_GLYPHS[_role] = ROLE_TO_GLYPHS.get(_role, frozenset()) | {_glyph}

# backend/app/utils/file.py, component_map
ROLE_TO_SO: dict[Role, str] = {
    Role.PROMOTER: "SO:0000167",
    Role.RBS: "SO:0000139",
    Role.CDS: "SO:0000316",
    Role.TERMINATOR: "SO:0000141",
    Role.OPERATOR: "SO:0000057",
    Role.ENGINEERED_REGION: "SO:0000804",
    Role.APTAMER_DNA: "SO:0000032",
    Role.APTAMER_RNA: "SO:0000033",
    Role.INERT_DNA_SPACER: "SO:0002223",
    Role.NCRNA: "SO:0000655",
    Role.POLYA_SITE: "SO:0000553",
    Role.PRIMER_BINDING_SITE: "SO:0005850",
    Role.ORIGIN_OF_TRANSFER: "SO:0000724",
    Role.ORIGIN_OF_REPLICATION: "SO:0000296",
    Role.MRNA: "SO:0000234",
}

SO_TO_ROLE: dict[str, Role] = {term: role for role, term in ROLE_TO_SO.items()}

RNA_ROLES: frozenset[Role] = frozenset({Role.APTAMER_RNA, Role.NCRNA, Role.POLYA_SITE, Role.MRNA})
"""Roles given the RNA SBO type.

A design may mix them with DNA parts: both sequence encodings resolve to the
same IUPAC nucleotide format, so the service accepts the combination.
"""

IGEM_URI = "http://parts.igem.org/"

DISPLAY_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
"""A part name has to match this, because it becomes an SBOL displayId."""

IUPAC_DNA = frozenset("acgtrykmswbdhvn")
