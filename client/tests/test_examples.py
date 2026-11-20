"""The scripts in examples/.

They are imported by name because conftest puts their directory on the path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

import image_to_sbol
from gcai import GCAIClient
from tests.helpers import EXAMPLES, Recorder, detection_payload, zip_bytes

MODULES = [image_to_sbol]


def service(handler: Recorder) -> None:
    """Answer the three calls a build makes."""
    handler.json("POST", "/inference/", detection_payload())
    handler.route(
        "POST",
        "/file/create",
        lambda _r: httpx.Response(200, content=b"<rdf:RDF/>", headers={"file_path_structural": "/p"}),
    )
    handler.route("POST", "/file/convert", lambda _r: httpx.Response(200, content=zip_bytes({"d_fasta.fasta": b">s"})))
    handler.json(
        "GET",
        "/component/details",
        {"name": "BBa_R0010", "description": "a promoter", "sequence": "TTGACA", "sequence_length": 6},
    )


@pytest.fixture
def image(tmp_path: Path) -> Path:
    path = tmp_path / "circuit.png"
    path.write_bytes(b"pretend this is a png")
    return path


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_each_script_describes_itself(module: Any) -> None:
    assert module.__doc__
    with pytest.raises(SystemExit) as exit_info:
        module.main(["--help"])
    assert exit_info.value.code == 0


# --------------------------------------------------------------- image_to_sbol


def test_an_unnamed_part_is_sent_as_new_with_no_sequence(
    client: GCAIClient, handler: Recorder, image: Path, tmp_path: Path
) -> None:
    service(handler)
    summary = image_to_sbol.run(client, image, name="CIRCUIT", namespace="https://example.org/d/", out=tmp_path)

    assert summary.parts == ["promoter_1", "rbs_1"]
    assert summary.without_sequence == summary.parts
    created = next(r for r in handler.requests if r.url.path == "/file/create")
    parts = json.loads(created.content)["components"][1:]
    assert [p["new"] for p in parts] == [True, True]
    assert [p["sequence"] for p in parts] == ["", ""]
    assert [path.name for path in summary.written] == ["CIRCUIT.xml"], "no bases, so no GenBank or FASTA"


def test_a_name_binds_the_part_to_the_registry(client: GCAIClient, handler: Recorder, image: Path) -> None:
    service(handler)
    summary = image_to_sbol.run(
        client, image, name="CIRCUIT", namespace="https://example.org/d/", names=["BBa_R0010", ""]
    )

    assert summary.parts == ["BBa_R0010", "rbs_1"], "an empty entry falls back to the role"
    assert summary.without_sequence == ["rbs_1"]
    parts = json.loads(next(r for r in handler.requests if r.url.path == "/file/create").content)["components"][1:]
    assert parts[0]["new"] is False and parts[0]["sequence"] == "ttgaca"


def test_the_wrong_number_of_names_is_refused_before_anything_is_sent(
    client: GCAIClient, handler: Recorder, image: Path
) -> None:
    service(handler)
    with pytest.raises(SystemExit, match="1 names given for 2 parts"):
        image_to_sbol.run(client, image, name="CIRCUIT", namespace="https://example.org/d/", names=["BBa_R0010"])
    assert not any(r.url.path == "/file/create" for r in handler.requests)


def test_an_image_with_nothing_in_it_is_refused(client: GCAIClient, handler: Recorder, image: Path) -> None:
    handler.json("POST", "/inference/", detection_payload([], []))
    with pytest.raises(SystemExit, match="no glyph"):
        image_to_sbol.run(client, image, name="CIRCUIT", namespace="https://example.org/d/")
