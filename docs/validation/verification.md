# Implementation verification

Baseline: upstream main `38906ca3c653b12af678bc03c3df253ca2b91b24`.
Branch: `fix/sbol3-correctness-epic`. Python 3.12.13.
Commands below ran from the repository root unless specified. Exit status 0
means the check completed; unavailable services are not counted as passes.

| Command / check | Result |
| --- | --- |
| `python -m pytest backend/tests -q --disable-warnings` | 46 passed; exit 0. Dependency deprecation warnings remain. |
| `cd client && python -m pytest -q` | 123 passed, 22 live integration tests deselected; exit 0. |
| `cd frontend && npm test` | 4 passed; exit 0. |
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
This is not the human scientific approval required before merge. See
scientific-review.md for the inherited protein-role mapping concern.

PR #5 provenance: https://github.com/DRAGGON-Lab/GC-AI/pull/5 . Its intended
examples/client delta is included, with corrections for the changed semantics.
Original docs/examples artifacts are unchanged. See acceptance-matrix.md for
remaining issue-closure gates. No live integration or issue closure is claimed.
