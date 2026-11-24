"""On stdio, stdout carries the protocol.

Anything written there that is not a protocol message corrupts the stream, so
the server package may only write to stderr.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "gcai" / "mcp"
PRINT = re.compile(r"\bprint\s*\(")


def test_nothing_in_the_server_writes_to_stdout() -> None:
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if PRINT.search(line) and "file=sys.stderr" not in line:
                # A call split over lines: look ahead for the stream argument.
                window = "\n".join(path.read_text().splitlines()[number - 1 : number + 6])
                if "file=sys.stderr" in window:
                    continue
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, "these write to stdout:\n" + "\n".join(offenders)


def test_unexpected_tool_errors_do_not_log_credentials(caplog) -> None:
    from gcai.mcp.server import _fail

    secret = "private-password-must-not-reach-logs"
    try:
        raise RuntimeError(secret)
    except RuntimeError as exc:
        error = _fail(exc)
    assert secret not in str(error)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("failure_path", ["/inference/", "/file/create"])
async def test_protocol_errors_do_not_log_credentials(client, handler, image, caplog, failure_path) -> None:
    from tests.helpers import detection_payload

    secret = "private-transport-credential-do-not-log"
    handler.json("POST", "/inference/", detection_payload())

    def fail(_request):
        raise RuntimeError(secret)

    handler.route("POST", failure_path, fail)
    result = await client.call_tool(
        "design_from_image",
        {
            "name": "Circuit",
            "namespace": "https://example.org/design",
            "image_path": str(image),
        },
    )
    assert result.is_error
    assert secret not in str(result)
    assert secret not in caplog.text
