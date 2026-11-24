#!/usr/bin/env python3
"""Execute a provenance-verified checkpoint through actual image routes.

Run only in an isolated, network-disabled runtime with read-only inputs. The
checkpoint is trusted pickle input. This reports CPU/GPU execution separately.
"""

import argparse
import hashlib
import io
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = os.environ.get("GCAI_EXPECTED_CHECKPOINT_SHA256", "")
    if len(expected) != 64:
        parser.error("Set GCAI_EXPECTED_CHECKPOINT_SHA256 from the verified extraction receipt")
    if not __debug__:
        parser.error("Run without Python optimization")
    checkpoint = Path(os.environ["GCAI_MODEL_PATH"])
    digest = hashlib.sha256()
    with checkpoint.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        parser.error("Checkpoint hash differs from the expected provenance receipt")
    import torch
    import torchvision
    from app import create_app
    from app.config import get_model

    torch.set_num_threads(2)
    report = {
        "evidence_kind": "real_checkpoint_route_replay",
        "checkpoint_sha256": expected,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "fixtures": [],
    }
    try:
        model = get_model()
        report["device"] = str(next(model.parameters()).device)
        report["gpu_execution"] = report["device"].startswith("cuda")
        client = create_app({"TESTING": True, "FILES_GENERATED_DIR": "/tmp/gcai-checkpoint-artifacts"}).test_client()
        directories = sorted(p for p in args.examples.iterdir() if (p / "detections.json").exists())
        assert len(directories) == 3
        for directory in directories:
            image = next(directory.glob("*-CIRCUIT.png"))
            expected_detections = json.loads((directory / "detections.json").read_text())
            response = client.post(
                "/inference/",
                data={"image": (io.BytesIO(image.read_bytes()), image.name)},
                content_type="multipart/form-data",
            )
            assert response.status_code == 200
            data = response.get_json()
            assert len(data["draw_boxes"]) == len(data["pred_classes"])
            glyphs = sorted(
                [{"glyph_class": kind, "box": box} for kind, box in zip(data["pred_classes"], data["draw_boxes"])],
                key=lambda glyph: glyph["box"][0],
            )
            observed = {"has_predictions": bool(glyphs), "count": len(glyphs), "glyphs": glyphs}
            expected_core = expected_detections
            report["fixtures"].append(
                {
                    "name": directory.name,
                    "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                    "record_sha256": hashlib.sha256((directory / "detections.json").read_bytes()).hexdigest(),
                    "expected": expected_core,
                    "observed": observed,
                    "result": "passed" if observed == expected_core else "failed",
                }
            )
        report["result"] = "passed" if all(f["result"] == "passed" for f in report["fixtures"]) else "failed"
    except Exception as error:
        report["result"] = "error"
        report["error_type"] = type(error).__name__
    with open(args.output, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print("Checkpoint route replay: " + report["result"])
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
