#!/usr/bin/env python3
"""Verify grants, a fresh database restore, janitor and live proxy replacement."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = os.environ["COMPOSE_PROJECT_NAME"]
    if not project.startswith("gcai-qualify-"):
        raise ValueError("Operational qualification is restricted to a new gcai-qualify-* project")
    compose = ["docker", "compose", "-f", str(args.compose.resolve())]

    def run(command, data=None, check=True):
        return subprocess.run(command, input=data, check=check, capture_output=True, timeout=90)

    def output(command):
        return run(command).stdout.decode().strip()

    def inspect(identity):
        return json.loads(output(["docker", "inspect", identity]))[0]

    source_db = output(compose + ["ps", "-q", "db"])

    def sql(container, query, user="root", check=True):
        command = """set -eu; umask 077; config=$(mktemp); trap 'rm -f "$config"' EXIT
printf '[client]\\nuser=%s\\npassword=%s\\n' "$1" "$(cat "/run/gcai/$2")" > "$config"
mysql --defaults-extra-file="$config" --batch --skip-column-names iGEM2024"""
        return run(
            [
                "docker",
                "exec",
                "-i",
                "--user",
                "0:0",
                container,
                "sh",
                "-c",
                command,
                "sql",
                user,
                "db_root_password" if user == "root" else "db_app_password",
            ],
            query.encode(),
            check,
        )

    grants = sql(source_db, "SHOW GRANTS;", user="gcai").stdout.decode().splitlines()
    if not grants or any(
        "GRANT SELECT ON `iGEM2024`.* TO" not in line and "GRANT USAGE ON *.* TO" not in line for line in grants
    ):
        raise ValueError("Application grants exceed the required SELECT-only database access")
    original = sql(source_db, "SELECT COUNT(*) FROM parts; CHECKSUM TABLE parts;").stdout.decode()
    if int(original.splitlines()[0]) <= 0:
        raise ValueError("Registry import is empty")
    forbidden = sql(source_db, "CREATE TABLE qualification_forbidden (id INT);", user="gcai", check=False)
    if forbidden.returncode == 0 or b"1142" not in forbidden.stderr:
        raise ValueError("Application account did not receive the expected grant denial")
    if (
        sql(source_db, "SELECT COUNT(*) FROM mysql.user WHERE User='root' AND Host<>'localhost';").stdout.strip()
        != b"0"
    ):
        raise ValueError("Remote root accounts are forbidden")
    backup = Path("registry-backup.sql")
    backup_script = """set -eu; umask 077; config=$(mktemp); trap 'rm -f "$config"' EXIT
printf '[client]\\nuser=root\\npassword=%s\\n' "$(cat /run/gcai/db_root_password)" > "$config"
mysqldump --defaults-extra-file="$config" --single-transaction --skip-lock-tables --skip-triggers --no-tablespaces --set-gtid-purged=OFF iGEM2024 parts"""
    # Stream the dump to a private file; never buffer the real registry in command output.
    with backup.open("xb") as stream:
        subprocess.run(
            ["docker", "exec", "--user", "0:0", source_db, "sh", "-c", backup_script],
            stdout=stream,
            stderr=subprocess.PIPE,
            check=True,
            timeout=180,
        )
    secret_volume = next(mount["Name"] for mount in inspect(source_db)["Mounts"] if mount["Destination"] == "/run/gcai")
    restored = project + "-restore"
    restore_volume = restored + "-data"
    holder = project + "-old-ip"
    report = {"status": "failed", "checks": {}}
    try:
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                restored,
                "--network",
                "none",
                "--env",
                "MYSQL_ROOT_PASSWORD_FILE=/run/gcai/db_root_password",
                "--env",
                "MYSQL_DATABASE=iGEM2024",
                "--mount",
                "type=volume,src=" + secret_volume + ",dst=/run/gcai,readonly",
                "--mount",
                "type=volume,src=" + restore_volume + ",dst=/var/lib/mysql",
                os.environ["GCAI_MYSQL_IMAGE"],
            ]
        )
        deadline = time.monotonic() + 90
        while True:
            try:
                ready = sql(restored, "SELECT @@GLOBAL.skip_networking;", check=False)
                if ready.returncode == 0 and ready.stdout.strip() == b"0":
                    break
            except subprocess.CalledProcessError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("Fresh restore instance did not start")
            time.sleep(1)
        restore_command = """set -eu; umask 077; config=$(mktemp); trap 'rm -f "$config"' EXIT
printf '[client]\\nuser=root\\npassword=%s\\n' "$(cat /run/gcai/db_root_password)" > "$config"
mysql --defaults-extra-file="$config" iGEM2024"""
        with backup.open("rb") as stream:
            subprocess.run(
                ["docker", "exec", "-i", "--user", "0:0", restored, "sh", "-c", restore_command],
                stdin=stream,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=180,
            )
        restored_identity = sql(restored, "SELECT COUNT(*) FROM parts; CHECKSUM TABLE parts;").stdout.decode()
        if restored_identity != original:
            raise ValueError("Fresh restore row count or checksum differs")
        if sql(restored, "SELECT COUNT(*) FROM mysql.user WHERE User='gcai';").stdout.strip() != b"0":
            raise ValueError("Registry backup unexpectedly imported accounts")
        report["checks"]["grants_backup_restore"] = {
            "status": "passed",
            "table_identity": original.strip(),
            "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
            "accounts_restored": False,
        }
        code = """import os,time
from app.utils.artifacts import ArtifactStore
from app.utils.cleanup import cleanup_files
store=ArtifactStore(os.environ['GCAI_ARTIFACT_DIR'])
handle=store.publish(b'<x/>',b'<x/>',now=time.time()-86401)
cleanup_files()
from pathlib import Path
assert not (Path(store.root)/handle).exists()
"""
        run(compose + ["run", "--rm", "-T", "--no-deps", "--entrypoint", "python", "janitor", "-"], code.encode())
        report["checks"]["janitor"] = {"status": "passed"}
        backend = output(compose + ["ps", "-q", "backend"])
        proxy = output(compose + ["ps", "-q", "proxy"])
        proxy_start = inspect(proxy)["State"]["StartedAt"]
        network, config = next(
            (name, config)
            for name, config in inspect(backend)["NetworkSettings"]["Networks"].items()
            if name.endswith("_application")
        )
        old_ip = config["IPAddress"]
        started = time.monotonic()
        run(compose + ["stop", "--timeout", "1", "backend"])
        run(compose + ["rm", "-f", "backend"])
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                holder,
                "--network",
                network,
                "--ip",
                old_ip,
                "--entrypoint",
                "sleep",
                os.environ["GCAI_BACKEND_IMAGE"],
                "60",
            ]
        )
        run(compose + ["up", "-d", "--no-deps", "backend"])
        new_backend = output(compose + ["ps", "-q", "backend"])
        new_ip = inspect(new_backend)["NetworkSettings"]["Networks"][network]["IPAddress"]
        if old_ip == new_ip:
            raise ValueError("Replacement did not change the backend IP")
        import httpx, ssl

        tls = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
        password = Path(os.environ["GCAI_PASSWORD_FILE"]).read_text().strip()
        with httpx.Client(verify=tls, auth=(os.environ["GCAI_USERNAME"], password), timeout=2) as client:
            while True:
                try:
                    if client.get(os.environ["GCAI_URL"] + "/livez").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() - started >= 15:
                    raise RuntimeError("Proxy recovery exceeded fifteen seconds")
                time.sleep(0.25)
        elapsed = time.monotonic() - started
        if (
            elapsed > 15
            or output(compose + ["ps", "-q", "proxy"]) != proxy
            or inspect(proxy)["State"]["StartedAt"] != proxy_start
        ):
            raise ValueError("Proxy was restarted or recovery exceeded fifteen seconds")
        report["checks"]["proxy_replacement"] = {
            "status": "passed",
            "old_ip": old_ip,
            "new_ip": new_ip,
            "recovery_seconds": elapsed,
            "proxy_restarted": False,
        }
        report["status"] = "passed"
    finally:
        for container in [restored, holder]:
            run(["docker", "rm", "-f", container], check=False)
        run(["docker", "volume", "rm", restore_volume], check=False)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
