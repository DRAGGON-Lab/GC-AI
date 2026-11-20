"""The `gcai` command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

from gcai.client import DEFAULT_URL, GCAIClient
from gcai.constants import Role
from gcai.design import Design
from gcai.errors import GCAIConnectionError, GCAIError

if TYPE_CHECKING:  # pragma: no cover
    from gcai.interop import SbolDb

ClientFactory = Callable[[str], GCAIClient]


def _default_factory(url: str) -> GCAIClient:
    return GCAIClient(url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gcai", description="Talk to a GC-AI service.")
    parser.add_argument("--url", default=None, help=f"service URL (default: $GCAI_URL, else {DEFAULT_URL})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="report whether the service is usable")

    detect = sub.add_parser("detect", help="detect glyphs in an image")
    detect.add_argument("image", type=Path)
    detect.add_argument("--json", action="store_true", help="print the detection as JSON")
    detect.add_argument("--save-annotated", type=Path, metavar="PNG", help="write the annotated image")

    parts = sub.add_parser("parts", help="list registry part names for a role")
    parts.add_argument("role", choices=[role.value for role in Role])
    parts.add_argument("--grep", metavar="TEXT", help="only names containing this")
    parts.add_argument("--limit", type=int, default=25, help="how many to print (0 for all)")

    part = sub.add_parser("part", help="show one registry part")
    part.add_argument("name")
    part.add_argument("--role", choices=[role.value for role in Role])

    check = sub.add_parser("check", help="validate a request body without sending it")
    check.add_argument("request", type=Path)

    validate = sub.add_parser("validate", help="validate a generated document locally")
    validate.add_argument("document", type=Path)

    roundtrip = sub.add_parser("roundtrip", help="compare the glyphs in an image with the parts in a document")
    roundtrip.add_argument("image", type=Path)
    roundtrip.add_argument("document", type=Path)

    publish = sub.add_parser("publish", help="publish a generated document to an SBOL DB registry")
    publish.add_argument("document", type=Path)
    publish.add_argument("--registry", help="registry URL (default: $SBOL_DB_URL)")
    publish.add_argument("--iri", required=True, help="document IRI to publish under")
    publish.add_argument("--name")
    publish.add_argument("--description", default="")
    publish.add_argument("--namespace")
    publish.add_argument(
        "--overwrite",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help="0 fail if it exists, 1 replace, 2 merge",
    )
    publish.add_argument(
        "--yes",
        action="store_true",
        help="required: publishing writes to a registry other people can read",
    )

    fetch = sub.add_parser("fetch", help="read a document back out of an SBOL DB registry")
    fetch.add_argument("iri")
    fetch.add_argument("-o", "--out", type=Path, required=True)
    fetch.add_argument("--registry", help="registry URL (default: $SBOL_DB_URL)")
    fetch.add_argument("--sbol2", action="store_true", help="ask the registry for SBOL2 instead of SBOL3")

    build = sub.add_parser("build", help="generate SBOL3, GenBank and FASTA from a request body")
    build.add_argument("request", type=Path)
    build.add_argument("-o", "--out", type=Path, required=True, help="directory to write into")
    build.add_argument("--stem", help="base name for the files (default: the design's name)")
    build.add_argument("--no-genbank", action="store_true")
    build.add_argument("--no-fasta", action="store_true")
    build.add_argument("--force", action="store_true", help="send the request even if it fails validation")
    return parser


def main(argv: Sequence[str] | None = None, *, factory: ClientFactory = _default_factory) -> int:
    args = build_parser().parse_args(argv)
    url = args.url or ""
    try:
        with factory(url) as client:
            return _dispatch(args, client)
    except GCAIConnectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except GCAIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace, client: GCAIClient) -> int:
    if args.command == "health":
        healthy = client.health()
        print(f"{client.base_url}: {'healthy' if healthy else 'not healthy'}")
        return 0 if healthy else 1

    if args.command == "detect":
        detection = client.detect(args.image)
        if args.save_annotated and detection.annotated_png:
            args.save_annotated.write_bytes(detection.annotated_png)
            print(f"annotated image: {args.save_annotated}", file=sys.stderr)
        if args.json:
            print(json.dumps(detection.to_json(), indent=2))
            return 0
        if not detection.has_predictions:
            print("no glyphs detected")
            return 0
        print(f"{len(detection.glyphs)} glyphs, left to right:")
        for index, glyph in enumerate(detection.ordered(), start=1):
            role = glyph.role.value if glyph.role else "(no role)"
            box = glyph.box
            print(f"  {index:>2}. {glyph.glyph_class.value:<22} {role:<22} x {box.x1}-{box.x2}")
        return 0

    if args.command == "parts":
        names = client.part_names(Role(args.role))
        if args.grep:
            names = [name for name in names if args.grep.lower() in name.lower()]
        shown = names if args.limit == 0 else names[: args.limit]
        for name in shown:
            print(name)
        if len(shown) < len(names):
            print(f"... {len(names) - len(shown)} more of {len(names)}", file=sys.stderr)
        return 0

    if args.command == "part":
        details = client.part_details(args.name, Role(args.role) if args.role else None)
        print(f"name        {details.name}")
        print(f"role        {details.role or '-'}")
        print(f"length      {details.sequence_length if details.sequence_length is not None else '-'}")
        print(f"description {(details.description or '-')[:200]}")
        if details.sequence:
            print(f"sequence    {details.sequence[:80]}{'...' if len(details.sequence) > 80 else ''}")
        return 0

    if args.command == "check":
        design = Design.from_payload(_read_json(args.request))
        issues = design.validate()
        if not issues:
            print("no problems found")
            return 0
        for issue in issues:
            print(issue)
        return 1 if any(issue.severity == "error" for issue in issues) else 0

    if args.command == "build":
        payload = _read_json(args.request)
        design = Design.from_payload(payload)
        stem = args.stem or design.name or "design"
        result = client.build(
            design,
            genbank=not args.no_genbank,
            fasta=not args.no_fasta,
            validate=not args.force,
        )
        for path in result.write(args.out, stem):
            print(path)
        return 0

    if args.command == "validate":
        from gcai.interop import validate as validate_document

        issues = validate_document(args.document.read_bytes())
        if not issues:
            print(f"{args.document}: valid")
            return 0
        for issue in issues:
            print(issue)
        return 1 if any(issue.severity == "error" for issue in issues) else 0

    if args.command == "roundtrip":
        from gcai.interop import check_order

        detection = client.detect(args.image)
        report = check_order(detection, args.document.read_bytes())
        print(report.format())
        return 0 if report.ok else 1

    if args.command == "publish":
        if not args.yes:
            print(
                "error: publishing writes to a registry other people can read. " "Pass --yes to go ahead.",
                file=sys.stderr,
            )
            return 1
        with _registry(args.registry) as registry:
            published = registry.publish(
                args.document.read_bytes(),
                document_iri=args.iri,
                name=args.name,
                description=args.description,
                namespace=args.namespace,
                overwrite=args.overwrite,
            )
        print(published)
        if not published.valid:
            # The document is published either way: the registry records the
            # findings and keeps the import.
            print(
                f"warning: the registry's validator reported "
                f"{published.validation_issue_count} issues ({published.validation_status})",
                file=sys.stderr,
            )
        return 0

    if args.command == "fetch":
        with _registry(args.registry) as registry:
            data = registry.to_sbol2(args.iri) if args.sbol2 else registry.fetch(args.iri)
        args.out.write_bytes(data)
        print(f"{args.out} ({len(data)} bytes)")
        return 0

    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


def _registry(url: str | None) -> "SbolDb":
    """Open the registry named on the command line, or in the environment."""
    from gcai.interop import SbolDb

    if url:
        return SbolDb(url)
    return SbolDb.from_env()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        data: dict[str, Any] = json.load(handle)
    return data


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
