#!/usr/bin/env python3
"""Reproducible metrics from approved COCO labels and frozen ranked predictions."""

import argparse
import copy
from contextlib import redirect_stdout
from importlib.metadata import version
import io
import json
import math
from pathlib import Path
import re

from corpus import validate, corpus_identity, digest, contained
from settings import EFFECTIVE_OPERATING_THRESHOLD


def average(values):
    valid = values[values >= 0]
    return float(valid.mean()) if valid.size else None


def iou(a, b):
    x, y = max(a[0], b[0]), max(a[1], b[1])
    width = max(0, min(a[0] + a[2], b[0] + b[2]) - x)
    height = max(0, min(a[1] + a[3], b[1] + b[3]) - y)
    intersection = width * height
    return intersection / (a[2] * a[3] + b[2] * b[3] - intersection) if intersection else 0


def evaluator(ground, predictions, image_ids):
    from pycocotools.cocoeval import COCOeval
    from pycocotools.coco import COCO

    detections = ground.loadRes(copy.deepcopy(predictions)) if predictions else COCO()
    if not predictions:
        detections.dataset = {
            "images": ground.dataset["images"],
            "categories": ground.dataset["categories"],
            "annotations": [],
        }
        detections.createIndex()
    evaluation = COCOeval(ground, detections, "bbox")
    evaluation.params.imgIds = image_ids
    evaluation.params.maxDets = [1, 10, 100]
    evaluation.evaluate()
    evaluation.accumulate()
    return evaluation


def metrics(ground, predictions, image_ids):
    ranked = evaluator(ground, predictions, image_ids)
    operating = evaluator(ground, [p for p in predictions if p["score"] >= EFFECTIVE_OPERATING_THRESHOLD], image_ids)
    rows = []
    false_positives, missed, matched = [], [], []
    for category_index, category in enumerate(ground.dataset["categories"]):
        category_id = category["id"]
        tp = fp = fn = support = 0
        for item in operating.evalImgs:
            if item is None or item["category_id"] != category_id or item["aRng"] != operating.params.areaRng[0]:
                continue
            support += sum(not ignored for ignored in item["gtIgnore"])
            for index, prediction_id in enumerate(item["dtIds"]):
                if item["dtIgnore"][0][index]:
                    continue
                annotation_id = int(item["dtMatches"][0][index])
                if annotation_id:
                    tp += 1
                    matched.append((item["image_id"], operating.cocoDt.anns[prediction_id], ground.anns[annotation_id]))
                else:
                    fp += 1
                    false_positives.append(operating.cocoDt.anns[prediction_id])
            for index, annotation_id in enumerate(item["gtIds"]):
                if not item["gtIgnore"][index] and not item["gtMatches"][0][index]:
                    fn += 1
                    missed.append(ground.anns[annotation_id])
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
        precision_grid = ranked.eval["precision"][:, :, category_index, 0, 2]
        annotations = [
            a for a in ground.dataset["annotations"] if a["category_id"] == category_id and a["image_id"] in image_ids
        ]
        rows.append(
            {
                "class": category["name"],
                "category_id": category_id,
                "support_glyphs": support,
                "support_images": len({a["image_id"] for a in annotations}),
                "support_families": len({ground.imgs[a["image_id"]]["family_id"] for a in annotations}),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "ap50": average(precision_grid[0]),
                "ap50_95": average(precision_grid),
            }
        )
    return rows, false_positives, missed, matched


def evaluate(coco, record, images, *, qualification=True):
    import numpy as np
    import pycocotools.cocoeval
    from pycocotools.coco import COCO

    if version("pycocotools") != "2.0.11":
        raise ValueError("Use the pinned official pycocotools==2.0.11 evaluator")
    support = validate(coco, images, qualification=qualification)
    if qualification and record.get("development_fixture") is not False:
        raise ValueError("Development predictions cannot qualify a release")
    expected_settings = {
        "score_floor": 0.001,
        "operating_threshold": 0.7,
        "overlap_suppression": 0.3,
        "coco_max_dets": [1, 10, 100],
        "operating_point_parity": True,
        "score_dtype": "float32",
        "effective_operating_threshold": EFFECTIVE_OPERATING_THRESHOLD,
    }
    if any(record.get("settings", {}).get(key) != value for key, value in expected_settings.items()):
        raise ValueError("Prediction settings do not preserve the frozen evaluation and deployment protocol")
    for key in ["source_revision", "environment_revision"]:
        if not re.fullmatch("[0-9a-f]{40}", record.get(key, "")):
            raise ValueError("Record full source and environment revisions")
    if not re.fullmatch("[0-9a-f]{64}", record.get("checkpoint_sha256", "")):
        raise ValueError("Record the verified checkpoint identity")
    if record.get("corpus_sha256") != corpus_identity(coco):
        raise ValueError("Predictions do not match the approved corpus identity")
    predictions = record["predictions"]
    by_image = {image["id"]: image for image in coco["images"]}
    categories = {category["id"] for category in coco["categories"]}
    for prediction in predictions:
        image = by_image[prediction["image_id"]]
        box, score = prediction["bbox"], prediction["score"]
        if (
            prediction["category_id"] not in categories
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(score)
            or not 0.001 <= score <= 1
        ):
            raise ValueError("Predictions contain an invalid class or model score")
        if (
            len(box) != 4
            or any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in box)
            or min(box[2:]) < 0
        ):
            raise ValueError("Prediction boxes must be finite xywh values")
    ground = COCO()
    ground.dataset = copy.deepcopy(coco)
    ground.createIndex()
    ids = sorted(by_image)
    rows, false_positives, missed, matched = metrics(ground, predictions, ids)
    conditions = {}
    for condition in sorted({image["condition"] for image in coco["images"]}):
        subset = [image["id"] for image in coco["images"] if image["condition"] == condition]
        conditions[condition] = metrics(ground, predictions, subset)[0]
    confusions, duplicates = [], []
    for prediction in false_positives:
        overlaps = [
            annotation
            for annotation in coco["annotations"]
            if annotation["image_id"] == prediction["image_id"] and iou(annotation["bbox"], prediction["bbox"]) >= 0.5
        ]
        for annotation in overlaps:
            target = duplicates if prediction["category_id"] == annotation["category_id"] else confusions
            target.append(
                {
                    "image_id": prediction["image_id"],
                    "predicted_class": prediction["category_id"],
                    "actual_class": annotation["category_id"],
                    "annotation_id": annotation["id"],
                    "bbox": prediction["bbox"],
                }
            )
    reading_order = []
    for image_id in ids:
        pairs = [
            (prediction, annotation) for matched_image, prediction, annotation in matched if matched_image == image_id
        ]
        if any("reading_order" not in annotation for annotation in ground.imgToAnns[image_id]):
            reading_order.append(
                {"image_id": image_id, "inversions": None, "reason": "N/A: missing reviewed reading order"}
            )
            continue
        ordered = sorted(pairs, key=lambda pair: pair[0]["bbox"][0])
        inversions = sum(
            left[1]["reading_order"] > right[1]["reading_order"]
            for index, left in enumerate(ordered)
            for right in ordered[index + 1 :]
        )
        reading_order.append({"image_id": image_id, "matched_glyphs": len(pairs), "inversions": inversions})
    return {
        "schema_version": 1,
        "status": "passed",
        "sources": {"application": record["source_revision"], "environment": record["environment_revision"]},
        "evidence_kind": "detector_accuracy" if qualification else "development_evaluator_test",
        "scientific_acceptance": "pending",
        "qualification_data_complete": qualification,
        "source_revision": record["source_revision"],
        "environment_revision": record["environment_revision"],
        "checkpoint_sha256": record["checkpoint_sha256"],
        "corpus_sha256": corpus_identity(coco),
        "cocoeval_sha256": digest(pycocotools.cocoeval.__file__),
        "pycocotools": version("pycocotools"),
        "numpy": np.__version__,
        "settings": record["settings"],
        "families": len({image["family_id"] for image in coco["images"]}),
        "images": len(ids),
        "family_support": support,
        "per_class": rows,
        "per_condition": conditions,
        "map50": (
            float(np.mean([row["ap50"] for row in rows if row["ap50"] is not None]))
            if any(row["ap50"] is not None for row in rows)
            else None
        ),
        "map50_95": (
            float(np.mean([row["ap50_95"] for row in rows if row["ap50_95"] is not None]))
            if any(row["ap50_95"] is not None for row in rows)
            else None
        ),
        "errors": {
            "false_positives": false_positives,
            "missed_glyphs": missed,
            "duplicate_candidates": duplicates,
            "confusion_candidates": confusions,
            "reading_order": reading_order,
        },
        "limitations": [
            "Model scores are not calibrated probabilities.",
            "Eighty images represent twenty related circuit families.",
            "Confusion and duplicate overlaps are diagnostic candidates, not extra COCO matches.",
            "No minimum accuracy threshold; owner acceptance of measured limitations is required.",
            "Detection limits and internal filtering can hide low-score candidates.",
        ],
    }


def annotate_errors(coco, report, images, output):
    from PIL import Image, ImageDraw, ImageOps

    output.mkdir(exist_ok=False)
    for record in coco["images"]:
        errors = [("red", error) for error in report["errors"]["false_positives"] if error["image_id"] == record["id"]]
        errors += [("blue", error) for error in report["errors"]["missed_glyphs"] if error["image_id"] == record["id"]]
        if not errors:
            continue
        with Image.open(contained(images, record["file_name"])) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            canvas = ImageDraw.Draw(image)
            for color, error in errors:
                x, y, width, height = error["bbox"]
                canvas.rectangle((x, y, x + width, y + height), outline=color, width=3)
                canvas.text((x, y), str(error["category_id"]), fill=color)
            image.save(output / f'{record["id"]}.png')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["annotations", "predictions", "images", "output"]:
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument(
        "--development", action="store_true", help="Never qualifying; test evaluator with separate fixtures"
    )
    args = parser.parse_args()
    coco = json.loads(args.annotations.read_text())
    with redirect_stdout(io.StringIO()) as log:
        report = evaluate(
            coco, json.loads(args.predictions.read_text()), args.images, qualification=not args.development
        )
    report["annotation_file_sha256"] = digest(args.annotations)
    report["prediction_file_sha256"] = digest(args.predictions)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    args.output.with_suffix(".log").write_text(log.getvalue())
    annotate_errors(coco, report, args.images, args.output.with_suffix(".errors"))
