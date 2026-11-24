"""Integrity gate for the trusted legacy checkpoint, before any deserialization."""
from contextlib import contextmanager
import hashlib
import hmac
import re


@contextmanager
def verified_checkpoint(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("GCAI_EXPECTED_CHECKPOINT_SHA256 must be a 64-character SHA256")
    with open(path, 'rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if not hmac.compare_digest(actual, expected_sha256.lower()):
            raise ValueError("Checkpoint SHA256 does not match the approved release manifest")
        stream.seek(0)
        yield stream
