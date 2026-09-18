#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Write docs/tools.md from the running server, or check it is current.

Usage: tool_catalogue.py [--check]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pain001_mcp.server as srv

OUT = Path(__file__).resolve().parent.parent / "docs" / "tools.md"


def render() -> str:
    """Return the catalogue markdown for the registered tools."""
    tools = asyncio.run(srv.server.list_tools())
    lines = [
        "# Tool catalogue",
        "",
        "Every tool the server registers, with the description an agent sees and the",
        "arguments it accepts. Generated from the running server by",
        "`scripts/tool_catalogue.py`; CI fails if this file drifts from the code.",
        "",
        f'{len(tools)} tools. Every one returns JSON; a failure is an `{{"error": ...}}`',
        "payload, never an exception.",
        "",
    ]
    for tool in tools:
        # The SDK has renamed this field across versions.
        schema = (
            getattr(tool, "inputSchema", None)
            or getattr(tool, "input_schema", None)
            or getattr(tool, "parameters", None)
            or {}
        )
        props = schema.get("properties", {}) or {}
        required = set(schema.get("required", []) or [])
        args = (
            ", ".join(
                f"`{k}`" + ("" if k in required else " (optional)")
                for k in props
            )
            or "none"
        )
        desc = (
            (tool.description or "")
            .strip()
            .split("\n\n")[0]
            .replace("\n", " ")
        )
        lines += [f"## `{tool.name}`", "", desc, "", f"Arguments: {args}", ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the catalogue, or with --check exit 1 when it is stale."""
    text = render()
    if "--check" in (argv or sys.argv[1:]):
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(
                f"{OUT} is stale; run scripts/tool_catalogue.py",
                file=sys.stderr,
            )
            return 1
        print(f"{OUT} is current ({text.count(chr(10))} lines)")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
