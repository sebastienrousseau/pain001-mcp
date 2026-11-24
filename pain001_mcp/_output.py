# SPDX-FileCopyrightText: 2023-2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Where commit_payment_batch may write (GHSA-hqw7-q8v2-pq3m).

Every write is confined to one output directory: ``PAIN001_MCP_OUTPUT_DIR``
when set, else the server's working directory. A path is resolved
(symlinks included) before it is checked, only ``.xml`` files are
written, and an existing file is never replaced.

Hardening reported by Serhii Shunko against 0.0.90: a NUL byte, a trailing separator or
the root itself is refused before anything is created; files are created
owner-only (``0o600`` before the umask) and removed again if the write
fails; refusals name the caller's path, never the host directory.
"""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT_DIR_ENV = "PAIN001_MCP_OUTPUT_DIR"

_CREATE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_BINARY", 0)
)


class OutputPathError(ValueError):
    """A requested output path is refused; the message says why."""


def output_root() -> Path:
    """Return the directory every committed file must stay inside."""
    configured = os.environ.get(OUTPUT_DIR_ENV)
    return Path(configured or Path.cwd()).resolve()


def _refuse_malformed(requested: str) -> None:
    """Refuse a path that cannot name a file, before it is resolved.

    Args:
        requested: The caller's path.

    Raises:
        OutputPathError: If it holds a NUL byte or ends in a separator.
    """
    if "\x00" in requested:
        raise OutputPathError(f"{requested!r} contains a NUL byte.")
    if requested.endswith(("/", "\\")):
        raise OutputPathError(f"{requested!r} names a directory, not a file.")


def confined_path(requested: str) -> Path:
    """Resolve ``requested`` against the output root, or refuse it.

    Args:
        requested: The caller's path, relative to the output root or
            absolute inside it.

    Returns:
        The resolved destination.

    Raises:
        OutputPathError: If the path is malformed, is the output root,
            leaves it, does not end in ``.xml``, or names a file that
            already exists.
    """
    _refuse_malformed(requested)
    root = output_root()
    destination = (root / requested).resolve()
    if destination == root:
        raise OutputPathError(f"{requested!r} is the output directory.")
    if not destination.is_relative_to(root):
        raise OutputPathError(
            f"{requested!r} is outside the output directory "
            f"(set {OUTPUT_DIR_ENV} to change it)."
        )
    if destination.suffix.lower() != ".xml":
        raise OutputPathError(f"{requested!r} must end in .xml.")
    if destination.exists():
        raise OutputPathError(
            f"{requested!r} already exists; committed files are never "
            "overwritten."
        )
    return destination


def write_new(destination: Path, content: str) -> None:
    """Create ``destination`` owner-only and write ``content``.

    The file is created exclusively, so an existing file is never
    replaced, and it is removed again if the write fails part way.

    Args:
        destination: A path returned by :func:`confined_path`.
        content: The XML document.

    Raises:
        OutputPathError: If a file appeared at the path since the check.
        OSError: If the directory or file cannot be written.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(destination, _CREATE_FLAGS, 0o600)
    except FileExistsError as exc:
        raise OutputPathError(
            f"{destination.name!r} already exists; committed files are "
            "never overwritten."
        ) from exc
    try:
        view = memoryview(content.encode("utf-8"))
        while view:
            view = view[os.write(fd, view) :]
    except OSError:
        os.close(fd)
        destination.unlink(missing_ok=True)
        raise
    os.close(fd)


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
        or the write failed. Error messages never name the host
        directory.
    """
    if requested is None:
        return None, None
    try:
        destination = confined_path(requested)
        write_new(destination, content)
    except OutputPathError as exc:
        return None, str(exc)
    except (OSError, ValueError) as exc:
        reason = getattr(exc, "strerror", None) or type(exc).__name__
        return None, f"Failed to write output XML file {requested!r}: {reason}"
    return str(destination), None
