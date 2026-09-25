# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Keep coordinated main builds on the same core source as feature CI."""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "workflow",
    [
        "ci",
        "docker",
        "docs",
        "mcp-inspect",
        "mutation",
        "nightly",
        "pr",
        "security",
    ],
)
@pytest.mark.parametrize(
    ("ref", "matches"),
    [
        ("main", True),
        ("feat/v0.0.71", True),
        ("fix/regression", True),
        ("v0.0.70", False),
        ("maintenance", False),
        ("", False),
    ],
)
def test_core_branch_predicates(
    workflow: str, ref: str, matches: bool
) -> None:
    """Run each actual shell predicate; releases must retain PyPI selection."""
    text = (ROOT / f".github/workflows/{workflow}.yml").read_text()
    predicates = re.findall(r"if (\[\[ .*? \]\]) &&", text)
    assert len(predicates) == (3 if workflow == "ci" else 1)
    for predicate in predicates:
        result = subprocess.run(
            ["bash", "-c", predicate],
            env={**os.environ, "REF": ref},
            capture_output=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == (0 if matches else 1), result.stderr
