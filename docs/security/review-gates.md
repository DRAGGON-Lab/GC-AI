# Reviewing the remaining deployment gates

The deployment repository is [DRAGGON-Lab/GC-AI-environment](https://github.com/DRAGGON-Lab/GC-AI-environment).
Its hardened local and hosted profiles replace direct database/backend publication.
A review deployment is a fresh isolated stack; it does not migrate an existing
production volume. ADR 0001 was accepted on 23 November 2026.

## Inputs discovered on 24 November 2026

The requested environment repository main was `2646936`, retaining these immutable
legacy inputs. Docker Hub manifest inspection confirmed the same digests:

- Checkpoint image: `cvtalrc/gc-ai-backend@sha256:ca69a541fb8b9cecec88764b36e19274d058f8407078f6efa0320a89c9ebd37a`.
- Registry image: `cvtalrc/gc-ai-db@sha256:ff285f1370a7ee900d871c0a621232d3de29ecc39afd096d342f30449d89a695`.

The checkpoint path is `/app/app/models/model_files/160_model.pth`; its SHA256 is
`06ac3f64292ed93f49e296b60e32dab0b5b0182e86141b52ff43a253dba51749`.
The real isolated registry export contains 84285 parts and has SHA256
`e869efcaa5bc37bc68065bb90eb48136d7319c1d52aec5a20dcdf4f045aa1766`.
Private review assets are at `/private/tmp/gcai-real-assets` and linked into the
environment review checkout's ignored `assets` directory. Fresh review credential
files are under `/private/tmp/gcai-environment-review/secrets`; the proposed local
review URL is `https://localhost:8443` (the local CPU review service).

These are migration inputs. Build the hardened runtime images from reviewed GC-AI
source; do not deploy the old backend. The old environment includes a legacy
credential; use it only through a private input file for the isolated legacy
export, then create fresh root, application and workspace credentials. Never copy
that credential into the new Compose file, logs or command arguments.

## Executable runtime checks

Install the backend test dependencies and `client[dev,db,mcp]`. Configure an HTTPS
review URL ending in `/api`, `GCAI_USERNAME`, and `GCAI_PASSWORD_FILE`. For a private
CA set `SSL_CERT_FILE` to its PEM file; certificate verification stays enabled.

```sh
python tools/verify_deployment.py \
  --image 'docs/examples/YES GATE/YES-GATE-CIRCUIT.png' \
  --old-password-file /private/path/previous-workspace-password \
  --output /private/path/new-review-evidence
```

The new output directory is private (0700); its sanitized JSON report is 0600.
The runner tests readiness/liveness, denied anonymous access, denied unsafe
Origin, actual inference, Python SBOL/create/convert with exact sequences and
GenBank coordinates, CLI readiness, MCP image-to-SBOL, and rejection of the old
workspace password. It records failed checks by exception class only. Missing
rotation evidence is `not_run` and makes the command fail. It never changes
credentials or production data. Repeating the command requires a fresh evidence
directory. `Review deployment acceptance` runs these checks manually against a
selected GitHub environment; configure its review-only URL and credentials first.

A passing runtime report does not assert checkpoint provenance, GPU execution,
legacy migration, database credential rotation, browser acceptance or rollback.
Those require the separate environment receipts and operator review.

## Registry and notebook checks

Use a disposable SBOL DB registry: the live tests publish unique temporary graphs
and delete them after checking regenerated documents have zero registry findings.
Historical XML is retained as evidence, not used as the passing conformance target.

```sh
cd client
GCAI_URL=https://review.example/api SBOL_DB_URL=http://127.0.0.1:8899 \
  python -m pytest -m integration
```

The service suite now expects supported readiness200 and independent liveness200.
The notebook reads `GCAI_URL` and the same private authentication configuration.
Set `GCAI_NOTEBOOK_OUT` for its output directory and
`GCAI_NOTEBOOK_PART_NAMES` to match the detected glyph count. An empty value skips
the named-parts example. Registry publishing additionally requires
`GCAI_NOTEBOOK_PUBLISH=1` and `SBOL_DB_URL`; its unique graph is removed afterward.
Execute to a new notebook output, keeping committed source unchanged:

```sh
jupyter nbconvert --execute --to notebook examples/quickstart.ipynb \
  --output executed-quickstart.ipynb --output-dir /private/path/review
```

## Evidence still needed for release

The environment import receipt must include checkpoint/registry hashes and image
provenance. Verify a fresh MySQL 8.4 import, row counts, SELECT-only application
grants, backup/restore into isolated storage, hourly janitor, and old database and
workspace credential rejection after rotation. Record actual source and image
identities and rollback location. Real detector and registry results must identify
the execution environment; synthetic fixtures do not satisfy those gates. Keep
#16 and epic #7 open until accepted.

## Real checkpoint route replay

Build the dedicated CPU verifier with `docker build -f backend/Dockerfile.checkpoint`.
It uses Torch 2.6.0+cpu and TorchVision 0.21.0+cpu; it is a verification image, not the
production GPU runtime. Set `GCAI_MODEL_PATH` and
`GCAI_EXPECTED_CHECKPOINT_SHA256` from the verified extraction receipt. Run
`tools/verify_checkpoint.py --examples docs/examples --output <new-private-report>`
inside a non-root container with no network, read-only checkpoint/example mounts,
a private writable report directory and resource limits. It verifies the hash
before loading trusted pickle, runs all three examples through actual Flask
inference routes, compares boxes/classes to committed detections and records
CPU/GPU device and versions separately. CPU success does not establish GPU parity.


The environment repository also provides `compose.registry.yml` for a disposable
SBOL DB on `127.0.0.1:18899`, pinned to
`ghcr.io/marpaia/sbol-db@sha256:ec35a160248e1db1b50e2a55c251e140c6f2f6c0d5781822b5140aa475af759b`.
Five live storage integration checks passed against that image on 24 November
2026; the sixth service-to-registry test was skipped because no full GC-AI review
service was running. SQLite migration must complete before server startup and its
working directory must be writable for blob storage; the profile configures both.


Real checkpoint replay passed for all three committed image records on CPU
(Torch 2.6.0+cpu, TorchVision 0.21.0+cpu, Python 3.12.16). Exact boxes/classes matched;
see [checkpoint-replay.json](checkpoint-replay.json). The image ran without network,
non-root with read-only checkpoint/example inputs and explicit resource limits.
GPU execution remains unverified. The CPU review service can be built by first
building `backend/Dockerfile.checkpoint` as `gcai-cpu-review:temporary`, then
`backend/Dockerfile.review`. Production GPU deployments use `backend/Dockerfile`
and require their own runtime/checkpoint acceptance.

`backend/requirements-checkpoint.lock` captures the exact package set from the
executed CPU verifier; the verifier recipe applies those constraints to future
builds. Image IDs in the evidence identify the actual executed snapshots.


## Browser and dependency review

Install `tools/requirements-browser.txt` and run `python -m playwright install chromium`.
`tools/verify_browser.py --output <new-private-directory>` checks the authenticated
React render, all fourteen real registry role queries and JavaScript errors; it
saves a private screenshot. For localhost only, `--local-certificate <tls.crt>`
pins that certificate's exact public key in Chromium. Public deployments use
normal browser certificate validation. SDK checks continue verifying the local CA.

Runtime dependency audit is zero after React Router7.18.6 and compatible dependency
patches. The unused standalone React debugger/Electron dependency was removed.
Two development-tool findings remain for Vite/esbuild; npm proposes a Vite major
upgrade. The production image contains Nginx and built assets, with no development
server or node_modules. See [dependency-audit.json](dependency-audit.json). The CI
runtime audit fails on new production dependency findings; this is not a claim
that every development tool is advisory-free.

A production GPU host can add `compose.gpu.yml` from the environment repository.
Run checkpoint acceptance with `--require-gpu`; CPU fallback then fails before
inference instead of being counted as GPU verification. Local CPU replay remains
valid CPU evidence; GPU execution still requires actual equipped-host acceptance.
