# ADR 0001: SBOL3 generation and relationship semantics

Status: Proposed — pending scientific review.

The behavior below describes the proposed interpretation implemented on this
branch. Formal scientific acceptance has not been recorded and remains a merge
prerequisite.

## Context

The generator previously treated the shared EDAM nucleotide encoding as evidence of
DNA molecular type, inserted BioBrick scars around unknown parts, used `meets` for
scar-separated parts, and silently omitted functional data without operons.
`Regulate` called the SBOL utilities positional `order` alias; it never created an
SBO regulatory interaction. These behaviors confuse physical composition and function.

## Decision

`components[0]` is the physical DNA assembly; subsequent components are its DNA
members. Their molecular type must be SBO DNA, and known sequences must contain
IUPAC DNA characters. EDAM `format_1207` remains the nucleotide sequence encoding;
it is not a molecular type test. RNA, protein and chemical species belong in the
functional system, including the new `DNA` and `RNA` species types.

A fully known DNA assembly retains the existing BioBrick scar policy. Unknown
sequence members remain valid structural features. No placeholder bases, scar-only
parent sequence or zero-length ranges are manufactured; an incompletely known
assembly has no assembled sequence or parent-coordinate ranges. Conversion that
requires the assembled sequence fails explicitly.

`Order` means relative sequence order and emits `sbol:precedes`, including between
scar-separated members. Legacy `Regulate` input remains a deprecated positional
alias with precisely the same meaning. New user interfaces offer `Order` only.
Callers intending functional regulation must choose a typed interaction such as
Stimulation, Inhibition or Control and provide compatible participation roles.

For example, both positional union spellings produce:

```turtle
@prefix sbol: <http://sbols.org/v3#> .
@prefix ex: <https://example.org/design/> .
ex:order1 a sbol:Constraint ;
    sbol:restriction sbol:precedes ;
    sbol:subject ex:promoter ; sbol:object ex:cds .
```

Actual stimulation instead produces a functional interaction:

```turtle
@prefix sbol: <http://sbols.org/v3#> .
@prefix sbo: <https://identifiers.org/SBO:> .
@prefix ex: <https://example.org/design/> .
ex:activation a sbol:Interaction ; sbol:type sbo:0000170 ;
    sbol:hasParticipation ex:regulatorParticipation, ex:targetParticipation .
ex:regulatorParticipation a sbol:Participation ;
    sbol:role sbo:0000459 ; sbol:participant ex:regulator .
ex:targetParticipation a sbol:Participation ;
    sbol:role sbo:0000643 ; sbol:participant ex:target .
```

Functional information creates a system even when there are no operons. Every
referenced assembly member is available in that system independently of operon
membership. Every requested relationship must resolve or generation fails; partial
functional success is not returned. An absolute definition URI creates an
`ExternallyDefined` feature; a species without one is a typed `LocalSubComponent`.
This preserves the unknown LuxR-AHL species without inventing its definition.

## Validation and compatibility

Every pySBOL3 finding blocks export, including warnings. The complete full and
structural documents must both pass before either is exposed. GC-AI's additional
DNA, reference and interaction invariants are mandatory for raw API callers too.

Existing request shapes and successful attachment/header contracts are retained.
Intentional graph differences are `meets` → `precedes`, local representation of
undefined species, preservation of functional data without operons, and removal of
invented assembled sequence for unknown parts. Original committed examples remain
historical inputs; they must not be overwritten to conceal these differences.

SBOL DB is a release verification tool rather than a per-export dependency. Each
registry finding requires a documented disposition. True conformance defects block
release; profile differences and tool defects require explicit scientific review.
A successful registry import is not a scientific-validity assertion.

## Sources

- [SBOL 3.0.1 specification](https://sbolstandard.org/docs/SBOL3.0.1.pdf)
- [pySBOL3 validation](https://pysbol3.readthedocs.io/en/latest/validation.html)
- [SBOL utilities component helpers](https://github.com/SynBioDex/SBOL-utilities/blob/develop/sbol_utilities/component.py)
