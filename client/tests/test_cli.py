"""The command line, over a mock transport."""

from __future__ import annotations

import json

import httpx
import pytest

from gcai import GCAIClient
from gcai.cli import main
from tests.helpers import EXAMPLES, Recorder, detection_payload, error_response, zip_bytes


@pytest.fixture
def run(handler: Recorder):
    def factory(_url: str) -> GCAIClient:
        return GCAIClient("http://gcai.test", transport=httpx.MockTransport(handler))

    def invoke(*argv: str) -> int:
        return main(list(argv), factory=factory)

    return invoke


def test_health_reports_a_working_service(run, handler: Recorder, capsys) -> None:
    handler.json("GET", "/component/names", ["BBa_R0010"])
    assert run("health") == 0
    assert "healthy" in capsys.readouterr().out


def test_health_exits_nonzero_when_unhealthy(run, handler: Recorder, capsys) -> None:
    handler.route("GET", "/component/names", lambda _r: error_response(500, "down"))
    assert run("health") == 1
    assert "not healthy" in capsys.readouterr().out


def test_health_exits_two_when_unreachable(capsys) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def factory(_url: str) -> GCAIClient:
        return GCAIClient("http://gcai.test", transport=httpx.MockTransport(refuse))

    assert main(["health"], factory=factory) == 2
    assert "cannot reach" in capsys.readouterr().err


def test_detect_prints_glyphs_in_order(run, handler: Recorder, capsys, tmp_path) -> None:
    handler.json(
        "POST",
        "/inference/",
        detection_payload(["terminator", "promoter"], [[300, 0, 350, 50], [10, 0, 60, 50]]),
    )
    image = tmp_path / "c.png"
    image.write_bytes(b"png")
    assert run("detect", str(image)) == 0
    out = capsys.readouterr().out
    assert out.index("promoter") < out.index("terminator")


def test_detect_as_json_and_saving_the_image(run, handler: Recorder, capsys, tmp_path) -> None:
    handler.json("POST", "/inference/", detection_payload())
    image = tmp_path / "c.png"
    image.write_bytes(b"png")
    annotated = tmp_path / "annotated.png"
    assert run("detect", str(image), "--json", "--save-annotated", str(annotated)) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 2
    assert annotated.exists()


def test_detect_says_so_when_nothing_is_found(run, handler: Recorder, capsys, tmp_path) -> None:
    handler.json("POST", "/inference/", detection_payload([], []))
    image = tmp_path / "c.png"
    image.write_bytes(b"png")
    assert run("detect", str(image)) == 0
    assert "no glyphs detected" in capsys.readouterr().out


def test_parts_filters_and_limits(run, handler: Recorder, capsys) -> None:
    handler.json("GET", "/component/names", ["BBa_R0010", "BBa_R0011", "BBa_J23100"])
    assert run("parts", "Promoter", "--grep", "R001") == 0
    captured = capsys.readouterr()
    assert captured.out.split() == ["BBa_R0010", "BBa_R0011"]


def test_parts_reports_how_many_were_hidden(run, handler: Recorder, capsys) -> None:
    handler.json("GET", "/component/names", [f"BBa_{i}" for i in range(30)])
    assert run("parts", "CDS", "--limit", "5") == 0
    captured = capsys.readouterr()
    assert len(captured.out.split()) == 5
    assert "25 more of 30" in captured.err


def test_part_prints_the_details(run, handler: Recorder, capsys) -> None:
    handler.json(
        "GET",
        "/component/details",
        {
            "name": "BBa_R0010",
            "description": "promoter",
            "role": "Promoter",
            "sequence": "caatacg",
            "sequence_length": 7,
        },
    )
    assert run("part", "BBa_R0010") == 0
    out = capsys.readouterr().out
    assert "BBa_R0010" in out and "caatacg" in out


def test_check_passes_a_committed_example(run, capsys) -> None:
    assert run("check", str(EXAMPLES / "YES GATE" / "request.json")) == 0
    assert "no problems found" in capsys.readouterr().out


def test_check_reports_errors_and_exits_nonzero(run, capsys, tmp_path) -> None:
    broken = tmp_path / "request.json"
    broken.write_text(
        json.dumps(
            {
                "components": [{"name": "C", "role": "Engineered-Region", "uri": "http://x/", "new": True}],
                "expressions": [],
                "interactions": [],
                "eds": [],
            }
        )
    )
    assert run("check", str(broken)) == 1
    assert "namespace" in capsys.readouterr().out


def test_build_writes_every_file(run, handler: Recorder, capsys, tmp_path) -> None:
    handler.route(
        "POST",
        "/file/create",
        lambda _r: httpx.Response(
            200,
            content=b"<rdf/>",
            headers={"X-GCAI-Structural-Handle": "v1_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"},
        ),
    )
    handler.route(
        "POST",
        "/file/convert",
        lambda _r: httpx.Response(200, content=zip_bytes({"d_genbank.gb": b"LOCUS", "d_fasta.fasta": b">s"})),
    )
    out = tmp_path / "out"
    assert run("build", str(EXAMPLES / "YES GATE" / "request.json"), "-o", str(out), "--stem", "yes") == 0
    assert sorted(p.name for p in out.iterdir()) == ["yes.fasta", "yes.gb", "yes.xml"]
    assert "yes.xml" in capsys.readouterr().out


def test_build_reports_a_service_failure(run, handler: Recorder, capsys, tmp_path) -> None:
    handler.route("POST", "/file/create", lambda _r: error_response(500, "No component data found"))
    assert run("build", str(EXAMPLES / "YES GATE" / "request.json"), "-o", str(tmp_path)) == 1
    assert "No component data found" in capsys.readouterr().err


@pytest.mark.parametrize("sbol2,version", [(False, "sbol3"), (True, "sbol2")])
def test_fetch_uses_registry_export_rdf(monkeypatch, tmp_path, sbol2, version) -> None:
    from contextlib import nullcontext

    from gcai import cli

    class Registry:
        def export_rdf(self, iri: str, *, format: str, version: str) -> str:
            assert iri == "https://example.org/design"
            assert format == "rdfxml"
            assert version == expected_version
            return "<rdf>α</rdf>"

    expected_version = version
    monkeypatch.setattr(cli, "_registry", lambda url: nullcontext(Registry()))
    out = tmp_path / "design.xml"
    arguments = ["fetch", "https://example.org/design", "-o", str(out)]
    assert main([*arguments, *(["--sbol2"] if sbol2 else [])]) == 0
    assert out.read_text() == "<rdf>α</rdf>"
