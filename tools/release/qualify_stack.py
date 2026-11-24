#!/usr/bin/env python3
"""Run the engineering channel in an isolated stack from two clean exact revisions.

This never publishes or grants scientific acceptance. Missing prerequisites fail.
Private raw logs and credentials must never be included in a public bundle.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def exact_checkout(path, revision):
    if not re.fullmatch("[a-f0-9]{40}", revision):
        raise ValueError("Use full forty-character source revisions")
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True)
    if actual != revision or dirty:
        raise ValueError("Qualification requires a clean checkout at the exact requested revision")


def no_skips(path):
    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    if not suites or sum(int(suite.attrib.get("tests", 0)) for suite in suites) == 0:
        raise ValueError("No integration tests executed")
    if any(int(suite.attrib.get(key, 0)) for suite in suites for key in ["failures", "errors", "skipped"]):
        raise ValueError("Failed, errored or skipped cases cannot qualify the live channel")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-bundle", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    for name in ["source-ref", "environment-ref", "checkpoint-sha256", "registry-sha256", "mysql-image"]:
        parser.add_argument("--" + name, required=True)
    for name in ["checkpoint", "registry", "probe", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    for name in ["environment", "image_bundle", "checkpoint", "registry", "probe", "output"]:
        setattr(args, name, getattr(args, name).resolve())
    exact_checkout(ROOT, args.source_ref)
    exact_checkout(args.environment, args.environment_ref)
    for path, expected in [(args.checkpoint, args.checkpoint_sha256), (args.registry, args.registry_sha256)]:
        if not re.fullmatch("[a-f0-9]{64}", expected) or sha(path) != expected:
            raise ValueError("Qualification asset identity mismatch")
    if not re.fullmatch(r"mysql(?::8\.4)?@sha256:[a-f0-9]{64}", args.mysql_image):
        raise ValueError("Use a reviewed MySQL 8.4 immutable digest")
    if not args.probe.is_file():
        raise ValueError("Build the pinned sbol-rs probe before qualification")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    source = {"application": args.source_ref, "environment": args.environment_ref}
    report = {
        "sources": source,
        "status": "failed",
        "evidence_kind": "real_cpu_engineering_stack",
        "checks": {},
        "checkpoint_sha256": args.checkpoint_sha256,
        "registry_sha256": args.registry_sha256,
        "scientific_acceptance": "pending",
        "release_qualified": False,
    }
    project = "gcai-qualify-" + secrets.token_hex(5)
    env = dict(
        os.environ,
        COMPOSE_PROJECT_NAME=project,
        GCAI_TRUSTED_ORIGINS="https://localhost:18443",
        GCAI_EXPECTED_CHECKPOINT_SHA256=args.checkpoint_sha256,
        GCAI_EXPECTED_REGISTRY_SHA256=args.registry_sha256,
    )
    stack = args.output / ".private-stack"
    stack.mkdir(mode=0o700)
    log = args.output / "private-execution.log"
    commands = []

    def run(command, *, cwd=ROOT, timeout=600, data=None):
        commands.append({"command": list(map(str, command)), "cwd": str(cwd)})
        with log.open("ab") as stream:
            result = subprocess.run(
                list(map(str, command)), cwd=cwd, env=env, input=data, stdout=stream, stderr=stream, timeout=timeout
            )
        commands[-1]["exit_status"] = result.returncode
        if result.returncode:
            raise RuntimeError("Qualification command failed; see private log")

    def capture(command):
        return subprocess.check_output(list(map(str, command)), env=env, text=True, timeout=60).strip()

    compose = [
        "docker",
        "compose",
        "-f",
        str(stack / "compose.review.yml"),
        "-f",
        str(stack / "compose.registry.yml"),
        "-f",
        str(stack / "compose.ports.yml"),
    ]
    stack_started = False
    images = []
    try:
        for name in ["compose.services.yml", "compose.review.yml", "compose.proxy.yml", "compose.registry.yml"]:
            shutil.copyfile(args.environment / name, stack / name)
        for name in ["scripts", "nginx"]:
            shutil.copytree(args.environment / name, stack / name)
        (stack / "assets").mkdir(mode=0o700)
        for name, path in [("160_model.pth", args.checkpoint), ("registry.sql", args.registry)]:
            try:
                os.link(path.resolve(), stack / "assets" / name)
            except OSError as error:
                import errno

                if error.errno != errno.EXDEV:
                    raise
                shutil.copyfile(path, stack / "assets" / name)
        run([sys.executable, stack / "scripts/init-review.py", "--directory", stack / "secrets"])
        (stack / "compose.ports.yml").write_text(
            'services:\n  proxy:\n    ports: !override ["127.0.0.1:18443:443"]\n  registry:\n    ports: !override ["127.0.0.1:18898:8080"]\n'
        )
        image_info = json.loads((args.image_bundle / "images.json").read_text())
        if image_info["sources"] != source or image_info["images"]["mysql"] != args.mysql_image:
            raise ValueError("Reviewed image bundle does not match qualification inputs")
        from oci import verify_archive, verify_imported_identity

        verified_configs = {}
        for component in ["backend", "frontend"]:
            from manifest import safe_file

            archive = safe_file(args.image_bundle, image_info["image_archives"][component]["name"])
            if sha(archive) != image_info["image_archives"][component]["sha256"]:
                raise ValueError("Reviewed image archive checksum mismatch")
            identities = verify_archive(archive, image_info["images"][component].split("@")[1], args.source_ref)
            verified_configs[component] = identities["config_digest"]
            if image_info["config_digests"][component] != identities["config_digest"]:
                raise ValueError("Bundle config identity differs from the verified OCI archive")
            imported_tag = (
                image_info["images"][component].split("@")[0]
                + ":rc-cpu-"
                + args.source_ref[:12]
                + "-"
                + args.environment_ref[:12]
            )
            existing = subprocess.run(["docker", "image", "inspect", imported_tag], capture_output=True, env=env)
            if existing.returncode == 0:
                identity = json.loads(existing.stdout)[0]["Id"]
                verify_imported_identity(identities, image_info["config_digests"][component], identity)
            else:
                images.append(imported_tag)
                run(["docker", "load", "--input", archive], timeout=300)
            image = project + "-" + component
            run(["docker", "tag", imported_tag, image])
            images.append(image)
            env["GCAI_" + component.upper() + "_IMAGE"] = capture(
                ["docker", "image", "inspect", image, "--format", "{{.Id}}"]
            )
            verify_imported_identity(
                identities, image_info["config_digests"][component], env["GCAI_" + component.upper() + "_IMAGE"]
            )
        env["GCAI_SBOL_DB_IMAGE"] = image_info["images"]["registry"]
        report["qualified_images"] = image_info["images"]
        report["qualified_config_digests"] = verified_configs
        env["GCAI_MYSQL_IMAGE"] = args.mysql_image
        for prefix, image, user in [
            ("MYSQL", args.mysql_image, "mysql"),
            ("NGINX", env["GCAI_FRONTEND_IMAGE"], "nginx"),
        ]:
            for key, flag in [("UID", "-u"), ("GID", "-g")]:
                env["GCAI_" + prefix + "_" + key] = capture(
                    ["docker", "run", "--rm", "--network", "none", "--entrypoint", "id", image, flag, user]
                )
        run(compose + ["config", "--quiet"], cwd=stack)
        (stack / "compose.qualify.yml").write_text(capture(compose + ["config"]))
        compose = ["docker", "compose", "-f", str(stack / "compose.qualify.yml")]
        stack_started = True
        run(compose + ["up", "-d"], cwd=stack)
        env.update(
            GCAI_URL="https://localhost:18443/api",
            GCAI_USERNAME="review",
            GCAI_PASSWORD_FILE=str(stack / "secrets/workspace_password"),
            SSL_CERT_FILE=str(stack / "secrets/tls.crt"),
            SBOL_DB_URL="http://127.0.0.1:18898",
            GCAI_NOTEBOOK_PUBLISH="1",
            GCAI_NOTEBOOK_PART_NAMES="BBa_R0010,BBa_B0034",
            GCAI_NOTEBOOK_OUT=str(stack / "notebook-output"),
        )
        import httpx
        import ssl

        tls = ssl.create_default_context(cafile=env["SSL_CERT_FILE"])
        password = (stack / "secrets/workspace_password").read_text().strip()
        deadline = time.monotonic() + 180
        with httpx.Client(verify=tls, auth=("review", password), timeout=10) as client:
            while True:
                try:
                    if client.get(env["GCAI_URL"] + "/healthcheck/").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Real checkpoint and database readiness timed out")
                time.sleep(1)
        report["checks"]["real_readiness"] = {"status": "passed"}
        wrong = stack / "secrets/wrong-password"
        wrong.write_text(secrets.token_hex(32))
        image = next((ROOT / "docs/examples/YES GATE").glob("*-CIRCUIT.png"))
        run(
            [
                sys.executable,
                ROOT / "tools/verify_deployment.py",
                "--image",
                image,
                "--output",
                args.output / "live",
                "--old-password-file",
                wrong,
            ],
            timeout=600,
        )
        report["checks"]["wire_and_clients"] = {
            "status": "passed",
            "credential_test": "synthetic wrong credential rejection; no rotation claim",
        }
        junit = args.output / "client-live.xml"
        run(
            [sys.executable, "-m", "pytest", "-m", "integration", "--junitxml", junit, "-q", "--disable-warnings"],
            cwd=ROOT / "client",
            timeout=1200,
        )
        no_skips(junit)
        report["checks"]["live_registry_and_clients"] = {"status": "passed"}
        run(
            [
                sys.executable,
                ROOT / "tools/verify_browser.py",
                "--image",
                image,
                "--local-certificate",
                stack / "secrets/tls.crt",
                "--output",
                args.output / "browser",
            ],
            timeout=600,
        )
        report["checks"]["browser"] = {"status": "passed"}
        import nbformat
        from nbclient import NotebookClient

        previous = dict(os.environ)
        try:
            os.environ.update(env)
            notebook = nbformat.read(ROOT / "examples/quickstart.ipynb", as_version=4)
            NotebookClient(
                notebook, timeout=240, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}
            ).execute()
            nbformat.write(notebook, args.output / "executed-quickstart.ipynb")
        finally:
            os.environ.clear()
            os.environ.update(previous)
        report["checks"]["notebook"] = {"status": "passed"}
        run(
            [
                sys.executable,
                ROOT / "tools/reconcile_sbol_validation.py",
                "--mode",
                "verify",
                "--probe",
                args.probe.resolve(),
                "--regenerate",
                args.output / "conformance",
                "--output",
                args.output / "conformance.json",
            ]
        )
        report["checks"]["dual_validator"] = {"status": "passed"}
        # Real SQL grant, backup/fresh-restore, janitor and replacement checks are a separate required command.
        run(
            [
                sys.executable,
                ROOT / "tools/release/stack_operations.py",
                "--compose",
                stack / "compose.qualify.yml",
                "--output",
                args.output / "operations.json",
            ],
            cwd=stack,
            timeout=600,
        )
        report["checks"]["operations"] = {"status": "passed"}
        report["images"] = {name: env["GCAI_" + name.upper() + "_IMAGE"] for name in ["backend", "frontend", "mysql"]}
        report["status"] = "passed"
    except Exception as error:
        report["error_type"] = type(error).__name__
    finally:
        # Scope cleanup to this freshly generated project; retain active review and rollback volumes.
        if stack_started:
            try:
                run(compose + ["down", "-v", "--remove-orphans"], cwd=stack, timeout=120)
            except Exception:
                report["cleanup_error"] = True
                report["status"] = "failed"
        for image in images:
            subprocess.run(["docker", "image", "rm", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(stack)
        report["commands"] = commands
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
