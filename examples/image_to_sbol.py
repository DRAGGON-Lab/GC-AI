r"""Turn a diagram into SBOL3.

    uv run --project client python examples/image_to_sbol.py \
        "docs/examples/YES GATE/YES-GATE-CIRCUIT.png" \
        --name YesGate --namespace http://sbols.org/unspecified_namespace \
        -o /tmp/yes-gate

The detector proposes a part per glyph it finds, in left to right order. A
diagram says what those parts are and what order they come in, not which
registry parts they are, so by default each one is named after its role and
carries no sequence. Pass `--names` to bind them to parts the service holds.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from gcai import DEFAULT_URL, Design, GCAIClient, Operon, name_parts, validate_design


@dataclass
class Summary:
    """What the run produced."""

    glyphs_found: int
    parts: list[str]
    without_sequence: list[str]
    written: list[Path]


def run(
    client: GCAIClient,
    image: Path,
    *,
    name: str,
    namespace: str,
    names: Sequence[str] | None = None,
    out: Path | None = None,
    annotated: Path | None = None,
) -> Summary:
    """Detect the glyphs in `image`, build the design they describe, write it."""
    detection = client.detect(image)
    ordered = detection.ordered()

    print(f"{len(ordered)} glyphs in {image.name}")
    for index, glyph in enumerate(ordered, start=1):
        role = glyph.role.value if glyph.role else "no role for this class"
        print(f"  {index:>2}. {glyph.glyph_class.value:<22} {role:<22} {glyph.box.as_list()}")

    if annotated and detection.annotated_png:
        annotated.parent.mkdir(parents=True, exist_ok=True)
        annotated.write_bytes(detection.annotated_png)
        print(f"detections drawn on {annotated}")

    design = Design.from_detection(detection, name=name, namespace=namespace)
    if not design.parts:
        raise SystemExit("no glyph in that image maps to a component role")
    if names and len(names) != len(design.parts):
        raise SystemExit(f"{len(names)} names given for {len(design.parts)} parts; give one per part, 5' to 3'")

    name_parts(design, names)
    client.fill_parts(design)
    # One operon over every part in order, which is what the diagram shows.
    design.operons.append(Operon(name=f"{name}_operon", parts=list(design.parts)).chain())

    issues = validate_design(design)
    for issue in issues:
        print(f"{issue.severity}: {issue.path}: {issue.message}")
    if any(issue.severity == "error" for issue in issues):
        raise SystemExit("the design is not valid, so nothing was sent")

    # GenBank and FASTA come from a conversion to SBOL2, which rejects a part
    # whose range ends at zero. A part with no bases has one.
    without_sequence = [part.name for part in design.parts if not part.sequence]
    built = client.build(design, genbank=not without_sequence, fasta=not without_sequence)
    written = built.write(out, name) if out else []
    for path in written:
        print(f"wrote {path}")

    print(f"built {name} from {len(design.parts)} parts: {', '.join(part.name for part in design.parts)}")
    if without_sequence:
        print(
            f"{len(without_sequence)} of them carry no sequence, so the document records their "
            "role and their place in the order, and the parent's sequence is the assembly scars "
            "between them. GenBank and FASTA need bases, so only the SBOL3 was written."
        )
    return Summary(
        glyphs_found=len(ordered),
        parts=[part.name for part in design.parts],
        without_sequence=without_sequence,
        written=written,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path)
    parser.add_argument("--name", required=True, help="name for the design: letters, digits and _ only")
    parser.add_argument("--namespace", default="http://sbols.org/unspecified_namespace")
    parser.add_argument(
        "--names",
        help="comma separated registry part names, one per part in 5' to 3' order. "
        "Leave an entry empty to name that one after its role instead.",
    )
    parser.add_argument("-o", "--out", type=Path, help="directory to write the documents into")
    parser.add_argument("--annotated", type=Path, help="write the image with the detections drawn on it here")
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args(argv)

    names = args.names.split(",") if args.names else None
    with GCAIClient(args.url) as client:
        run(
            client,
            args.image,
            name=args.name,
            namespace=args.namespace,
            names=names,
            out=args.out,
            annotated=args.annotated,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
