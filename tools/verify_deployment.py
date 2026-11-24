#!/usr/bin/env python3
"""Run non-destructive review checks; write a private, sanitized evidence report.

Credentials come only from GCAI_USERNAME/GCAI_PASSWORD_FILE; SSL_CERT_FILE can
supply a private deployment CA. This is runtime evidence, not a migration receipt.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from gcai import GCAIClient

ROOT = Path(__file__).resolve().parents[1]


def design():
    return {
        "namespace": "https://gc-ai.test/review",
        "components": [
            {"name": "Review", "role": "Engineered-Region", "new": True, "uri": "https://gc-ai.test/parts/"},
            {"name": "GFP", "role": "CDS", "new": True, "uri": "https://gc-ai.test/parts/", "sequence": "ATGC"},
            {"name": "part2", "role": "CDS", "new": True, "uri": "https://gc-ai.test/parts/", "sequence": "NNAA"},
        ],
        "expressions": [],
        "interactions": [],
        "eds": [],
    }


def verify_formats(built, expected=None):
    import sbol3
    from Bio import SeqIO

    document = sbol3.Document()
    document.read_string(built.sbol3.decode(), "xml")
    assert len(document.validate()) == 0
    expected = expected or {"Review": "atgctactagagnnaa", "GFP": "atgc", "part2": "nnaa"}
    for content, kind in ((built.fasta, "fasta"), (built.genbank, "genbank")):
        assert content
        records = list(SeqIO.parse(io.StringIO(content.decode()), kind))
        assert len(records) == len(expected)
        assert {r.id.split(".")[0]: str(r.seq).lower() for r in records} == expected
        if kind == "genbank":
            parent = next(r for r in records if r.id.split(".")[0] == "Review")
            assert sorted((int(f.location.start), int(f.location.end)) for f in parent.features) == [(0, 4), (12, 16)]


async def verify_mcp(url, image, output):
    from mcp import Client

    from gcai.mcp.server import build_server

    server = build_server(base_url=url, allowed_roots=(image.parent, output))
    async with Client(server, raise_exceptions=False) as client:
        result = await client.call_tool(
            "design_from_image",
            {
                "name": "ReviewMCP",
                "namespace": "https://gc-ai.test/review",
                "image_path": str(image),
                "output_dir": str(output / "mcp"),
            },
        )
        assert not result.is_error
        assert result.structured_content["built"] is True
        assert result.structured_content["parts"]


def run_checks(url, image, output, *, old_password_file=None):
    checks = {}

    def check(name, function):
        try:
            function()
        except Exception as error:
            # Never expose HTTP bodies, URLs, credential paths or exception text.
            checks[name] = {"status": "failed", "error_type": type(error).__name__}
        else:
            checks[name] = {"status": "passed"}

    with GCAIClient(url) as client:

        def ready():
            assert client.health()
            assert client._request("GET", "/livez").json()["status"] == "alive"

        check("readiness_liveness", ready)
        check("sdk_create_convert", lambda: verify_formats(client.build(design())))

        def infer():
            detection = client.detect(image)
            assert detection.has_predictions and detection.glyphs and detection.annotated_png

        check("inference", infer)
        check("inference_limits_and_admission", lambda: verify_inference_limits(client, image))

        def denied_origin():
            response = client._http.post("/file/create", json=design(), headers={"Origin": "https://untrusted.invalid"})
            assert response.status_code == 403

        check("unsafe_origin_denied", denied_origin)

        def denied_anonymous():
            with httpx.Client(timeout=30) as anonymous:
                response = anonymous.get(url.rstrip("/") + "/livez")
                assert response.status_code == 401
                assert "Basic" in response.headers.get("www-authenticate", "")

        check("anonymous_denied", denied_anonymous)

        def frontend():
            parsed = urlsplit(url)
            origin = parsed.scheme + "://" + parsed.netloc
            with httpx.Client(timeout=30) as anonymous:
                assert anonymous.get(origin + "/").status_code == 401
            response = client._http.get(origin + "/")
            assert response.status_code == 200
            assert "<!doctype html>" in response.text.lower()

        check("frontend_authentication", frontend)

        if old_password_file:

            def old_denied():
                username = os.environ["GCAI_USERNAME"]
                password = old_password_file.read_text().rstrip("\r\n")
                with GCAIClient(url, auth=(username, password)) as old:
                    assert old._http.get("/livez").status_code == 401

            check("old_workspace_credential_denied", old_denied)
        else:
            checks["old_workspace_credential_denied"] = {
                "status": "not_run",
                "reason": "Old private password file not supplied",
            }

    def cli():
        process = subprocess.run(
            [sys.executable, "-m", "gcai.cli", "--url", url, "health"], capture_output=True, timeout=200
        )
        assert process.returncode == 0

    check("cli_readiness", cli)
    check("mcp_image_to_sbol", lambda: asyncio.run(verify_mcp(url, image.resolve(), output.resolve())))
    return checks


def verify_inference_limits(client, image):
    """Exercise real rejection paths and concurrent admission without a stub runner."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    assert client._http.post("/inference/").status_code == 400
    invalid = client._http.post("/inference/", files={"image": ("bad.png", b"invalid", "image/png")})
    assert invalid.status_code == 422 and invalid.json()["code"] == "invalid_image"
    oversized = client._http.post(
        "/inference/",
        files={"image": ("large.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")},
    )
    assert oversized.status_code == 413
    content = image.read_bytes()
    barrier = Barrier(4)

    def request():
        barrier.wait(timeout=30)
        return client._http.post(
            "/inference/",
            files={"image": (image.name, content, "image/png")},
            timeout=180,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda _: request(), range(4)))
    assert any(response.status_code == 200 for response in responses)
    busy = [response for response in responses if response.status_code == 503]
    assert busy, "Concurrent real inference did not demonstrate busy rejection"
    assert all(response.status_code in {200, 503} for response in responses)
    assert all(
        response.json()["code"] == "inference_busy" and int(response.headers["Retry-After"]) > 0 for response in busy
    )
    assert (
        client._http.post(
            "/inference/",
            files={"image": (image.name, content, "image/png")},
            timeout=180,
        ).status_code
        == 200
    )



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New private evidence directory; never overwritten")
    parser.add_argument("--old-password-file", type=Path)
    args = parser.parse_args(argv)
    if not __debug__:
        parser.error("Run acceptance checks without Python optimization (-O)")
    url = os.environ.get("GCAI_URL", "")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        parser.error("Set GCAI_URL to an HTTPS API base URL without credentials, query or fragment")
    if not os.environ.get("GCAI_USERNAME") or not os.environ.get("GCAI_PASSWORD_FILE"):
        parser.error("Set GCAI_USERNAME and GCAI_PASSWORD_FILE")
    if not args.image.is_file():
        parser.error("Provide an existing PNG/JPEG diagram")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {
        "evidence_kind": "review_runtime_checks",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "production_migration": "not_run",
        "database_credential_rotation": "not_run",
        "gpu_execution": "not_verified",
        "checkpoint_provenance": "not_verified",
    }
    try:
        report["source_revision"] = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        source_hash = hashlib.sha256()
        for pattern in (
            "backend/app/**/*.py",
            "client/src/**/*.py",
            "frontend/src/**/*",
            "tools/**/*.py",
            "examples/*.ipynb",
        ):
            for source in sorted(ROOT.glob(pattern)):
                if source.is_file():
                    source_hash.update(str(source.relative_to(ROOT)).encode() + b"\0" + source.read_bytes())
        report["source_fingerprint_sha256"] = source_hash.hexdigest()
        report["source_dirty"] = bool(
            subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True)
        )
        report["checks"] = run_checks(url, args.image, args.output, old_password_file=args.old_password_file)
    except Exception as error:
        report["execution_error_type"] = type(error).__name__
    report["result"] = (
        "passed"
        if report["checks"]
        and all(c["status"] == "passed" for c in report["checks"].values())
        and "execution_error_type" not in report
        else "incomplete"
    )
    with open(args.output / "report.json", "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print("Review checks: " + report["result"] + "; see private report.json")
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
