"""Publication preserves OCI digests and never overwrites a candidate identity."""

import hashlib
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import publish


def candidate():
    return {
        "candidate": "rc-cpu-" + "a" * 12 + "-" + "b" * 12,
        "images": {
            name: "ghcr.io/draggon-lab/gc-ai-" + name + "@sha256:" + letter * 64
            for name, letter in [("backend", "c"), ("frontend", "d")]
        },
        "image_archives": {name: {"name": name + ".oci.tar"} for name in ["backend", "frontend"]},
    }


def test_images_are_copied_from_reviewed_archives_with_preserved_manifest_digests(monkeypatch, tmp_path):
    manifest = candidate()
    expected = [manifest["images"][name].split("@")[1] for name in ["backend", "frontend"]]
    remote = Mock(side_effect=[None, None, *expected])
    run = Mock()
    monkeypatch.setattr(publish, "remote_digest", remote)
    monkeypatch.setattr(publish.subprocess, "run", run)
    publish.publish_images(manifest, tmp_path)
    assert run.call_count == 2
    assert all(call.args[0][:3] == ["skopeo", "copy", "--preserve-digests"] for call in run.call_args_list)
    assert str(tmp_path / "backend.oci.tar") in run.call_args_list[0].args[0][3]


def test_conflicting_existing_tag_stops_before_any_publication(monkeypatch, tmp_path):
    monkeypatch.setattr(publish, "remote_digest", Mock(side_effect=["sha256:" + "0" * 64, None]))
    run = Mock()
    monkeypatch.setattr(publish.subprocess, "run", run)
    with pytest.raises(ValueError, match="cannot be overwritten"):
        publish.publish_images(candidate(), tmp_path)
    run.assert_not_called()


def test_matching_existing_tags_are_not_rewritten(monkeypatch, tmp_path):
    manifest = candidate()
    expected = [manifest["images"][name].split("@")[1] for name in ["backend", "frontend"]]
    monkeypatch.setattr(publish, "remote_digest", Mock(side_effect=[*expected, *expected]))
    run = Mock()
    monkeypatch.setattr(publish.subprocess, "run", run)
    publish.publish_images(manifest, tmp_path)
    run.assert_not_called()


def test_authentication_or_network_errors_are_not_treated_as_absent_tags(monkeypatch):
    monkeypatch.setattr(
        publish.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=1, stderr=b"unauthorized", stdout=b""))
    )
    with pytest.raises(RuntimeError, match="refusing publication"):
        publish.remote_digest("example")


def test_main_refuses_writes_when_release_lookup_is_unknown(monkeypatch, tmp_path):
    import json

    (tmp_path / "release-manifest.json").write_text(json.dumps(candidate()))
    monkeypatch.setattr(sys, "argv", ["publish.py", "--bundle", str(tmp_path), "--publish"])
    monkeypatch.setattr(publish, "validate", Mock())
    monkeypatch.setattr(publish, "verify_images", Mock())
    writes = Mock()
    monkeypatch.setattr(publish, "publish_images", writes)
    monkeypatch.setattr(
        publish.subprocess,
        "run",
        Mock(return_value=SimpleNamespace(returncode=1, stderr=b"authentication unavailable", stdout=b"")),
    )
    with pytest.raises(RuntimeError, match="refusing publication"):
        publish.main()
    writes.assert_not_called()
