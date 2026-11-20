r"""Put a document produced from a diagram into an SBOL DB registry.

Build one first:

    uv run --project client python examples/image_to_sbol.py \
        "docs/examples/YES GATE/YES-GATE-CIRCUIT.png" \
        --name YesGate --names BBa_R0010,BBa_B0034 -o /tmp/yes-gate

then publish it, reading it back to confirm the registry holds it:

    uv run --project client python examples/publish_to_registry.py \
        /tmp/yes-gate/YesGate.xml --design YesGate \
        --iri https://gc-ai.example/designs/yes-gate \
        --registry http://127.0.0.1:8899 --yes

`--iri` names the graph the import becomes. The design itself is at
`<namespace>/<design>`, which is how the service builds it, so reading it back
needs nothing written down. The registry holds SBOL3 and validates every
import, keeping the graph whatever the validator says. It serves an object in
either SBOL vocabulary, so the SBOL2 form is a fetch rather than a local
conversion.

Needs the db extra: `uv sync --extra db`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from gcai import storage

DEFAULT_NAMESPACE = "http://sbols.org/unspecified_namespace"


def design_iri(namespace: str, design: str) -> str:
    """Where the service puts a design it built under `namespace`."""
    return f"{namespace.rstrip('/')}/{design}"


def run(
    registry_url: str,
    document: Path,
    *,
    iri: str,
    design: str,
    namespace: str = DEFAULT_NAMESPACE,
    description: str = "",
    overwrite: int = 0,
) -> None:
    """Publish `document` as the graph `iri`, then read the design back out."""
    with storage.client(registry_url) as registry:
        report = storage.publish(
            registry,
            document.read_bytes(),
            document_iri=iri,
            name=design,
            description=description,
            overwrite=overwrite,
        )
        print(f"published {document.name} as {iri}")
        print(f"  {report.object_count} objects, {report.triple_count} triples")
        print(f"  validation {report.validation_status}, {report.validation_issue_count} issues")
        if report.validation_status != "passed":
            print("  the import is kept either way; the registry records the issues against the graph")

        root = design_iri(namespace, design)
        sbol3 = storage.fetch(registry, root)
        sbol2 = storage.to_sbol2(registry, root)
        print(f"read {root} back")
        print(f"  {len(sbol3)} bytes of SBOL3, naming the v3 vocabulary: {'http://sbols.org/v3#' in sbol3}")
        print(f"  {len(sbol2)} bytes of SBOL2, which does not: {'http://sbols.org/v3#' not in sbol2}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("document", type=Path, help="an SBOL3 RDF/XML document")
    parser.add_argument("--design", required=True, help="the design's name, as it was built")
    parser.add_argument("--iri", required=True, help="the graph IRI to publish under")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="the namespace the design was built under")
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--overwrite",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help="0 fail if the IRI is taken, 1 replace, 2 merge",
    )
    parser.add_argument("--registry", default=os.environ.get("SBOL_DB_URL", ""))
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required: publishing writes to a registry other people can read",
    )
    args = parser.parse_args(argv)

    if not args.registry:
        parser.error("give --registry or set SBOL_DB_URL")
    if not args.yes:
        parser.error(f"this writes {args.iri} to {args.registry}; pass --yes to go ahead")

    run(
        args.registry,
        args.document,
        iri=args.iri,
        design=args.design,
        namespace=args.namespace,
        description=args.description,
        overwrite=args.overwrite,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
