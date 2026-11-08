# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""``_common.__all__`` lists exactly what the tool modules import from it.

The shared names keep their leading underscore, so ``__all__`` is what
says they cross module boundaries. Kept equal to the imports, it cannot
name something nothing uses nor miss something a module needs.
"""

from __future__ import annotations

import ast
from pathlib import Path

from pain001_mcp import _common

PACKAGE = Path(_common.__file__).parent


def _imported_from_common() -> set[str]:
    names: set[str] = set()
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "pain001_mcp._common"
            ):
                names.update(alias.name for alias in node.names)
    return names


def test_all_matches_what_the_tool_modules_import() -> None:
    assert set(_common.__all__) == _imported_from_common()


def test_every_name_in_all_exists() -> None:
    missing = [name for name in _common.__all__ if not hasattr(_common, name)]
    assert not missing
