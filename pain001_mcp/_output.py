# SPDX-FileCopyrightText: 2023-2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Where commit_payment_batch may write (GHSA-hqw7-q8v2-pq3m).

Every write is confined to one output directory: ``PAIN001_MCP_OUTPUT_DIR``
when set, else the server's working directory. A path is resolved
(symlinks included) before it is checked, only ``.xml`` files are
written, and an existing file is never replaced.
"""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT_DIR_ENV = "PAIN001_MCP_OUTPUT_DIR"


class OutputPathError(ValueError):
    """A requested output path is refused; the message says why."""


def output_root() -> Path:
    """Return the directory every committed file must stay inside."""
    configured = os.environ.get(OUTPUT_DIR_ENV)
    return Path(configured or Path.cwd()).resolve()


def confined_path(requested: str) -> Path:
    """Resolve ``requested`` against the output root, or refuse it.

    Args:
        requested: The caller's path, relative to the output root or
            absolute inside it.

    Returns:
        The resolved destination.

    Raises:
        OutputPathError: If the path leaves the output root, does not
            end in ``.xml``, or names a file that already exists.
    """
    root = output_root()
    destination = (root / requested).resolve()
    if not destination.is_relative_to(root):
        raise OutputPathError(
            f"{requested!r} is outside the output directory {root} "
            f"(set {OUTPUT_DIR_ENV} to change it)."
        )
    if destination.suffix.lower() != ".xml":
        raise OutputPathError(f"{requested!r} must end in .xml.")
    if destination.exists():
        raise OutputPathError(
            f"{destination} already exists; committed files are never "
            "overwritten."
        )
    return destination


def write_new(destination: Path, content: str) -> None:
    """Create ``destination`` and write ``content``; never replace a file.

    Args:
        destination: A path returned by :func:`confined_path`.
        content: The XML document.

    Raises:
        OutputPathError: If a file appeared at the path since the check.
        OSError: If the directory or file cannot be written.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise OutputPathError(
            f"{destination} already exists; committed files are never "
            "overwritten."
        ) from exc


def save_committed(
    requested: str | None, content: str
) -> tuple[str | None, str | None]:
    """Write a committed batch when a path was asked for.

    Args:
        requested: The caller's ``output_file_path``, or None to skip.
        content: The XML document.

    Returns:
        ``(written path, None)`` on success, ``(None, None)`` when no path
        was asked for, or ``(None, error message)`` when it was refused
        or the write failed.
    """
    if requested is None:
        return None, None
    try:
        destination = confined_path(requested)
        write_new(destination, content)
    except OutputPathError as exc:
        return None, str(exc)
    except OSError as exc:
        return None, f"Failed to write output XML file: {exc}"
    return str(destination), None
