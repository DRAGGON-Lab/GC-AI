# CPU research release candidate — epic #8

Starting source: GC-AI `3cace2414cab`; canonical environment
[DRAGGON-Lab/GC-AI-environment](https://github.com/DRAGGON-Lab/GC-AI-environment)
`29378b9a0e57`. Production cutover, production credential rotation and GPU
qualification remain separate epic #7 gates. Candidate publication requires
review of concrete qualification evidence and scientific acceptance.

## #22 integration acceptance

[PR #5](https://github.com/DRAGGON-Lab/GC-AI/pull/5), head
`25dd74dfd74164b05bb2af5c898289f90e9eb6a7`, was merged as `5690835` on its
original branch. [PR #30](https://github.com/DRAGGON-Lab/GC-AI/pull/30)
integrated its intended delta into main. This acceptance change preserves that
implementation; it does not cherry-pick the obsolete branch over current main.

Provenance comparison: `git diff 5690835^ 5690835 -- examples client .github
README.md` identifies 16 changed files. All three example entrypoints, both
example test modules, shared `name_parts` in `gcai.design`, its MCP caller and
the zero-base conversion guard remain present. Comparing `25dd74d` to the
starting main shows subsequent fixes to namespace isolation, opaque handles,
TLS authentication, explicit participant identity and sequence-aware exports.
Those fixes intentionally supersede the original wire behavior.

Executed on 24 November 2026, Python 3.12.13, clean starting main:

| Command | Result |
| --- | --- |
| `/private/tmp/gcai-venv/bin/python -m pytest client/tests -q` | exit 0; 146 passed, 22 live integrations deselected; db and MCP extras installed |
| `python -m mypy --config-file client/pyproject.toml client/src examples` | exit 0; 15 source files |
| Example imports | Included in `test_examples.py`; no live services needed |

The historical acceptance matrix contains earlier counts and prerequisites;
current release claims must use this candidate's own evidence. Historical
example inference records remain immutable and are regression evidence only.

Pre-commit rerun: exit 0, all eight hooks passed using pinned hook revisions and
`PRE_COMMIT_HOME=/private/tmp/gcai-precommit`. Initial hook environment setup
needed `cryptography==46.0.7` (the installed client test version) because the
newest transitive source distribution required unavailable local OpenSSL build
support. The final cached-hook run passed without network access or constraints.

## #23–#25 engineering checks

The expanded isolated backend suite passed 183 tests (exit 0). The built-app
Chromium harness first passed the generation/download/conversion workflow.
A new create-400 test then failed against the unchanged build: custom inputs
were missing after the response because their local mode reset on remount.
After keeping editors mounted and controlling custom mode from the draft,
all eight browser cases passed, including 400/500/network create errors,
conversion retry with the same opaque handle, retained registry successes,
confirmed reset and a late details response after a newer selection.
Failure trace/screenshot retained locally in
`/private/tmp/gcai-epic8/editor-regression-before`; CI retains equivalent failure
artifacts. Mocked browser evidence does not qualify real model or SBOL accuracy.

## #26–#28 runtime and scientific checks

The all-class contract spans YAML, Python, JavaScript and backend role sets;
background is excluded and inherited object names cannot become glyph roles.
RNA assembly restrictions remain unchanged. Independent engineering review
reproduced and verified corrections for second-image discard confirmation,
late camera permission cleanup and stable operon identities. Thirteen built-app
Chromium workflows now pass, including explicit human review before generation.

The expanded backend suite passed 191 tests before score additions. The real
loader's seven new integrity cases failed before correction, then all 29
checkpoint/readiness tests passed. Wheel and source distributions built and
installed outside the checkout; installed WSGI imports, CLI/WSGI liveness,
janitor, generation and conversion passed. This detector-free installed smoke
is distinct from real inference. The CPU image built from its hashed Linux lock
and immutable Python base. Safe `weights_only=True` execution against the
verified legacy checkpoint failed on its NumPy scalar global; trusted pickle
loading remains explicit behind mandatory integrity verification.

Scientific review verified the official pinned COCO evaluator on an independent
synthetic TP/FP fixture. Eleven evaluator/provenance tests pass, including the
float32 deployed-threshold boundary. These establish evaluator behavior, not
model accuracy. Twenty distinct source designs and the 80-image inventory are
in [the draft corpus](../benchmark/corpus-draft/inventory.json). Real physical
captures, approved ground truth and scientific acceptance remain outstanding.
No benchmark accuracy measurements or candidate qualification are claimed.

## Continuation qualification

Exact `a4b367fe85262657e19e71f59e2fc0b13ef7569a` CPU archives were built and
verified with environment `e142b837d982360257106f1a4cecccbf06ccc386`.
Both wheel and source installations passed outside the checkout using backend
`1.0.0rc1` and client `0.2.1rc1`. Private artifacts and hash-bound receipts are in
`/private/tmp/gcai-epic8/candidate-exact`.

The first disposable full-stack run passed real readiness, authenticated wire,
Python/CLI/MCP, generation and conversion checks. Live integrations executed
all 22 cases: 19 passed and three historical replay comparisons failed solely
because optional model scores were newly included. Historical records remain
immutable; the comparison now excludes only the newly added score field.
This failed run is retained at `/private/tmp/gcai-epic8/qualification-exact-1`;
its disposable services and volumes were removed. It does not qualify a release.

Independent review identified missing live admission checks and incomplete
prerelease evidence distribution. The wire suite now checks malformed/oversized
images, concurrent busy rejection and subsequent recovery. These checks passed
against the real disposable CPU service. Publication now attaches an allowlisted
archive containing the manifest, referenced reports, Python/OCI artifacts and
approved benchmark reproduction inputs; private execution logs are excluded.
Public distribution of these selected inputs remains part of bundle review.

Hosted CI rejected deliberate regression `7527f19` in both backend and cross-client
checks; correction `6fd846b` passed both on the disposable proof branch.
Both repositories' live merge protections were rechecked. The publication
environment is absent and configuration requires an explicit decision about
self-approval semantics. No publication or scientific acceptance is asserted.

## Docker interruption

The CPU image build completed. The subsequent real CPU replay produced no
receipt while Docker Desktop's VM was unavailable. Desktop logged a disk-full
shutdown at 17:34 UTC on 24 November 2026 (`init.log: no space left on device`).
Workspace sandbox socket denial is a separate restriction. The host later had
approximately 16 GiB free; recovery and fresh CPU replay are required before
counting this channel as passed. Existing review/database volumes are preserved.

Docker recovery completed: the VM and existing review/backend/MySQL services
recovered after terminating stale Desktop processes and relaunching. The first
candidate contained zero-byte dependency files following the disk-full incident;
it was rejected. A no-cache rebuild now verifies installed hashes against wheel
RECORDs, runs `pip check`, imports Torch/TorchVision/OpenCV/WSGI and passes real
installed CPU replay for all three historical examples. Receipt:
`/private/tmp/gcai-epic8/checkpoint-28-clean-image.json` (CPU only).

The companion environment passed all 16 unit tests under Python 3.12/OpenSSL 3.
Authenticated proxy replacement forced IP `172.23.0.2` → `172.23.0.4` and
recovered in 4.649 seconds without restarting/replacing the proxy. This receipt
uses the explicitly documented stdlib backend stub; full candidate-stack
qualification remains a separate required check. Production and rollback volumes
were preserved. Thirteen release-gate regressions pass, including deliberate
invalid evidence, missing channels, skipped live tests and unaccepted reports.
