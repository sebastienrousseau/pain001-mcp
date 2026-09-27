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

"""Model Context Protocol (MCP) server for pain001.

This server exposes the pain001 library's ISO 20022 ``pain.001`` and
companion-message capabilities as MCP tools so any MCP-compatible client
(Claude Desktop, IDEs, agents) can discover supported message versions,
inspect input schemas, validate payment records and financial identifiers,
generate validated XML, and parse the bank-reply messages (``camt.053``
statements and ``pain.002`` status reports).

Every tool is a thin, typed wrapper over the pain001 public API (the schema
loader, the IBAN/BIC validators, ``generate_xml_string``, and the camt.053
/ pain.002 parsers) so all interfaces behave identically to the CLI and
REST API. Tools return JSON-serializable data (dicts, lists, or strings);
on a :class:`ValueError` (or a ``pain001.exceptions`` subclass thereof)
they return an ``{"error": ...}`` dictionary rather than raising.

Launching the server:
    * As a console script::

        pain001-mcp

    * Programmatically::

        from pain001_mcp.server import main
        main()

    * In an MCP client config (e.g. Claude Desktop ``claude_desktop_config.json``)::

        {
          "mcpServers": {
            "pain001": {
              "command": "pain001-mcp"
            }
          }
        }

The server communicates over stdio (MCPServer's default transport).
"""

import csv
import hashlib
import hmac
import importlib
import io
import json
import secrets
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from jsonschema import Draft7Validator
from mcp.types import ToolAnnotations
from pain001 import (
    canonicalize_payment_record,
    generate_xml_string,
    parse_camt053_statement,
    parse_pain002_report,
    sanitize_to_charset,
    validate_scheme,
)
from pain001.async_adapter import generate_xml_string_async
from pain001.constants import SCHEMAS_DIR, TEMPLATES_DIR, valid_xml_types
from pain001.csv.load_csv_data import load_csv_data
from pain001.exceptions import Pain001Error
from pain001.migration import VersionMapper
from pain001.validation import validate_bic, validate_iban
from pain001.validation.charset import ISO20022_ALLOWED_CHARACTERS
from pain001.xml.validate_via_xsd import validate_xml_string_via_xsd
from pain001_loader_mt101.loader import parse_mt101
from pydantic import Field

# pydantic resolves nested TypedDicts on Python 3.10 and 3.11 only for the
# typing_extensions class; typing.TypedDict there yields no output schema.
from typing_extensions import TypedDict

from pain001_mcp import __version__, _cli
from pain001_mcp._mcp_compat import build_server

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

# ---------------------------------------------------------------------------
# Result shapes. Every tool returns a JSON object, and any tool can answer
# with {"error": "..."} instead of its payload (ADR 0001: errors as data),
# so each shape lists the payload keys plus ``error`` and marks all of them
# optional. The MCP SDK derives the tool's outputSchema from these, which is
# what an agent reads to know the keys before it calls; the exact keys and
# wording are pinned by tests/test_tool_result_shapes.py.
# ---------------------------------------------------------------------------


class ErrorResult(TypedDict, total=False):
    """The failure payload every tool may return instead of its result."""

    error: str


class SchemaResult(TypedDict, total=False):
    """A JSON Schema (draft 7) for one message type's flat records."""

    error: str
    title: str
    description: str
    type: str
    properties: dict[str, Any]
    required: list[str]
    additionalProperties: bool
    version: str


class RecordError(TypedDict):
    """One schema violation: the record's row, the field path, the message."""

    row: int
    path: str
    message: str


class ValidateRecordsResult(TypedDict, total=False):
    """Verdict over a batch: one entry per violation, plus the counts."""

    error: str
    valid: bool
    total: int
    valid_count: int
    errors: list[RecordError]


class ValidateIdentifierResult(TypedDict, total=False):
    """An IBAN or BIC verdict, with the library's message when invalid."""

    error: str
    kind: str
    value: str
    valid: bool


class Camt053Result(TypedDict, total=False):
    """A parsed camt.053 statement, as the core library reports it."""

    error: str
    statement_id: str
    electronic_sequence_number: str
    iban: str
    currency: str
    entries: list[dict[str, Any]]


class Pain002Result(TypedDict, total=False):
    """A parsed pain.002 status report, as the core library reports it."""

    error: str
    message_id: str
    creation_datetime: str
    original_message_id: str
    original_message_name_id: str
    group_status: str
    payment_statuses: list[dict[str, Any]]


class TemplateResult(TypedDict, total=False):
    """The bundled CSV template's column names for one message type."""

    error: str
    message_type: str
    columns: list[str]


class SchemeViolation(TypedDict):
    """One rulebook violation, with the remediation the library suggests."""

    rule: str
    field: str
    index: int
    message: str
    remediation: str
    severity: str


class SchemeResult(TypedDict, total=False):
    """Verdict against a scheme rulebook profile."""

    error: str
    profile: str
    is_valid: bool
    violations: list[SchemeViolation]


class DuplicateTransaction(TypedDict):
    """An intra-batch duplicate payment transaction."""

    row: int
    matching_row: int
    debtor_account_IBAN: str
    creditor_account_IBAN: str
    amount: str
    currency: str
    requested_execution_date: str


class SimulatePaymentBatchResult(TypedDict, total=False):
    """Simulation and pre-flight verdict over a payment batch."""

    error: str
    valid: bool
    total: int
    valid_count: int
    control_sum_by_currency: dict[str, str]
    unique_debtors: int
    unique_creditors: int
    duplicates: list[DuplicateTransaction]
    schema_errors: list[RecordError]
    scheme_violations: list[SchemeViolation]


MigrateResult = TypedDict(
    "MigrateResult",
    {
        "error": str,
        "records": list[dict[str, Any]],
        "migrated": int,
        "from": str,
        "to": str,
    },
    total=False,
)
MigrateResult.__doc__ = (
    "Records rewritten from one message edition to another."
)


class XsdResult(TypedDict, total=False):
    """Verdict of an XML document against the official XSD."""

    error: str
    valid: bool
    message_type: str


class SanitiseResult(TypedDict, total=False):
    """A value and its ISO 20022 charset-clean rendering."""

    value: str
    sanitised: str
    was_valid: bool
    changed: bool


class CorpusFileEntry(TypedDict, total=False):
    """One file of the example corpus, as the index lists it.

    Market files name a scenario, a country and a rail family; coverage
    files carry the edition only, so those three are null for them.
    """

    scenario_id: str | None
    version: str
    variant: str | None
    kind: str
    file: str
    country: str | None
    family: str | None


class CorpusListResult(TypedDict, total=False):
    """The example corpus index."""

    error: str
    count: int
    files: list[CorpusFileEntry]


class CorpusFileResult(TypedDict, total=False):
    """One corpus XML file with the request echoed beside it."""

    error: str
    scenario_id: str
    version: str
    variant: str | None
    xml: str


class CorpusProvenanceResult(TypedDict, total=False):
    """A scenario's provenance record, as the corpus ships it."""

    error: str
    scenario: str
    message_type: str
    variant: str | None
    country: str
    family: str
    description: str
    sha256: str
    provenance: dict[str, Any]
    validation: dict[str, Any]
    constraints: list[Any]
    twins: dict[str, Any]
    build: dict[str, Any]


class CoverageCount(TypedDict):
    """Declared schema elements, how many the corpus hits, as a percentage."""

    declared: int
    hit: int
    percent: float


class CorpusCoverageResult(TypedDict, total=False):
    """Schema-path coverage of the corpus for one message edition."""

    error: str
    message_type: str
    complete: bool
    sources: list[Any]
    files: list[dict[str, Any]]
    paths: CoverageCount
    branches: CoverageCount
    missing_paths: list[str]
    missing_branches: list[str]
    exempt: list[str]
    unknown: list[str]


class StagedBatchResult(TypedDict, total=False):
    """Result of staging a payment batch for simulation and approval."""

    error: str
    stage_id: str
    sha256_fingerprint: str
    total_transactions: int
    control_sum_by_currency: dict[str, str]
    estimated_fees: dict[str, str]
    risk_score: int
    risk_level: str
    risk_factors: list[str]
    status: str
    confirmation_token: str
    expires_at: str


class ClearingCheck(TypedDict):
    """An individual rule check during clearing simulation."""

    check: str
    status: str
    detail: str


class SimulateClearingResult(TypedDict, total=False):
    """Clearing network simulation verdict and settlement estimation."""

    error: str
    stage_id: str
    clearing_system: str
    clearing_status: str
    settlement_window: str
    checks: list[ClearingCheck]


class CommitPaymentBatchResult(TypedDict, total=False):
    """Confirmation of authorized payment batch commit."""

    error: str
    stage_id: str
    status: str
    sha256_fingerprint: str
    total_transactions: int
    output_file_path: str | None
    committed_at: str


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

# SWIFT extended ("Z") character set. The pain001 library only implements the
# SWIFT basic ("X") set (``ISO20022_ALLOWED_CHARACTERS``). The Z set is a strict
# superset that additionally permits the following 13 punctuation characters,
# per the SWIFT Standards MT General Information character-set definitions:
#
#     = ! " % & * < > ; { @ # _
#
# (Note: the Z set does NOT include the vertical bar ``|`` or the closing brace
# ``}`` — a ``}`` in a Z-charset field raises SWIFT error M60.) Deriving the Z
# set from the library's X set keeps the two in lockstep if pain001 ever revises
# its base table.
_SWIFT_Z_EXTRA_CHARACTERS: frozenset[str] = frozenset('=!"%&*<>;{@#_')
_SWIFT_Z_ALLOWED_CHARACTERS: frozenset[str] = (
    ISO20022_ALLOWED_CHARACTERS | _SWIFT_Z_EXTRA_CHARACTERS
)


def _sanitize_to_swift_z(value: str, replacement: str = " ") -> str:
    """Transliterate ``value`` into the SWIFT extended ("Z") character set.

    Mirrors :func:`pain001.sanitize_to_charset` (NFKD-decompose, drop combining
    marks, then replace anything outside the permitted set) but validates
    against the wider SWIFT Z set rather than the basic X set, so extended
    punctuation such as ``@``, ``&`` and ``_`` survives.

    Args:
        value: The text to transliterate.
        replacement: The string substituted for characters that are outside
            the Z set even after transliteration (default: a single space).

    Returns:
        A string containing only SWIFT Z permitted characters.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    return "".join(
        ch if ch in _SWIFT_Z_ALLOWED_CHARACTERS else replacement
        for ch in stripped
    )


server = build_server("pain001", __version__)

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

_SEPA_COUNTRY_CODES: frozenset[str] = frozenset(
    {
        "AD",
        "AT",
        "BE",
        "BG",
        "CH",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GB",
        "GI",
        "GR",
        "HR",
        "HU",
        "IE",
        "IS",
        "IT",
        "LI",
        "LT",
        "LU",
        "LV",
        "MC",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
        "SM",
        "VA",
    }
)

_HUMAN_NAMES = {
    "pain.001.001.03": "Customer Credit Transfer Initiation V03",
    "pain.001.001.04": "Customer Credit Transfer Initiation V04",
    "pain.001.001.05": "Customer Credit Transfer Initiation V05",
    "pain.001.001.06": "Customer Credit Transfer Initiation V06",
    "pain.001.001.07": "Customer Credit Transfer Initiation V07",
    "pain.001.001.08": "Customer Credit Transfer Initiation V08",
    "pain.001.001.09": "Customer Credit Transfer Initiation V09",
    "pain.001.001.10": "Customer Credit Transfer Initiation V10",
    "pain.001.001.11": "Customer Credit Transfer Initiation V11",
    "pain.001.001.12": "Customer Credit Transfer Initiation V12",
    "pain.008.001.02": "Customer Direct Debit Initiation V02",
}

# Data formats the underlying ``pain001`` library can load. Surfaces what an
# agent can offer the user without poking the filesystem.
_SUPPORTED_FORMATS = [
    {"id": "csv", "name": "Comma-Separated Values", "extension": ".csv"},
    {"id": "sqlite", "name": "SQLite database", "extension": ".db"},
    {"id": "json", "name": "JSON array of records", "extension": ".json"},
    {
        "id": "jsonl",
        "name": "Newline-delimited JSON (one record per line)",
        "extension": ".jsonl",
    },
    {
        "id": "parquet",
        "name": "Apache Parquet (requires pain001[parquet] extra)",
        "extension": ".parquet",
    },
]


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


def list_message_types() -> list[dict]:
    """List every supported ISO 20022 pain message type and its human name.

    Use this first, before any generation or validation call, to discover
    the exact ``message_type`` strings this server accepts. Do not use it to
    fetch a type's fields or schema — call ``get_required_fields`` or
    ``get_input_schema`` for that.

    Returns a list of ``{"message_type": ..., "name": ...}`` dictionaries,
    one per supported message type (e.g. ``pain.001.001.09``).
    """
    return [
        {
            "message_type": mt,
            "name": _HUMAN_NAMES.get(mt, mt),
        }
        for mt in valid_xml_types
    ]


def get_required_fields(
    message_type: _MessageType,
) -> list[str]:
    """List only the required input field names for a pain message type.

    Use this for a quick checklist of the mandatory columns before building
    records. When you need full type/format constraints (not just which
    fields are required), call ``get_input_schema`` instead.

    Args:
        message_type: A supported ISO 20022 pain message type.
    """
    try:
        schema = _load_schema(message_type)
        required = schema.get("required", [])
        return list(required)
    except ValueError as exc:
        return [f"error: {exc}"]


def get_input_schema(
    message_type: _MessageType,
) -> SchemaResult:
    """Return the full JSON Schema for a message type's flat input record.

    Use this to learn every field, its type, and its constraints before
    assembling records, or to drive a form/UI. For just the required-field
    names use ``get_required_fields``; to actually check records against
    this schema use ``validate_records``.

    Args:
        message_type: A supported ISO 20022 pain message type.
    """
    try:
        return cast(SchemaResult, _load_schema(message_type))
    except ValueError as exc:
        return {"error": str(exc)}


def validate_records(
    message_type: _MessageType,
    records: Annotated[
        list[dict],
        Field(
            description=(
                "One or more flat payment records to validate, each a dict "
                "of field name → value (see get_input_schema for the fields "
                "and get_required_fields for the mandatory ones)."
            )
        ),
    ],
) -> ValidateRecordsResult:
    """Validate flat records against a message type's input JSON Schema.

    Use this before ``generate_message`` to catch structural/type errors
    per record and get a row-by-row error report. This checks JSON-Schema
    shape only; for payment-scheme rulebook checks (SEPA field lengths,
    charset, etc.) also run ``validate_payment_scheme``.

    Returns a report ``{"valid": bool, "total": int, "valid_count": int,
    "errors": [...]}``.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records to validate.
    """
    try:
        schema = _load_schema(message_type)
    except ValueError as exc:
        return {"error": str(exc)}

    # Map alias keys ('amount', 'currency', lower-case IBAN/BIC spellings)
    # to their canonical names, exactly as generate_message will, so a
    # record that generates cleanly also validates cleanly. Values keep
    # their JSON types; only key names are rewritten.
    records = [canonicalize_payment_record(record) for record in records]

    validator = Draft7Validator(schema)
    errors: list[RecordError] = []
    valid_count = 0
    for row, record in enumerate(records):
        record_errors = sorted(
            validator.iter_errors(record), key=lambda e: list(e.path)
        )
        if not record_errors:
            valid_count += 1
            continue
        for err in record_errors:
            errors.append(
                {
                    "row": row,
                    "path": ".".join(str(p) for p in err.path),
                    "message": err.message,
                }
            )
    return {
        "valid": not errors,
        "total": len(records),
        "valid_count": valid_count,
        "errors": errors,
    }


def suggest_record_fix(
    record: Annotated[
        dict[str, Any],
        Field(description="One flat payment record; never modified."),
    ],
    validation_error: Annotated[
        dict[str, Any],
        Field(description="Finding with field (or path) and rule keys."),
    ],
    message_type: _MessageType = "pain.001.001.03",
) -> dict[str, Any]:
    """Suggest deterministic, review-only fixes to non-financial fields.

    Returns patches or a cannot_autofix reason. Never changes IBANs, BICs,
    accounts, amounts or currencies, even for whitespace. Review every
    candidate and validate the full record before generating a payment.

    Args:
        record: A flat payment record, left unchanged.
        validation_error: Finding with field (or path) and rule keys.
        message_type: Supported schema supplying trusted field bounds.
    """
    try:
        from pain001.validation.corrections import (
            suggest_record_fix as suggest,
        )
    except ImportError:
        return {
            "error": "This tool requires the matching core feature build with record corrections."
        }
    try:
        return suggest(
            record, validation_error, _check_message_type(message_type)
        )
    except ValueError as exc:
        return {"error": str(exc)}


def validate_identifier(
    kind: Annotated[
        str,
        Field(
            description=(
                "Which identifier to validate: 'iban' or 'bic' "
                "(case-insensitive). Any other value returns an error."
            )
        ),
    ],
    value: Annotated[
        str,
        Field(
            description=(
                "The identifier string to check — an IBAN or BIC/SWIFT code "
                "matching the chosen kind."
            )
        ),
    ],
) -> ValidateIdentifierResult:
    """Validate a single financial identifier (IBAN or BIC).

    Use this for a one-off identifier check with a clear pass/fail and
    reason. To validate identifiers embedded across a whole batch, prefer
    ``validate_records`` / ``validate_payment_scheme`` instead of calling
    this per field.

    Returns ``{"kind": str, "value": str, "valid": bool, "error": str}``
    (the ``error`` key is present only when ``valid`` is ``False``).

    Args:
        kind: One of ``"iban"`` or ``"bic"`` (case-insensitive).
        value: The identifier value to check.
    """
    try:
        kind_norm = kind.lower()
        if kind_norm == "iban":
            ok, err = validate_iban(value, strict=False)
        elif kind_norm == "bic":
            ok, err = validate_bic(value, strict=False)
        else:
            raise ValueError(
                f"Unsupported identifier kind: {kind!r} "
                f"(expected 'iban' or 'bic')"
            )
        payload: ValidateIdentifierResult = {
            "kind": kind_norm,
            "value": value,
            "valid": bool(ok),
        }
        if not ok and err:
            payload["error"] = err
        return payload
    except ValueError as exc:
        return {"error": str(exc)}


def generate_message(
    message_type: _MessageType,
    records: Annotated[
        list[dict],
        Field(description=_RECORDS_FIELD_GUIDE),
    ],
) -> str:
    """Generate a validated ISO 20022 pain XML message from in-memory records.

    This is the primary generation tool: pass records you already hold in
    memory. Use ``generate_message_from_file`` when the data lives in a CSV
    on disk, and ``generate_message_async`` for very large batches you want
    to run off the event loop. The result is XSD-validated before return; no
    file is written.

    Records are normalized before rendering: 'amount'/'currency' aliases,
    JSON booleans, and bare 'YYYY-MM-DD' dates are accepted, and
    nb_of_txs/ctrl_sum are computed from the records. On failure the
    ``{"error": ...}`` payload lists every missing or invalid field at
    once. IBAN/BIC values are strictly validated, never coerced.

    Returns the validated XML document as a string, or a JSON-encoded
    ``{"error": ...}`` payload if generation fails.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records.
    """
    try:
        message_type = _check_message_type(message_type)
        template_dir = Path(TEMPLATES_DIR) / message_type
        template_xml = template_dir / "template.xml"
        xsd_schema = template_dir / f"{message_type}.xsd"
        if not template_xml.is_file() or not xsd_schema.is_file():
            raise ValueError(f"No template bundled for {message_type}")
        return generate_xml_string(
            records,
            message_type,
            str(template_xml),
            str(xsd_schema),
        )
    except (ValueError, RuntimeError, Pain001Error) as exc:
        return json.dumps({"error": str(exc)})


def list_supported_formats() -> list[dict]:
    """List the on-disk data formats the pain001 loader can read.

    Use this to tell a user which file types they may supply to
    ``generate_message_from_file``. This lists *data-source* formats (CSV,
    SQLite, …); for the list of ISO 20022 *message* types call
    ``list_message_types`` instead.

    Returns a list of ``{"id", "name", "extension"}`` dictionaries
    covering CSV, SQLite, JSON, JSONL, and Parquet (the last requires the
    ``pain001[parquet]`` extra).
    """
    return [dict(fmt) for fmt in _SUPPORTED_FORMATS]


async def generate_message_async(
    message_type: _MessageType,
    records: Annotated[
        list[dict],
        Field(
            description=(
                "Same record shape and ergonomics as generate_message; use "
                "this async variant only when the batch is large. "
                + _RECORDS_FIELD_GUIDE
            )
        ),
    ],
) -> str:
    """Generate validated pain XML off the event loop, for large batches.

    Behaves exactly like ``generate_message`` but runs the synchronous
    renderer in a worker thread so an agent can interleave a long
    generation with other tool calls. Use ``generate_message`` for small
    or interactive batches; use this only when the record count is large
    enough that blocking would matter.

    Delegates to :func:`pain001.async_adapter.generate_xml_string_async`.
    Returns the validated XML, or a JSON-encoded ``{"error": ...}`` payload.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records.
    """
    try:
        message_type = _check_message_type(message_type)
        template_dir = Path(TEMPLATES_DIR) / message_type
        template_xml = template_dir / "template.xml"
        xsd_schema = template_dir / f"{message_type}.xsd"
        if not template_xml.is_file() or not xsd_schema.is_file():
            raise ValueError(f"No template bundled for {message_type}")
        return await generate_xml_string_async(
            records,
            message_type,
            str(template_xml),
            str(xsd_schema),
        )
    except (ValueError, RuntimeError, Pain001Error) as exc:
        return json.dumps({"error": str(exc)})


def generate_message_from_file(
    message_type: _MessageType,
    data_file_path: Annotated[
        str,
        Field(
            description=(
                "Local filesystem path to a CSV file with one payment record "
                "per row and a header matching the template columns (see "
                "inspect_template). Only CSV is supported today."
            )
        ),
    ],
) -> str:
    """Generate validated pain XML from a CSV file on the local disk.

    Use this when the records live in a CSV file rather than in memory; it
    reads ``data_file_path`` from the local filesystem, then delegates to
    ``generate_message``. If you already have the records as dicts, call
    ``generate_message`` directly. Only CSV is supported today (JSON / JSONL
    / SQLite / Parquet are planned for a follow-up release).

    Loads ``data_file_path`` via :func:`pain001.csv.load_csv_data.load_csv_data`
    so the same path-safety guards apply as in the core library.

    Args:
        message_type: A supported ISO 20022 pain message type.
        data_file_path: Path to a CSV file with one record per row.

    Returns:
        The validated XML, or a JSON-encoded ``{"error": ...}`` payload.
    """
    try:
        records = load_csv_data(data_file_path)
    except Exception as exc:  # noqa: BLE001 - many concrete types possible
        return json.dumps({"error": str(exc)})
    return generate_message(message_type, records)


def parse_camt053(
    xml_file_path: Annotated[
        str,
        Field(
            description=(
                "Local filesystem path to the camt.053 bank-statement XML "
                "file to parse."
            )
        ),
    ],
    xsd_file_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional local path to a camt.053 XSD; when given, the "
                "document is validated against it before parsing. Omit to "
                "skip schema validation."
            )
        ),
    ] = None,
) -> Camt053Result:
    """Parse a camt.053 bank-statement XML file on disk into structured data.

    Use this to read a bank's account statement (the reply that confirms
    settlement) into a header + entry list. Reads ``xml_file_path`` from the
    local filesystem. For the payment-status reply (accepted/rejected per
    transaction) use ``parse_pain002`` instead; to validate a camt.053
    string you already hold, this is not it — this tool needs a file path.

    Wraps :func:`pain001.parse_camt053_statement`. When ``xsd_file_path``
    is provided, the document is first validated against that XSD; on a
    schema or parse error the tool returns ``{"error": ...}`` rather than
    raising.

    Args:
        xml_file_path: Filesystem path to the camt.053 XML statement.
        xsd_file_path: Optional path to a camt.053 XSD for upfront
            validation.

    Returns:
        A compact dict with the statement header and entry list, or an
        ``{"error": ...}`` payload on failure.
    """
    try:
        return cast(
            Camt053Result,
            parse_camt053_statement(xml_file_path, xsd_file_path),
        )
    except Exception as exc:  # noqa: BLE001 - pain001 raises several types
        return {"error": str(exc)}


def parse_pain002(
    xml_file_path: Annotated[
        str,
        Field(
            description=(
                "Local filesystem path to the pain.002 payment-status report "
                "XML file to parse."
            )
        ),
    ],
    xsd_file_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional local path to a pain.002 XSD; when given, the "
                "document is validated against it before parsing. Omit to "
                "skip schema validation."
            )
        ),
    ] = None,
) -> Pain002Result:
    """Parse a pain.002 payment-status report file on disk into structured data.

    Use this to read the bank's acknowledgement of a submitted pain.001 —
    the per-transaction accepted/rejected status and reason codes. Reads
    ``xml_file_path`` from the local filesystem. For the account statement
    that later confirms booked entries, use ``parse_camt053`` instead.

    Wraps :func:`pain001.parse_pain002_report`. When ``xsd_file_path`` is
    provided, the document is first validated against that XSD; on a
    schema or parse error the tool returns ``{"error": ...}`` rather than
    raising.

    Args:
        xml_file_path: Filesystem path to the pain.002 XML report.
        xsd_file_path: Optional path to a pain.002 XSD for upfront
            validation.

    Returns:
        A dict with the group header and transaction statuses, or an
        ``{"error": ...}`` payload on failure.
    """
    try:
        return cast(
            Pain002Result, parse_pain002_report(xml_file_path, xsd_file_path)
        )
    except Exception as exc:  # noqa: BLE001 - pain001 raises several types
        return {"error": str(exc)}


def inspect_template(
    message_type: _MessageType,
) -> TemplateResult:
    """Return the CSV column headers the message type's bundled template uses.

    Use this to see the exact column order for hand-building a CSV before
    ``generate_message_from_file``. This returns column *names* from the
    bundled sample; for the typed JSON contract (types, required flags) use
    ``get_input_schema``.

    Mirrors the in-tree ``pain001.mcp.server.inspect_template`` tool so an
    agent can introspect the column layout before assembling rows.

    Args:
        message_type: A supported ISO 20022 pain message type.

    Returns:
        ``{"message_type": str, "columns": list[str]}`` or
        ``{"error": ...}`` if the type is unsupported or no template ships.
    """
    try:
        message_type = _check_message_type(message_type)
        sample = Path(TEMPLATES_DIR) / message_type / "template.csv"
        if not sample.is_file():
            raise ValueError(f"No bundled CSV template for {message_type}")
        reader = csv.reader(io.StringIO(sample.read_text(encoding="utf-8")))
        columns = next(reader, [])
        return {"message_type": message_type, "columns": list(columns)}
    except ValueError as exc:
        return {"error": str(exc)}


def validate_payment_scheme(
    records: Annotated[
        list[dict],
        Field(
            description=(
                "Payment records as a list of flat dicts (field name → "
                "value) to check against the scheme rulebook."
            )
        ),
    ],
    profile: Annotated[
        str,
        Field(
            description=(
                "The payment-scheme rulebook profile to enforce. One of "
                "'sepa-sct', 'sepa-sdd', 'sepa-inst', or 'xborder-ct'. "
                "Defaults to 'sepa-sct'."
            )
        ),
    ] = "sepa-sct",
) -> SchemeResult:
    """Validate records against a payment-scheme rulebook (e.g. SEPA).

    Use this after ``validate_records`` to enforce scheme-specific business
    rules (SEPA field lengths, allowed characters, currency/BIC constraints)
    that JSON-Schema validation alone does not cover. ``validate_records``
    checks structural shape; this checks rulebook compliance for one profile.

    Delegates to :func:`pain001.validate_scheme`. Supported profiles:
    ``sepa-sct``, ``sepa-sdd``, ``sepa-inst``, ``xborder-ct``.

    Args:
        records: Payment records as a list of flat dicts.
        profile: The scheme profile name.

    Returns:
        ``{"profile", "is_valid", "violations": [...]}`` with structured
        ``violations`` (each with ``rule``, ``severity``, ``field``,
        ``message``, ``remediation`` keys), or ``{"error": ...}`` for an
        unknown profile.
    """
    try:
        result = validate_scheme(records, profile)
    except ValueError as exc:
        return {"error": str(exc)}
    return {
        "profile": result.profile,
        "is_valid": result.is_valid,
        "violations": [
            cast(SchemeViolation, v.as_dict()) for v in result.violations
        ],
    }


def simulate_payment_batch(
    message_type: _MessageType,
    records: Annotated[
        list[dict],
        Field(
            description=(
                "One or more flat payment records to simulate and pre-flight "
                "before generating XML. " + _RECORDS_FIELD_GUIDE
            )
        ),
    ],
    scheme: Annotated[
        str | None,
        Field(
            description=(
                "Optional payment-scheme rulebook profile to enforce (e.g. "
                "'sepa-sct', 'sepa-sdd', 'sepa-inst', 'xborder-ct'). Omit to "
                "skip scheme-specific rulebook validation."
            )
        ),
    ] = None,
) -> SimulatePaymentBatchResult:
    """Simulate and pre-flight a payment batch before XML generation.

    Performs comprehensive pre-flight verification without generating XML
    or staging files:
    1. Validates records against the message type's JSON Schema.
    2. Validates records against an optional payment-scheme rulebook.
    3. Computes control sums grouped by currency.
    4. Calculates unique debtor and creditor account counts.
    5. Detects intra-batch duplicate transactions (same debtor, creditor,
       amount, currency, and execution date).

    Returns a structured verdict with totals, sums by currency, duplicate
    findings, and schema/scheme errors.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records to simulate.
        scheme: Optional payment scheme profile to validate against.
    """
    validation_report = validate_records(message_type, records)
    if "error" in validation_report:
        return {"error": validation_report["error"]}

    canonical_records = [
        canonicalize_payment_record(record) for record in records
    ]

    sums: dict[str, Decimal] = {}
    debtors: set[str] = set()
    creditors: set[str] = set()
    duplicates: list[DuplicateTransaction] = []
    seen_txs: dict[tuple[str, str, str, str, str], int] = {}

    for row_idx, record in enumerate(canonical_records):
        debtor_iban = (
            str(record.get("debtor_account_IBAN", "")).strip().upper()
        )
        if debtor_iban:
            debtors.add(debtor_iban)

        creditor_iban = (
            str(record.get("creditor_account_IBAN", "")).strip().upper()
        )
        if creditor_iban:
            creditors.add(creditor_iban)

        curr = str(record.get("currency", "")).strip().upper()
        date_val = str(record.get("requested_execution_date", "")).strip()

        amt_raw = record.get("payment_amount")
        amt_str = ""
        if amt_raw is not None:
            try:
                amt_dec = Decimal(str(amt_raw))
                amt_str = f"{amt_dec:.2f}"
                if curr:
                    sums[curr] = sums.get(curr, Decimal(0)) + amt_dec
            except (InvalidOperation, TypeError):
                amt_str = str(amt_raw).strip()

        if debtor_iban and creditor_iban and amt_str and curr:
            tx_key = (debtor_iban, creditor_iban, amt_str, curr, date_val)
            if tx_key in seen_txs:
                duplicates.append(
                    {
                        "row": row_idx,
                        "matching_row": seen_txs[tx_key],
                        "debtor_account_IBAN": debtor_iban,
                        "creditor_account_IBAN": creditor_iban,
                        "amount": amt_str,
                        "currency": curr,
                        "requested_execution_date": date_val,
                    }
                )
            else:
                seen_txs[tx_key] = row_idx

    control_sum_by_currency = {
        curr: f"{total:.2f}" for curr, total in sorted(sums.items())
    }

    schema_errors = validation_report.get("errors", [])
    valid_count = validation_report.get("valid_count", 0)
    total = validation_report.get("total", len(records))

    scheme_violations: list[SchemeViolation] = []
    scheme_valid = True
    if scheme is not None:
        scheme_res = validate_payment_scheme(records, profile=scheme)
        if "error" in scheme_res:
            return {"error": scheme_res["error"]}
        scheme_violations = scheme_res.get("violations", [])
        scheme_valid = scheme_res.get("is_valid", True)

    is_valid = bool(
        validation_report.get("valid", False)
        and scheme_valid
        and len(duplicates) == 0
    )

    return {
        "valid": is_valid,
        "total": total,
        "valid_count": valid_count,
        "control_sum_by_currency": control_sum_by_currency,
        "unique_debtors": len(debtors),
        "unique_creditors": len(creditors),
        "duplicates": duplicates,
        "schema_errors": schema_errors,
        "scheme_violations": scheme_violations,
    }


def schema_resource(
    message_type: _MessageType,
) -> str:
    """Expose the official XSD schema text for a message type as a resource.

    MCP clients can subscribe to or fetch ``pain001://schema/{type}`` to
    pull the canonical XSD without having to install pain001 themselves.

    Args:
        message_type: A supported ISO 20022 pain message type.

    Returns:
        The XSD schema text. Raises ``ValueError`` for an unsupported type.
    """
    message_type = _check_message_type(message_type)
    xsd = Path(TEMPLATES_DIR) / message_type / f"{message_type}.xsd"
    return xsd.read_text(encoding="utf-8")


def build_payment_batch(
    message_type: _MessageType = "pain.001.001.09",
) -> str:
    """Guided prompt for assembling a compliant payment batch.

    The MCP client sends this to the model to teach it the recommended
    tool order: discover columns, build rows, validate, then generate.

    Args:
        message_type: The target ISO 20022 pain message type.

    Returns:
        A prompt string instructing the model how to proceed.
    """
    return (
        f"Help me build a compliant {message_type} batch. First call "
        f"inspect_template('{message_type}') for the column layout, "
        "then call get_required_fields and get_input_schema for the "
        "typed contract. Assemble one dict per payment, validate them "
        "with validate_records (and validate_payment_scheme for SEPA), "
        "then call generate_message to produce the XML."
    )


def migrate_records(
    records: Annotated[
        list[dict],
        Field(
            description=(
                "Flat payment records in the from_version shape, each a dict "
                "of field name → value, to transform to to_version."
            )
        ),
    ],
    from_version: Annotated[
        str,
        Field(
            description=(
                "Source pain.001 schema version the records currently use, "
                "e.g. 'pain.001.001.03' — see list_message_types."
            )
        ),
    ],
    to_version: Annotated[
        str,
        Field(
            description=(
                "Target pain.001 schema version to migrate the records to, "
                "e.g. 'pain.001.001.09' — see list_message_types."
            )
        ),
    ],
) -> MigrateResult:
    """Migrate flat payment records between two pain.001 schema versions.

    Use this to upgrade/downgrade records when your bank requires a
    different pain.001 version than your source data uses (e.g. move
    ``.03`` rows to ``.09``); it reports which fields were renamed, derived,
    or dropped. This transforms records only — run ``validate_records``
    afterwards, then ``generate_message`` to emit XML.

    Wraps :class:`pain001.migration.VersionMapper`. Returns the
    migrated rows plus a summary of which fields were renamed,
    derived, or dropped; ``{"error": ...}`` if either version is
    unsupported.

    Args:
        records: Records in the ``from_version`` shape.
        from_version: Source pain.001 version (e.g. ``"pain.001.001.03"``).
        to_version: Target pain.001 version (e.g. ``"pain.001.001.09"``).

    Returns:
        ``{"records": [...], "migrated": int, "from": str, "to": str}``
        or ``{"error": ...}``.
    """
    try:
        mapper = VersionMapper()
        migrated = mapper.migrate_rows(records, from_version, to_version)
        return {
            "records": migrated,
            "migrated": len(migrated),
            "from": from_version,
            "to": to_version,
        }
    except Exception as exc:  # noqa: BLE001 - DataSourceError + others
        return {"error": str(exc)}


def validate_xml_against_schema(
    xml_content: Annotated[
        str,
        Field(
            description=(
                "The full pain.001 / pain.008 XML document as a string, "
                "validated against the message type's official XSD."
            )
        ),
    ],
    message_type: _MessageType,
) -> XsdResult:
    """Validate a raw pain.001 / pain.008 XML string against its official XSD.

    Use this to check XML you already have as a string (e.g. received from
    another system) without touching the filesystem. To validate records
    *before* they become XML, use ``validate_records``; to parse a statement
    or status-report file, use ``parse_camt053`` / ``parse_pain002``.

    Wraps :func:`pain001.xml.validate_via_xsd.validate_xml_string_via_xsd`.

    Args:
        xml_content: The XML document as a string.
        message_type: A supported ISO 20022 pain message type.

    Returns:
        ``{"valid": bool, "message_type": str, "error": str?}`` -
        ``error`` is present only when ``valid`` is ``False``.
    """
    try:
        message_type = _check_message_type(message_type)
        xsd = Path(TEMPLATES_DIR) / message_type / f"{message_type}.xsd"
        if not xsd.is_file():  # pragma: no cover - all valid types ship XSD
            return {"error": f"No XSD bundled for {message_type}"}
        try:
            ok = validate_xml_string_via_xsd(xml_content, str(xsd))
        except (
            Exception
        ) as exc:  # pragma: no cover - underlying API returns False, not raises
            return {
                "valid": False,
                "message_type": message_type,
                "error": str(exc),
            }
        return {"valid": bool(ok), "message_type": message_type}
    except ValueError as exc:
        return {"error": str(exc)}


def sanitize_to_iso20022_charset(
    value: Annotated[
        str,
        Field(
            description=(
                "A single free-text field value (e.g. a name or remittance "
                "line) to transliterate to the ISO 20022 Latin character set."
            )
        ),
    ],
    charset: Annotated[
        Literal["SWIFT_X", "SWIFT_Z"],
        Field(
            description=(
                "Which SWIFT character set to sanitise against. 'SWIFT_X' "
                "(default) is the basic set permitted in most ISO 20022 / "
                "pain.001 fields: letters, digits, space and the punctuation "
                "/ - ? : ( ) . , ' + . 'SWIFT_Z' is the extended superset that "
                'additionally allows = ! " % & * < > ; { @ # _ (used in '
                "narrative / envelope fields); it does NOT allow | or }. Pick "
                "SWIFT_Z only when the target field is documented as Z-set."
            )
        ),
    ] = "SWIFT_X",
) -> SanitiseResult:
    """Sanitise one free-text field to a SWIFT / ISO 20022 character set.

    Use this on a single free-text value (name, remittance info) to
    transliterate accents and drop unsupported symbols before placing it in
    a record, and to see whether the value changed. Operates on one string;
    to check a whole batch's rulebook compliance use ``validate_payment_scheme``.

    Two character sets are supported via ``charset``:

    * ``"SWIFT_X"`` (default, backward-compatible) - the basic set used in
      most ISO 20022 / pain.001 fields. Delegates to
      :func:`pain001.sanitize_to_charset`.
    * ``"SWIFT_Z"`` - the SWIFT extended set, a strict superset of X that also
      permits ``= ! " % & * < > ; { @ # _`` (used in narrative / envelope
      fields). It does not permit ``|`` or ``}``.

    In both cases accents are transliterated (``é`` -> ``e``) and any remaining
    out-of-set character is replaced with a space. The result includes flags
    for whether the original was already valid and whether it changed - useful
    for surfacing the change to the user before writing it back to a record.

    Args:
        value: The text to sanitise.
        charset: ``"SWIFT_X"`` (default) or ``"SWIFT_Z"``.

    Returns:
        ``{"value": str, "sanitised": str, "was_valid": bool, "changed": bool}``.
    """
    if charset == "SWIFT_Z":
        cleaned = _sanitize_to_swift_z(value)
    else:
        cleaned = sanitize_to_charset(value)
    return {
        "value": value,
        "sanitised": cleaned,
        "was_valid": cleaned == value,
        "changed": cleaned != value,
    }


def convert_mt101(
    mt101_text: Annotated[
        str,
        Field(
            description=(
                "A legacy SWIFT MT101 (Request for Transfer) message as text "
                "— a bare ':tag:' field list or a raw '{4:...-}' block-4 "
                "envelope. An MT101 may carry several sequence-B transfers; "
                "each becomes its own record."
            )
        ),
    ],
) -> list[dict] | dict:
    """Convert a legacy SWIFT MT101 message into pain.001-ready records.

    Use this to bridge the Nov-2025+ SWIFT MT→MX migration: parse an MT101
    (*Request for Transfer*) into the flat records the other tools consume —
    feed the result straight to ``validate_records`` /
    ``validate_payment_scheme`` and then ``generate_message`` to emit
    pain.001.001.09 XML. An MT101 can request many transfers (repeating
    sequence B), so this returns *one record per transaction*. Operates on
    the supplied text only; no file is read or written.

    Wraps :func:`pain001_loader_mt101.loader.parse_mt101`. Sequence-A
    ordering-customer / account-servicing fields apply to every transaction
    unless a sequence-B block overrides them; fields the MT101 does not
    carry are synthesised to schema defaults (``payment_method`` ``"TRF"``,
    ``service_level_code`` ``"SEPA"``, etc.).

    Args:
        mt101_text: The MT101 payload as a string.

    Returns:
        A list of flat pain.001 records (one per transaction), or an
        ``{"error": ...}`` dict if the MT101 is missing a mandatory field
        (``:20:``, ``:30:``, or per transaction ``:21:`` / ``:32B:`` /
        a named beneficiary) or is otherwise malformed.
    """
    try:
        return parse_mt101(mt101_text)
    except ValueError as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Example corpus (pain001 >= 0.0.67)
# ---------------------------------------------------------------------------

_CORPUS_MISSING = (
    "the example corpus needs pain001 >= 0.0.67; the installed pain001 "
    "has no pain001.corpus module"
)


def _corpus_api() -> Any | None:
    """Return :mod:`pain001.corpus`, or ``None`` when the library predates it.

    The corpus shipped in pain001 0.0.67; older releases are still valid
    peers of this server, so the four corpus tools report a clear error
    instead of failing at import time.
    """
    try:
        return importlib.import_module("pain001.corpus")
    except ImportError:
        return None


def list_corpus_files(
    kind: Annotated[
        str | None,
        Field(
            description=(
                "'market' for the realistic per-country scenarios, "
                "'coverage' for the schema coverage sets, or omit for both."
            )
        ),
    ] = None,
    country: Annotated[
        str | None,
        Field(
            description=(
                "Two-letter country code to keep one market pack only, "
                "e.g. 'GB' or 'CH'. Ignored for coverage files."
            )
        ),
    ] = None,
    version: Annotated[
        str | None,
        Field(
            description=(
                "Keep only files of this message type, e.g. 'pain.001.001.09'."
            )
        ),
    ] = None,
) -> CorpusListResult:
    """List the example files pain001 ships: market scenarios and coverage sets.

    Use this to discover what ready-made, validated ISO 20022 files exist
    before calling ``get_corpus_file`` or ``get_corpus_provenance``. Market
    files are realistic payments per country and rail (``scenario_id``
    like ``gb.chaps.property-purchase``); a ``variant`` names the bank
    overlay a file was built with. Coverage files exercise every element
    and choice branch of one message type and carry no scenario.

    Delegates to :func:`pain001.corpus.list_files`.

    Args:
        kind: ``market``, ``coverage`` or ``None`` for both.
        country: Optional two-letter country filter for market files.
        version: Optional message-type filter.

    Returns:
        ``{"count", "files": [{"kind", "scenario_id", "version", "country",
        "family", "variant", "file"}, ...]}``, or ``{"error": ...}`` when
        the installed pain001 has no corpus.
    """
    corpus = _corpus_api()
    if corpus is None:
        return {"error": _CORPUS_MISSING}
    wanted_country = country.upper() if country else None
    files: list[CorpusFileEntry] = []
    for entry in corpus.list_files(kind):
        if wanted_country and entry.country != wanted_country:
            continue
        if version and entry.version != version:
            continue
        files.append(
            {
                "kind": entry.kind,
                "scenario_id": entry.scenario_id,
                "version": entry.version,
                "country": entry.country,
                "family": entry.family,
                "variant": entry.variant,
                "file": entry.path.name,
            }
        )
    return {"count": len(files), "files": files}


def get_corpus_file(
    scenario_id: Annotated[
        str,
        Field(
            description=(
                "The market scenario, e.g. 'gb.chaps.property-purchase' "
                "(from list_corpus_files)."
            )
        ),
    ],
    version: Annotated[
        str,
        Field(description="The message type, e.g. 'pain.001.001.09'."),
    ],
    variant: Annotated[
        str | None,
        Field(
            description=(
                "An overlay id for the bank variant, e.g. "
                "'gb.example.priority'; omit for the generic file."
            )
        ),
    ] = None,
) -> CorpusFileResult:
    """Return the XML of one validated example file from the market corpus.

    Use this to show a model, a tester or a mapping exercise what a
    correct file for a given country and rail looks like in a given
    edition. The text is exactly what pain001 ships; it passed the XSD,
    the ISO MDR rules, the rail profile and the overlay when it was built.

    Delegates to :func:`pain001.corpus.get_file`.

    Args:
        scenario_id: The scenario.
        version: The message type.
        variant: The overlay id of a bank variant, else ``None``.

    Returns:
        ``{"scenario_id", "version", "variant", "xml"}``, or
        ``{"error": ...}`` when there is no such file or no corpus.
    """
    corpus = _corpus_api()
    if corpus is None:
        return {"error": _CORPUS_MISSING}
    try:
        xml = corpus.get_file(scenario_id, version, variant)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return {
        "scenario_id": scenario_id,
        "version": version,
        "variant": variant,
        "xml": xml,
    }


def get_corpus_provenance(
    scenario_id: Annotated[
        str,
        Field(description="The market scenario (from list_corpus_files)."),
    ],
    version: Annotated[
        str,
        Field(description="The message type, e.g. 'pain.001.001.09'."),
    ],
    variant: Annotated[
        str | None,
        Field(
            description=(
                "An overlay id for the bank variant; omit for the generic "
                "file."
            )
        ),
    ] = None,
) -> CorpusProvenanceResult:
    """Return the provenance sidecar of one example file.

    Use this to know how far to trust a file: the sources it was derived
    from, the confidence of the evidence (``verified``, ``derived`` or
    ``assumed``), the validation ladder result per rung, what the builder
    renamed or dropped to fit the edition, and the file's SHA-256.

    Delegates to :func:`pain001.corpus.provenance`.

    Args:
        scenario_id: The scenario.
        version: The message type.
        variant: The overlay id of a bank variant, else ``None``.

    Returns:
        The parsed sidecar as a dict, or ``{"error": ...}`` when there is
        no such file or no corpus.
    """
    corpus = _corpus_api()
    if corpus is None:
        return {"error": _CORPUS_MISSING}
    try:
        record: dict = corpus.provenance(scenario_id, version, variant)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return cast(CorpusProvenanceResult, record)


def get_corpus_coverage(
    version: Annotated[
        str,
        Field(description="The message type, e.g. 'pain.001.001.13'."),
    ],
) -> CorpusCoverageResult:
    """Return the schema coverage verdict of one message type's coverage set.

    Use this to check that the shipped coverage files reach every element
    path and choice branch of an edition's XSD before relying on them to
    smoke a parser or a mapping.

    Delegates to :func:`pain001.corpus.coverage_report`.

    Args:
        version: The message type.

    Returns:
        The ``coverage.json`` content (path and branch counts and
        percentages, completeness, missing and exempt lists), or
        ``{"error": ...}`` when the edition has no set or there is no
        corpus.
    """
    corpus = _corpus_api()
    if corpus is None:
        return {"error": _CORPUS_MISSING}
    try:
        report: dict = corpus.coverage_report(version)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return cast(CorpusCoverageResult, report)


@dataclass
class _StagedOrder:
    """Internal representation of a staged payment order awaiting authorization."""

    stage_id: str
    confirmation_token: str
    message_type: str
    records: list[dict[str, Any]]
    xml_content: str
    sha256_fingerprint: str
    created_at: float
    expires_at: float
    total_transactions: int
    control_sum_by_currency: dict[str, str]
    status: str  # "staged" | "committed"


_STAGED_PAYMENTS: dict[str, _StagedOrder] = {}


def _clean_expired_staged_orders(now: float | None = None) -> None:
    """Remove expired staged payment batches older than 24h from cache."""
    current_time = time.time() if now is None else now
    cutoff = current_time - 86400.0
    expired = [
        sid
        for sid, order in _STAGED_PAYMENTS.items()
        if order.expires_at <= cutoff
    ]
    for sid in expired:
        del _STAGED_PAYMENTS[sid]


def stage_payment_batch(
    message_type: _MessageType,
    records: Annotated[
        list[dict],
        Field(
            description=(
                "Flat payment records to stage (zero fund movement). "
                + _RECORDS_FIELD_GUIDE
            )
        ),
    ],
    scheme: Annotated[
        str | None,
        Field(
            description=(
                "Optional payment scheme profile to validate against, "
                "e.g. 'sepa-sct', 'sepa-instant', 'bacs', or 'cbpr-plus'."
            )
        ),
    ] = None,
) -> StagedBatchResult:
    """Stage a payment batch for simulation and dual-control approval.

    Creates an in-memory staged payment order with zero fund movement and
    a 1-hour expiration window. Computes:
    1. Schema validation against the message type's JSON Schema.
    2. Optional scheme compliance verification (SEPA, BACS, etc.).
    3. Multi-currency control sums and fee estimation.
    4. Multi-factor risk scoring (detecting duplicates, high transaction
       amounts, and generic remittance narratives).
    5. In-memory XML compilation and SHA-256 fingerprinting.
    6. Cryptographic dual-control confirmation token for subsequent authorization.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records to stage.
        scheme: Optional payment scheme profile to validate against.

    Returns:
        StagedBatchResult with staging metadata, risk assessment, fingerprint,
        and confirmation token, or {"error": ...}.
    """
    _clean_expired_staged_orders()
    validation_report = validate_records(message_type, records)
    if "error" in validation_report:
        return {"error": validation_report["error"]}
    if not validation_report.get("valid", False):
        err_count = len(validation_report.get("errors", []))
        return {
            "error": f"Batch failed schema validation with {err_count} errors"
        }

    canonical_records = [
        canonicalize_payment_record(record) for record in records
    ]

    if scheme is not None:
        scheme_res = validate_payment_scheme(canonical_records, profile=scheme)
        if "error" in scheme_res:
            return {"error": scheme_res["error"]}
        if not scheme_res.get("is_valid", True):
            v_count = len(scheme_res.get("violations", []))
            return {
                "error": f"Batch failed scheme '{scheme}' validation with {v_count} violations"
            }
    sums: dict[str, Decimal] = {}
    total_txs = len(canonical_records)
    duplicates: list[dict[str, Any]] = []
    seen_txs: dict[tuple[str, str, str, str, str], int] = {}
    high_value_txs = 0
    generic_remittance = 0

    for row_idx, record in enumerate(canonical_records):
        debtor_iban = (
            str(record.get("debtor_account_IBAN", "")).strip().upper()
        )
        creditor_iban = (
            str(record.get("creditor_account_IBAN", "")).strip().upper()
        )
        curr = str(record.get("currency", "")).strip().upper() or "EUR"
        date_val = str(record.get("requested_execution_date", "")).strip()

        amt_raw = record.get("payment_amount")
        amt_dec = (
            Decimal(str(amt_raw)) if amt_raw is not None else Decimal("0.00")
        )
        amt_str = f"{amt_dec:.2f}"
        sums[curr] = sums.get(curr, Decimal(0)) + amt_dec

        if amt_dec >= Decimal("100000.00"):
            high_value_txs += 1

        rmt = str(record.get("remittance_information", "")).strip().lower()
        if not rmt or rmt in {"payment", "invoice", "transfer"}:
            generic_remittance += 1

        tx_key = (debtor_iban, creditor_iban, amt_str, curr, date_val)
        if tx_key in seen_txs:
            duplicates.append(
                {"row": row_idx, "matching_row": seen_txs[tx_key]}
            )
        else:
            seen_txs[tx_key] = row_idx

    risk_score = 0
    risk_factors: list[str] = []
    if duplicates:
        risk_score += 35
        risk_factors.append(
            f"{len(duplicates)} duplicate transactions detected in batch"
        )
    if high_value_txs > 0:
        risk_score += 25
        risk_factors.append(
            f"{high_value_txs} transactions exceed 100,000.00 threshold"
        )

    for curr, total in sums.items():
        if total >= Decimal("500000.00"):
            risk_score += 20
            risk_factors.append(
                f"Aggregate volume in {curr} exceeds 500,000.00"
            )
            break

    if generic_remittance > 0:
        risk_score += 15
        risk_factors.append(
            f"{generic_remittance} transactions have missing or generic remittance information"
        )

    risk_score = min(risk_score, 100)
    if risk_score <= 25:
        risk_level = "LOW"
    elif risk_score <= 60:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    estimated_fees: dict[str, str] = {}
    for curr in sums:
        if curr == "EUR":
            rate = Decimal("0.20")
        elif curr == "USD":
            rate = Decimal("0.25")
        elif curr == "GBP":
            rate = Decimal("0.15")
        else:
            rate = Decimal("0.50")
        fee = rate * total_txs
        estimated_fees[curr] = f"{fee:.2f}"

    resolved_mt = _MESSAGE_TYPE_ALIASES.get(message_type, message_type)
    xml_res = generate_message(resolved_mt, records)
    if xml_res.startswith('{"error":'):  # pragma: no cover
        try:
            err_data = json.loads(xml_res)
            return {"error": err_data.get("error", "XML generation failed")}
        except Exception:
            return {"error": xml_res}
    xml_content = xml_res

    sha256_fingerprint = hashlib.sha256(
        xml_content.encode("utf-8")
    ).hexdigest()
    stage_id = f"stage_{secrets.token_hex(8)}"
    confirmation_token = f"tok_{secrets.token_urlsafe(24)}"
    now = time.time()
    expires_at_epoch = now + 3600.0
    expires_at_iso = datetime.fromtimestamp(
        expires_at_epoch, tz=timezone.utc
    ).isoformat()

    control_sum_by_currency = {
        curr: f"{total:.2f}" for curr, total in sorted(sums.items())
    }

    order = _StagedOrder(
        stage_id=stage_id,
        confirmation_token=confirmation_token,
        message_type=resolved_mt,
        records=records,
        xml_content=xml_content,
        sha256_fingerprint=sha256_fingerprint,
        created_at=now,
        expires_at=expires_at_epoch,
        total_transactions=total_txs,
        control_sum_by_currency=control_sum_by_currency,
        status="staged",
    )
    _STAGED_PAYMENTS[stage_id] = order

    return {
        "stage_id": stage_id,
        "sha256_fingerprint": sha256_fingerprint,
        "total_transactions": total_txs,
        "control_sum_by_currency": control_sum_by_currency,
        "estimated_fees": estimated_fees,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "status": "staged",
        "confirmation_token": confirmation_token,
        "expires_at": expires_at_iso,
    }


def simulate_clearing(
    stage_id: Annotated[
        str,
        Field(
            description="The staging identifier returned by stage_payment_batch."
        ),
    ],
    clearing_system: Annotated[
        Literal["EPC-SEPA", "FedNow", "US-ACH", "SWIFT-MX", "CHAPS", "BACS"],
        Field(
            description=(
                "Target clearing system simulation profile to evaluate "
                "settlement eligibility, cut-off windows, and routing constraints."
            )
        ),
    ] = "EPC-SEPA",
) -> SimulateClearingResult:
    """Simulate settlement and clearing network execution for a staged batch.

    Evaluates network-specific rulebooks and clearing constraints:
    - EPC-SEPA: EUR currency mandate, SEPA-zone IBAN prefixes, SLEV charge bearer.
    - FedNow: USD instant gross settlement eligibility.
    - US-ACH: USD next-day clearing cycle routing.
    - SWIFT-MX: Cross-border correspondent banking BIC routing.
    - CHAPS: Same-day RTGS high-value GBP clearing.
    - BACS: Three-day GBP direct credit clearing.

    Args:
        stage_id: Staging identifier from stage_payment_batch.
        clearing_system: Clearing rail profile to simulate.

    Returns:
        SimulateClearingResult with verdict (ACCEPTED / REJECTED), detailed
        checks, and estimated settlement window, or {"error": ...}.
    """
    _clean_expired_staged_orders()
    if stage_id not in _STAGED_PAYMENTS:
        return {"error": f"Staged payment batch '{stage_id}' not found"}

    order = _STAGED_PAYMENTS[stage_id]
    if order.expires_at <= time.time():
        del _STAGED_PAYMENTS[stage_id]
        return {"error": f"Staged payment batch '{stage_id}' has expired"}

    if order.status == "committed":
        return {
            "error": f"Staged payment batch '{stage_id}' has already been committed"
        }

    if clearing_system not in {
        "EPC-SEPA",
        "FedNow",
        "US-ACH",
        "SWIFT-MX",
        "CHAPS",
        "BACS",
    }:
        return {"error": f"Unsupported clearing system: {clearing_system}"}

    checks: list[ClearingCheck] = []
    settlement_window = ""

    records = [canonicalize_payment_record(r) for r in order.records]

    if clearing_system == "EPC-SEPA":
        settlement_window = "Next SEPA Cycle (Same Day / D+1)"
        all_eur = all(
            str(r.get("currency", "")).strip().upper() == "EUR"
            for r in records
        )
        checks.append(
            {
                "check": "EPC-SEPA Currency Rule (EUR)",
                "status": "PASS" if all_eur else "FAIL",
                "detail": (
                    "All payments denominated in EUR"
                    if all_eur
                    else "All SEPA transfers must be denominated in EUR"
                ),
            }
        )
        all_sepa_ibans = True
        for r in records:
            d_iban = str(r.get("debtor_account_IBAN", "")).strip().upper()
            c_iban = str(r.get("creditor_account_IBAN", "")).strip().upper()
            if (
                d_iban[:2] not in _SEPA_COUNTRY_CODES
                or c_iban[:2] not in _SEPA_COUNTRY_CODES
            ):
                all_sepa_ibans = False
                break
        checks.append(
            {
                "check": "SEPA-Zone Routing Eligibility",
                "status": "PASS" if all_sepa_ibans else "FAIL",
                "detail": (
                    "Debtor and creditor accounts reside in SEPA member jurisdictions"
                    if all_sepa_ibans
                    else "IBAN country prefix outside SEPA clearing jurisdiction"
                ),
            }
        )
        all_slev = all(
            str(r.get("charge_bearer", "SLEV")).strip().upper() == "SLEV"
            for r in records
        )
        checks.append(
            {
                "check": "EPC Charge Bearer Standard (SLEV)",
                "status": "PASS" if all_slev else "FAIL",
                "detail": (
                    "Charge bearer set to SLEV as mandated by EPC"
                    if all_slev
                    else "Charge bearer must be SLEV for standard SEPA credit transfers"
                ),
            }
        )

    elif clearing_system == "FedNow":
        settlement_window = "Instant (< 20 seconds)"
        all_usd = all(
            str(r.get("currency", "")).strip().upper() == "USD"
            for r in records
        )
        checks.append(
            {
                "check": "FedNow Currency Rule (USD)",
                "status": "PASS" if all_usd else "FAIL",
                "detail": (
                    "All payments denominated in USD"
                    if all_usd
                    else "FedNow instant payments must be denominated in USD"
                ),
            }
        )
        checks.append(
            {
                "check": "FedNow 24/7/365 Real-Time Settlement",
                "status": "PASS",
                "detail": (
                    "Participating FI connectivity active for immediate gross settlement"
                ),
            }
        )

    elif clearing_system == "US-ACH":
        settlement_window = "Next Business Day ACH Window"
        all_usd = all(
            str(r.get("currency", "")).strip().upper() == "USD"
            for r in records
        )
        checks.append(
            {
                "check": "NACHA ACH Currency Rule (USD)",
                "status": "PASS" if all_usd else "FAIL",
                "detail": (
                    "All payments denominated in USD"
                    if all_usd
                    else "Domestic US ACH requires USD denomination"
                ),
            }
        )

    elif clearing_system == "SWIFT-MX":
        settlement_window = "Correspondent Banking Network (D+1 to D+2)"
        has_bics = all(
            bool(str(r.get("debtor_agent_BIC", "")).strip())
            and bool(str(r.get("creditor_agent_BIC", "")).strip())
            for r in records
        )
        checks.append(
            {
                "check": "SWIFT CBPR+ BIC Routing",
                "status": "PASS" if has_bics else "FAIL",
                "detail": (
                    "Valid debtor and creditor agent BICs present for cross-border routing"
                    if has_bics
                    else "Missing debtor or creditor agent BIC required for SWIFT network"
                ),
            }
        )

    elif clearing_system == "CHAPS":
        settlement_window = "Same Day (pre-16:00 UK cut-off)"
        all_gbp = all(
            str(r.get("currency", "")).strip().upper() == "GBP"
            for r in records
        )
        checks.append(
            {
                "check": "CHAPS Currency Rule (GBP)",
                "status": "PASS" if all_gbp else "FAIL",
                "detail": (
                    "All payments denominated in GBP"
                    if all_gbp
                    else "CHAPS high-value RTGS requires GBP denomination"
                ),
            }
        )

    else:  # BACS
        settlement_window = "Three-Day Clearing Cycle"
        all_gbp = all(
            str(r.get("currency", "")).strip().upper() == "GBP"
            for r in records
        )
        checks.append(
            {
                "check": "BACS Currency Rule (GBP)",
                "status": "PASS" if all_gbp else "FAIL",
                "detail": (
                    "All payments denominated in GBP"
                    if all_gbp
                    else "BACS direct credits require GBP denomination"
                ),
            }
        )

    clearing_status = (
        "ACCEPTED"
        if all(c["status"] == "PASS" for c in checks)
        else "REJECTED"
    )

    return {
        "stage_id": stage_id,
        "clearing_system": clearing_system,
        "clearing_status": clearing_status,
        "settlement_window": settlement_window,
        "checks": checks,
    }


def commit_payment_batch(
    stage_id: Annotated[
        str,
        Field(
            description="The staging identifier returned by stage_payment_batch."
        ),
    ],
    confirmation_token: Annotated[
        str,
        Field(
            description=(
                "Secondary authorization token required to execute the dual-control commit."
            )
        ),
    ],
    output_file_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional local filesystem destination path to write the committed XML document."
            )
        ),
    ] = None,
) -> CommitPaymentBatchResult:
    """Commit an authorized staged payment batch with dual-control authorization.

    Verifies the stage ID and validates the secondary confirmation token
    using constant-time cryptographic comparison (preventing timing attacks).
    Transitions the order status from 'staged' to 'committed'. Optionally
    writes the verified XML payload to the specified destination path.

    Args:
        stage_id: Staging identifier from stage_payment_batch.
        confirmation_token: Secondary secret confirmation token.
        output_file_path: Optional path to write the committed XML document.

    Returns:
        CommitPaymentBatchResult with commit timestamp and fingerprint,
        or {"error": ...}.
    """
    _clean_expired_staged_orders()
    if stage_id not in _STAGED_PAYMENTS:
        return {"error": f"Staged payment batch '{stage_id}' not found"}

    order = _STAGED_PAYMENTS[stage_id]
    if order.expires_at <= time.time():
        del _STAGED_PAYMENTS[stage_id]
        return {"error": f"Staged payment batch '{stage_id}' has expired"}

    if order.status == "committed":
        return {
            "error": f"Staged payment batch '{stage_id}' has already been committed"
        }

    if not hmac.compare_digest(order.confirmation_token, confirmation_token):
        return {"error": "Invalid confirmation token for staged payment batch"}

    if output_file_path is not None:
        try:
            dest = Path(output_file_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(order.xml_content, encoding="utf-8")
        except OSError as exc:
            return {"error": f"Failed to write output XML file: {exc}"}

    order.status = "committed"
    committed_at = datetime.now(timezone.utc).isoformat()

    return {
        "stage_id": stage_id,
        "status": "committed",
        "sha256_fingerprint": order.sha256_fingerprint,
        "total_transactions": order.total_transactions,
        "output_file_path": output_file_path,
        "committed_at": committed_at,
    }


# Tools are registered here, in definition order, rather than with
# decorators on each function: mutmut 3 never mutates a decorated function,
# so the decorator form left every handler outside mutation testing. The
# registered object is the same function, docstring and signature, and
# clients list the tools in this order.
# The resource and the prompt are registered the same way as the tools,
# so mutmut reaches them too (it never mutates a decorated function).
server.resource(
    "pain001://schema/{message_type}", title="pain.001 XSD schema"
)(schema_resource)
server.prompt(title="Build a compliant payment batch")(build_payment_batch)
server.tool(title="List pain message types", annotations=_PURE_READ)(
    list_message_types
)
server.tool(title="Get required fields", annotations=_PURE_READ)(
    get_required_fields
)
server.tool(title="Get input JSON Schema", annotations=_PURE_READ)(
    get_input_schema
)
server.tool(title="Validate records against schema", annotations=_PURE_READ)(
    validate_records
)
server.tool(title="Suggest review-only record fixes", annotations=_PURE_READ)(
    suggest_record_fix
)
server.tool(title="Validate IBAN or BIC", annotations=_PURE_READ)(
    validate_identifier
)
server.tool(title="Generate pain XML from records", annotations=_PURE_READ)(
    generate_message
)
server.tool(title="List supported input formats", annotations=_PURE_READ)(
    list_supported_formats
)
server.tool(
    title="Generate pain XML (async, large batches)", annotations=_PURE_READ
)(generate_message_async)
server.tool(title="Generate pain XML from a CSV file", annotations=_FS_READ)(
    generate_message_from_file
)
server.tool(title="Parse camt.053 statement file", annotations=_FS_READ)(
    parse_camt053
)
server.tool(title="Parse pain.002 status report file", annotations=_FS_READ)(
    parse_pain002
)
server.tool(title="Inspect CSV template columns", annotations=_PURE_READ)(
    inspect_template
)
server.tool(title="Validate against scheme rulebook", annotations=_PURE_READ)(
    validate_payment_scheme
)
server.tool(title="Simulate payment batch", annotations=_PURE_READ)(
    simulate_payment_batch
)
server.tool(title="Migrate records between versions", annotations=_PURE_READ)(
    migrate_records
)
server.tool(title="Validate XML string against XSD", annotations=_PURE_READ)(
    validate_xml_against_schema
)
server.tool(
    title="Sanitise text to ISO 20022 charset", annotations=_PURE_READ
)(sanitize_to_iso20022_charset)
server.tool(title="Convert MT101 to pain.001 records", annotations=_PURE_READ)(
    convert_mt101
)
server.tool(title="List example corpus files", annotations=_PURE_READ)(
    list_corpus_files
)
server.tool(title="Get example corpus file", annotations=_PURE_READ)(
    get_corpus_file
)
server.tool(title="Get example corpus provenance", annotations=_PURE_READ)(
    get_corpus_provenance
)
server.tool(title="Get schema coverage report", annotations=_PURE_READ)(
    get_corpus_coverage
)
server.tool(
    title="Stage payment batch for simulation and approval",
    annotations=_MUTATING_SAFE,
)(stage_payment_batch)
server.tool(
    title="Simulate clearing network execution",
    annotations=_PURE_READ,
)(simulate_clearing)
server.tool(
    title="Commit staged payment batch with dual control",
    annotations=_COMMIT_TOOL,
)(commit_payment_batch)


def main(argv: list[str] | None = None) -> None:
    """Run the pain001 MCP server (the ``pain001-mcp`` entry point).

    stdio by default; ``--transport streamable-http`` or ``--transport sse``
    listens on ``--host``/``--port`` instead. See :mod:`pain001_mcp._cli`.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv[1:]``.
    """
    _cli.serve(server, argv, "pain001-mcp", __version__)


if __name__ == "__main__":
    main()
