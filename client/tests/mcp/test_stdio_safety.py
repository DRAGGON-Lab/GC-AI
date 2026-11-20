"""On stdio, stdout carries the protocol.

Anything written there that is not a protocol message corrupts the stream, so
the server package may only write to stderr.
"""

from __future__ import annotations

import re
from pathlib import Path

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
