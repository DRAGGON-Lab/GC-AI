"""The `gcai-mcp` command."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from gcai.client import DEFAULT_URL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gcai-mcp", description="Serve GC-AI over MCP.")
    parser.add_argument("--url", help=f"GC-AI service (default: $GCAI_URL, else {DEFAULT_URL})")
    parser.add_argument(
        "--allow-root",
        action="append",
        metavar="DIR",
        help="a directory the server may read images from and write files to "
        "(repeatable, default: the working directory)",
    )
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--allowed-host",
        action="append",
        metavar="HOST",
        help="a Host header to accept; required when --host is not loopback",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # stdout carries the protocol on stdio, so every log line goes to stderr.
    logging.basicConfig(
        level=args.log_level.upper(),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    roots = []
    for raw in args.allow_root or [os.getcwd()]:
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            print(f"error: --allow-root {raw!r} is not a directory", file=sys.stderr)
            return 2
        roots.append(path)

    from gcai.mcp.server import build_server

    server = build_server(base_url=args.url, allowed_roots=tuple(roots))

    if not args.http:
        server.run()
        return 0

    loopback = args.host in {"127.0.0.1", "localhost", "::1"}
    if not loopback and not args.allowed_host:
        print(
            "error: serving on a non-loopback address needs --allowed-host, " "or every request is rejected",
            file=sys.stderr,
        )
        return 2

    from mcp.server.transport_security import TransportSecuritySettings

    security = (
        TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=list(args.allowed_host))
        if args.allowed_host
        else None
    )
    server.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        transport_security=security,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
