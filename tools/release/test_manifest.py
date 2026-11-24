"""Publication must fail when evidence is missing, stale, modified or unaccepted."""

import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from manifest import validate, SCHEMA
from fixture_bundle import benchmark, oci


@pytest.fixture
def bundle(tmp_path):
    sources = {"application": "a" * 40, "environment": "b" * 40}
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "candidate": "rc-cpu-" + "a" * 12 + "-" + "b" * 12,
        "channel": "cpu-research",
        "platform": "linux/amd64",
        "sources": sources,
        "images": {
            name: "ghcr.io/draggon-lab/gc-ai-" + name + "@sha256:" + "d" * 64 for name in ["backend", "frontend"]
        },
        "artifacts": [],
        "checkpoint_sha256": "c" * 64,
        "registry_sha256": "e" * 64,
        "dataset_sha256": "f" * 64,
        "qualification": {},
        "scientific_acceptance": {},
        "accepted_limitations": ["Synthetic manifest test only."],
        "gpu_qualified": False,
    }
    manifest["images"].update(
        mysql="mysql:8.4@sha256:" + "1" * 64, registry="ghcr.io/marpaia/sbol-db@sha256:" + "2" * 64
    )
    manifest["image_archives"] = {}
    for name in ["backend", "frontend"]:
        archive = tmp_path / (name + ".oci.tar")
        image_digest = oci(archive, sources["application"])
        manifest["images"][name] = "ghcr.io/draggon-lab/gc-ai-" + name + "@" + image_digest
        manifest["image_archives"][name] = {"name": archive.name, "sha256": sha(archive)}
    measured = benchmark(tmp_path, sources)
    manifest["dataset_sha256"] = measured["corpus_sha256"]
    for package in ["gc_ai_backend-1.0.0rc1", "gc_ai_client-0.2.1rc1"]:
        for suffix in [".whl", ".tar.gz"]:
            path = tmp_path / (package + suffix)
            path.write_bytes(b"synthetic artifact; never publish")
            manifest["artifacts"].append({"name": path.name, "sha256": sha(path)})
    for name in json.loads(SCHEMA.read_text())["properties"]["qualification"]["required"]:
        report = {"sources": sources, "status": "passed"}
        if name == "benchmark":
            report = measured
        if name == "installed_artifacts":
            report["artifacts"] = manifest["artifacts"]
        if name in [
            "real_cpu",
            "python_cli_mcp_notebook",
            "browser",
            "authentication_origins_admission",
            "registry_grants",
            "backup_restore",
            "janitor",
            "proxy_replacement",
        ]:
            report["qualified_images"] = manifest["images"]
        if name == "proxy_replacement":
            report.update(old_ip="172.20.0.2", new_ip="172.20.0.3", recovery_seconds=2.5, proxy_restarted=False)
        if name == "real_cpu":
            report["checkpoint_sha256"] = "c" * 64
        if name == "registry_grants":
            report["registry_sha256"] = "e" * 64
        if name == "independent_reviews":
            report["issues_reviewed"] = list(range(22, 30))
        if name == "merge_protection":
            report["repositories"] = ["DRAGGON-Lab/GC-AI", "DRAGGON-Lab/GC-AI-environment"]
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(report))
        manifest["qualification"][name] = {"status": "passed", "report": path.name, "sha256": sha(path)}
    manifest["scientific_acceptance"] = {
        "accepted": True,
        "reviewer": "synthetic test",
        "report_sha256": manifest["qualification"]["benchmark"]["sha256"],
        "accepted_at": "2026-11-24T00:00:00Z",
    }
    return manifest, tmp_path


def test_complete_synthetic_manifest_passes_validation_only(bundle):
    manifest, root = bundle
    assert validate(manifest, root, publish=True)["publication_ready"] is True


@pytest.mark.parametrize(
    "defect",
    [
        "artifact",
        "missing_report",
        "tampered_report",
        "unaccepted",
        "wrong_acceptance",
        "bad_candidate",
        "unqualified_gpu",
        "missing_channel",
        "unreviewed",
    ],
)
def test_deliberate_invalid_candidates_never_publish(bundle, defect):
    manifest, root = bundle
    if defect == "artifact":
        (root / manifest["artifacts"][0]["name"]).write_bytes(b"tampered")
    if defect == "missing_report":
        (root / "real_cpu.json").unlink()
    if defect == "tampered_report":
        (root / "benchmark.json").write_text("{}")
    if defect == "unaccepted":
        manifest["scientific_acceptance"]["accepted"] = False
    if defect == "wrong_acceptance":
        manifest["scientific_acceptance"]["report_sha256"] = "0" * 64
    if defect == "bad_candidate":
        manifest["candidate"] = "rc-cpu-" + "0" * 12 + "-" + "b" * 12
    if defect == "unqualified_gpu":
        manifest["gpu_qualified"] = True
    if defect == "missing_channel":
        del manifest["qualification"]["backup_restore"]
    if defect == "unreviewed":
        path = root / "independent_reviews.json"
        report = json.loads(path.read_text())
        report["issues_reviewed"] = [22]
        path.write_text(json.dumps(report))
        manifest["qualification"]["independent_reviews"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(Exception):
        validate(manifest, root, publish=True)


def test_not_run_channel_is_not_a_publication_pass(bundle):
    manifest, root = bundle
    path = root / "real_cpu.json"
    report = json.loads(path.read_text())
    report["status"] = "not_run"
    path.write_text(json.dumps(report))
    manifest["qualification"]["real_cpu"].update(status="not_run", sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert validate(manifest, root)["publication_ready"] is False
    with pytest.raises(ValueError, match="every qualification"):
        validate(manifest, root, publish=True)


@pytest.mark.parametrize("missing", ["per_class", "settings", "errors", "family_support", "annotation_file_name"])
def test_incomplete_measured_benchmark_never_publishes(bundle, missing):
    manifest, root = bundle
    path = root / "benchmark.json"
    report = json.loads(path.read_text())
    report.pop(missing)
    path.write_text(json.dumps(report))
    identity = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["qualification"]["benchmark"]["sha256"] = identity
    manifest["scientific_acceptance"]["report_sha256"] = identity
    with pytest.raises((ValueError, FileNotFoundError, IsADirectoryError)):
        validate(manifest, root, publish=True)


@pytest.mark.parametrize("channel", ["real_cpu", "installed_artifacts"])
def test_qualification_is_bound_to_executed_image_and_artifact_identities(bundle, channel):
    manifest, root = bundle
    path = root / (channel + ".json")
    report = json.loads(path.read_text())
    if channel == "real_cpu":
        report["qualified_images"]["backend"] = "ghcr.io/draggon-lab/gc-ai-backend@sha256:" + "0" * 64
    else:
        report["artifacts"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(report))
    manifest["qualification"][channel]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="identities differ"):
        validate(manifest, root, publish=True)


def test_oci_manifest_digest_is_distinct_from_config_and_verified_from_archive(bundle):
    from oci import verify_archive

    manifest, root = bundle
    expected = manifest["images"]["backend"].split("@")[1]
    identities = verify_archive(root / "backend.oci.tar", expected, manifest["sources"]["application"])
    assert identities["config_digest"] != identities["manifest_digest"]
    with pytest.raises(ValueError, match="manifest differs"):
        verify_archive(root / "backend.oci.tar", identities["config_digest"], manifest["sources"]["application"])


def test_published_evidence_is_self_contained_and_excludes_private_files(bundle, tmp_path):
    import tarfile
    from publish import evidence_archive

    manifest, root = bundle
    (root / "release-manifest.json").write_text(json.dumps(manifest))
    (root / "private-execution.log").write_text("private credential")
    path = tmp_path / "evidence.tar.gz"
    evidence_archive(manifest, root, path)
    extracted = tmp_path / "downloaded"
    with tarfile.open(path) as archive:
        assert "private-execution.log" not in archive.getnames()
        archive.extractall(extracted, filter="data")
    downloaded = json.loads((extracted / "release-manifest.json").read_text())
    assert validate(downloaded, extracted, publish=True)["publication_ready"] is True

