"""Fail-closed provenance and scientific prerequisites for a qualification corpus."""

import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageOps

CONDITIONS = {"digital", "printed-photo", "hand-drawn-clear", "hand-drawn-hard"}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def contained(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Image paths must remain inside the corpus directory")
    return path


def validate(coco, images_root, *, qualification=True):
    import yaml

    root = Path(__file__).resolve().parents[2]
    classes = yaml.safe_load((root / "backend/app/data_configs/glyphs.yaml").read_text())["CLASSES"][1:]
    expected_categories = [{"id": index + 1, "name": name} for index, name in enumerate(classes)]
    if coco["categories"] != expected_categories:
        raise ValueError("Corpus classes must exactly match the frozen 14-class detector YAML")
    if qualification and coco.get("development_fixture") is not False:
        raise ValueError("Development fixtures cannot qualify a release")
    images = coco["images"]
    if any(type(image.get("id")) is not int or image["id"] <= 0 for image in images):
        raise ValueError("COCO image identities must be positive integers")
    by_id = {image["id"]: image for image in images}
    if len(by_id) != len(images):
        raise ValueError("Duplicate image identities")
    families = {}
    image_hashes = set()
    for image in images:
        for field in ["annotator", "provenance", "reuse_rights", "approved_by", "approved_at", "sha256"]:
            if not isinstance(image.get(field), str) or not image[field].strip():
                raise ValueError(f'Image {image["id"]} is missing {field}')
        if image.get("approved") is not True or image.get("independently_labeled") is not True:
            raise ValueError("Every image needs independently established labels and explicit approval")
        path = contained(images_root, image["file_name"])
        actual_hash = digest(path)
        if actual_hash != image["sha256"]:
            raise ValueError(f'Image identity changed: {image["file_name"]}')
        if qualification and actual_hash in image_hashes:
            raise ValueError("Duplicate image bytes cannot stand in for fresh capture conditions")
        image_hashes.add(actual_hash)
        with Image.open(path) as pixels:
            oriented = ImageOps.exif_transpose(pixels)
            if oriented.size != (image["width"], image["height"]):
                raise ValueError("Image dimensions must match EXIF-normalized inference pixels")
        conditions = families.setdefault(image["family_id"], [])
        conditions.append(image["condition"])
    if qualification and (
        len(images) != 80
        or len(families) != 20
        or any(len(conditions) != 4 or set(conditions) != CONDITIONS for conditions in families.values())
    ):
        raise ValueError("Qualification requires 80 images: 20 families with all four capture conditions")
    if qualification:
        sources = coco.get("sources", [])
        if (
            len(sources) != 20
            or {source["id"] for source in sources} != set(families)
            or len({source["sha256"] for source in sources}) != 20
        ):
            raise ValueError("Record twenty distinct original digital source identities and family relationships")
        if any(not source.get("author") or not source.get("reuse_rights") for source in sources):
            raise ValueError("Original digital sources require authorship and reuse rights")
    support = {category["id"]: set() for category in expected_categories}
    annotation_ids = set()
    orders = {}
    for annotation in coco["annotations"]:
        if type(annotation.get("id")) is not int or annotation["id"] <= 0:
            raise ValueError("COCO annotation identities must be positive integers; zero is an unmatched sentinel")
        if annotation["id"] in annotation_ids:
            raise ValueError("Duplicate annotation identity")
        annotation_ids.add(annotation["id"])
        image = by_id[annotation["image_id"]]
        bbox = annotation["bbox"]
        if len(bbox) != 4 or any(
            isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in bbox
        ):
            raise ValueError("Annotations require four finite xywh coordinates")
        x, y, width, height = bbox
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > image["width"] or y + height > image["height"]:
            raise ValueError("Annotation box is empty or outside image bounds")
        if annotation.get("iscrowd", 0) != 0:
            raise ValueError("Individual-glyph qualification does not support crowd annotations")
        if not math.isclose(annotation["area"], width * height):
            raise ValueError("Annotation area must agree with its bbox")
        order = annotation.get("reading_order")
        if order is not None:
            if isinstance(order, bool) or not isinstance(order, int) or order < 0:
                raise ValueError("Reading order must be a nonnegative integer")
            used = orders.setdefault(image["id"], set())
            if order in used:
                raise ValueError("Reading order must be unique within an image")
            used.add(order)
        support[annotation["category_id"]].add(image["family_id"])
    if qualification and any(len(families) < 5 for families in support.values()):
        raise ValueError("Every foreground class needs annotation support in at least five families")
    return {str(category): len(families) for category, families in support.items()}


def corpus_identity(coco):
    return hashlib.sha256(json.dumps(coco, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
