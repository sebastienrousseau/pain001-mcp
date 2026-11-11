# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Render the canonical portfolio README from reviewed repository evidence.

``--check`` fails when the committed README differs from the rendering,
when its section headings leave the portfolio template's order
(``~/Code/README-TEMPLATE.md``, mirrored in ``docs/readme-template.md``),
or when a ``{{...}}`` token is left unresolved.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The portfolio template's headings, in order. "{name}" is the project.
CANONICAL_HEADINGS = (
    "## Contents",
    "## Install",
    "### As a Python library",
    "## Requirements",
    "## Quick Start",
    "## The {name} ecosystem",
    "## Capabilities at a glance",
    "## Ecosystem comparison",
    "## Benchmarks",
    "## Features",
    "## Configuration",
    "## Examples",
    "## When not to use {name}",
    "## Development",
    "## Security",
    "## Documentation",
    "## Stability guarantees",
    "## License",
)


def render() -> str:
    """Substitute evidence without altering the canonical layout."""
    values = json.loads((ROOT / "docs/readme-values.json").read_text())
    template = (ROOT / "docs/readme-template.md").read_text()
    return re.sub(
        r"\{\{([A-Z_]+)\}\}", lambda match: values[match[1]], template
    )


def headings(text: str) -> list[str]:
    """Return the level-2 and level-3 headings outside code fences."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{2,3} ", line):
            found.append(line.rstrip())
    return found


def structure_problems(text: str, name: str) -> list[str]:
    """Return every way text departs from the canonical README shape."""
    expected = [heading.format(name=name) for heading in CANONICAL_HEADINGS]
    problems = []
    actual = headings(text)
    if actual != expected:
        problems.append(
            "headings differ from the portfolio template:\n"
            f"  expected {expected}\n  found    {actual}"
        )
    tokens = sorted(set(re.findall(r"\{\{[^}]*\}\}", text)))
    if tokens:
        problems.append(f"unresolved template tokens: {tokens}")
    return problems


def main() -> None:
    """Regenerate the README, or fail if committed output has drifted."""
    rendered = render()
    target = ROOT / "README.md"
    if "--check" in sys.argv:
        committed = target.read_text()
        if committed != rendered:
            raise SystemExit("README is stale: run scripts/render_readme.py")
        name = json.loads((ROOT / "docs/readme-values.json").read_text())[
            "PROJECT_NAME"
        ]
        problems = structure_problems(committed, name)
        if problems:
            raise SystemExit("README structure:\n" + "\n".join(problems))
    else:
        target.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
