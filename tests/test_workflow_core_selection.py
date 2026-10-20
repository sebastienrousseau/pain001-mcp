# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Keep CI installs pinned and on the same core source as feature CI."""

import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
INSTALLER = "scripts/ci-install.sh"

#: Workflows that install the package and so select a core source.
INSTALLING = ["ci", "docs", "mcp-inspect", "mutation", "nightly", "pr"]


def _predicates(path: Path) -> list[str]:
    """The core-branch shell predicates in ``path``."""
    return re.findall(r"if (\[\[ .*? \]\]) &&", path.read_text())


@pytest.mark.parametrize(
    ("source", "count"),
    [(INSTALLER, 1), (".github/workflows/docker.yml", 1)],
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
    source: str, count: int, ref: str, matches: bool
) -> None:
    """Run each actual shell predicate; releases must retain PyPI selection."""
    predicates = _predicates(ROOT / source)
    assert len(predicates) == count
    for predicate in predicates:
        result = subprocess.run(
            ["bash", "-c", predicate],
            env={**os.environ, "REF": ref, "ref": ref},
            capture_output=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == (0 if matches else 1), result.stderr


@pytest.mark.parametrize("workflow", [*INSTALLING, "security"])
def test_installing_workflows_use_the_pinned_installer(workflow: str) -> None:
    """Every install goes through the one hash-pinned installer."""
    text = (WORKFLOWS / f"{workflow}.yml").read_text()
    assert f"run: {INSTALLER} requirements/" in text
    assert "REF: ${{ github.head_ref || github.ref_name }}" in text


def _pip_installs(text: str) -> list[list[str]]:
    """Every ``pip install`` command in ``text``, split into words."""
    joined = text.replace("\\\n", " ")
    commands = []
    for line in joined.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for part in re.split(r"&&|\|\||;", line.replace("run:", " ")):
            words = shlex.split(part) if "install" in part else []
            if "install" in words and any(
                w == "pip" or w.endswith("/pip") for w in words
            ):
                commands.append(words[words.index("install") + 1 :])
    return commands


def _is_pinned(args: list[str]) -> bool:
    """Scorecard's rule: hashes required, or --no-deps local/wheel only."""
    if "--require-hashes" in args:
        return True
    targets = [a for a in args if not a.startswith("-")]
    local = all(
        a.endswith(".whl") or not re.match(r"(git|svn|hg|bzr)", a)
        for a in targets
    )
    editable = "-e" in args or "--editable" in args
    wheels = bool(targets) and all(a.endswith(".whl") for a in targets)
    return "--no-deps" in args and ((editable and local) or wheels)


@pytest.mark.parametrize(
    "path",
    [
        *sorted(WORKFLOWS.glob("*.yml")),
        ROOT / "Dockerfile",
        ROOT / INSTALLER,
    ],
    ids=lambda p: p.name,
)
def test_every_pip_install_is_pinned(path: Path) -> None:
    """OpenSSF Scorecard Pinned-Dependencies: no unpinned pip install."""
    unpinned = [
        " ".join(args)
        for args in _pip_installs(path.read_text())
        if not _is_pinned(args)
    ]
    assert not unpinned, f"unpinned pip install in {path.name}: {unpinned}"


def test_container_base_images_are_pinned_by_digest() -> None:
    """OpenSSF Scorecard Pinned-Dependencies: FROM lines carry a digest."""
    froms = re.findall(
        r"^FROM\s+(\S+)", (ROOT / "Dockerfile").read_text(), re.M
    )
    assert froms
    assert all(re.search(r"@sha256:[0-9a-f]{64}$", f) for f in froms), froms
