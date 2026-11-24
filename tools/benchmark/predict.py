#!/usr/bin/env python3
"""Frozen CPU prediction export; preserves deployed operating-point outputs."""

import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re

from corpus import validate, corpus_identity
from settings import EFFECTIVE_OPERATING_THRESHOLD


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["annotations", "images", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ["source-revision", "environment-revision"]:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    for revision in [args.source_revision, args.environment_revision]:
        if not re.fullmatch("[0-9a-f]{40}", revision):
            parser.error("Full 40-character source and environment revisions are required")
    coco = json.loads(args.annotations.read_text())
    validate(coco, args.images, qualification=not args.development)
    import numpy as np
    from PIL import Image, ImageOps
    import torch
    from app.config import get_model
    from app.models.inference import process_image

    torch.set_num_threads(2)
    model = get_model()
    if next(model.parameters()).device.type != "cpu":
        raise ValueError("This protocol qualifies CPU execution only")
    original_threshold = model.roi_heads.score_thresh
    category = {item["name"]: item["id"] for item in coco["categories"]}
    records = []
    for record in coco["images"]:
        with Image.open(args.images / record["file_name"]) as source:
            image = np.array(ImageOps.exif_transpose(source).convert("RGB"), dtype=np.uint8)[:, :, ::-1].copy()
        deployed = process_image(image, model)
        try:
            model.roi_heads.score_thresh = 0.001
            ranked = process_image(image, model, score_threshold=0.001)
        finally:
            model.roi_heads.score_thresh = original_threshold
        kept = [
            (list(box), name, score)
            for box, name, score in zip(ranked[1], ranked[2], ranked[3])
            if score >= EFFECTIVE_OPERATING_THRESHOLD
        ]
        expected = [(list(box), name, score) for box, name, score in zip(deployed[1], deployed[2], deployed[3])]
        if kept != expected:
            raise RuntimeError("Evaluation floor changed deployed operating-point outputs")
        for box, name, score in zip(ranked[1], ranked[2], ranked[3]):
            x1, y1, x2, y2 = map(float, box)
            records.append(
                {
                    "image_id": record["id"],
                    "category_id": category[name],
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "score": score,
                }
            )
    report = {
        "development_fixture": args.development,
        "source_revision": args.source_revision,
        "environment_revision": args.environment_revision,
        "corpus_sha256": corpus_identity(coco),
        "checkpoint_sha256": os.environ["GCAI_EXPECTED_CHECKPOINT_SHA256"],
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torchvision": version("torchvision"),
        },
        "settings": {
            "score_floor": 0.001,
            "operating_threshold": 0.7,
            "overlap_suppression": 0.3,
            "coco_max_dets": [1, 10, 100],
            "operating_point_parity": True,
            "score_dtype": "float32",
            "effective_operating_threshold": EFFECTIVE_OPERATING_THRESHOLD,
            "original_internal_score_threshold": original_threshold,
            "evaluation_internal_score_threshold": 0.001,
            "roi_nms_threshold": model.roi_heads.nms_thresh,
            "detections_per_image": model.roi_heads.detections_per_img,
            "rpn_nms_threshold": model.rpn.nms_thresh,
            "rpn_score_threshold": model.rpn.score_thresh,
            "rpn_pre_nms_top_n": model.rpn.pre_nms_top_n(),
            "rpn_post_nms_top_n": model.rpn.post_nms_top_n(),
        },
        "predictions": records,
    }
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
