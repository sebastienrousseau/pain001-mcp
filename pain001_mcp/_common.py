# Copyright (C) 2023-2026 Sebastien Rousseau.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Parameter types, annotations and helpers every tool family shares.

The message-type vocabulary, the scheme-profile vocabulary and the
records field guide are derived from the pain001 library here, once, so
no tool module restates them and none can drift from the core.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pain001.constants import SCHEMAS_DIR, TEMPLATES_DIR, valid_xml_types

# The checks the core's loaders run on every load (pain001 >= 0.0.81).
# The core keeps them in private modules and has no public name for
# either; they are imported here only, so a public export replaces two
# lines.
from pain001.validation._identifiers import (
    check_identifiers as _check_identifiers,
)
from pain001.validation._identifiers import (
    identifier_errors as _identifier_errors,
)
from pain001.validation._one_batch import require_one_batch as _one_batch
from pain001.validation.schemes import PROFILES
from pydantic import Field

# Bare family names accepted as ergonomic aliases for a concrete version:
# agents routinely say "pain.001" (the catalogue name) rather than a full
# versioned message type, and previously received an unhelpful
# "Invalid XML message type" error.
_MESSAGE_TYPE_ALIASES: dict[str, str] = {
    "pain.001": "pain.001.001.09",
    "pain.008": "pain.008.001.02",
}

# Enumerated value list for the ``message_type`` MCP parameter. Surfacing the
# concrete allowed values as a JSON Schema ``enum`` (and in the description)
# lets clients — and the Glama TDQS grader — see the valid inputs without a
# tool call. Derived from the pain001 library so it never drifts. The enum is
# schema metadata only; ``_check_message_type`` remains the runtime guard.
_PAIN_MESSAGE_TYPES: list[str] = sorted(valid_xml_types) + sorted(
    _MESSAGE_TYPE_ALIASES
)
_MSG_TYPE_LIST = ", ".join(f"'{t}'" for t in _PAIN_MESSAGE_TYPES)

_MessageType = Annotated[
    str,
    Field(
        description=(
            "A supported ISO 20022 pain message type. Must be exactly one of: "
            f"{_MSG_TYPE_LIST} (see list_message_types). The bare family "
            "names 'pain.001' and 'pain.008' are accepted as aliases for "
            "'pain.001.001.09' and 'pain.008.001.02'."
        ),
        json_schema_extra={"enum": _PAIN_MESSAGE_TYPES},
    ),
]

# Every scheme profile pain001 ships, so no description names a fake one.
_SCHEME_PROFILES: list[str] = sorted(PROFILES)
_SCHEME_PROFILE_LIST = ", ".join(f"'{name}'" for name in _SCHEME_PROFILES)

# A comma-separated list of profile names, as pain001.validate_scheme
# parses it: items are stripped, empty items are ignored, and at least
# one name must remain. Profile names are lower-case words joined by
# hyphens, so they need no escaping in an ECMA-262 pattern.
_ONE_PROFILE = "(?:" + "|".join(_SCHEME_PROFILES) + ")"
_PROFILE_SPEC_PATTERN = (
    rf"^(?:\s*,)*\s*{_ONE_PROFILE}\s*(?:,\s*(?:{_ONE_PROFILE}\s*)?)*$"
)


def _profile_schema(schema: dict[str, Any]) -> None:
    """Offer the core's profiles as an enum, and a comma list of them.

    Applied by pydantic to a profile parameter's JSON Schema. The string
    branch becomes two: one profile name from ``PROFILES`` (an ``enum``
    a client can show), or a comma-separated list of names (a
    ``pattern``). A ``null`` branch, on an optional parameter, stays.
    The core still validates the value; this is schema metadata.
    """
    schema.pop("type", None)
    keep = [b for b in schema.pop("anyOf", []) if b.get("type") == "null"]
    schema["anyOf"] = [
        {"type": "string", "enum": _SCHEME_PROFILES},
        {"type": "string", "pattern": _PROFILE_SPEC_PATTERN},
        *keep,
    ]


_OptionalSchemeProfile = Annotated[
    str | None,
    Field(
        description=(
            "Optional payment-scheme rulebook profile to enforce, or several "
            f"joined by commas. One of {_SCHEME_PROFILE_LIST}. Omit to skip "
            "scheme-specific rulebook validation."
        ),
        json_schema_extra=_profile_schema,
    ),
]
_SchemeProfile = Annotated[
    str,
    Field(
        description=(
            "The payment-scheme rulebook profile to enforce, or several "
            "joined by commas (e.g. 'sepa-sct,anti-duplicate'). One of "
            f"{_SCHEME_PROFILE_LIST}. Defaults to 'sepa-sct'."
        ),
        json_schema_extra=_profile_schema,
    ),
]

_IdentifierChecks = Annotated[
    bool,
    Field(
        description=(
            "Check every IBAN (mod-97) and BIC (ISO 9362) column, as the "
            "pain001 CLI and file loaders do (default true). Set false only "
            "for identifiers you have verified another way, the CLI's "
            "--no-identifier-checks."
        )
    ),
]


def _identifier_findings(records: list[dict]) -> list[tuple[int, str, str]]:
    """Return ``(row, column, reason)`` per invalid IBAN or BIC.

    The core's own check (what its loaders run): the reason never repeats
    the identifier, which is personal data.
    """
    findings: list[tuple[int, str, str]] = _identifier_errors(records)
    return findings


def _refuse_bad_identifiers(records: list[dict]) -> None:
    """Raise the core's ``PaymentValidationError`` for a bad IBAN or BIC."""
    _check_identifiers(records)


def _refuse_mixed_batch(records: list[dict], message_type: str) -> None:
    """Raise the core's ``PaymentValidationError`` for a mixed batch.

    Rows that would not share one PmtInf are refused as the CLI and the
    generator refuse them. An empty batch is left to the other checks.
    """
    if records:
        _one_batch(records, message_type)


# What generate_message accepts per record, surfaced in the tool schema so an
# agent can build a correct call without a discovery round-trip.
_RECORDS_FIELD_GUIDE = (
    "One or more flat payment records (dicts of field name → value). "
    "Key fields (see get_input_schema for the full contract): id, date "
    "(payment-initiation timestamp; 'YYYY-MM-DD' is accepted and rendered "
    "as midnight), initiator_name, payment_id, requested_execution_date "
    "('YYYY-MM-DD'), debtor_name, debtor_account_IBAN, debtor_agent_BIC, "
    "creditor_name, creditor_account_IBAN, creditor_agent_BIC, "
    "payment_amount (alias: 'amount'; max two decimals), currency (alias: "
    "'payment_currency'; ISO 4217, e.g. 'EUR'), remittance_information. "
    "batch_booking accepts JSON true/false. nb_of_txs and ctrl_sum are "
    "computed automatically from the records and may be omitted. "
    "payment_method defaults to 'TRF' and charge_bearer to 'SLEV'. "
    "IBAN and BIC values are strictly validated and never coerced."
)

# Shared MCP tool annotations. Every tool in this server is a pure,
# side-effect-free reader over the pain001 API, so all are marked
# ``readOnlyHint`` + ``idempotentHint`` and never ``destructiveHint``.
# The only axis that varies is whether a tool reads a caller-supplied
# path from the local filesystem (``openWorldHint``): compute-only tools
# that operate solely on their arguments or on data bundled with the
# server are closed-world; tools that open an arbitrary path are not.
#
# These hints let MCP clients (and the Glama quality grader) reason about
# safety, caching, and auto-approval without executing the tool.
# camelCase is deliberate: mcp 1.x names these fields
# `readOnlyHint` etc.; 2.x renamed them to snake_case and kept
# camelCase as aliases. camelCase is the only spelling correct on
# both majors -- snake_case on 1.x lands in an extra attribute and
# silently leaves the real field None. mypy resolves against 2.x.
_PURE_READ = ToolAnnotations(  # type: ignore[call-arg]
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
# camelCase is deliberate: mcp 1.x names these fields
# `readOnlyHint` etc.; 2.x renamed them to snake_case and kept
# camelCase as aliases. camelCase is the only spelling correct on
# both majors -- snake_case on 1.x lands in an extra attribute and
# silently leaves the real field None. mypy resolves against 2.x.
_FS_READ = ToolAnnotations(  # type: ignore[call-arg]
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
_MUTATING_SAFE = ToolAnnotations(  # type: ignore[call-arg]
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_COMMIT_TOOL = ToolAnnotations(  # type: ignore[call-arg]
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)


def _check_message_type(message_type: str) -> str:
    """Resolve aliases and validate a message type against the bundle.

    Args:
        message_type: A full message type (``pain.001.001.09``) or a bare
            family alias (``pain.001``).

    Returns:
        The canonical, fully-versioned message type.

    Raises:
        ValueError: If the resolved type is not bundled with pain001.
    """
    resolved = _MESSAGE_TYPE_ALIASES.get(
        message_type.strip().lower(), message_type.strip()
    )
    if resolved not in valid_xml_types:
        raise ValueError(
            f"Invalid XML message type: {message_type}. Expected one of: "
            f"{_MSG_TYPE_LIST}."
        )
    return resolved


def _template_dir(message_type: str) -> Path:
    """Return the bundled template directory of a resolved message type.

    Reads :data:`TEMPLATES_DIR` from this module at call time, so a test
    can point it at an empty directory to reach the missing-file paths.
    """
    return Path(TEMPLATES_DIR) / message_type


def _template_bundle(message_type: str) -> tuple[str, str]:
    """Return the template and XSD paths generation needs for a type.

    Args:
        message_type: A message type already resolved by
            :func:`_check_message_type`.

    Returns:
        ``(template.xml path, XSD path)`` as strings.

    Raises:
        ValueError: If either file is missing.
    """
    template_dir = _template_dir(message_type)
    template_xml = template_dir / "template.xml"
    xsd_schema = template_dir / f"{message_type}.xsd"
    if not template_xml.is_file() or not xsd_schema.is_file():
        raise ValueError(f"No template bundled for {message_type}")
    return str(template_xml), str(xsd_schema)


def _schema_path(message_type: str) -> Path:
    """Return the on-disk path of the bundled JSON Schema for ``message_type``."""
    return Path(SCHEMAS_DIR) / f"{message_type}.schema.json"


@lru_cache(maxsize=16)
def _load_schema(message_type: str) -> dict:
    """Load the bundled JSON Schema for ``message_type`` (raises on miss).

    Cached. The schemas ship inside the installed package and are
    read-only, so re-reading them cannot pick up a change.

    This was previously left uncached on the grounds that the load costs
    0.18ms against ~92ms for a 200-record ``generate_message`` — 0.2% of
    the work. That compared it against the wrong tool. The read-only
    tools do essentially nothing else, and a model exploring the server
    calls them repeatedly:

        get_required_fields   0.0788ms -> 0.0002ms  (475x)
        get_input_schema      0.0736ms -> 0.0001ms  (888x)

    ``validate_identifier`` and ``list_message_types`` do not touch the
    schema and are unchanged, which is the control for those numbers.
    """
    message_type = _check_message_type(message_type)
    path = _schema_path(message_type)
    if not path.is_file():  # pragma: no cover - all valid types ship a schema
        raise ValueError(f"No JSON Schema bundled for {message_type}")
    with path.open("r", encoding="utf-8") as fh:
        loaded: dict = json.load(fh)
        return loaded
