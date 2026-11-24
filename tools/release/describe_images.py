#!/usr/bin/env python3
"""Record exact OCI identities before executing candidate qualification."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from oci import verify_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["source-revision", "environment-revision", "mysql-image", "registry-image"]:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    sources = {"application": args.source_revision, "environment": args.environment_revision}
    if any(not re.fullmatch("[a-f0-9]{40}", value) for value in sources.values()):
        raise ValueError("Record both full source revisions")
    data = {
        "sources": sources,
        "images": {"mysql": args.mysql_image, "registry": args.registry_image},
        "image_archives": {},
        "config_digests": {},
    }
    for name in ["backend", "frontend"]:
        path = args.bundle / (name + ".oci.tar")
        identities = verify_archive(path, None, args.source_revision)
        data["images"][name] = "ghcr.io/draggon-lab/gc-ai-" + name + "@" + identities["manifest_digest"]
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        data["image_archives"][name] = {"name": path.name, "sha256": digest}
        data["config_digests"][name] = identities["config_digest"]
    with (args.bundle / "images.json").open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
