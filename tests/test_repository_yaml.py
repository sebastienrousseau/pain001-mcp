# Copyright (C) 2023-2026 Pain001. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Every YAML file the repository ships must parse.

GitHub silently drops an issue form, and refuses a workflow, whose YAML
does not load. Nothing else in the suite reads these files, so a stray
unquoted ``{`` in a description went unnoticed until a pre-commit run.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

YAML_FILES = sorted(
    [
        *ROOT.glob(".github/**/*.yml"),
        *ROOT.glob(".github/**/*.yaml"),
        *ROOT.glob("*.yml"),
        *ROOT.glob(".*.yml"),
        *ROOT.glob(".*.yaml"),
        ROOT / "CITATION.cff",
    ]
)


def test_the_yaml_inventory_is_not_empty() -> None:
    """Guard against a glob that silently matches nothing."""
    names = {p.relative_to(ROOT).as_posix() for p in YAML_FILES}
    assert ".github/ISSUE_TEMPLATE/bug_report.yml" in names
    assert ".github/workflows/ci.yml" in names


@pytest.mark.parametrize(
    "path", YAML_FILES, ids=lambda p: p.relative_to(ROOT).as_posix()
)
def test_yaml_file_parses(path: Path) -> None:
    """Each file loads as YAML without error."""
    yaml.safe_load(path.read_text(encoding="utf-8"))
