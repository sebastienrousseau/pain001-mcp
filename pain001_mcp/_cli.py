# SPDX-FileCopyrightText: 2023-2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""The command line every server in the suite shares.

``serve`` is the body of each ``main()``: it parses ``--transport``,
``--host``, ``--port`` and ``--version`` and hands the result to
:func:`_transports.run`. Flag names, defaults and help text live here and
nowhere else, so the suite is started and documented the same way.

Copied verbatim into every server of the suite.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from pain001_mcp._transports import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    TRANSPORTS,
    run,
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add ``--transport``, ``--host`` and ``--port`` to ``parser``."""
    group = parser.add_argument_group("transport")
    group.add_argument(
        "--transport",
        choices=TRANSPORTS,
        default="stdio",
        help=(
            "how to talk to the client: stdio (default; the client spawns "
            "this process), streamable-http (HTTP at --host:--port/mcp, "
            "protocol 2026-07-28 and 2025-11-25) or sse (the older HTTP+SSE "
            "transport at /sse and /messages/)"
        ),
    )
    group.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="interface to bind for the HTTP transports (default: 127.0.0.1)",
    )
    group.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="port to bind for the HTTP transports (default: 8000)",
    )


def serve(
    server: Any, argv: Sequence[str] | None, prog: str, version: str
) -> None:
    """Parse ``argv`` and run ``server``: the body of every ``main()``."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description=f"{prog} {version}: an MCP server. Speaks stdio by default.",
    )
    parser.add_argument(
        "--version", action="version", version=f"{prog} {version}"
    )
    add_arguments(parser)
    args = parser.parse_args(argv)
    run(server, args.transport, args.host, args.port)
