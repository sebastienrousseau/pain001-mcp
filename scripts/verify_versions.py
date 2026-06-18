#!/usr/bin/env python3
"""Verify that the pain001-mcp package version is in lockstep everywhere.

Single source of truth: ``pain001_mcp.__version__``. This script reads
that value, then asserts the same string appears in:

* ``pyproject.toml`` (``[tool.poetry] version = "..."``)
* ``CHANGELOG.md`` (an ``[X.Y.Z]`` heading for the current version)

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
    print("OK: every source agrees on", pkg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
