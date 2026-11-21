#!/usr/bin/env python3
"""Verify conformance and immutable historical diagnostics, or explicitly capture evidence."""

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
        "path": display_path(path),
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
            diagnostic = result["sbol_rs"]
            if (
                not isinstance(diagnostic, dict)
                or diagnostic.get("validator") != "sbol-rs"
                or not isinstance(diagnostic.get("version"), str)
                or not isinstance(diagnostic.get("findings"), list)
            ):
                raise ValueError("Malformed probe diagnostic report")
            identities(diagnostic["findings"])
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


BASELINE = ROOT / "docs/validation/historical-baseline.json"
PROBE_VERSION = "0.2.2"


def display_path(path):
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def identities(findings):
    """Canonical diagnostic identity, preserving duplicate findings."""
    return sorted(
        [
            {
                "severity": f["severity"],
                "rule_id": f["rule_id"],
                "subject": f["subject"],
                "property": f.get("property"),
            }
            for f in findings
        ],
        key=lambda item: json.dumps(item, sort_keys=True),
    )


def verify(report, baseline, generated_paths):
    """Return policy violations. Missing/execution evidence is handled separately."""
    violations = []
    historical = {
        f["path"]: f for f in report["fixtures"] if f.get("group") == "historical"
    }
    if set(historical) != set(baseline["fixtures"]):
        violations.append("Historical fixture set differs from baseline")
    for path, expected in baseline["fixtures"].items():
        if path not in historical:
            continue
        observed = historical[path]
        if observed["sha256"] != expected["sha256"]:
            violations.append(f"{path}: historical RDF hash changed")
        for validator in ("pysbol3", "sbol_rs"):
            if identities(observed[validator]["findings"]) != expected[validator]:
                violations.append(f"{path}: {validator} diagnostic identities changed")
    generated = {display_path(path) for path in generated_paths}
    if len(generated) != 6:
        violations.append("Expected exactly six regenerated full/structural documents")
    for fixture in report["fixtures"]:
        if fixture["path"] in generated:
            for validator in ("pysbol3", "sbol_rs"):
                if fixture[validator]["findings"]:
                    violations.append(
                        f"{fixture['path']}: {validator} reported findings"
                    )
    return violations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("verify", "capture"), default="verify")
    parser.add_argument("--probe", type=Path)
    parser.add_argument(
        "--regenerate",
        type=Path,
        help="Save offline request replays; temporary paths outside the repository are supported",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--registry-url", default=os.environ.get("SBOL_DB_URL"))
    args = parser.parse_args(argv)
    report = {
        "mode": args.mode,
        "gating": args.mode == "verify",
        "python": platform.python_version(),
        "versions": {
            name: version(name) for name in ("sbol3", "rdflib", "pyshacl", "sbol-db")
        },
        "fixtures": [],
        "violations": [],
        "execution_errors": [],
    }
    historical_paths = sorted((ROOT / "docs/examples").glob("*/*.xml"))
    # Verification must never replace its expected evidence or historical inputs.
    protected = {
        args.baseline.resolve(),
        *(path.resolve() for path in historical_paths),
    }
    if (
        args.output.resolve() in protected
        or (ROOT / "docs/examples").resolve() in args.output.resolve().parents
    ):
        print("Refusing to overwrite historical baseline or RDF input", file=sys.stderr)
        return 2
    if args.regenerate and (
        args.output.resolve() == args.regenerate.resolve()
        or args.regenerate.resolve() in args.output.resolve().parents
    ):
        print(
            "Report output must be outside the regenerated evidence directory",
            file=sys.stderr,
        )
        return 2
    try:
        if args.regenerate and (
            (ROOT / "docs/examples").resolve() == args.regenerate.resolve()
            or (ROOT / "docs/examples").resolve() in args.regenerate.resolve().parents
        ):
            raise ValueError("Regeneration cannot overwrite historical fixtures")
        if args.mode == "verify" and (args.probe is None or args.regenerate is None):
            raise ValueError("Verification requires --probe and --regenerate")
        baseline = (
            json.loads(args.baseline.read_text()) if args.mode == "verify" else None
        )
        if baseline is not None and (
            baseline.get("schema_version") != 1
            or baseline.get("probe_version") != PROBE_VERSION
        ):
            raise ValueError("Unsupported historical baseline or probe pin")
        if args.probe is not None and not args.probe.is_file():
            raise ValueError("Probe executable is missing")
        if baseline is not None:
            for historical in baseline["fixtures"]:
                if not (ROOT / historical).is_file():
                    raise FileNotFoundError(
                        f"Historical RDF input is missing: {historical}"
                    )
        generated_paths = (
            regenerate(args.regenerate.resolve()) if args.regenerate else []
        )
        for path in historical_paths + generated_paths:
            fixture = inspect(path, args.probe, args.registry_url)
            fixture["group"] = (
                "historical" if path in historical_paths else "regenerated"
            )
            report["fixtures"].append(fixture)
            diagnostic = fixture["sbol_rs"]
            if diagnostic.get("status") == "error":
                raise RuntimeError(
                    f"Probe execution failed for {fixture['path']}: {diagnostic.get('stderr', '')}"
                )
            if args.mode == "verify" and diagnostic.get("version") != PROBE_VERSION:
                raise ValueError(
                    f"Expected pinned sbol-rs {PROBE_VERSION}, got {diagnostic.get('version')}"
                )
        if args.mode == "verify":
            report["violations"] = verify(report, baseline, generated_paths)
    except Exception as exc:
        report["execution_errors"].append(f"{type(exc).__name__}: {exc}")
    report["result"] = (
        "error"
        if report["execution_errors"]
        else (
            "failed"
            if report["violations"]
            else "passed" if args.mode == "verify" else "captured_non_gating"
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if report["execution_errors"]:
        return 2
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
