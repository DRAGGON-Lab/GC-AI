"""Fixtures for the client tests."""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx
import pytest

from gcai import GCAIClient
from tests.helpers import EXAMPLES, Recorder


@pytest.fixture
def handler() -> Recorder:
    return Recorder()


@pytest.fixture
def client(handler: Recorder) -> Iterator[GCAIClient]:
    with GCAIClient("http://gcai.test", transport=httpx.MockTransport(handler)) as instance:
        yield instance


@pytest.fixture(params=sorted(p.name for p in EXAMPLES.iterdir() if (p / "request.json").exists()))
def example_request(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Each committed example request, one per test run."""
    with (EXAMPLES / request.param / "request.json").open() as handle:
        payload: dict[str, Any] = json.load(handle)
    return payload
