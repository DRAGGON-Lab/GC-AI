"""Validate an OCI archive's exact manifest, config and layer identities."""

import hashlib
import json
import tarfile


def verify_archive(path, expected, source_revision):
    with tarfile.open(path) as archive:

        def blob(descriptor, *, decode=False):
            identity = descriptor["digest"]
            algorithm, value = identity.split(":", 1)
            if algorithm != "sha256" or len(value) != 64:
                raise ValueError("OCI objects require SHA256 identities")
            with archive.extractfile("blobs/sha256/" + value) as stream:
                if decode:
                    content = stream.read()
                    actual = hashlib.sha256(content).hexdigest()
                else:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != value:
                raise ValueError("OCI blob identity mismatch")
            return json.loads(content) if decode else None

        with archive.extractfile("index.json") as stream:
            index = json.load(stream)
        if len(index["manifests"]) != 1:
            raise ValueError("CPU archive must contain exactly one platform manifest")
        descriptor = index["manifests"][0]
        descriptor_digest = descriptor["digest"]
        manifest = blob(descriptor, decode=True)
        if "manifests" in manifest:
            choices = [
                item
                for item in manifest["manifests"]
                if item.get("platform", {}).get("os") == "linux"
                and item.get("platform", {}).get("architecture") == "amd64"
            ]
            if len(choices) != 1 or len(manifest["manifests"]) != 1:
                raise ValueError("CPU archive must contain only Linux/amd64")
            descriptor = choices[0]
            manifest = blob(descriptor, decode=True)
        if expected is not None and descriptor["digest"] != expected:
            raise ValueError("OCI manifest differs from reviewed image digest")
        config = blob(manifest["config"], decode=True)
        if config.get("os") != "linux" or config.get("architecture") != "amd64":
            raise ValueError("CPU image platform mismatch")
        if config.get("config", {}).get("Labels", {}).get("org.opencontainers.image.revision") != source_revision:
            raise ValueError("OCI source label differs from qualification source")
        for layer in manifest["layers"]:
            blob(layer)
        return {
            "descriptor_digest": descriptor_digest,
            "manifest_digest": descriptor["digest"],
            "config_digest": manifest["config"]["digest"],
        }


def verify_imported_identity(identities, declared_config, observed_id):
    if declared_config != identities["config_digest"]:
        raise ValueError("Bundle config identity differs from the verified OCI archive")
    if observed_id not in set(identities.values()):
        raise ValueError("Executed Docker identity is outside the verified OCI graph")
