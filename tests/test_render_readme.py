# SPDX-License-Identifier: Apache-2.0 OR MIT
"""The README keeps the portfolio template's shape (render_readme.py)."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "render_readme", ROOT / "scripts" / "render_readme.py"
)
assert _SPEC and _SPEC.loader
render_readme = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(render_readme)

NAME = "pain001-mcp"


def test_the_committed_readme_has_the_canonical_shape():
    """The README on disk is current and has no structure problems."""
    text = (ROOT / "README.md").read_text()
    assert text == render_readme.render()
    assert render_readme.structure_problems(text, NAME) == []


def test_every_readme_image_is_an_absolute_url():
    """PyPI does not resolve relative paths, so every image is absolute."""
    text = (ROOT / "README.md").read_text()
    sources = re.findall(r'(?:src|srcset)="([^"]+)"', text)
    assert sources
    assert all(source.startswith("https://") for source in sources), sources
    prefix = (
        f"https://raw.githubusercontent.com/sebastienrousseau/{NAME}/main/"
    )
    tree = [s.removeprefix(prefix) for s in sources if s.startswith(prefix)]
    assert ".github/demo.gif" in tree
    assert all((ROOT / path).is_file() for path in tree), tree


def test_the_registry_marker_is_kept():
    """The MCP Registry reads its ownership marker from the README."""
    text = (ROOT / "README.md").read_text()
    assert "<!-- mcp-name: io.github.sebastienrousseau/pain001-mcp -->" in (
        text
    )


def test_an_extra_section_is_reported():
    """A section the template does not have fails the check."""
    text = (ROOT / "README.md").read_text()
    extra = text.replace("## License", "## Extra\n\ntext\n\n## License")
    (problem,) = render_readme.structure_problems(extra, NAME)
    assert "## Extra" in problem


def test_reordered_sections_are_reported():
    """Two sections swapped fail the check."""
    text = (ROOT / "README.md").read_text()
    swapped = (
        text.replace("## Security", "## @@")
        .replace("## Development", "## Security")
        .replace("## @@", "## Development")
    )
    assert render_readme.structure_problems(swapped, NAME)


def test_a_heading_inside_a_code_fence_is_not_a_section():
    """Comments in a shell block are not mistaken for headings."""
    fenced = "## Contents\n```bash\n## not a heading\n```\n"
    assert render_readme.headings(fenced) == ["## Contents"]


def test_an_unresolved_token_is_reported():
    """A placeholder left in the output fails the check."""
    text = (ROOT / "README.md").read_text() + "\n{{PROJECT_NAME}}\n"
    (problem,) = render_readme.structure_problems(text, NAME)
    assert "{{PROJECT_NAME}}" in problem


def test_check_mode_fails_on_a_stale_readme(tmp_path, monkeypatch):
    """--check exits non-zero when README.md differs from the rendering."""
    for relative in ("docs/readme-values.json", "docs/readme-template.md"):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text((ROOT / relative).read_text())
    (tmp_path / "README.md").write_text("stale\n")
    monkeypatch.setattr(render_readme, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["render_readme.py", "--check"])
    with pytest.raises(SystemExit, match="stale"):
        render_readme.main()


def test_check_mode_fails_on_a_broken_structure(tmp_path, monkeypatch):
    """--check exits non-zero when the template itself loses a section."""
    for relative in ("docs/readme-values.json", "docs/readme-template.md"):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text((ROOT / relative).read_text())
    template = tmp_path / "docs/readme-template.md"
    template.write_text(template.read_text().replace("## Benchmarks", "##x"))
    monkeypatch.setattr(render_readme, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["render_readme.py"])
    render_readme.main()
    monkeypatch.setattr(sys, "argv", ["render_readme.py", "--check"])
    with pytest.raises(SystemExit, match="README structure"):
        render_readme.main()
