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

The server communicates over stdio (FastMCP's default transport).
"""

import csv
import io
import json
from pathlib import Path
from typing import Annotated

from jsonschema import Draft7Validator
from mcp.server.fastmcp import FastMCP
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
from pain001.xml.validate_via_xsd import validate_xml_string_via_xsd
from pain001_loader_mt101.loader import parse_mt101
from pydantic import Field

from pain001_mcp import __version__

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

server = FastMCP("pain001")
# FastMCP does not expose a version kwarg; without this override the
# MCP SDK's own version leaks into serverInfo.version, breaking
# manifest/runtime coherence checks (e.g. Glama scoring).
server._mcp_server.version = __version__

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
_PURE_READ = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_FS_READ = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
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


def _load_schema(message_type: str) -> dict:
    """Load the bundled JSON Schema for ``message_type`` (raises on miss)."""
    message_type = _check_message_type(message_type)
    path = _schema_path(message_type)
    if not path.is_file():  # pragma: no cover - all valid types ship a schema
        raise ValueError(f"No JSON Schema bundled for {message_type}")
    with path.open("r", encoding="utf-8") as fh:
        loaded: dict = json.load(fh)
        return loaded


@server.tool(title="List pain message types", annotations=_PURE_READ)
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


@server.tool(title="Get required fields", annotations=_PURE_READ)
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


@server.tool(title="Get input JSON Schema", annotations=_PURE_READ)
def get_input_schema(
    message_type: _MessageType,
) -> dict:
    """Return the full JSON Schema for a message type's flat input record.

    Use this to learn every field, its type, and its constraints before
    assembling records, or to drive a form/UI. For just the required-field
    names use ``get_required_fields``; to actually check records against
    this schema use ``validate_records``.

    Args:
        message_type: A supported ISO 20022 pain message type.
    """
    try:
        return _load_schema(message_type)
    except ValueError as exc:
        return {"error": str(exc)}


@server.tool(title="Validate records against schema", annotations=_PURE_READ)
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
) -> dict:
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
    errors: list[dict] = []
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


@server.tool(title="Validate IBAN or BIC", annotations=_PURE_READ)
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
) -> dict:
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
        payload: dict = {"kind": kind_norm, "value": value, "valid": bool(ok)}
        if not ok and err:
            payload["error"] = err
        return payload
    except ValueError as exc:
        return {"error": str(exc)}


@server.tool(title="Generate pain XML from records", annotations=_PURE_READ)
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


@server.tool(title="List supported input formats", annotations=_PURE_READ)
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


@server.tool(
    title="Generate pain XML (async, large batches)", annotations=_PURE_READ
)
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


@server.tool(title="Generate pain XML from a CSV file", annotations=_FS_READ)
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


@server.tool(title="Parse camt.053 statement file", annotations=_FS_READ)
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
) -> dict:
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
        return parse_camt053_statement(xml_file_path, xsd_file_path)
    except Exception as exc:  # noqa: BLE001 - pain001 raises several types
        return {"error": str(exc)}


@server.tool(title="Parse pain.002 status report file", annotations=_FS_READ)
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
) -> dict:
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
        return parse_pain002_report(xml_file_path, xsd_file_path)
    except Exception as exc:  # noqa: BLE001 - pain001 raises several types
        return {"error": str(exc)}


@server.tool(title="Inspect CSV template columns", annotations=_PURE_READ)
def inspect_template(
    message_type: _MessageType,
) -> dict:
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


@server.tool(title="Validate against scheme rulebook", annotations=_PURE_READ)
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
) -> dict:
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
        "violations": [v.as_dict() for v in result.violations],
    }


@server.resource(
    "pain001://schema/{message_type}", title="pain.001 XSD schema"
)
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


@server.prompt(title="Build a compliant payment batch")
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


@server.tool(title="Migrate records between versions", annotations=_PURE_READ)
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
) -> dict:
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


@server.tool(title="Validate XML string against XSD", annotations=_PURE_READ)
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
) -> dict:
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


@server.tool(
    title="Sanitise text to ISO 20022 charset", annotations=_PURE_READ
)
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
) -> dict:
    """Sanitise one free-text field to the ISO 20022 Latin character set.

    Use this on a single free-text value (name, remittance info) to
    transliterate accents and drop unsupported symbols before placing it in
    a record, and to see whether the value changed. Operates on one string;
    to check a whole batch's rulebook compliance use ``validate_payment_scheme``.

    Wraps :func:`pain001.sanitize_to_charset`. Transliterates accents
    (``é`` -> ``e``), removes unsupported symbols, and returns both
    the cleaned string and a flag for whether the original was
    already valid - useful for surfacing the change to the user
    before writing it back to a record.

    Args:
        value: The text to sanitise.

    Returns:
        ``{"value": str, "sanitised": str, "was_valid": bool, "changed": bool}``.
    """
    cleaned = sanitize_to_charset(value)
    return {
        "value": value,
        "sanitised": cleaned,
        "was_valid": cleaned == value,
        "changed": cleaned != value,
    }


@server.tool(title="Convert MT101 to pain.001 records", annotations=_PURE_READ)
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


def main() -> None:
    """Run the pain001 MCP server over stdio (the ``pain001-mcp`` entry point)."""
    server.run()


if __name__ == "__main__":
    main()
