"""Qualification preconditions must reject ambiguous source and skipped live tests."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from qualify_stack import exact_checkout, no_skips


def test_live_junit_rejects_missing_tests_and_skips(tmp_path):
    path = tmp_path / "live.xml"
    for xml in [
        "<testsuites/>",
        '<testsuite tests="0"/>',
        '<testsuite tests="2" skipped="1"/>',
        '<testsuite tests="1" failures="1"/>',
    ]:
        path.write_text(xml)
        with pytest.raises(ValueError):
            no_skips(path)
    path.write_text('<testsuite tests="22" failures="0" errors="0" skipped="0"/>')
    no_skips(path)


def test_qualification_requires_full_immutable_revisions(tmp_path):
    for reference in ["main", "3cace24", "a" * 39, "g" * 40]:
        with pytest.raises(ValueError):
            exact_checkout(tmp_path, reference)


def test_imported_image_identity_is_bound_to_the_hashed_oci_graph():
    from oci import verify_imported_identity

    identities = {
        "descriptor_digest": "sha256:" + "a" * 64,
        "manifest_digest": "sha256:" + "b" * 64,
        "config_digest": "sha256:" + "c" * 64,
    }
    for observed in identities.values():
        verify_imported_identity(identities, identities["config_digest"], observed)
    with pytest.raises(ValueError, match="config identity"):
        verify_imported_identity(identities, "sha256:" + "0" * 64, identities["manifest_digest"])
    with pytest.raises(ValueError, match="outside"):
        verify_imported_identity(identities, identities["config_digest"], "sha256:" + "0" * 64)
