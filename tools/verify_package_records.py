#!/usr/bin/env python3
"""Detect truncated or altered installed wheel files before a runtime is accepted."""

import base64
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path


def verify():
    checked = 0
    versions = {}
    for distribution in distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name or not version or distribution.files is None:
            raise RuntimeError("Installed package metadata is missing or incomplete")
        versions[name] = version
        for record in distribution.files:
            if record.hash is None:
                continue
            if record.hash.mode != "sha256":
                raise RuntimeError("Unsupported installed-file hash algorithm")
            path = Path(distribution.locate_file(record))
            with path.open("rb") as stream:
                actual = base64.urlsafe_b64encode(hashlib.file_digest(stream, "sha256").digest()).rstrip(b"=").decode()
            if actual != record.hash.value:
                raise RuntimeError(f"Installed file differs from wheel RECORD: {name}/{record}")
            checked += 1
    return {"result": "passed", "hashed_files_checked": checked, "packages": versions}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
