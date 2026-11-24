# Local integration and deployment review — 24 November 2026

Application baseline `fcde121`; ADR approval committed as `8339711`.
Environment baseline `DRAGGON-Lab/GC-AI-environment` main `2646936`.
Executed against a fresh local CPU review deployment, not production. Runtime
image identities and sanitized operational receipts are in the environment's
`verification` directory. Original historical SBOL examples remain unchanged.

| Executed check | Result |
| --- | --- |
| Backend regression suite, Python 3.12.13 | 177 passed |
| Client default unit suite | 146 passed;22 live cases deselected |
| Actual HTTP Python/CLI/MCP/React-conversion, private reports, notebook and TLS-pin policy regressions | 10 passed; detector/database replaced by explicit fakes in this suite |
| Full live client suite over verified localhost TLS with real checkpoint, MySQL 8.4 and disposable SBOL DB | 22 passed;146 unit cases deselected; no live tests skipped |
| Complete quickstart notebook | Executed with real detection, named registry parts, conversion, temporary registry publication/readback and cleanup |
| Real checkpoint inference route replay | All3 image records matched exact boxes/classes on CPU; [receipt](checkpoint-replay.json) |
| Strict pinned pySBOL3+sbol-rs verification | Passed; all 6 regenerated outputs have zero findings; immutable historical diagnostics retained |
| Environment configuration/bootstrap/import regressions | 14 passed |
| Fresh real registry import | 84285 rows; SELECT-only application grants; localhost-only root |
| Credential rotation in the new review project | New root/application credentials accepted; old root/application/workspace credentials rejected |
| Private backup/isolated fresh restore | 84285 rows; source/restored table checksum2942824569; accounts not restored |
| Production janitor command on shared review artifact volume | Expired test artifact removed |
| Frontend unit/lint/build | 19 tests passed; lint and production build passed |
| Actual Chromium workflow | All 14 role lists loaded; real image/SBOL/FASTA/GenBank flow passed; synthetic first-conversion503 preserved handle/selection and retry succeeded with exact parsed outputs |
| Runtime npm audit | Zero findings; unused debugger/Electron removed; [remaining development findings](dependency-audit.json) |
| Client mypy/flake8/black/isort, workflow YAML, Python/shell syntax, diff whitespace | Passed |

Representative commands:

```sh
python -m pytest backend/tests -q --disable-warnings
python -m pytest client/tests -q --disable-warnings
PYTHONPATH=backend:client/src python -m pytest tools/tests -q --disable-warnings
# Configure private authentication files, verified CA, and disposable registry first:
cd client && python -m pytest -m integration -q --disable-warnings
# Run the notebook sequentially with live inference tests; admission has no queue.
```

The first combined live run passed 21 tests and exposed an incorrect test-only MCP
wording assertion. It was corrected to verify 404 and the missing part identifier;
the targeted case and a fresh full 22-case run passed. An initial parallel notebook
run correctly received 503 inference admission; the complete sequential run passed.
Real legacy initialization also exposed a missing MYSQL_DATABASE input, and Docker
Desktop exposed host-bind execution-bit differences for MySQL init scripts. Both
have regressions and successful real execution after correction.

CPU verification used Python 3.12.16, Torch 2.6.0+cpu and TorchVision 0.21.0+cpu.
The exact executed package set is captured in backend/requirements-checkpoint.lock;
future verifier builds apply those constraints. The production CUDA runtime remains
a separate acceptance target. The project owner accepted the local UI and integration evidence on 24 November
2026; see [review-approval.md](review-approval.md). Public production migration,
production credential rotation, published release image digests, GPU parity and
integrated merge-to-main remain separate gates. Keep #16 and epic #7 open until
the coordinated changes and operator evidence are accepted.
