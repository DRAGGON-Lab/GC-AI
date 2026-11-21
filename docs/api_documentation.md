# GC-AI API

The development API binds loopback. Hosted clients use `https://<workspace>/api` with TLS Basic authentication; React and API share the proxy origin. See [deployment](deployment.md) and [OpenAPI](openapi.yaml) for configuration and schemas.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/livez` | Cheap dependency-independent liveness |
| GET | `/healthcheck/` | Readiness, 200 or sanitized 503 |
| POST | `/inference/` | PNG/JPEG glyph detection |
| GET | `/component/names?role=Promoter` | Registry names; retains detector guard |
| GET | `/component/details?component_name=BBa_R0010&role=Promoter` | Registry part details; unknown parts return 404 |
| GET | `/component/interactions?interaction_type=Stimulation` | Allowed participation roles |
| POST | `/file/create` | Full validated SBOL3 attachment and structural handle |
| POST | `/file/convert` | Complete ZIP containing exactly the requested formats |

All application failures use `{status_code, error, code}`. Validation failures can include bounded `issues`, `total_count` and `truncated`. Unexpected failures expose no dependency diagnostics, filesystem paths or credentials. Framework headers such as `Allow`, `WWW-Authenticate` and `Retry-After` survive error serialization. Proxy authentication failures may be HTML and retain `WWW-Authenticate`.

`/healthcheck/` loads the detector through the synchronized initializer and verifies a consumed `SELECT 1`. The Python client's `health()` calls readiness directly. `/livez` never accesses these dependencies.

Inference accepts one multipart `image` field. Defaults are 12 MiB total request, 10 MiB image bytes, 16 million pixels and 8192 pixels per dimension. Actual PNG or JPEG content is inspected before pixel allocation. Corrupt, truncated, multiframe or unsupported data returns 422; oversized requests/images return 413. Supported image modes normalize to three channels. One inference runs per process with no waiting queue. An occupied detector returns `503`, `code: inference_busy`, and `Retry-After`.

`/file/create` requires `namespace`, `components`, `expressions`, `interactions` and `eds`. The namespace must be an absolute HTTP(S) URL without credentials, whitespace, controls, query or fragment. Missing/wrong type is 400; invalid value is 422. Trailing slashes are stripped and generated identifiers use one joining slash. Each top-level Component and Sequence carries the explicit request namespace. The SBOL library's global namespace is never changed.

The components array contains a DNA assembly parent followed by ordered DNA parts. Unsupported roles, incompatible interaction participants, unknown registry parts, and invalid SBOL identities are rejected before publication. A design without complete bases retains its physical order and functional species; it invents no parent sequence or feature coordinates. Complete assemblies preserve the validated sequences and feature coordinates. Both full and structural SBOL documents must pass validation and serialization checks before the handle is published.

The response body is the full SBOL/XML attachment. `X-GCAI-Structural-Handle` contains `v1_` plus 43 URL-safe characters encoding 32 cryptographically random bytes. This bearer capability expires after 24 hours, survives worker restarts, and must be kept private. No server path is returned.

Conversion JSON is:

```json
{"structural_handle":"v1_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","genbank":true,"fasta":true}
```

Use the issued handle from create; the example is unissued. Legacy `file_path` is rejected with an actionable 400. Malformed handles return 400; unissued, expired or deleted handles return 404. Both format flags must be actual booleans and at least one must be true. Conversion requires complete DNA sequences and supported coordinate representations; unsupported designs return actionable 422 errors. The pinned local GenBank converter never uploads designs or changes the global online-validation setting. Every requested output must be nonempty and parseable with matching sequences and coordinates before any ZIP is returned. Failure returns no partial archive, so clients can retry the same unexpired handle.

Hosted operators configure explicit `GCAI_TRUSTED_ORIGINS`. Untrusted browser origins on unsafe methods are rejected before route execution, including multipart requests. Requests without an Origin remain supported for CLI/MCP/SDK access behind the authenticated proxy.
