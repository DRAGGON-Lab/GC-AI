"""Private persistent capabilities. A metadata rename commits both documents.

The token is a bearer capability, never a server path. Readers open the root,
capability directory and fixed files with O_NOFOLLOW and parse those same bytes.
"""

from contextlib import contextmanager
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
import time

from app.utils.custom_error import CustomError

HANDLE = re.compile(r"v1_[A-Za-z0-9_-]{43}\Z")
TTL_SECONDS = 24 * 3600
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class ArtifactStore:
    def __init__(self, root):
        self.root = os.fspath(root)
        os.makedirs(self.root, mode=0o700, exist_ok=True)
        # Opening first prevents chmod from following a substituted symlink.
        with self._root() as fd:
            os.fchmod(fd, 0o700)

    @contextmanager
    def _root(self):
        fd = os.open(self.root, DIRECTORY_FLAGS)
        try:
            yield fd
        finally:
            os.close(fd)

    @staticmethod
    def validate_handle(handle):
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
            raise CustomError(
                "Expected a v1 structural_handle returned by /file/create; server paths are not accepted",
                400,
                code="invalid_handle",
            )

    @staticmethod
    def _read_file(directory_fd, name, maximum=None):
        fd = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
        )
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
                raise OSError("Artifact must be a private regular file")
            if maximum is not None and info.st_size > maximum:
                raise OSError("Invalid metadata")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                return stream.read() if maximum is None else stream.read(maximum + 1)
        finally:
            os.close(fd)

    @classmethod
    def _expires(cls, directory_fd):
        metadata = json.loads(cls._read_file(directory_fd, "metadata.json", 1024))
        created = metadata["created_at"]
        expires = metadata["expires_at"]
        if (
            type(created) not in (int, float)
            or type(expires) not in (int, float)
            or expires != created + TTL_SECONDS
        ):
            raise ValueError("Invalid immutable expiry")
        return expires

    def read(self, handle, filename="structural.xml"):
        self.validate_handle(handle)
        if filename not in ("structural.xml", "full.xml"):
            raise ValueError("Not a supported artifact filename")
        try:
            with self._root() as root_fd:
                fd = os.open(handle, DIRECTORY_FLAGS, dir_fd=root_fd)
                try:
                    if self._expires(fd) <= time.time():
                        raise FileNotFoundError("Expired")
                    return self._read_file(fd, filename)
                finally:
                    os.close(fd)
        except (OSError, ValueError, KeyError, TypeError):
            raise CustomError(
                "Structural handle was not found or has expired",
                404,
                code="handle_not_found",
            ) from None

    def publish(self, full, structural, *, now=None):
        now = time.time() if now is None else now
        staging = tempfile.mkdtemp(prefix=".staging-", dir=self.root)
        destination = None
        try:
            for name, contents in (
                ("full.xml", full),
                ("structural.xml", structural),
                (
                    "metadata.json",
                    json.dumps(
                        {"created_at": now, "expires_at": now + TTL_SECONDS}
                    ).encode(),
                ),
            ):
                fd = os.open(
                    os.path.join(staging, name),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                with os.fdopen(fd, "wb") as stream:
                    stream.write(contents)
                    stream.flush()
                    os.fsync(stream.fileno())
            with self._root() as root_fd:
                for _ in range(100):
                    handle = "v1_" + secrets.token_urlsafe(32)
                    try:
                        os.mkdir(handle, mode=0o700, dir_fd=root_fd)
                        destination = handle
                        break
                    except FileExistsError:
                        continue
                else:
                    raise RuntimeError("Cannot allocate artifact capability")
                fd = os.open(handle, DIRECTORY_FLAGS, dir_fd=root_fd)
                try:
                    # Readers require metadata; publishing that last commits both files.
                    for name in ("full.xml", "structural.xml", "metadata.json"):
                        os.replace(os.path.join(staging, name), name, dst_dir_fd=fd)
                    os.fsync(fd)
                    os.fsync(root_fd)
                finally:
                    os.close(fd)
            return handle
        except Exception:
            if destination:
                with self._root() as root_fd:
                    shutil.rmtree(destination, dir_fd=root_fd)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def cleanup(self, *, now=None):
        now = time.time() if now is None else now
        removed = 0
        with self._root() as root_fd:
            for handle in os.listdir(root_fd):
                is_staging = handle.startswith(".staging-")
                if not HANDLE.fullmatch(handle) and not is_staging:
                    continue
                fd = None
                try:
                    fd = os.open(handle, DIRECTORY_FLAGS, dir_fd=root_fd)
                    try:
                        expired = not is_staging and self._expires(fd) <= now
                    except FileNotFoundError:
                        # A crashed publisher may have allocated a capability before
                        # committing metadata. A full TTL safely exceeds publication.
                        expired = os.fstat(fd).st_mtime + TTL_SECONDS <= now
                    if is_staging:
                        expired = os.fstat(fd).st_mtime + TTL_SECONDS <= now
                    if expired:
                        shutil.rmtree(handle, dir_fd=root_fd)
                        removed += 1
                except (OSError, ValueError, KeyError, TypeError):
                    # Concurrent cleanup and incomplete publication are harmless.
                    continue
                finally:
                    if fd is not None:
                        os.close(fd)
        return removed
