#!/usr/bin/env python3
"""Assemble independent per-image review exports into approved COCO data."""

import argparse
import json
from pathlib import Path
from corpus import validate, digest, contained


def assemble(inventory, reviews, images):
    result = {
        "info": {"description": "GC-AI independent qualification corpus"},
        "development_fixture": False,
        "sources": inventory["families"],
        "categories": inventory["categories"],
        "images": [],
        "annotations": [],
    }
    for expected in inventory["images"]:
        review = json.loads((reviews / f'{expected["id"]}.json').read_text())
        if any(review.get(field) != expected[field] for field in ["id", "file_name", "family_id", "condition"]):
            raise ValueError("Review export does not match the capture inventory")
        annotations = review.pop("annotations")
        result["images"].append(review)
        for annotation in annotations:
            result["annotations"].append(
                {
                    **annotation,
                    "id": len(result["annotations"]) + 1,
                    "image_id": review["id"],
                    "area": annotation["bbox"][2] * annotation["bbox"][3],
                    "iscrowd": 0,
                }
            )
    validate(result, images)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["inventory", "reviews", "images", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    for source in inventory["families"]:
        if digest(contained(args.inventory.parent, source["source"])) != source["sha256"]:
            raise ValueError("Original digital source differs from the capture inventory")
    result = assemble(inventory, args.reviews, args.images)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
