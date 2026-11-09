# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Check an existing payment file (pain001 >= 0.0.82).

``check_payment_file`` runs :func:`pain001.check.check_document`, the
engine behind ``pain001 check`` and ``POST /api/v1/check`` (ADR-0010 in
the core repository): the XSD of the message type the document's
namespace names, the message definition's cross-element rules, and the
scheme profiles and Schematron preset asked for. The document arrives as
XML text, never a server path, and a Schematron rulebook is named by
preset only, so a call cannot make the server read a file.
"""

from __future__ import annotations

import importlib
from typing import Annotated, Any

from pydantic import Field
from typing_extensions import TypedDict

from pain001_mcp._common import _OptionalSchemeProfile

CHECK_MISSING = (
    "checking needs pain001 >= 0.0.82; the installed pain001 has no "
    "pain001.check.check_document"
)


def _check_api() -> Any | None:
    """Return :mod:`pain001.check`, or ``None`` when the library predates it."""
    try:
        return importlib.import_module("pain001.check")
    except ImportError:
        return None


def _presets() -> list[str]:
    """The Schematron presets the installed pain001 packages."""
    try:
        schematron = importlib.import_module("pain001.schematron")
    except ImportError:  # pragma: no cover - every supported core has it
        return []
    return sorted(schematron.PRESET_RULEBOOKS)


_PRESETS = _presets()

_XmlContent = Annotated[
    str,
    Field(
        description=(
            "The full pain.001 or pain.008 document as XML text (not a file "
            "path), at most 10 MiB."
        )
    ),
]
_Schematron = Annotated[
    str | None,
    Field(
        description=(
            "Optional Schematron rulebook preset: one of "
            f"{', '.join(_PRESETS)}. A path is not accepted."
        ),
        json_schema_extra={"enum": _PRESETS} if _PRESETS else None,
    ),
]


class CheckFindingResult(TypedDict):
    """One problem one rung found."""

    rung: str
    rule: str
    severity: str
    message: str
    location: str | None


class CheckResult(TypedDict, total=False):
    """The verdict, the rungs that ran and every finding, or a refusal."""

    error: str
    message_type: str
    passed: bool
    errors: int
    warnings: int
    rungs: list[str]
    findings: list[CheckFindingResult]


def check_payment_file(
    xml_content: _XmlContent,
    scheme: _OptionalSchemeProfile = None,
    schematron: _Schematron = None,
) -> CheckResult:
    """Check an existing pain.001 or pain.008 file, as ``pain001 check`` does.

    Use this on a payment file that already exists (one a bank returned,
    another system wrote, or an earlier run produced) to learn whether it
    is valid and why not. ``validate_records`` checks rows before
    generation; this checks the XML itself: its message type's XSD, the
    cross-element rules of the message definition, and the scheme
    profiles and Schematron preset asked for. Every rung runs, so all
    problems come back at once.

    Delegates to :func:`pain001.check.check_document`.

    Args:
        xml_content: The document as XML text.
        scheme: Scheme profiles, comma-separated, or ``None``.
        schematron: A Schematron preset, or ``None``.

    Returns:
        ``{"message_type", "passed", "errors", "warnings", "rungs",
        "findings": [{"rung", "rule", "severity", "message",
        "location"}, ...]}``, or ``{"error": ...}`` when the document
        cannot be checked (not a bundled pain.001 or pain.008, a DTD,
        too large, an unknown scheme or preset) or the installed
        pain001 has no checker.
    """
    check = _check_api()
    if check is None:
        return {"error": CHECK_MISSING}
    if schematron is not None and schematron.lower() not in _PRESETS:
        return {"error": f"schematron must be a preset: {', '.join(_PRESETS)}"}
    try:
        report = check.check_document(
            xml_content, scheme=scheme, schematron=schematron
        )
    except ValueError as exc:
        return {"error": str(exc)}
    result: CheckResult = report.as_dict()
    return result
