"""Synthetic files for release-gate tests; never detector or release evidence."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
from PIL import Image
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmark"))
from corpus import corpus_identity
from evaluate import evaluate
from settings import EFFECTIVE_OPERATING_THRESHOLD


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def oci(path, source):
    config = json.dumps(
        {"os": "linux", "architecture": "amd64", "config": {"Labels": {"org.opencontainers.image.revision": source}}}
    ).encode()
    config_hash = hashlib.sha256(config).hexdigest()
    manifest = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "digest": "sha256:" + config_hash,
                "size": len(config),
            },
            "layers": [],
        }
    ).encode()
    manifest_hash = hashlib.sha256(manifest).hexdigest()
    index = json.dumps(
        {
            "schemaVersion": 2,
            "manifests": [
                {
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "digest": "sha256:" + manifest_hash,
                    "size": len(manifest),
                    "platform": {"os": "linux", "architecture": "amd64"},
                }
            ],
        }
    ).encode()
    with tarfile.open(path, "w") as archive:
        for name, content in [
            ("oci-layout", b'{"imageLayoutVersion":"1.0.0"}'),
            ("index.json", index),
            ("blobs/sha256/" + config_hash, config),
            ("blobs/sha256/" + manifest_hash, manifest),
        ]:
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return "sha256:" + manifest_hash


def benchmark(root, sources):
    classes = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "backend/app/data_configs/glyphs.yaml").read_text()
    )["CLASSES"][1:]
    (root / "images").mkdir()
    (root / "sources").mkdir()
    coco = {
        "info": {"description": "Synthetic release-gate fixture; never measured detector accuracy"},
        "development_fixture": False,
        "categories": [{"id": i + 1, "name": name} for i, name in enumerate(classes)],
        "images": [],
        "annotations": [],
        "sources": [],
    }
    predictions = []
    conditions = ["digital", "printed-photo", "hand-drawn-clear", "hand-drawn-hard"]
    for family in range(20):
        source = root / "sources" / f"family-{family}.svg"
        source.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>' + str(family) + "</text></svg>")
        coco["sources"].append(
            {
                "id": str(family),
                "source": str(source.relative_to(root)),
                "sha256": hash_file(source),
                "author": "synthetic fixture",
                "reuse_rights": "CC0",
            }
        )
        for condition in conditions:
            identity = len(coco["images"]) + 1
            image = root / "images" / f"{identity}.png"
            Image.new("RGB", (32, 32), (identity, 0, 0)).save(image)
            coco["images"].append(
                {
                    "id": identity,
                    "file_name": image.name,
                    "family_id": str(family),
                    "condition": condition,
                    "width": 32,
                    "height": 32,
                    "sha256": hash_file(image),
                    "annotator": "synthetic fixture",
                    "provenance": "synthetic fixture",
                    "reuse_rights": "CC0",
                    "approved_by": "synthetic test only",
                    "approved_at": "2026-11-24T00:00:00Z",
                    "approved": True,
                    "independently_labeled": True,
                }
            )
            for category in range(1, 15):
                bbox = [category * 2, 2, 1, 1]
                coco["annotations"].append(
                    {
                        "id": len(coco["annotations"]) + 1,
                        "image_id": identity,
                        "category_id": category,
                        "bbox": bbox,
                        "area": 1,
                        "iscrowd": 0,
                        "reading_order": category,
                    }
                )
                predictions.append({"image_id": identity, "category_id": category, "bbox": bbox, "score": 0.9})
    record = {
        "development_fixture": False,
        "source_revision": sources["application"],
        "environment_revision": sources["environment"],
        "checkpoint_sha256": "c" * 64,
        "corpus_sha256": corpus_identity(coco),
        "settings": {
            "score_floor": 0.001,
            "operating_threshold": 0.7,
            "overlap_suppression": 0.3,
            "coco_max_dets": [1, 10, 100],
            "operating_point_parity": True,
            "score_dtype": "float32",
            "effective_operating_threshold": EFFECTIVE_OPERATING_THRESHOLD,
        },
        "predictions": predictions,
    }
    annotations = root / "approved-coco.json"
    annotations.write_text(json.dumps(coco))
    prediction_file = root / "predictions.json"
    prediction_file.write_text(json.dumps(record))
    with contextlib.redirect_stdout(io.StringIO()):
        report = evaluate(coco, record, root / "images")
    report.update(
        annotation_file_name=annotations.name,
        prediction_file_name=prediction_file.name,
        images_directory="images",
        annotation_file_sha256=hash_file(annotations),
        prediction_file_sha256=hash_file(prediction_file),
    )
    return report
