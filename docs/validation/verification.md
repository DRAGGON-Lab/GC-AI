# Implementation verification

Baseline: upstream main `38906ca3c653b12af678bc03c3df253ca2b91b24`.
Branch: `fix/sbol3-correctness-epic`. Python 3.12.13.
Commands below ran from the repository root unless specified. Exit status 0
means the check completed; unavailable services are not counted as passes.

| Command / check | Result |
| --- | --- |
| `python -m pytest backend/tests -q --disable-warnings` | 68 passed (52 export/identity/annotation tests and 16 reconciliation tests); exit 0. Dependency deprecation warnings remain. |
| `cd client && python -m pytest -q` | 123 passed, 22 live integration tests deselected; exit 0. |
| `cd frontend && npm test` | 10 passed; exit 0. |
| `cd frontend && npm run build` | Passed; exit 0. |
| ESLint on changed frontend files | Passed; exit 0. Global lint retains two existing hook dependency warnings in Interaction.jsx and PredictionAccordion.jsx. |
| `python -m mypy --config-file client/pyproject.toml client/src examples` | 15 source files; exit 0. |
| `python -m black --check --config client/pyproject.toml client examples` | 34 Python files; exit 0. Notebook formatting skipped: optional Jupyter formatter dependencies absent. |
| `python -m isort --check-only --settings-path client/pyproject.toml client examples` | Passed; exit 0. |
| `python -m flake8 --config client/.flake8 client examples` | Passed; exit 0. |
| `git diff --check` | Passed; exit 0. |
| Reconciliation command in README.md | Completed; exit 0. All six regenerated documents: 0 pySBOL3 and 0 Rust findings. Final source hashes match replay provenance. |
| `PRE_COMMIT_HOME=/private/tmp/gcai-precommit python -m pre_commit run --all-files` | Failed initialization, exit 3: hook repository GitHub DNS fetch unavailable. Direct available checks listed above ran separately. |
| Live detector/MySQL/SBOL DB and notebook execution | not_run: no URLs; Docker daemon unavailable and installed Docker.app has no launchable executable. |

The test environment used Flask 2.0.1, Werkzeug 2.0.3, pySBOL3
1.2.0.post0, sbol-utilities 1.0a17 and pytest 9.2.0. Backend test dependency
pins are committed. Runtime validator pins match this environment. Rust probe
uses pinned sbol 0.2.2 with Cargo.lock. Exact scientific versions, raw diagnostics
and fixture hashes are in committed-examples.json and regenerated provenance.

Independent engineering/scientific code review found and corrected retention,
optional-description validation and species/operon reference ambiguity defects.
The independent code review does not establish human scientific approval.
ADR 0001 was subsequently accepted by explicit user approval on 23 November 2026;
remaining scientific and live verification gates are tracked in acceptance-matrix.md.
The inherited blanket protein-role mapping has been removed; see scientific-review.md.

PR #5 provenance: https://github.com/DRAGGON-Lab/GC-AI/pull/5 . Its intended
examples/client delta is included, with corrections for the changed semantics.
Original docs/examples artifacts are unchanged. See acceptance-matrix.md for
remaining issue-closure gates. No live integration or issue closure is claimed.

## Four review corrections

The React selection stores source kind and stable source ID separately from the
interaction row ID. Four cross-layer tests invoke those exact JavaScript helpers,
submit through Flask, parse returned RDF/XML, and assert that same-name GFP DNA
instances and local/external GFP proteins remain different participation targets.
Two export tests assert protein molecular type/definition are retained without
inferred transcription-factor activity. All 123 client tests still pass.

Reconciliation now defaults to verification: original hashes and diagnostic
identities must match an immutable baseline; all six fresh generated files must
have zero findings from both pinned validators. Capture mode is explicitly
non-gating. Sixteen tests cover findings, changed historical evidence, missing
prerequisites, parse/execution failures and output-overwrite protection.
The new conformance workflow builds the locked probe, regenerates temporary RDF
and uploads verification evidence; remote CI execution is not claimed here.

The final local command was:

```sh
/private/tmp/gcai-venv/bin/python tools/reconcile_sbol_validation.py --mode verify \
  --probe /private/tmp/gcai-sbol-target/debug/gcai-sbol-diagnostics \
  --regenerate docs/validation/regenerated \
  --output docs/validation/committed-examples.json
```

Exit 0, result passed. All regenerated RDF/provenance and raw reports were
refreshed after the backend correction. Original examples remain unchanged.
ADR 0001 was Proposed at the time of these checks. On 23 November 2026, the user
explicitly stated “I approve the ADR” in the project conversation, establishing
acceptance of its generation and relationship semantics. This approval supplies
the decision evidence; live integration and deployment verification remain
separate requirements.

## PR #30 detector readiness review corrections

Follow-up to reviewed revision `281e0e84d7cf3d7666c68d8b0e0fee05c4c50ccc`,
using the same Python 3.12.13 detector-free environment. The new readiness suite
first reproduced five failures before the correction. The shared lazy loader now
serializes initialization per process and rejects absent models; valid names
lookups verify it before querying MySQL. Initialization failures remain retryable.
Independent engineering review found no material issue in the final diff.

Executed checks after the correction (all exit 0):

- `/private/tmp/gcai-venv/bin/python -m pytest backend/tests -q --disable-warnings`:
  77 passed, including nine new readiness/concurrency cases. Dependency warnings
  remain. Torch and MySQL are replaced by controlled stubs in these cases.
- From `client/`, `/private/tmp/gcai-venv/bin/python -m pytest -q`:
  123 passed, 22 live integration tests deselected.
- `/private/tmp/gcai-venv/bin/python tools/reconcile_sbol_validation.py --mode verify
  --probe /private/tmp/gcai-sbol-target/debug/gcai-sbol-diagnostics
  --regenerate /private/tmp/gcai-readiness-review/regenerated
  --output /private/tmp/gcai-readiness-review/report.json`:
  all six regenerated outputs have zero pySBOL3 and Rust findings; no violations
  or execution errors. Original historical evidence was preserved.
- OpenAPI YAML parsed successfully; `git diff --check` passed.

Real checkpoint/GPU/MySQL verification: not_run; these checks establish the
readiness and synchronization contract using stubs. The separate existing
`/healthcheck/` unread-query defect is outside this correction.
