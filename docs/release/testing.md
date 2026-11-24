# Candidate test channels

Core checks report on every push and pull request, including documentation-only
changes. Required contexts have distinct job names. Heavy Docker qualification
is invoked separately; it must not be confused with these isolated checks.

`python -m pytest backend/tests -q --disable-warnings` uses Python 3.12 and
`backend/requirements-test.txt`, plus an editable client for SDK route tests.
No checkpoint, Torch, MySQL server or model download is needed. The route matrix:

| Surface | Regression modules |
| --- | --- |
| create, assembly, identity, functional species | test_exports, test_namespaces |
| conversion, handles, expiry, atomic publication | test_conversion_handles, test_artifacts |
| inference decoding, admission, recovery | test_inference |
| liveness, readiness, lazy loading and retry | test_readiness, test_checkpoint_loading |
| registry names/details, query binding, missing parts, cleanup | test_component_routes |
| JSON shapes, origins, errors, credential sanitization | test_api_boundary |
| actual SDK generation/conversion | test_sdk_routes |
| strict offline dual-validator gate | test_reconciliation |

`cd client && python -m pytest` requires the dev, db and mcp extras. Integration
cases are explicitly deselected in this channel. Live execution requires private
TLS/authentication, a real checkpoint and expected SHA256, MySQL fixture data and
a disposable SBOL DB; use `pytest -m integration` with documented GCAI settings.
A skipped live test cannot qualify a release.

`cd frontend && npm ci && npm run lint && npm test && npm run build` runs on
Node 24. The browser harness serves the production build locally and mocks API
traffic; it requires pinned Playwright Chromium but no backend services.
