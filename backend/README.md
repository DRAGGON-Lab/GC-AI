# GC-AI backend CPU research candidate

Supported target: Python 3.12, Linux/amd64, Torch 2.6 and TorchVision 0.21.
Install the hashed CPU lock before the wheel with `--no-deps`. The runtime uses
one headless OpenCV distribution. Tests use `requirements-test.txt` without a
checkpoint or database server. Training dependencies are intentionally separate.

Build: `python -m build backend`. The wheel includes detector YAML and exposes
`app.wsgi:application`, `gc-ai-backend` (development server) and
`gc-ai-janitor`. Example production start:
`gunicorn --bind 127.0.0.1:5001 --workers 1 --threads 4 app.wsgi:application`.
Use the repository's Gunicorn configuration for production bounds and logging.

Real initialization requires `GCAI_MODEL_PATH` and
`GCAI_EXPECTED_CHECKPOINT_SHA256` from the reviewed release manifest. Missing,
malformed and mismatched hashes fail before deserialization. The loader hashes
an open stream, rewinds it and loads that same stream. The legacy checkpoint
cannot use Torch 2.6 `weights_only=True`: verified CPU execution rejects its
`numpy.core.multiarray.scalar` global. Trusted pickle loading is explicit and
mandatory integrity/provenance verification precedes it. There is no automatic
unsafe fallback. Supply the approved file through a private read-only mount.

The approved historical checkpoint SHA256 is
`06ac3f64292ed93f49e296b60e32dab0b5b0182e86141b52ff43a253dba51749`,
extracted from the immutable source documented in the canonical environment's
`legacy-images.json`. A matching hash establishes asset identity, not detector
accuracy or safe provenance for an arbitrary replacement checkpoint.
