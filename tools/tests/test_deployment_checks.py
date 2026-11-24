"""Real HTTP Flask -> Python/CLI/MCP smoke, with explicit detector/database fakes."""

import importlib.util
from pathlib import Path
from threading import Thread

import pytest
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("verify_deployment", ROOT / "tools/verify_deployment.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    from app import create_app
    from app.routes import healthcheck_routes
    from flask import Response, request
    from PIL import Image

    class Cursor:
        def execute(self, query):
            assert query == "SELECT 1"

        def fetchone(self):
            return (1,)

        def close(self):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(healthcheck_routes, "get_model", lambda: object())
    monkeypatch.setattr(healthcheck_routes, "get_db_connection", Connection)
    app = create_app(
        {
            "TESTING": True,
            "FILES_GENERATED_DIR": str(tmp_path / "artifacts"),
            "INFERENCE_RUNNER": lambda image: (image, [[1, 1, 8, 8]], ["promoter"]),
        }
    )

    @app.route("/")
    def frontend():
        return "<!doctype html><html>synthetic frontend fixture</html>"

    @app.before_request
    def auth():
        supplied = request.authorization
        if not supplied or supplied.username != "review" or supplied.password != "synthetic-current":
            return Response(status=401, headers={"WWW-Authenticate": 'Basic realm="review"'})

    password = tmp_path / "password"
    password.write_text("synthetic-current")
    monkeypatch.setenv("GCAI_USERNAME", "review")
    monkeypatch.setenv("GCAI_PASSWORD_FILE", str(password))
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "client/src") + ":" + str(ROOT / "backend"))
    image = tmp_path / "diagram.png"
    Image.new("RGB", (16, 16), "white").save(image)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", image, tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_wire_checks_parse_real_exports_and_use_cli_and_mcp(deployment):
    url, image, output = deployment
    old = output / "old-password"
    old.write_text("synthetic-old")
    result = checks.run_checks(url, image, output, old_password_file=old)
    assert result and all(c["status"] == "passed" for c in result.values()), str(result)


def test_missing_rotation_evidence_is_not_a_pass(deployment):
    url, image, output = deployment
    result = checks.run_checks(url, image, output)
    assert result["old_workspace_credential_denied"]["status"] == "not_run"


def test_unchanged_credential_fails_rotation_gate(deployment):
    url, image, output = deployment
    old = output / "old-password"
    old.write_text("synthetic-current")
    result = checks.run_checks(url, image, output, old_password_file=old)
    assert result["old_workspace_credential_denied"] == {"status": "failed", "error_type": "AssertionError"}


def test_wrong_conversion_sequence_is_rejected():
    from types import SimpleNamespace

    with pytest.raises(Exception):
        checks.verify_formats(SimpleNamespace(sbol3=b"<broken/>", fasta=b">Review\nBAD", genbank=b"bad"))


def test_notebook_executes_against_real_http_without_publishing(deployment, monkeypatch):
    import nbformat
    from nbclient import NotebookClient

    url, _, output = deployment
    monkeypatch.setenv("GCAI_URL", url)
    monkeypatch.setenv("GCAI_NOTEBOOK_OUT", str(output / "notebook"))
    monkeypatch.setenv("GCAI_NOTEBOOK_PART_NAMES", "")
    monkeypatch.delenv("GCAI_NOTEBOOK_PUBLISH", raising=False)
    document = nbformat.read(ROOT / "examples/quickstart.ipynb", as_version=4)
    NotebookClient(document, timeout=180, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).execute()
    assert (output / "notebook/YesGate.xml").is_file()
    assert (output / "notebook/annotated.png").is_file()
    assert all(not any(o.output_type == "error" for o in c.get("outputs", [])) for c in document.cells)


def test_react_conversion_helper_consumes_actual_server_zip(deployment):
    import json
    import subprocess

    from gcai import GCAIClient

    url, _, _ = deployment
    with GCAIClient(url) as client:
        created = client.create(checks.design())
        response = client._request(
            "POST",
            "/file/convert",
            json={"structural_handle": created.structural_handle, "genbank": True, "fasta": True},
        )
    script = """
import fs from 'node:fs';
const {conversionArtifacts} = await import(process.argv[1]);
const files = await conversionArtifacts(fs.readFileSync(0), {fasta:true, genbank:true});
console.log(JSON.stringify(files.map(f => ({name:f.name, data:Buffer.from(f.data).toString('base64')}))));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, (ROOT / "frontend/src/utils/Conversion.js").as_uri()],
        input=response.content,
        capture_output=True,
        check=True,
    )
    import base64
    from types import SimpleNamespace

    files = {f["name"]: base64.b64decode(f["data"]) for f in json.loads(result.stdout)}
    checks.verify_formats(SimpleNamespace(sbol3=created.sbol3, fasta=files["design.fasta"], genbank=files["design.gb"]))


def test_private_report_sanitizes_unexpected_failures(tmp_path, monkeypatch):
    import json
    import stat

    monkeypatch.setenv("GCAI_URL", "https://review.example/api")
    monkeypatch.setenv("GCAI_USERNAME", "review")
    monkeypatch.setenv("GCAI_PASSWORD_FILE", str(tmp_path / "password"))
    image = tmp_path / "diagram.png"
    image.write_bytes(b"fixture")

    def fail(*args, **kwargs):
        raise RuntimeError("private-password-that-must-never-appear")

    monkeypatch.setattr(checks, "run_checks", fail)
    output = tmp_path / "evidence"
    assert checks.main(["--image", str(image), "--output", str(output)]) == 1
    raw = (output / "report.json").read_text()
    assert "private-password-that-must-never-appear" not in raw
    report = json.loads(raw)
    assert report["execution_error_type"] == "RuntimeError"
    assert report["result"] == "incomplete"
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "report.json").stat().st_mode) == 0o600


def test_checkpoint_hash_is_checked_before_loading_pickle(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("verify_checkpoint", ROOT / "tools/verify_checkpoint.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    checkpoint = tmp_path / "checkpoint.pth"
    checkpoint.write_bytes(b"not trusted pickle")
    monkeypatch.setenv("GCAI_MODEL_PATH", str(checkpoint))
    monkeypatch.setenv("GCAI_EXPECTED_CHECKPOINT_SHA256", "0" * 64)
    monkeypatch.setattr(
        "sys.argv", ["verify_checkpoint", "--examples", str(tmp_path), "--output", str(tmp_path / "report.json")]
    )
    with pytest.raises(SystemExit) as caught:
        verifier.main()
    assert caught.value.code == 2
    assert not (tmp_path / "report.json").exists()


def test_browser_local_certificate_pin_cannot_bypass_public_tls(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("verify_browser", ROOT / "tools/verify_browser.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    monkeypatch.setenv("GCAI_URL", "https://review.example/api")
    monkeypatch.setattr(
        "sys.argv",
        ["verify_browser", "--output", str(tmp_path / "report"), "--local-certificate", str(tmp_path / "certificate")],
    )
    with pytest.raises(SystemExit) as caught:
        verifier.main()
    assert caught.value.code == 2
    assert not (tmp_path / "report").exists()


def test_gpu_gate_rejects_cpu_fallback_before_inference(tmp_path, monkeypatch):
    import hashlib
    import sys
    from types import SimpleNamespace

    from app import config

    spec = importlib.util.spec_from_file_location("gpu_verifier", ROOT / "tools/verify_checkpoint.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    checkpoint = tmp_path / "checkpoint"
    checkpoint.write_bytes(b"provenance fixture; never deserialized")
    monkeypatch.setenv("GCAI_MODEL_PATH", str(checkpoint))
    monkeypatch.setenv("GCAI_EXPECTED_CHECKPOINT_SHA256", hashlib.sha256(checkpoint.read_bytes()).hexdigest())
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(__version__="fake", set_num_threads=lambda _: None))
    monkeypatch.setitem(sys.modules, "torchvision", SimpleNamespace(__version__="fake"))
    monkeypatch.setattr(
        config, "get_model", lambda: SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device="cpu")]))
    )
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        sys, "argv", ["verify_checkpoint", "--examples", str(tmp_path), "--output", str(report), "--require-gpu"]
    )
    assert verifier.main() == 1
    import json

    result = json.loads(report.read_text())
    assert result["execution_error_code"] == "gpu_required"
    assert result["gpu_execution"] is False
    assert result["fixtures"] == []
