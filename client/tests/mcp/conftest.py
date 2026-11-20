"""Fixtures for the MCP server tests."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest

from gcai import GCAIClient
from gcai.mcp.server import build_server
from tests.helpers import Recorder

pytest.importorskip("mcp", reason="install gc-ai-client[mcp]")

from mcp import Client  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def handler() -> Recorder:
    return Recorder()


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    directory = tmp_path / "work"
    directory.mkdir()
    return directory


@pytest.fixture
def server(handler: Recorder, workdir: Path):
    def factory() -> GCAIClient:
        return GCAIClient("http://gcai.test", transport=httpx.MockTransport(handler))

    return build_server(allowed_roots=(workdir,), service_factory=factory)


@pytest.fixture
async def client(server) -> AsyncIterator["Client"]:
    async with Client(server, raise_exceptions=False) as connected:
        yield connected


@pytest.fixture
def image(workdir: Path) -> Path:
    path = workdir / "circuit.png"
    path.write_bytes(b"pretend this is a png")
    return path
