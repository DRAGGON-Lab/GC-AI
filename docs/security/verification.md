# Epic #7 implementation evidence

Base: `9bba7de2dd82` (starting main). Initial tested integration revision: `77c279eac6db312351734398543c587c29d5feae`, tree `180c6745d2a6d5c5fa1792b3be7ee55c117df92a` before the final credential-safe logging refinement. Tested on macOS, Python 3.12.13, NumPy 1.26.4, Pillow 13.0.0, pinned Flask/SBOL packages. This is implementation evidence, not an assertion that production migration or rotation occurred. Seven focused dependent PRs preserve child ownership; deploy the final integrated source and maintained clients together (client 0.2.0).

| Child | Evidence | Result / remaining gate |
| --- | --- | --- |
| #17 | Actual route malformed JSON/types/roles/registry errors, methods/header preservation, safe failures, Origin/preflight | API boundary suite 10 passed; existing export validation retained |
| #15 | Persistent cross-process/restart lookup, private permissions, no-follow symlinks, collision, TTL/mtime invariance, deleted handles, publication failure, cleanup/read race and crashed staging | Handle regressions pass; all maintained clients use structural_handle; hourly janitor provided |
| #18 | A/missing/B and barrier-controlled A/B full/structural RDF identity/namespace/reference isolation, preexisting library global namespace, invalid-control rejection | 21 namespace tests passed; independent scientific review and strict reconciliation passed |
| #19 | Every requested format, actual parsed sequence/ranges/strands against committed examples, unsupported sequence/orientation, partial conversion failure/retry, SDK archive completeness | 31 combined artifact/conversion tests passed; independent Biopython extraction matched all 38 subcomponents in three examples |
| #20 | Actual Pillow PNG/JPEG decode, corrupt/truncated/multiframe/unsupported bytes, limits before model execution, concurrent admission and failure recovery | Mocked detector runner with real image decoder; actual checkpoint/GPU not_run |
| #21 | Unread-result-sensitive SELECT1 fake, query/fetch/cleanup failures, readiness503 and liveness independence, synchronized cold initialization | 39 combined inference/readiness tests passed before later extra checkpoint tests; SDK calls readiness |
| #16 | Loopback defaults, WSGI configuration, mounted credential support, explicit browser origins, Docker image/CI and coordinated environment PR | Linux dependency resolution passed; Application Docker runtime and dedicated MySQL smoke passed on GitHub; hosted acceptance and operator rotation remain gated; remain open |

Executed integrated commands (exit 0):

```sh
/private/tmp/gcai-venv/bin/python -m pytest backend/tests -q --disable-warnings
# 176 passed (checkpoint/GPU mocked; real Pillow and local converters)
/private/tmp/gcai-venv/bin/python -m pytest client/tests -q --disable-warnings
# 146 passed, 22 integration tests deselected
npm --prefix frontend test
# 12 passed
npm --prefix frontend run lint
npm --prefix frontend run build
/private/tmp/gcai-venv/bin/python -m mypy --config-file client/pyproject.toml client/src
/private/tmp/gcai-venv/bin/flake8 --config client/.flake8 client/src client/tests
/private/tmp/gcai-venv/bin/black --check --config client/pyproject.toml client/src client/tests
/private/tmp/gcai-venv/bin/isort --check-only --settings-path client/pyproject.toml client/src client/tests
redocly lint docs/openapi.yaml
PYTHONPATH=backend:client/src /private/tmp/gcai-venv/bin/python tools/reconcile_sbol_validation.py \
  --mode verify --probe /private/tmp/gcai-sbol-target/debug/gcai-sbol-diagnostics \
  --regenerate /private/tmp/gcai-epic7-final --output /private/tmp/gcai-epic7-final-report.json
# result passed, violations [], execution_errors []
```

Evidence files were produced in `/private/tmp/gcai-epic7-*`. They are local execution artifacts, not portable deployment receipts. The strict reconciliation includes immutable historical diagnostics and six regenerated validated documents. Runtime Linux dependencies resolved using `uv pip compile backend/requirements-production.txt --python-version 3.12 --python-platform x86_64-manylinux_2_28`; the resulting lockfile is committed.

Review findings fixed before publication: namespace backslash/control inconsistency, unsupported feature-level reverse orientation, offline detector construction incorrectly requesting pretrained downloads, Nginx/MySQL consumer secret permissions, executable MySQL init script scope, remote root account rotation gap, and Docker fixture mount layout. A preexisting React effect warning was fixed by using a functional state update that returns the previous state when available names have not changed; frontend lint now passes.

The environment repository's eight daemon-independent tests verify rendered profiles and private consumer secret preparation. Its Docker workflow must run against the exact reviewed application SHA. This machine's Docker socket is absent. Full authenticated hosted smoke is pending. No real checkpoint/GPU execution, live legacy registry access, legacy asset import, production migration, credential rotation or operator receipt is claimed. Do not close #16 or epic #7 until the coordinated environment PR and these gates are accepted.

Post-review integration: PRs #31–#36 merged in dependency order. Main `afcb5255c5279378f708b427b61f5c2a06fb076d` exactly matches the tested #36 source tree (169 backend/123 client tests); its post-merge client, backend and conformance CI passed. Deployment PR #37 remains draft; #16 and epic #7 stay open.

[Application Docker CI](https://github.com/DRAGGON-Lab/GC-AI/actions/runs/44932338230) passed source image builds, 54 real-decoder/artifact/conversion tests inside the production runtime, and Gunicorn liveness200/degraded-readiness503. The detector runner remains mocked; no checkpoint/GPU result is implied. The first environment Docker run found a root-over-TCP health-probe mismatch; the corrected read-only application-account probe passed [dedicated MySQL Docker CI](https://github.com/Gonza10V/GC-AI-environment/actions/runs/45162255399). Full authenticated hosted smoke is the remaining CI check. Final runtime results belong in the coordinated PR's execution receipt. No operator migration/rotation is claimed.

Implementation fingerprint over sorted paths/content in `backend/app`, `client/src` and `frontend/src` (excluding bytecode/logs): SHA256 `afd7cf51b6e0f40b961c8b01bb198a6b5859ab8ad1d6605261fb48caf575a34e`. The final refinement removes raw dependency exceptions from export/cleanup logs. Its actual-route regression reproduced a password leak before the fix; the final 176-test backend suite and strict dual-validator reconciliation both passed. Independent boundary/export review reran 62 regressions successfully. Final source revisions are recorded by the PR and linked CI runs.

MCP credential logging refinement: a regression reproduced raw dependency credentials in unexpected-tool logs. The handler now records only the exception class. All 146 client tests passed, including actual MCP inference/create error paths proving neither protocol responses nor logs contain the synthetic credential. The real pinned synthetic import and fresh MySQL/grant jobs also passed [Docker CI](https://github.com/Gonza10V/GC-AI-environment/actions/runs/45163757429); these fixtures are not real legacy assets or production receipts. Hosted ingress verification remains pending the proxy-only edge-network correction.
