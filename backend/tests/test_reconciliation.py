"""Exercise the conformance command's gating/exit-code contract with isolated evidence."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools/reconcile_sbol_validation.py"
spec = importlib.util.spec_from_file_location("reconciliation", SCRIPT)
reconciliation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconciliation)


@pytest.fixture
def run(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(reconciliation, "ROOT", root)
    baseline = root / "baseline.json"
    entries = {}
    findings = [
        {
            "severity": "error",
            "rule_id": "historical-rule",
            "subject": "urn:old",
            "property": None,
        }
    ]
    for i in range(3):
        path = root / "docs/examples" / str(i) / "original.xml"
        path.parent.mkdir(parents=True)
        path.write_text("historical RDF")
        entries[str(path.relative_to(root))] = {
            "sha256": "original",
            "pysbol3": [],
            "sbol_rs": findings,
        }
    baseline.write_text(
        json.dumps({"schema_version": 1, "probe_version": "0.2.2", "fixtures": entries})
    )
    initial_baseline = baseline.read_bytes()
    generated = tmp_path / "outside-repo"
    output = tmp_path / "report.json"
    probe = tmp_path / "probe"
    probe.write_text("probe executable")
    state = {
        "hash": "original",
        "old_findings": findings,
        "new_findings": [],
        "version": "0.2.2",
        "generated_count": 6,
    }

    def regenerate(directory):
        return [directory / f"{i}.xml" for i in range(state["generated_count"])]

    def inspect(path, *args):
        if state.get("raise"):
            raise state["raise"]
        historical = "docs/examples" in str(path)
        return {
            "path": reconciliation.display_path(path),
            "sha256": state["hash"],
            "pysbol3": {
                "findings": state.get("new_python", []) if not historical else []
            },
            "sbol_rs": {
                "version": state["version"],
                "status": state.get("probe_status", "completed"),
                "findings": (
                    state["old_findings"] if historical else state["new_findings"]
                ),
            },
        }

    monkeypatch.setattr(reconciliation, "regenerate", regenerate)
    monkeypatch.setattr(reconciliation, "inspect", inspect)

    def execute(mode="verify", extra=()):
        args = [
            "--mode",
            mode,
            "--probe",
            str(probe),
            "--regenerate",
            str(generated),
            "--baseline",
            str(baseline),
            "--output",
            str(output),
            *extra,
        ]
        code = reconciliation.main(args)
        assert baseline.read_bytes() == initial_baseline
        return code, json.loads(output.read_text())

    return execute, state, baseline, output


def test_verify_passes_all_six_and_supports_external_output_directory(run):
    execute, _, _, _ = run
    code, report = execute()
    assert code == 0
    assert report["result"] == "passed"
    assert report["gating"] is True
    assert len(report["fixtures"]) == 9


@pytest.mark.parametrize("validator", ["new_findings", "new_python"])
def test_generated_findings_including_warnings_fail_verification(run, validator):
    execute, state, _, _ = run
    state[validator] = [{"severity": "warning", "rule_id": "new", "subject": "urn:new"}]
    code, report = execute()
    assert code == 1
    assert report["violations"]


def test_changed_historical_hash_fails_without_updating_baseline(run):
    execute, state, _, _ = run
    state["hash"] = "changed"
    assert execute()[0] == 1


def test_equal_count_changed_diagnostic_identity_fails(run):
    execute, state, _, _ = run
    state["old_findings"] = copy.deepcopy(state["old_findings"])
    state["old_findings"][0]["subject"] = "urn:different"
    assert execute()[0] == 1


def test_missing_generated_output_fails(run):
    execute, state, _, _ = run
    state["generated_count"] = 5
    assert execute()[0] == 1


@pytest.mark.parametrize("change", ["version", "execution", "parse"])
def test_wrong_probe_or_execution_or_parse_error_is_exit_two(run, change):
    execute, state, _, _ = run
    if change == "version":
        state["version"] = "wrong"
    elif change == "execution":
        state["probe_status"] = "error"
    else:
        state["raise"] = ValueError("bad RDF")
    code, report = execute()
    assert code == 2
    assert report["result"] == "error"


def test_capture_is_explicitly_non_gating_even_with_findings(run):
    execute, state, _, _ = run
    state["new_findings"] = [
        {"severity": "error", "rule_id": "new", "subject": "urn:new"}
    ]
    code, report = execute("capture")
    assert code == 0
    assert report["result"] == "captured_non_gating"
    assert report["gating"] is False


def test_output_cannot_overwrite_baseline(run):
    execute, _, baseline, _ = run
    # Inspect directly: no report should be written over protected input.
    original = baseline.read_bytes()
    assert (
        reconciliation.main(["--output", str(baseline), "--baseline", str(baseline)])
        == 2
    )
    assert baseline.read_bytes() == original


def test_cli_defaults_to_verify_and_missing_probe_is_exit_two(tmp_path):
    output = tmp_path / "report.json"
    process = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 2, process.stderr
    assert json.loads(output.read_text())["mode"] == "verify"


def test_unbaselined_historical_fixture_fails_verification(run):
    execute, _, baseline, _ = run
    extra = baseline.parent / "docs/examples/unexpected/new.xml"
    extra.parent.mkdir(parents=True)
    extra.write_text("unbaselined RDF")
    code, report = execute()
    assert code == 1
    assert "Historical fixture set differs from baseline" in report["violations"]


def test_report_cannot_overwrite_regenerated_rdf(run):
    _, _, baseline, _ = run
    temporary = baseline.parent.parent
    generated = temporary / "outside-repo"
    generated.mkdir()
    rdf = generated / "0.xml"
    rdf.write_text("generated RDF")
    code = reconciliation.main(
        [
            "--probe",
            str(temporary / "probe"),
            "--regenerate",
            str(generated),
            "--baseline",
            str(baseline),
            "--output",
            str(rdf),
        ]
    )
    assert code == 2
    assert rdf.read_text() == "generated RDF"


def test_report_cannot_overwrite_historical_request(run):
    _, _, baseline, _ = run
    request = baseline.parent / "docs/examples/0/request.json"
    request.write_text('{"historical": true}')
    code = reconciliation.main(["--output", str(request), "--baseline", str(baseline)])
    assert code == 2
    assert request.read_text() == '{"historical": true}'


def test_missing_historical_input_is_exit_two(run):
    execute, _, baseline, _ = run
    (baseline.parent / "docs/examples/0/original.xml").unlink()
    code, report = execute()
    assert code == 2
    assert "Historical RDF input is missing" in report["execution_errors"][0]
