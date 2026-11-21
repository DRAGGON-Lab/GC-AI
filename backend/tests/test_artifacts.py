"""Capability storage regressions exercise persistent files and hostile references."""

import json
import multiprocessing
import os
from pathlib import Path
import time

import pytest
from app.utils.artifacts import ArtifactStore
from app.utils.custom_error import CustomError


def child_read(root, handle, queue):
    queue.put(ArtifactStore(root).read(handle, "structural.xml"))


def test_private_persistent_cross_process_store(tmp_path):
    root = tmp_path / "private"
    store = ArtifactStore(root)
    handle = store.publish(b"<full/>", b"<structural/>")
    assert handle.startswith("v1_") and len(handle) == 46
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / handle).stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in (root / handle).iterdir())
    assert ArtifactStore(root).read(handle, "full.xml") == b"<full/>"
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    process = ctx.Process(target=child_read, args=(str(root), handle, queue))
    process.start()
    assert queue.get(timeout=10) == b"<structural/>"
    process.join(10)
    assert process.exitcode == 0


@pytest.mark.parametrize("handle", ["/etc/passwd", "../secret", "", "v1_bad", None, 2])
def test_malformed_handles_are_400(tmp_path, handle):
    with pytest.raises(CustomError) as error:
        ArtifactStore(tmp_path).read(handle)
    assert error.value.status_code == 400


def test_unissued_deleted_and_expired_are_404(tmp_path):
    store = ArtifactStore(tmp_path)
    with pytest.raises(CustomError) as error:
        store.read("v1_" + "a" * 43)
    assert error.value.status_code == 404
    handle = store.publish(b"full", b"structural", now=time.time() - 86401)
    with pytest.raises(CustomError) as error:
        store.read(handle)
    assert error.value.status_code == 404
    assert store.cleanup() == 1
    assert not (tmp_path / handle).exists()


def test_symlink_cannot_escape_store(tmp_path):
    root = tmp_path / "store"
    store = ArtifactStore(root)
    handle = store.publish(b"full", b"structural")
    secret = tmp_path / "secret"
    secret.write_bytes(b"secret")
    (root / handle / "structural.xml").unlink()
    (root / handle / "structural.xml").symlink_to(secret)
    with pytest.raises(CustomError) as error:
        store.read(handle)
    assert error.value.status_code == 404
    other = "v1_" + "b" * 43
    (root / other).symlink_to(root / handle, target_is_directory=True)
    with pytest.raises(CustomError):
        store.read(other)
    assert secret.read_bytes() == b"secret"


def test_collision_does_not_replace_previous_artifact(tmp_path, monkeypatch):
    from app.utils import artifacts

    tokens = iter(["a" * 43, "a" * 43, "b" * 43])
    monkeypatch.setattr(artifacts.secrets, "token_urlsafe", lambda n: next(tokens))
    store = ArtifactStore(tmp_path)
    first = store.publish(b"first", b"first")
    second = store.publish(b"second", b"second")
    assert first != second
    assert store.read(first) == b"first"
    assert store.read(second) == b"second"


def test_failed_publication_is_not_resolvable(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    from app.utils import artifacts

    real = artifacts.os.replace

    def fail(source, dest, **kwargs):
        if dest == "metadata.json":
            raise OSError("publication failed")
        return real(source, dest, **kwargs)

    monkeypatch.setattr(artifacts.os, "replace", fail)
    with pytest.raises(OSError):
        store.publish(b"full", b"structural")
    assert list(tmp_path.iterdir()) == []


def test_cleanup_racing_an_opened_document_returns_same_bytes(tmp_path, monkeypatch):
    """Unlink after open must neither reopen another file nor leak a descriptor."""
    from app.utils import artifacts

    store = ArtifactStore(tmp_path)
    handle = store.publish(b"full", b"original structural bytes")
    real_open = artifacts.os.open
    raced = []

    def racing_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path == "structural.xml" and not raced:
            raced.append(True)
            assert store.cleanup(now=time.time() + 86401) == 1
        return fd

    monkeypatch.setattr(artifacts.os, "open", racing_open)
    assert store.read(handle) == b"original structural bytes"
    with pytest.raises(CustomError) as error:
        store.read(handle)
    assert error.value.status_code == 404


def test_deleted_handle_is_404(tmp_path):
    import shutil

    store = ArtifactStore(tmp_path)
    handle = store.publish(b"full", b"structural")
    shutil.rmtree(tmp_path / handle)
    with pytest.raises(CustomError) as error:
        store.read(handle)
    assert error.value.status_code == 404


def test_metadata_mtime_cannot_extend_expiry(tmp_path):
    store = ArtifactStore(tmp_path)
    handle = store.publish(b"full", b"structural", now=time.time() - 86401)
    os.utime(tmp_path / handle / "metadata.json", None)
    os.utime(tmp_path / handle, None)
    with pytest.raises(CustomError) as error:
        store.read(handle)
    assert error.value.status_code == 404
    assert store.cleanup() == 1


def test_janitor_cleans_old_crashed_publications_but_preserves_active(tmp_path):
    store = ArtifactStore(tmp_path)
    current = tmp_path / ("v1_" + "a" * 43)
    current.mkdir()
    crashed = tmp_path / ("v1_" + "b" * 43)
    crashed.mkdir()
    staging = tmp_path / ".staging-abandoned"
    staging.mkdir()
    active = tmp_path / ".staging-active"
    active.mkdir()
    old = time.time() - 86401
    os.utime(crashed, (old, old))
    os.utime(staging, (old, old))
    assert store.cleanup() == 2
    assert current.exists() and active.exists()
    assert not crashed.exists() and not staging.exists()
