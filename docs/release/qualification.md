# CPU research candidate qualification

The CPU research channel requires every evidence channel in
[the shared manifest schema](release-manifest.schema.json). A publicly reachable
private deployment additionally requires operator deployment review under epic
#7. Production cutover, credential rotation and CUDA qualification remain
separate. GPU artifacts must not be described as qualified by CPU evidence.

Candidate ID: `rc-cpu-<application SHA first 12>-<environment SHA first 12>`.
Use full forty-character revisions in the manifest and immutable GHCR digests
for backend/frontend images. Record wheel/source checksums, approved checkpoint
and dataset hashes, executed qualification reports and accepted limitations.
Both repositories carry byte-identical copies of the schema. Changed manifests
or evidence require another review; historical acceptance does not carry forward
automatically to changed source, images, checkpoint or dataset.

The candidate bundle must contain:

- Core test/lint/typing, installed-wheel/source, real CPU and strict dual-validator evidence.
- Python, CLI, MCP, complete notebook and real rendered browser workflows.
- Readiness, authentication, origins, bounded admission and failure responses.
- Disposable registry publication/readback, restricted MySQL grants, fresh backup/restore, janitor and proxy replacement recovery.
- The measured approved 80-image benchmark, reviewer acceptance of its exact report, and accepted limitations.
- Independent review of #22 through #29 and verified merge protection on both repositories.

Use the canonical environment's disposable orchestration at exact source
revisions. Never reuse the active review project's database volumes for
qualification. Clean only the new project's containers and disposable volumes.
Do not suppress unavailable prerequisites with skips. A missing capture,
unapproved annotation or missing acceptance keeps #28, #29 and epic #8 open.

Run `python tools/release/manifest.py release-manifest.json --bundle candidate
--publish` before publication. This checks all artifact/evidence hashes, exact
source identities and every named gate. `not_run` is a failure for publication.
Publish only after the owner reviews the concrete bundle and scientific report.
The dispatch workflow builds candidate artifacts; publication additionally uses
a protected GitHub Environment configured by the repository owner. No automatic
production deployment is part of this workflow.

Validator findings, successful registry round trips and historical example
replay are separate evidence. None establishes detector accuracy or biological
correctness. Release notes must scope measured performance to this corpus and
its twenty related design families; N/A measurements stay N/A.

Engineering stack command (the output directory must be new and private):

```sh
python tools/release/qualify_stack.py \
  --image-bundle /private/reviewed-oci-bundle \
  --environment /path/to/clean/GC-AI-environment \
  --source-ref APPLICATION_FULL_SHA --environment-ref ENVIRONMENT_FULL_SHA \
  --checkpoint /private/160_model.pth --checkpoint-sha256 APPROVED_SHA256 \
  --registry /private/registry.sql --registry-sha256 APPROVED_SHA256 \
  --mysql-image mysql:8.4@sha256:REVIEWED_DIGEST \
  --probe /path/to/gcai-sbol-diagnostics --output /private/new-candidate-evidence
```

Prerequisites: Python 3.12 with client dev/db/mcp extras,
`tools/requirements-release.txt`, OpenSSL 3, Node 24, pinned Playwright browsers,
the locked Rust probe and Docker/Compose. This command creates a unique project,
uses ports 18443/18898, checks that live tests have no skips, executes the complete
notebook and actual browser, restores a backup into a separate new MySQL volume,
and forces a changed backend IP while retaining the proxy. It removes only its
own disposable containers/images/volumes. Its report explicitly remains an
engineering result until benchmark and owner acceptance gates are complete.
Private execution logs and notebooks must be reviewed/redacted before selecting
sanitized reports for a public bundle.

Qualification executes the reviewed OCI archives described by `images.json`;
it does not rebuild images. `describe_images.py` records the exact manifest,
config and archive identities. Publication checks every referenced OCI blob,
platform and source label, preserves manifest digests with Skopeo, and refuses
to overwrite a candidate tag that already identifies different bytes. Installed
artifact evidence and runtime evidence must match the manifest's exact hashes.
The scientific gate recomputes COCO metrics from the bundled approved images,
labels and ranked prediction inputs and compares the entire measured report.
