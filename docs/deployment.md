# Deploying a trusted GC-AI workspace

This release changes the conversion wire contract. Release Flask, React, Python, CLI and MCP together. Existing server paths cannot be migrated into handles: generate the design again. Use one trusted workspace with a TLS reverse proxy and password authentication. Read the coordinated `cvtalrc/GC-AI-environment` change before deploying.

## Build and run reviewed source

The runtime lock and Docker CI target Linux/amd64. Build for that platform when using another host architecture.

From the GC-AI repository root:

```sh
docker build -f backend/Dockerfile -t gcai-backend:<revision> .
docker build -f frontend/Dockerfile -t gcai-frontend:<revision> .
```

Record the source revision and resulting immutable image digests in the deployment receipt. Mount the checkpoint read-only at `GCAI_MODEL_PATH`, and a private artifact volume at `GCAI_ARTIFACT_DIR`. The runtime defaults to UID/GID 10001. The environment secret initializer copies operator inputs into private consumer-owned volumes and initializes artifact ownership; verify the configured MySQL and Nginx UID/GIDs against the pinned images. Never bake credentials or checkpoints into a source image.

The development launcher `python backend/run.py` binds `127.0.0.1` by default. Production uses `gunicorn --config gunicorn.conf.py 'app:create_app()'` from `/app` (or `backend` locally). The default bind is loopback; set `GCAI_BIND=0.0.0.0:5001` only inside the private container network. One worker, four threads, no preloading, one detector admission slot. Health routes and registry lookups remain responsive during admitted inference.

Proxy and threaded worker timeouts do not cancel GPU execution. The proxy response timeout is 180 seconds. A sustained detector hang requires restarting the worker/container. See [Gunicorn timeout semantics](https://gunicorn.org/reference/settings/#timeout). Increasing workers also multiplies checkpoint/GPU memory and admission slots; scale detector instances deliberately.

## Proxy, credentials and origins

Hosted mode publishes only TLS proxy 443. Backend and MySQL have no published ports. The environment proxy serves the built React files and forwards `/api/` to Flask on the same origin, stripping `/api`. React defaults to `/api`; no browser build variable contains passwords. The mounted password-hash file protects both the frontend and `/api/` with [Nginx Basic authentication](https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html). TLS certificates and key files are operator inputs.

Generate the password hash interactively using `htpasswd -cB <private-file> <username>` (no password argument). Protect private inputs with file permissions and restrictive directory ownership. Do not log Authorization, password files, request bodies or credential-bearing URLs. The application returns sanitized dependency errors and does not log raw exception messages.

Python accepts `auth=(username, password)`. CLI/MCP read `GCAI_USERNAME` and `GCAI_PASSWORD_FILE`. Both must be configured together. Basic authentication requires HTTPS outside loopback. Configure database access through `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` and secret-mounted `DB_PASSWORD_FILE`.

Set `GCAI_TRUSTED_ORIGINS` to a comma-separated explicit allowlist, including the hosted HTTPS origin. Unsafe methods with an untrusted browser Origin are rejected before processing; CORS alone is insufficient. Local defaults allow only `http://localhost:5173` and `http://127.0.0.1:5173`. Do not use wildcard origins. CLI requests without Origin are supported behind the proxy.

Resource defaults: `GCAI_MAX_REQUEST_BYTES=12582912`, `GCAI_MAX_IMAGE_BYTES=10485760`, `GCAI_MAX_IMAGE_PIXELS=16000000`, `GCAI_MAX_IMAGE_DIMENSION=8192`. Coordinate increases with proxy and SDK/MCP bounds. One occupied inference returns 503 with `Retry-After`. The proxy also bounds request admission without a waiting queue.

## Asset import and fresh database

Use the environment repository's import script with immutable legacy image digests. Extract only the checkpoint from a stopped created container; never execute the legacy application. Start the legacy database in an isolated network with no published ports and supply its credential through a private input file. Export registry schema/data only. Do not carry over users, grants or system tables.

Initialize fresh MySQL 8.4 storage with new root and application secrets, import the registry, and grant the application SELECT on the required parts table only. Do not reuse legacy accounts or upgrade the legacy volume in place. Preserve the old volume as a rollback artifact under operator control. Pinned digests and actual checkpoint/database assets are prerequisites, not outputs that source changes can establish.

## Retention, health and maintenance

Run `python -m app.utils.cleanup` from `backend` (the image uses `/app`) hourly in a separate janitor sharing the artifact volume and UID. Lookup enforces immutable 24-hour expiry independently of cleanup. Handle directories and files are private 0700/0600. Expired files, abandoned staging and interrupted publication directories are removed conservatively; active publications are retained. Handles survive worker restarts but are bearer capabilities, so keep them private and avoid recording them in access logs.

Use `/livez` for cheap liveness and `/healthcheck/` for readiness. Readiness initializes the detector and consumes `SELECT 1`. It returns 200 only if both dependencies work, otherwise sanitized 503. The proxy protects these public paths too; container-local health probes can use the private network.

Before upgrades, export a fresh logical registry backup to a private file, checksum it, and retain source/image revisions and checkpoint digest. Restore into a fresh isolated volume, reapply restricted grants with new secrets, and verify row counts, readiness and sample design creation/conversion before switching traffic. The environment repository supplies backup/restore commands and credential rotation steps. Root/database and workspace passwords must be rotated using private input files; restart clients and verify old credentials fail.

## Acceptance evidence

Code validation does not establish deployment completion. Docker-capable CI builds reviewed source and exercises real Pillow decoding, WSGI liveness and degraded readiness. The environment workflow verifies TLS authentication, private networking, registry import, grants, backup/restore and janitor behavior when invoked with reviewed source and pinned assets.

The operator receipt must record source/image/checkpoint digests, import/backup checksums, row counts, least-privilege grants, successful authenticated create/convert/inference/readiness, unauthenticated denial, old-credential rejection, janitor operation, and rollback location. Never include secret values. Checkpoint/GPU smoke tests must be distinguished from mocked runners. Keep issue #16 and epic #7 open until the environment PR, integrated deployment checks, actual migration and credential-rotation receipts are accepted.
