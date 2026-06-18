# Copyright (C) 2023-2026 Sebastien Rousseau.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""End-to-end stdio regression for ``pain001-mcp``.

The fast in-process suite covers the FastMCP dispatch layer, but only a
real subprocess exercises the JSON-RPC stdio framing, the ``initialize``
handshake, and the entry-point wiring as a real MCP client would see it.
This test drives the official MCP Python ``ClientSession`` so the
framing, version negotiation, and protocol-level errors are exactly what
a Claude Desktop / IDE client would surface.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import StdioServerParameters  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


def _spawn_env() -> dict[str, str]:
    """Build the subprocess env so the spawned server finds pain001."""
    env = os.environ.copy()
    repo_root = str(Path(__file__).resolve().parents[1])
    extras = [repo_root]
    sibling = Path(__file__).resolve().parents[2] / "pain001"
    if sibling.is_dir():
        extras.append(str(sibling))
    env["PYTHONPATH"] = os.pathsep.join(extras) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    return env


async def _round_trip() -> set[str]:
    """Spawn pain001-mcp, complete ``initialize``, return registered tools."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pain001_mcp.server"],
        env=_spawn_env(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return {tool.name for tool in result.tools}


def test_pain001_mcp_subprocess_lists_tools_over_stdio():
    """Real subprocess + real MCP framing returns every registered tool."""
    tools = asyncio.run(asyncio.wait_for(_round_trip(), timeout=30))
    assert {
        "list_message_types",
        "validate_records",
        "validate_identifier",
        "generate_message",
        "generate_message_async",
        "generate_message_from_file",
        "list_supported_formats",
        "parse_camt053",
        "parse_pain002",
    } <= tools
