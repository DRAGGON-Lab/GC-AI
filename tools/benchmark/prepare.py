#!/usr/bin/env python3
"""Author digital source families and a four-condition capture inventory."""

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

CONDITIONS = ["digital", "printed-photo", "hand-drawn-clear", "hand-drawn-hard"]
ROOT = Path(__file__).resolve().parents[2]


def prepare(output):
    import yaml

    classes = yaml.safe_load((ROOT / "backend/app/data_configs/glyphs.yaml").read_text())["CLASSES"][1:]
    output.mkdir(parents=True, exist_ok=False)
    (output / "sources").mkdir()
    inventory = {
        "schema_version": 1,
        "development_fixture": False,
        "families": [],
        "images": [],
        "categories": [{"id": i + 1, "name": name} for i, name in enumerate(classes)],
    }
    for family in range(20):
        name = f"family-{family + 1:02}"
        selected = [(family * 5 + index) % 14 for index in range(5 + family // 14)]
        svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width="1200", height="260", viewBox="0 0 1200 260")
        ET.SubElement(svg, "rect", width="1200", height="260", fill="white")
        ET.SubElement(svg, "path", d="M 35 145 H 1165", stroke="black", **{"stroke-width": "3"})
        spacing = 1000 / (len(selected) - 1)
        for index, class_index in enumerate(selected):
            left = 25 + index * spacing
            glyph = classes[class_index]
            if glyph == "cds-arrow":
                # Distinct simple arrow source, never a detector-generated annotation.
                ET.SubElement(
                    svg,
                    "path",
                    d=f"M {left} 110 h 115 l 35 35 l -35 35 h -115 z",
                    fill="white",
                    stroke="black",
                    **{"stroke-width": "4"},
                )
            else:
                source = ET.parse(ROOT / "frontend/src/assets/symbols" / (glyph + ".svg")).getroot()
                source.set("x", str(left))
                source.set("y", "60")
                source.set("width", "150")
                source.set("height", "140")
                svg.append(source)
        path = output / "sources" / (name + ".svg")
        ET.ElementTree(svg).write(path, encoding="unicode")
        inventory["families"].append(
            {
                "id": name,
                "source": str(path.relative_to(output)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "classes": [classes[index] for index in selected],
                "author": "GC-AI release tooling; owner review pending",
                "reuse_rights": "MIT repository glyph artwork and generated layout",
            }
        )
        for condition in CONDITIONS:
            inventory["images"].append(
                {
                    "id": len(inventory["images"]) + 1,
                    "family_id": name,
                    "condition": condition,
                    "file_name": name + "-" + condition + ".png",
                }
            )
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    return inventory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output)
