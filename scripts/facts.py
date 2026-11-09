#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Write pain001-mcp's facts.json: the numbers a release is described by.

The tool count was restated by hand (glama.json, docs) and drifted.
Every release now ships ``pain001-mcp-<version>.facts.json``, generated
from the running server and pyproject.toml, so manifests and the site
can render from it:

* ``version``, ``python`` and the ``pain001`` and
  ``pain001-loader-mt101`` floors from ``[tool.poetry]``;
* ``tools``, ``resource_templates`` and ``prompts`` from the server as
  an MCP client lists them.

Usage::

    python scripts/facts.py [-o FILE | --asset] [--check FILE]

``--check`` exits 1 when FILE is not what this tree would write.
``--asset`` writes the file under its release name, in the current
directory, and prints that name for the release workflow to upload.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

#: Bumped when a key changes meaning or disappears; new keys do not.
FACTS_VERSION = 1


def asset_name(version: str) -> str:
    """The release asset's name, the only place it is spelled.

    Args:
        version: The package version, without a leading ``v``.

    Returns:
        ``pain001-mcp-<version>.facts.json``, as core names its own.
    """
    return f"pain001-mcp-{version}.facts.json"


def _floor(spec: Any) -> str:
    """A Poetry dependency's version constraint, table or string."""
    return str(spec["version"] if isinstance(spec, dict) else spec)


def _listed(server: Any) -> dict[str, list[str]]:
    """What an MCP client sees when it lists the server's surfaces."""

    async def gather() -> dict[str, list[str]]:
        tools = await server.list_tools()
        templates = await server.list_resource_templates()
        prompts = await server.list_prompts()
        return {
            "tools": sorted(tool.name for tool in tools),
            "resource_templates": sorted(
                str(getattr(t, "uriTemplate", None) or t.uri_template)
                for t in templates
            ),
            "prompts": sorted(prompt.name for prompt in prompts),
        }

    return asyncio.run(gather())


def collect() -> dict[str, Any]:
    """Gather the facts from this tree and the server it builds.

    Returns:
        The facts, every list sorted, ready for ``json.dumps``.
    """
    from pain001_mcp.server import server

    with (ROOT / "pyproject.toml").open("rb") as handle:
        poetry = tomllib.load(handle)["tool"]["poetry"]
    deps = poetry["dependencies"]
    listed = _listed(server)
    return {
        "facts_version": FACTS_VERSION,
        "package": "pain001-mcp",
        "version": poetry["version"],
        "python": deps["python"],
        "requires": {
            "pain001": _floor(deps["pain001"]),
            "pain001-loader-mt101": _floor(deps["pain001-loader-mt101"]),
        },
        **listed,
        "counts": {key: len(value) for key, value in listed.items()},
    }


def render(facts: dict[str, Any]) -> str:
    """The facts as the file holds them: sorted keys, two-space indent."""
    return json.dumps(facts, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write or check facts.json.

    Args:
        argv: Arguments; ``sys.argv[1:]`` when None.

    Returns:
        0, or 1 when ``--check`` finds a difference.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--asset", action="store_true")
    parser.add_argument("--check", type=Path, default=None)
    args = parser.parse_args(argv)
    facts = collect()
    text = render(facts)
    if args.asset:
        name = asset_name(facts["version"])
        Path(name).write_text(text, encoding="utf-8")
        print(name)
        return 0
    if args.check is not None:
        if args.check.read_text(encoding="utf-8") != text:
            print(f"{args.check} is out of date", file=sys.stderr)
            return 1
        print(f"{args.check} is current")
        return 0
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
