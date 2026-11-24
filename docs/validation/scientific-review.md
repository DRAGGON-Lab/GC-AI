# Independent implementation review

This agent review supports, and does not replace, the human scientific review
required by epic #6. Reviewed the changed physical assembly, request validation,
functional participant resolution, export/convert boundary, Python validation and
React submission paths against ADR 0001.

## ADR acceptance

On 23 November 2026, the user explicitly stated “I approve the ADR” in the project
conversation. ADR 0001 is therefore Accepted, including `Order` as relative
sequence order and legacy `Regulate` as its deprecated positional alias.
Functional regulation uses typed interactions. This approval records acceptance
of the decision; the remaining scientific, live integration and deployment gates
remain tracked separately in acceptance-matrix.md and the security verification
report.

## Confirmed defect found and corrected

**P1: a species could resolve to an operon with the same name.** An operon named
`GFP` and a Protein species named `GFP` were both accepted. `Genetic Production`
with `Product: ["GFP"]` resolved to the operon's DNA `LocalSubComponent` because
name lookup traversed operon features before species. The requested protein was
silently replaced by DNA in the functional relationship.

The backend now rejects operon names colliding with species, part wire references
or previous operons, and keeps an explicit participant map restricted to assembly
references and requested species. A backend regression covers this payload.

## Scientific evidence

The exact original YES gate reproduces the historical 0-versus-13 validator
symptom. All errors identify contradictory scar-separated `meets` constraints.
The changed backend's six full/structural recorded-data replays pass both
pySBOL3 and sbol-rs; source hashes and full reports are saved alongside them.
This is evidence for the specified graph corrections, not a claim that either
validator can establish biological truth.

## Protein annotation correction

The pre-existing generator assigned GO:0003700 (DNA-binding transcription factor
activity) to every species whose type is `Protein`, including GFP. Molecular type
alone does not establish this function. This annotation predates the epic changes;
the blanket role assignment has now been removed, with local and external protein
regressions. Protein molecular type and supplied definition URIs are retained.
Passing SBOL conformance checks does not substantiate that biological annotation.

No additional confirmed new scientific defect was found in the reviewed paths.
Live-service unavailability is a verification prerequisite, not a code defect.
