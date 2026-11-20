# Standalone SBOL DB validator diagnostics

This probe calls `sbol::v3::Document::check()` with its default profile on the exact
RDF bytes supplied. It emits every finding plus coverage and applied options.
`Cargo.lock` fixes its transitive dependencies. The `sbol = 0.2.2` pin matches the
local SBOL DB checkout's lockfile at `504da7d48d9350ccd8ffaac75a24f1cb40208be8`.
It is not evidence that the historical registry in PR #3 ran this version.

From the repository root:

```sh
cargo build --locked --manifest-path tools/sbol-diagnostics/Cargo.toml
python tools/reconcile_sbol_validation.py \
  --probe tools/sbol-diagnostics/target/debug/gcai-sbol-diagnostics \
  --output docs/validation/committed-examples.json
```

Set `SBOL_DB_URL` to additionally import each fixture into a disposable registry.
The script creates unique graph IRIs and deletes each graph in `finally`.
Registry import reports contain counts only; standalone findings are comparable
only after verifying registry and probe versions and validation options match.

Python prerequisites: `sbol3`, `rdflib` (and `sbol-db` for live import).
