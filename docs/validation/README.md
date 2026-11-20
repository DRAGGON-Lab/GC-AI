# Epic #6 validation evidence

The original YES gate reproduces **0 pySBOL3 findings versus 13 sbol-rs findings**.
All thirteen are concrete `sbol3-11706` errors: positional `meets` constraints
contradict ranges separated by BioBrick scars. Lux has 17 and Repressilator 35
errors of the same kind. These are document defects missed by pySBOL3, rather
than a reason to relax validation. The approved relative-order semantics correct
these constraints to `precedes`.

| Fixture | Original pySBOL3 | Original sbol-rs | Regenerated full, both validators | Regenerated structural, both validators |
| --- | ---: | ---: | ---: | ---: |
| Lux System | 0 | 17 | 0 | 0 |
| Repressilator | 0 | 35 | 0 | 0 |
| YES gate | 0 | 13 | 0 | 0 |

`committed-examples.json` contains full findings, validator options and coverage,
RDF SHA-256 hashes, counts and Python package versions. Each of the 65 findings
is assigned a disposition and owner in `finding-dispositions.md`.

## What was executed

Python 3.12.13; pySBOL3 1.2.0.post0; RDFLib 6.3.2; pySHACL 0.28.1;
sbol-rs 0.2.2; Rust 1.96.1. The standalone Rust dependency is pinned and locked.
Its version matches the local SBOL DB checkout at
`504da7d48d9350ccd8ffaac75a24f1cb40208be8`. It is not a live registry test.

From the repository root, with the backend's test dependencies installed:

```sh
cargo build --locked --manifest-path tools/sbol-diagnostics/Cargo.toml
python tools/reconcile_sbol_validation.py \
  --probe tools/sbol-diagnostics/target/debug/gcai-sbol-diagnostics \
  --regenerate docs/validation/regenerated \
  --output docs/validation/committed-examples.json
```

This execution used writable temporary Cargo directories and cached dependencies:

```sh
CARGO_HOME=/private/tmp/gcai-cargo CARGO_TARGET_DIR=/private/tmp/gcai-sbol-target \
  cargo build --offline --manifest-path tools/sbol-diagnostics/Cargo.toml
/private/tmp/gcai-venv/bin/python tools/reconcile_sbol_validation.py \
  --probe /private/tmp/gcai-sbol-target/debug/gcai-sbol-diagnostics \
  --regenerate docs/validation/regenerated \
  --output docs/validation/committed-examples.json
```

Both commands completed with exit status 0. Each regenerated full and structural
RDF document was parsed by RDFLib and validated by both tools on identical bytes.

The replays call the changed backend generator with the original `request.json`.
A fixture cursor supplies part sequences and descriptions from the original RDF;
other registry metadata defaults to empty values. This proves generation and
scientific validation using recorded part data. It does not prove connectivity,
current registry metadata, detector behavior, or MySQL integration. Each replay
has a `provenance.json` recording request/source hashes and backend source hashes.
Original XML, request and sequence exports have not been rewritten.

## Release policy and remaining verification

Any pySBOL3 finding blocks runtime export. Additional GC-AI DNA, coordinate,
reference and role invariants block invalid requests even when pySBOL3 is silent.
A release also requires all registry discrepancies to have reviewed dispositions.
Conformance errors block release; a profile difference or tool defect requires an
explicit scientific-review disposition rather than a blanket exception.

A successful graph import does not waive a finding. The import API's count-only
report may be reconciled with this standalone probe only when registry engine
version and options match. The original PR #3 registry's exact version was not
recorded, so equal YES gate counts reproduce its symptom without proving that
historical execution's identity. PR #5's separately reported two findings cannot
be assigned historical diagnostics without its exact raw RDF and validator build.

Live GC-AI/MySQL/detector and SBOL DB verification: **not_run**. No configured
`GCAI_URL` or `SBOL_DB_URL` was available, Docker had no running daemon, and the
installed Docker application could not launch (`kLSNoExecutableErr`). Set
`SBOL_DB_URL` for disposable registry testing; the diagnostic script creates UUID
graph IRIs and deletes its graphs in `finally`. Record the registry server version
separately from the Python client version, then rerun the integration suites.
Scientific human review and merged-main verification remain required before
closing the epic or claiming release readiness.
