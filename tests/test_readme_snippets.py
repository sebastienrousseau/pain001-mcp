# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Run the README Quick Start commands exactly as a reader would.

The README is the first code a user copies. Each command in its Quick
Start block runs here as a subprocess, with stdin closed so the stdio
server sees end of input and exits, and must succeed. A renamed flag or
a broken entry point then fails CI instead of the reader's terminal.

The Install block is not run: it would replace the checked-out package
with the published release. The Development block is ``make check``,
which CI runs job by job.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

README = Path(__file__).resolve().parents[1] / "README.md"


def section_commands(text: str, heading: str) -> list[str]:
    """Return the shell commands in the first bash block under heading."""
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    block = re.search(r"```bash\n(.*?)```", section, re.DOTALL)
    assert block, f"no bash block under '## {heading}'"
    return [line for line in block[1].splitlines() if line.strip()]


def test_the_quick_start_block_is_found():
    """The parser finds the commands, so an empty run cannot pass."""
    commands = section_commands(README.read_text("utf-8"), "Quick Start")
    assert commands
    assert all(command.startswith("pain001-mcp") for command in commands)


@pytest.mark.parametrize(
    "command",
    section_commands(README.read_text("utf-8"), "Quick Start"),
)
def test_a_quick_start_command_runs(command):
    """Each Quick Start command exits 0 against the installed package."""
    argv = shlex.split(command)
    executable = shutil.which(argv[0])
    assert executable, f"{argv[0]} is not on PATH; install the package"
    result = subprocess.run(  # noqa: S603 - argv comes from the README
        [executable, *argv[1:]],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
