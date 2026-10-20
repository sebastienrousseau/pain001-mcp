# SPDX-License-Identifier: Apache-2.0 OR MIT
"""The suite-consistency check compares this tree with its own release."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_suite_consistency.py"
)


@pytest.fixture
def checker() -> types.ModuleType:
    """The script, loaded as a module."""
    spec = importlib.util.spec_from_file_location("consistency", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(
    checker: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tree: str,
    published: dict[str, str],
) -> list[str]:
    monkeypatch.setattr(checker, "tree_version", lambda: tree)
    monkeypatch.setattr(checker, "published_version", published.get)
    problems, _ = checker.check()
    return problems


def _suite(core: str, mcp: str) -> dict[str, str]:
    versions = dict.fromkeys(
        ("pain001", "pain001-lsp", "pain001-loader-mt101"), core
    )
    versions["pain001-loader-xlsx"] = core
    versions["pain001-mcp"] = mcp
    return versions


def test_this_package_is_named_from_pyproject(
    checker: types.ModuleType,
) -> None:
    assert checker.tree_name() == "pain001-mcp"


def test_a_released_tree_is_not_reported_as_unreleased(
    checker: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tree is pain001-mcp's, so it is compared with pain001-mcp."""
    problems = _run(checker, monkeypatch, "0.0.73", _suite("0.0.72", "0.0.73"))
    assert not [p for p in problems if "tree is" in p]
    assert problems == [
        "pain001-mcp: published 0.0.73, but the suite is at 0.0.72"
    ]


def test_a_bump_that_was_never_released_is_reported(
    checker: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = _run(checker, monkeypatch, "0.0.74", _suite("0.0.73", "0.0.73"))
    assert problems == [
        "pain001-mcp: tree is 0.0.74 but PyPI has 0.0.73. Either the "
        "release was never tagged, or the tree is behind."
    ]


def test_an_agreeing_suite_has_no_problems(
    checker: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not _run(checker, monkeypatch, "0.0.74", _suite("0.0.74", "0.0.74"))
