#!/usr/bin/env python3
"""Verify that the pain001-mcp package version is in lockstep everywhere.

Single source of truth: ``pain001_mcp.__version__``. This script reads
that value, then asserts the same string appears in:

* ``pyproject.toml`` (``[tool.poetry] version = "..."``)
* ``CHANGELOG.md`` (an ``[X.Y.Z]`` heading for the current version)
* ``glama.json`` (``version`` and the Docker tag in ``installation.docker``);
  the Glama directory reads this file, and it sat at 0.0.57 for thirteen
  releases before this check existed
* ``server.json`` (``version`` and ``packages[0].version``, the MCP
  registry manifest; the publish workflow re-stamps it from the tag, but
  the committed file should not lie)

Exit status 0 on agreement, 1 otherwise. Wire this into the release
flow so a missed bump can't slip through.

Usage:
    python scripts/verify_versions.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _package_version() -> str:
    sys.path.insert(0, str(ROOT))
    import pain001_mcp  # noqa: E402  (path-dependent import)

    return pain001_mcp.__version__


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("pyproject.toml has no version field")
    return match.group(1)


def _changelog_versions() -> set[str]:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return set(re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE))


def _glama_versions() -> tuple[str, str]:
    import json

    data = json.loads((ROOT / "glama.json").read_text(encoding="utf-8"))
    docker = str(data.get("installation", {}).get("docker", ""))
    tag = docker.rsplit(":", 1)[-1] if ":" in docker else ""
    return str(data.get("version", "")), tag


def _server_json_versions() -> tuple[str, str]:
    import json

    data = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    pkgs = data.get("packages") or [{}]
    return str(data.get("version", "")), str(pkgs[0].get("version", ""))


def main() -> int:
    """Compare versions across the package metadata and changelog."""
    pkg = _package_version()
    pp = _pyproject_version()
    changelog = _changelog_versions()
    print(f"  pain001_mcp.__version__   = {pkg}")
    print(f"  pyproject.toml version    = {pp}")
    print(f"  CHANGELOG.md headings     = {sorted(changelog) or '(none)'}")
    if pkg != pp:
        print("ERROR: __version__ does not match pyproject.toml")
        return 1
    if pkg not in changelog:
        print(f"ERROR: CHANGELOG.md has no [{pkg}] heading")
        return 1
    glama_version, glama_docker = _glama_versions()
    server_version, server_pkg = _server_json_versions()
    print(
        f"  glama.json version        = {glama_version} (docker tag {glama_docker})"
    )
    print(
        f"  server.json version       = {server_version} (package {server_pkg})"
    )
    if glama_version != pkg or glama_docker != pkg:
        print("ERROR: glama.json version or Docker tag does not match")
        return 1
    if server_version != pkg or server_pkg != pkg:
        print("ERROR: server.json version does not match")
        return 1
    print("OK: every source agrees on", pkg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
