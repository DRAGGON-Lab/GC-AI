"""Fixtures for the interop tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.interop.helpers import EXAMPLES


def example_dirs() -> list[Path]:
    return sorted(p for p in EXAMPLES.iterdir() if (p / "request.json").exists())


@pytest.fixture(params=example_dirs(), ids=lambda p: p.name)
def example(request: pytest.FixtureRequest) -> Path:
    """Each committed example directory."""
    return request.param


@pytest.fixture
def yes_gate() -> bytes:
    """The YES gate document, which has eight parts in a known order."""
    return (EXAMPLES / "YES GATE" / "YES-GATE.xml").read_bytes()
