#!/usr/bin/env python3
"""Capture complete diagnostics without rewriting historical RDF fixtures."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid

import rdflib
import sbol3

ROOT = Path(__file__).resolve().parents[1]


def version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def inspect(path, probe=None, registry_url=None):
    raw = path.read_bytes()
    result = {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    graph = rdflib.Graph().parse(data=raw, format="xml")
    result["rdf_triples"] = len(graph)
    document = sbol3.Document()
    document.read_string(raw.decode(), sbol3.RDF_XML)
    report = document.validate()
    result["pysbol3"] = {
        "status": "passed" if not len(report) else "findings",
        "count": len(report),
        "findings": [
            {
                "severity": severity,
                "rule_id": issue.rule_id,
                "subject": issue.object_id,
                "message": issue.message,
            }
            for severity, issues in (
                ("error", report.errors),
                ("warning", report.warnings),
            )
            for issue in issues
        ],
    }
    result["sbol_rs"] = {"status": "not_run", "reason": "provide --probe executable"}
    if probe:
        process = subprocess.run(
            [str(probe.resolve()), str(path.resolve())], capture_output=True, text=True
        )
        if process.returncode:
            result["sbol_rs"] = {
                "status": "error",
                "exit_code": process.returncode,
                "stderr": process.stderr,
            }
        else:
            result["sbol_rs"] = json.loads(process.stdout)
            result["sbol_rs"]["status"] = "completed"
            result["sbol_rs"]["count"] = len(result["sbol_rs"]["findings"])
    result["registry"] = {
        "status": "not_run",
        "reason": "SBOL_DB_URL not configured; no live registry available",
    }
    if registry_url:
        from sbol_db import SbolDbClient

        iri = f"https://gc-ai.test/validation/{uuid.uuid4()}"
        with SbolDbClient(registry_url) as registry:
            try:
                imported = registry.create_graph(
                    raw.decode(), format="rdfxml", document_iri=iri, version="sbol3"
                )
                result["registry"] = {
                    "status": imported.validation_status,
                    "count": imported.validation_issue_count,
                    "graph_iri": iri,
                    "client_version": version("sbol-db"),
                }
            finally:
                registry.delete_graph_by_document_iri(iri)
    return result


def regenerate(directory):
    """Replay request JSON using recorded RDF metadata in place of live MySQL."""
    sys.path.insert(0, str(ROOT / "backend"))
    from app.utils.file import create_file_sol3

    paths = []
    for original in sorted((ROOT / "docs/examples").glob("*/*.xml")):
        recorded = sbol3.Document()
        recorded.read(str(original))
        rows = {}
        for component in recorded.objects:
            if not isinstance(component, sbol3.Component):
                continue
            sequence = (
                component.sequences[0].lookup().elements if component.sequences else ""
            )
            rows[component.display_id] = (
                component.description or "",
                "",
                "",
                "",
                "",
                False,
                False,
                "",
                "",
                "",
                "",
                "",
                "",
                False,
                "",
                "",
                "",
                sequence,
                len(sequence),
                "",
            )

        class Cursor:
            def execute(self, query, parameters):
                self.name = parameters[0]

            def fetchone(self):
                return rows.get(self.name)

        request_path = original.parent / "request.json"
        payload = json.loads(request_path.read_text())
        output = directory / original.parent.name
        output.mkdir(parents=True, exist_ok=True)
        for functional, name in ((True, "full.xml"), (False, "structural.xml")):
            document = create_file_sol3(
                Cursor(), payload, include_functional=functional
            )
            path = output / name
            document.write(str(path), sbol3.RDF_XML)
            paths.append(path)
        (output / "provenance.json").write_text(
            json.dumps(
                {
                    "request": str(request_path.relative_to(ROOT)),
                    "request_sha256": hashlib.sha256(
                        request_path.read_bytes()
                    ).hexdigest(),
                    "metadata_source": str(original.relative_to(ROOT)),
                    "metadata_sha256": hashlib.sha256(
                        original.read_bytes()
                    ).hexdigest(),
                    "database": "offline fixture cursor: recorded part sequence and description; other metadata defaults",
                    "backend_sources": {
                        str(p.relative_to(ROOT)): hashlib.sha256(
                            p.read_bytes()
                        ).hexdigest()
                        for p in sorted((ROOT / "backend/app").rglob("*.py"))
                    },
                },
                indent=2,
            )
            + "\n"
        )
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path)
    parser.add_argument(
        "--regenerate",
        type=Path,
        help="Save offline request replays in this directory inside the repository",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry-url", default=os.environ.get("SBOL_DB_URL"))
    args = parser.parse_args()
    report = {
        "python": platform.python_version(),
        "versions": {
            name: version(name) for name in ("sbol3", "rdflib", "pyshacl", "sbol-db")
        },
        "fixtures": [],
    }
    paths = sorted((ROOT / "docs/examples").glob("*/*.xml"))
    if args.regenerate:
        paths += regenerate(args.regenerate.resolve())
    for path in paths:
        report["fixtures"].append(inspect(path, args.probe, args.registry_url))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    return (
        0
        if all(f["sbol_rs"].get("status") != "error" for f in report["fixtures"])
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
