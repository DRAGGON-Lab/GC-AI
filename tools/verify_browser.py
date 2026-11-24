#!/usr/bin/env python3
"""Render the real authenticated frontend; keep screenshots and reports private."""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit


def exercise_conversion(page, image, output, report):
    from verify_deployment import verify_formats

    report["conversion_stage"] = "upload"
    downloads = []
    page.on("download", lambda download: downloads.append(download))
    with page.expect_response(lambda response: response.url.endswith("/inference/"), timeout=180000) as inference:
        page.locator("#file-input").set_input_files(str(image.resolve()))
    assert inference.value.status == 200
    page.get_by_label("Namespace", exact=False).fill("https://gc-ai.test/browser-review")
    assert page.get_by_label("Namespace", exact=False).get_attribute("required") is not None
    report["conversion_stage"] = "configure"
    names = ["Review", "UI_Promoter", "UI_RBS"]
    roles = ["Engineered-Region", "Promoter", "RBS"]
    for index, (name, role) in enumerate(zip(names, roles)):
        accordion = page.locator(".MuiAccordion-root").nth(index)
        accordion.locator(".MuiAccordionSummary-root").click()
        accordion.locator("input[type=checkbox]").first.check()
        report["configuring_part_index"] = index
        role_input = accordion.get_by_role("combobox", name="Role", exact=True)
        if index == 0:
            role_input.fill(role)
            role_input.press("ArrowDown")
            role_input.press("Enter")
        assert role_input.input_value() == role
        accordion.locator("input[name=uri]").fill("https://gc-ai.test/synthetic-browser-parts/")
        accordion.locator("input[name=identifier]").fill("test_" + name)
        accordion.locator("input[name=name]").fill(name)
        if index:
            accordion.locator("textarea[name=sequence], input[name=sequence]").fill("ATGC" if index == 1 else "NNAA")
    report["conversion_stage"] = "create"
    page.get_by_role("checkbox", name=re.compile("I have reviewed")).check()
    page.get_by_role("button", name=re.compile("Create SBOL")).click()
    with page.expect_download(timeout=180000) as created:
        page.get_by_role("button", name="Confirm", exact=True).click()
    full = output / "Review.xml"
    assert created.value.suggested_filename == "Review.xml"
    created.value.save_as(full)
    full.chmod(0o600)
    report["conversion_stage"] = "convert_retry"
    attempts = []

    def convert(route):
        body = route.request.post_data_json
        assert body["fasta"] is True and body["genbank"] is True
        assert "structural_handle" in body and "file_path" not in body
        attempts.append(body["structural_handle"])
        if len(attempts) == 1:
            route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps(
                    {
                        "status_code": 503,
                        "error": "Synthetic retry check: temporary conversion failure",
                        "code": "conversion_unavailable",
                    }
                ),
            )
        else:
            route.continue_()

    page.route("**/api/file/convert", convert)
    page.get_by_role("checkbox", name="Convert to FASTA").check()
    page.get_by_role("checkbox", name="Convert to GenBank").check()
    page.get_by_role("button", name="Convert", exact=True).click()
    page.get_by_text("Synthetic retry check: temporary conversion failure", exact=True).wait_for()
    assert len(downloads) == 1
    page.keyboard.press("Escape")
    assert page.get_by_role("checkbox", name="Convert to FASTA").is_checked()
    assert page.get_by_role("checkbox", name="Convert to GenBank").is_checked()
    page.get_by_role("button", name="Convert", exact=True).click()
    page.get_by_text("Files converted successfully!", exact=True).wait_for(timeout=180000)
    deadline = time.monotonic() + 10
    while len(downloads) < 3 and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    assert len(downloads) == 3
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    files = {}
    for download in downloads[1:]:
        path = output / download.suggested_filename
        download.save_as(path)
        path.chmod(0o600)
        files[path.suffix] = path.read_bytes()
    verify_formats(
        SimpleNamespace(sbol3=full.read_bytes(), fasta=files[".fasta"], genbank=files[".gb"]),
        expected={"Review": "atgctactagagnnaa", "UI_Promoter": "atgc", "UI_RBS": "nnaa"},
    )
    report["real_image_upload"] = "passed"
    report["real_sbol_fasta_genbank_downloads"] = "passed: parsed exact sequences and coordinates"
    report["conversion_retry"] = (
        "passed: one synthetic503 followed by real server success; "
        "same handle and format selection retained; no partial download"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", type=Path, help="Exercise the committed two-glyph YES gate and conversion retry")
    parser.add_argument("--local-certificate", type=Path, help="Pin this exact local review TLS key; loopback only")
    args = parser.parse_args()
    parsed = urlsplit(os.environ["GCAI_URL"])
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        parser.error("Use an HTTPS service URL without credentials")
    if not __debug__:
        parser.error("Run without Python optimization")
    origin = parsed.scheme + "://" + parsed.netloc
    launch_args = []
    if args.local_certificate:
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            parser.error("Local certificate pinning is restricted to loopback review")
        public_key = subprocess.run(
            ["openssl", "x509", "-in", str(args.local_certificate), "-pubkey", "-noout"],
            capture_output=True,
            check=True,
        ).stdout
        der = subprocess.run(
            ["openssl", "pkey", "-pubin", "-outform", "DER"], input=public_key, capture_output=True, check=True
        ).stdout
        pin = base64.b64encode(hashlib.sha256(der).digest()).decode()
        launch_args.append("--ignore-certificate-errors-spki-list=" + pin)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {
        "evidence_kind": "real_browser_bootstrap",
        "role_queries": {},
        "javascript_errors": [],
        "result": "failed",
    }
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as engine:
            browser = engine.chromium.launch(args=launch_args)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                http_credentials={
                    "origin": origin,
                    "username": os.environ["GCAI_USERNAME"],
                    "password": Path(os.environ["GCAI_PASSWORD_FILE"]).read_text().rstrip("\r\n"),
                },
            )
            page = context.new_page()
            page.on("pageerror", lambda error: report["javascript_errors"].append(type(error).__name__))

            def response_seen(response):
                url = urlsplit(response.url)
                if url.path.endswith("/component/names"):
                    role = parse_qs(url.query).get("role", [""])[0]
                    report["role_queries"][role] = response.status

            page.on("response", response_seen)
            response = page.goto(origin + "/", wait_until="networkidle", timeout=180000)
            assert response.status == 200
            page.wait_for_function("document.querySelector('#root')?.textContent?.length > 100")
            assert len(report["role_queries"]) == 14 and all(s == 200 for s in report["role_queries"].values())
            assert not report["javascript_errors"]
            page.screenshot(path=str(args.output / "homepage.png"), full_page=True)
            (args.output / "homepage.png").chmod(0o600)
            if args.image:
                try:
                    exercise_conversion(page, args.image, args.output, report)
                except Exception:
                    page.screenshot(path=str(args.output / "failure.png"), full_page=True)
                    (args.output / "failure.png").chmod(0o600)
                    raise
                assert not report["javascript_errors"]
            report["browser_version"] = browser.version
            report["result"] = "passed"
            browser.close()
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["diagnostic_flags"] = {
            marker: marker.lower() in str(error).lower()
            for marker in [
                "strict mode violation",
                "detached",
                "ENOENT",
                "EACCES",
                "Timeout",
                "not found",
                "not attached",
                "not a file input",
                "closed",
            ]
        }
        frames = [
            f
            for f in traceback.extract_tb(error.__traceback__)
            if Path(f.filename).name in ("verify_browser.py", "verify_deployment.py")
        ]
        if frames:
            report["error_location"] = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}"
    with open(args.output / "report.json", "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print("Browser bootstrap: " + report["result"])
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
