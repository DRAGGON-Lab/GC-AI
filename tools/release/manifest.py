#!/usr/bin/env python3
"""Validate a complete evidence bundle before candidate publication."""

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[2] / "docs/release/release-manifest.schema.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_file(root, name):
    root = root.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Evidence files must exist inside the candidate bundle")
    return path


def verify_benchmark(report, bundle):
    import sys
    import contextlib
    import io

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmark"))
    from evaluate import evaluate

    annotations = safe_file(bundle, report.get("annotation_file_name", ""))
    predictions = safe_file(bundle, report.get("prediction_file_name", ""))
    for path, key in [(annotations, "annotation_file_sha256"), (predictions, "prediction_file_sha256")]:
        if digest(path) != report.get(key):
            raise ValueError("Benchmark input identity mismatch")
    images = (bundle / report.get("images_directory", "")).resolve()
    if not images.is_relative_to(bundle.resolve()) or not images.is_dir():
        raise ValueError("Approved benchmark images must exist inside the reviewed bundle")
    coco = json.loads(annotations.read_text())
    for source in coco.get("sources", []):
        if digest(safe_file(bundle, source["source"])) != source["sha256"]:
            raise ValueError("Original digital source identity mismatch")
    with contextlib.redirect_stdout(io.StringIO()):
        repeated = evaluate(coco, json.loads(predictions.read_text()), images, qualification=True)
    for key, value in repeated.items():
        if report.get(key) != value:
            raise ValueError("Benchmark report is incomplete or does not reproduce: " + key)


def validate(manifest, bundle, *, publish=False):
    import jsonschema

    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()), format_checker=jsonschema.FormatChecker()).validate(
        manifest
    )
    sources = manifest["sources"]
    expected = "rc-cpu-" + sources["application"][:12] + "-" + sources["environment"][:12]
    if manifest["candidate"] != expected:
        raise ValueError("Candidate identifier must be derived from both exact source revisions")
    names = [artifact["name"] for artifact in manifest["artifacts"]]
    if len(names) != len(set(names)) or not all(
        any(name.startswith(prefix) and name.endswith(suffix) for name in names)
        for prefix in ["gc_ai_backend-", "gc_ai_client-"]
        for suffix in [".whl", ".tar.gz"]
    ):
        raise ValueError("Both distributions require distinct wheel and source artifacts")
    for artifact in manifest["artifacts"]:
        if digest(safe_file(bundle, artifact["name"])) != artifact["sha256"]:
            raise ValueError("Artifact checksum mismatch")
    for name, archive in manifest["image_archives"].items():
        path = safe_file(bundle, archive["name"])
        if digest(path) != archive["sha256"]:
            raise ValueError("Reviewed OCI archive checksum mismatch")
        if publish:
            from oci import verify_archive

            verify_archive(path, manifest["images"][name].split("@")[1], sources["application"])
    reports = {}
    for name, evidence in manifest["qualification"].items():
        path = safe_file(bundle, evidence["report"])
        if digest(path) != evidence["sha256"]:
            raise ValueError("Qualification evidence checksum mismatch: " + name)
        report = json.loads(path.read_text())
        reports[name] = report
        if report.get("sources") != sources:
            raise ValueError("Qualification report source revisions differ: " + name)
        if report.get("status") != evidence["status"]:
            raise ValueError("Qualification status differs from its report: " + name)
        if publish and evidence["status"] != "passed":
            raise ValueError("Publication requires every qualification channel to pass: " + name)
    if publish:
        runtime_channels = [
            "real_cpu",
            "python_cli_mcp_notebook",
            "browser",
            "authentication_origins_admission",
            "registry_grants",
            "backup_restore",
            "janitor",
            "proxy_replacement",
        ]
        for channel in runtime_channels:
            if reports[channel].get("qualified_images") != manifest["images"]:
                raise ValueError("Qualified image identities differ from manifest: " + channel)
        if reports["installed_artifacts"].get("artifacts") != manifest["artifacts"]:
            raise ValueError("Installed artifact identities differ from manifest")
    benchmark = reports["benchmark"]
    if publish and (
        benchmark.get("evidence_kind") != "detector_accuracy"
        or benchmark.get("qualification_data_complete") is not True
        or benchmark.get("images") != 80
        or benchmark.get("families") != 20
        or benchmark.get("corpus_sha256") != manifest["dataset_sha256"]
        or benchmark.get("checkpoint_sha256") != manifest["checkpoint_sha256"]
    ):
        raise ValueError("A complete measured benchmark on approved data is required")
    if publish:
        recovery = reports["proxy_replacement"]
        if (
            recovery.get("proxy_restarted") is not False
            or not isinstance(recovery.get("recovery_seconds"), (int, float))
            or not 0 <= recovery["recovery_seconds"] <= 15
            or not recovery.get("old_ip")
            or recovery["old_ip"] == recovery.get("new_ip")
        ):
            raise ValueError(
                "Proxy replacement must change IP and recover within fifteen seconds without restarting the proxy"
            )
    if publish:
        verify_benchmark(benchmark, bundle)
    acceptance = manifest["scientific_acceptance"]
    if acceptance["report_sha256"] != manifest["qualification"]["benchmark"]["sha256"]:
        raise ValueError("Scientific acceptance must identify this exact measured benchmark report")
    if publish and acceptance["accepted"] is not True:
        raise ValueError("Owner scientific acceptance is required before publication")
    if publish and reports["registry_grants"].get("registry_sha256") != manifest["registry_sha256"]:
        raise ValueError("Live registry must use the release data identity")
    if publish and not reports["independent_reviews"].get("issues_reviewed") == list(range(22, 30)):
        raise ValueError("Independent engineering review is required for all eight packages")
    if publish and reports["real_cpu"].get("checkpoint_sha256") != manifest["checkpoint_sha256"]:
        raise ValueError("Real CPU execution must use the release checkpoint")
    if publish and reports["merge_protection"].get("repositories") != [
        "DRAGGON-Lab/GC-AI",
        "DRAGGON-Lab/GC-AI-environment",
    ]:
        raise ValueError("Merge protection must be verified for both repositories")
    return {"status": "passed", "candidate": expected, "publication_ready": publish}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(json.loads(args.manifest.read_text()), args.bundle, publish=args.publish)))
