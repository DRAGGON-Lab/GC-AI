# Epic #6 acceptance evidence

This is a tracking contract, not an issue-closure assertion. The integration
owner must attach final test results and obtain scientific review before merge.

| Issue | Required evidence | Current evidence / remaining gate |
| --- | --- | --- |
| #9 | Truthy-tuple regression; both documents validated; bounded actionable errors; cleanup | Backend regression suite and atomic-export implementation; 68 backend tests passed; live and human review pending |
| #10 | DNA-only molecular types, valid coordinates, structural-only unknown sequence, mixed functional species | Backend generation regressions; six recorded-data replays pass both validators; live conversion still required |
| #11 | Shared role table; invalid role/type/reference rejection; multiple participants preserved; contract parity | Backend/client regression suites and synchronized OpenAPI; 68 backend and 123 client tests passed; see verification.md |
| #12 | No-operon functional preservation; all references resolve; React retains submitted information | Backend RDF assertions and client/UI regressions; live cross-client replay still required |
| #13 | Versions, commands, full findings, traceable fixtures, dispositions and release policy | Original 0/17, 0/35, 0/13 disagreements reproduced; six offline backend replays 0/0; live SBOL DB and scientific review pending |
| #14 | Concrete positional and functional RDF, deprecated legacy semantics, migration guidance | ADR 0001; implementation changes to precedes; scientific review pending |
| #17 | Malformed JSON/shape 400; missing part 404; semantic 422; sanitized 500; uniform contract | Backend negative tables and error-envelope implementation; 68 backend and 123 client tests passed; see verification.md |
| #22 | PR #5 examples/notebook/shared naming/MCP conversion guard and tests present; lint/typing/CI coverage | Intended PR #5 delta integrated; 123 client tests and direct lint/type checks passed; pre-commit wrapper blocked by hook DNS; PR #5 provenance linked below |
| #6 | Every child acceptance criterion met on main | Open: live checks, human scientific review, PR merge and post-merge verification required |

Source baseline: upstream `38906ca3c653b12af678bc03c3df253ca2b91b24`.
PR #5 provenance: https://github.com/DRAGGON-Lab/GC-AI/pull/5 .

Executed checks and limits: [verification.md](verification.md).

Review corrections: explicit React participant identities with exported-SBOL
regressions; no inferred protein function; mandatory generated conformance gate
and CI; ADR status Proposed. See verification.md for final executed results.
