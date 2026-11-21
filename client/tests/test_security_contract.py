"""Hosted authentication and capability contracts at SDK boundaries."""

import base64

import httpx
import pytest

from gcai import GCAIClient
from gcai.errors import GCAIError
from gcai.validation import normalize_namespace
from tests.helpers import zip_bytes

HANDLE = "v1_" + "A" * 43


@pytest.mark.parametrize(
    "entries",
    [
        {},
        {"a.gb": b"LOCUS"},
        {"a.gb": b"", "a.fasta": b">seq"},
        {"a.gb": b"LOCUS", "b.gb": b"LOCUS", "a.fasta": b">seq"},
    ],
)
def test_incomplete_or_ambiguous_archives_rejected(entries):
    with GCAIClient(
        "https://gcai.test", transport=httpx.MockTransport(lambda _: httpx.Response(200, content=zip_bytes(entries)))
    ) as client:
        with pytest.raises(GCAIError, match="archive"):
            client.convert(HANDLE)


@pytest.mark.parametrize("handle", ["/etc/passwd", "../structural.xml", "v1_short", None])
def test_server_paths_rejected_before_network(handle):
    def request(_):
        pytest.fail("invalid capability reached network")

    with GCAIClient("https://gcai.test", transport=httpx.MockTransport(request)) as client:
        with pytest.raises(GCAIError, match="handle"):
            client.convert(handle)


def test_auth_can_be_loaded_from_private_file(tmp_path, monkeypatch):
    password = tmp_path / "password"
    password.write_text("private-password\n")
    monkeypatch.setenv("GCAI_USERNAME", "workspace")
    monkeypatch.setenv("GCAI_PASSWORD_FILE", str(password))
    requests = []

    def request(r):
        requests.append(r)
        return httpx.Response(200, json={"status": "healthy"})

    with GCAIClient("https://gcai.test/api", transport=httpx.MockTransport(request)) as client:
        assert client.health()
    assert requests[0].url.path == "/api/healthcheck/"
    assert requests[0].headers["Authorization"] == "Basic " + base64.b64encode(b"workspace:private-password").decode()
    assert "private" not in str(requests[0].url)


@pytest.mark.parametrize("url", ["https://user:secret@gcai.test", "http://gcai.test"])
def test_credentials_require_safe_transport(url):
    with pytest.raises(GCAIError):
        GCAIClient(url, auth=("u", "p"))


def test_sdk_bounds_path_read_before_network(tmp_path):
    from gcai.client import MAX_IMAGE_BYTES

    image = tmp_path / "oversized.png"
    with image.open("wb") as stream:
        stream.truncate(MAX_IMAGE_BYTES + 1)
    with GCAIClient("https://gcai.test") as client:
        with pytest.raises(GCAIError, match="10 MiB"):
            client.detect(image)


@pytest.mark.parametrize(
    "value",
    [
        "https://u:p@example.org",
        "https://@example.org",
        "https://example.org?q=x",
        "https://example.org#x",
        "https://example.org\\bad",
        "https://example.org/\x00bad",
        "https://example.org/\x7f",
        None,
    ],
)
def test_namespace_contract(value):
    with pytest.raises(ValueError):
        normalize_namespace(value)
    assert normalize_namespace("HTTPS://example.org/base///") == "HTTPS://example.org/base"
