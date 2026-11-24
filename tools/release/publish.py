#!/usr/bin/env python3
"""Publish only the exact reviewed image and Python artifact identities."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import tarfile

from manifest import validate, safe_file


def evidence_archive(manifest, bundle, destination):
    """Package only manifest-bound public inputs, never private execution logs."""
    names = {"release-manifest.json"}
    names.update(item["name"] for item in manifest["artifacts"])
    names.update(item["name"] for item in manifest["image_archives"].values())
    names.update(item["report"] for item in manifest["qualification"].values())
    benchmark = json.loads(safe_file(bundle, manifest["qualification"]["benchmark"]["report"]).read_text())
    names.update([benchmark["annotation_file_name"], benchmark["prediction_file_name"]])
    coco = json.loads(safe_file(bundle, benchmark["annotation_file_name"]).read_text())
    names.update(source["source"] for source in coco.get("sources", []))
    names.update(str(Path(benchmark["images_directory"]) / item["file_name"]) for item in coco["images"])
    with tarfile.open(destination, "w:gz") as archive:
        for name in sorted(names):
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("Unsafe evidence archive member")
            archive.add(safe_file(bundle, name), arcname=name, recursive=False)



def image_tags(manifest):
    return {
        name: reference.split("@")[0] + ":" + manifest["candidate"]
        for name, reference in manifest["images"].items()
        if name in ["backend", "frontend"]
    }


def verify_images(manifest, bundle):
    from oci import verify_archive

    for name in ["backend", "frontend"]:
        verify_archive(
            bundle / manifest["image_archives"][name]["name"],
            manifest["images"][name].split("@")[1],
            manifest["sources"]["application"],
        )


def remote_digest(tag):
    import hashlib

    result = subprocess.run(["skopeo", "inspect", "--raw", "docker://" + tag], capture_output=True)
    if result.returncode == 0:
        return "sha256:" + hashlib.sha256(result.stdout).hexdigest()
    message = result.stderr.decode(errors="replace").lower()
    if any(marker in message for marker in ["manifest unknown", "manifest_unknown", "name unknown", "name_unknown"]):
        return None
    raise RuntimeError("Unable to establish whether the candidate tag already exists; refusing publication")


def publish_images(manifest, bundle):
    tags = image_tags(manifest)
    existing = {name: remote_digest(tag) for name, tag in tags.items()}
    for name, observed in existing.items():
        expected = manifest["images"][name].split("@")[1]
        if observed is not None and observed != expected:
            raise ValueError("Candidate tag already identifies different bytes; immutable tags cannot be overwritten")
    for name, tag in tags.items():
        expected = manifest["images"][name].split("@")[1]
        if existing[name] is None:
            subprocess.run(
                [
                    "skopeo",
                    "copy",
                    "--preserve-digests",
                    "oci-archive:" + str(bundle / manifest["image_archives"][name]["name"]),
                    "docker://" + tag,
                ],
                check=True,
            )
        if remote_digest(tag) != expected:
            raise ValueError("Published image digest differs; no GitHub prerelease will be created")


def release_exists(candidate):
    result = subprocess.run(
        ["gh", "release", "view", candidate, "--repo", "DRAGGON-Lab/GC-AI", "--json", "tagName"],
        capture_output=True,
    )
    if result.returncode == 0:
        return True
    if b"release not found" in result.stderr.lower():
        return False
    raise RuntimeError("Unable to establish release absence; refusing publication")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify-images", action="store_true")
    group.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    path = args.bundle / "release-manifest.json"
    manifest = json.loads(path.read_text())
    validate(manifest, args.bundle, publish=True)
    verify_images(manifest, args.bundle)
    if not args.publish:
        return
    if release_exists(manifest["candidate"]):
        raise ValueError("Candidate release already exists; refusing to modify immutable release artifacts")
    publish_images(manifest, args.bundle)
    benchmark = args.bundle / manifest["qualification"]["benchmark"]["report"]
    notes = "CPU research candidate " + manifest["candidate"] + "\n\n"
    notes += (
        "Application: "
        + manifest["sources"]["application"]
        + "\nEnvironment: "
        + manifest["sources"]["environment"]
        + "\n\n"
    )
    notes += "Qualified for Linux/amd64 CPU research use. Production cutover and GPU execution remain separate gates.\n\nAccepted limitations:\n"
    notes += "\n".join("- " + limitation for limitation in manifest["accepted_limitations"]) + "\n"
    files = [str(args.bundle / artifact["name"]) for artifact in manifest["artifacts"]] + [str(path), str(benchmark)]
    with tempfile.TemporaryDirectory(prefix="gcai-release-notes-") as temporary:
        notes_file = Path(temporary) / "notes.md"
        notes_file.write_text(notes)
        evidence = Path(temporary) / "candidate-evidence.tar.gz"
        evidence_archive(manifest, args.bundle, evidence)
        subprocess.run(
            [
                "gh",
                "release",
                "create",
                manifest["candidate"],
                "--repo",
                "DRAGGON-Lab/GC-AI",
                "--prerelease",
                "--target",
                manifest["sources"]["application"],
                "--title",
                manifest["candidate"],
                "--notes-file",
                str(notes_file),
                *files,
                str(evidence),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
