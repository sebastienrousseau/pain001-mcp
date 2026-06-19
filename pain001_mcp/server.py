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

from jsonschema import Draft7Validator
from mcp.server.fastmcp import FastMCP
from pain001 import (
    generate_xml_string,
    parse_camt053_statement,
    parse_pain002_report,
    sanitize_to_charset,
    validate_scheme,
)
from pain001.async_adapter import generate_xml_string_async
from pain001.constants import SCHEMAS_DIR, TEMPLATES_DIR, valid_xml_types
from pain001.csv.load_csv_data import load_csv_data
from pain001.migration import VersionMapper
from pain001.validation import validate_bic, validate_iban
from pain001.xml.validate_via_xsd import validate_xml_string_via_xsd

server = FastMCP("pain001")

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


def _check_message_type(message_type: str) -> None:
    """Raise ``ValueError`` unless ``message_type`` is bundled with pain001."""
    if message_type not in valid_xml_types:
        raise ValueError(f"Invalid XML message type: {message_type}")


def _schema_path(message_type: str) -> Path:
    """Return the on-disk path of the bundled JSON Schema for ``message_type``."""
    return Path(SCHEMAS_DIR) / f"{message_type}.schema.json"


def _load_schema(message_type: str) -> dict:
    """Load the bundled JSON Schema for ``message_type`` (raises on miss)."""
    _check_message_type(message_type)
    path = _schema_path(message_type)
    if not path.is_file():  # pragma: no cover - all valid types ship a schema
        raise ValueError(f"No JSON Schema bundled for {message_type}")
    with path.open("r", encoding="utf-8") as fh:
        loaded: dict = json.load(fh)
        return loaded


@server.tool()
def list_message_types() -> list[dict]:
    """List every supported ISO 20022 pain message type.

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


@server.tool()
def get_required_fields(message_type: str) -> list[str]:
    """List the required input field names for a given pain message type.

    Args:
        message_type: A supported ISO 20022 pain message type.
    """
    try:
        schema = _load_schema(message_type)
        required = schema.get("required", [])
        return list(required)
    except ValueError as exc:
        return [f"error: {exc}"]


@server.tool()
def get_input_schema(message_type: str) -> dict:
    """Return the JSON Schema describing the flat input record for a type.

    Args:
        message_type: A supported ISO 20022 pain message type.
    """
    try:
        return _load_schema(message_type)
    except ValueError as exc:
        return {"error": str(exc)}


@server.tool()
def validate_records(message_type: str, records: list[dict]) -> dict:
    """Validate flat records against a message type's input JSON Schema.

    Returns a report ``{"valid": bool, "total": int, "valid_count": int,
    "errors": [...]}``.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records to validate.
    """
    try:
        schema = _load_schema(message_type)
    except (
        ValueError
    ) as exc:  # pragma: no cover - all valid types ship a schema
        return {"error": str(exc)}

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


@server.tool()
def validate_identifier(kind: str, value: str) -> dict:
    """Validate a financial identifier (IBAN or BIC).

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


@server.tool()
def generate_message(message_type: str, records: list[dict]) -> str:
    """Generate a validated ISO 20022 pain XML message from flat records.

    Returns the validated XML document as a string, or a JSON-encoded
    ``{"error": ...}`` payload if generation fails.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records.
    """
    try:
        _check_message_type(message_type)
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
    except ValueError as exc:
        return json.dumps({"error": str(exc)})


@server.tool()
def list_supported_formats() -> list[dict]:
    """List the input data formats the pain001 library can load.

    Returns a list of ``{"id", "name", "extension"}`` dictionaries
    covering CSV, SQLite, JSON, JSONL, and Parquet (the last requires the
    ``pain001[parquet]`` extra).
    """
    return [dict(fmt) for fmt in _SUPPORTED_FORMATS]


@server.tool()
async def generate_message_async(
    message_type: str, records: list[dict]
) -> str:
    """Async variant of :func:`generate_message` for long batches.

    Delegates to :func:`pain001.async_adapter.generate_xml_string_async`,
    which runs the synchronous renderer in a worker thread so an agent
    can interleave long XML generations with other tool calls. Returns
    the validated XML, or a JSON-encoded ``{"error": ...}`` payload.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records.
    """
    try:
        _check_message_type(message_type)
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
    except ValueError as exc:
        return json.dumps({"error": str(exc)})


@server.tool()
def generate_message_from_file(message_type: str, data_file_path: str) -> str:
    """Generate a validated pain XML message from a CSV file on disk.

    Loads ``data_file_path`` via :func:`pain001.csv.load_csv_data.load_csv_data`
    so the same path-safety guards apply as in the core library, then
    delegates to :func:`generate_message`. JSON / JSONL / SQLite /
    Parquet inputs are planned for a follow-up release.

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


@server.tool()
def parse_camt053(
    xml_file_path: str, xsd_file_path: str | None = None
) -> dict:
    """Parse a camt.053 bank statement XML file into structured data.

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


@server.tool()
def parse_pain002(
    xml_file_path: str, xsd_file_path: str | None = None
) -> dict:
    """Parse a pain.002 payment-status report XML file into structured data.

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


@server.tool()
def inspect_template(message_type: str) -> dict:
    """Return the payment-row columns the message type's bundled CSV expects.

    Mirrors the in-tree ``pain001.mcp.server.inspect_template`` tool so an
    agent can introspect the column layout before assembling rows.

    Args:
        message_type: A supported ISO 20022 pain message type.

    Returns:
        ``{"message_type": str, "columns": list[str]}`` or
        ``{"error": ...}`` if the type is unsupported or no template ships.
    """
    try:
        _check_message_type(message_type)
        sample = Path(TEMPLATES_DIR) / message_type / "template.csv"
        if not sample.is_file():
            raise ValueError(f"No bundled CSV template for {message_type}")
        reader = csv.reader(io.StringIO(sample.read_text(encoding="utf-8")))
        columns = next(reader, [])
        return {"message_type": message_type, "columns": list(columns)}
    except ValueError as exc:
        return {"error": str(exc)}


@server.tool()
def validate_payment_scheme(
    records: list[dict], profile: str = "sepa-sct"
) -> dict:
    """Validate records against a payment-scheme rulebook (e.g. SEPA).

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


@server.resource("pain001://schema/{message_type}")
def schema_resource(message_type: str) -> str:
    """Expose the official XSD schema text for a message type as a resource.

    MCP clients can subscribe to or fetch ``pain001://schema/{type}`` to
    pull the canonical XSD without having to install pain001 themselves.

    Args:
        message_type: A supported ISO 20022 pain message type.

    Returns:
        The XSD schema text. Raises ``ValueError`` for an unsupported type.
    """
    _check_message_type(message_type)
    xsd = Path(TEMPLATES_DIR) / message_type / f"{message_type}.xsd"
    return xsd.read_text(encoding="utf-8")


@server.prompt()
def build_payment_batch(
    message_type: str = "pain.001.001.09",
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


@server.tool()
def migrate_records(
    records: list[dict],
    from_version: str,
    to_version: str,
) -> dict:
    """Migrate flat payment records between pain.001 schema versions.

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
        migrated = mapper.migrate_rows(
            records, from_version, to_version
        )
        return {
            "records": migrated,
            "migrated": len(migrated),
            "from": from_version,
            "to": to_version,
        }
    except Exception as exc:  # noqa: BLE001 - DataSourceError + others
        return {"error": str(exc)}


@server.tool()
def validate_xml_against_schema(
    xml_content: str, message_type: str
) -> dict:
    """Validate a raw pain.001 / pain.008 XML string against its XSD.

    Wraps :func:`pain001.xml.validate_via_xsd.validate_xml_string_via_xsd`
    so an agent can verify an XML payload it received from another
    system without writing it to disk.

    Args:
        xml_content: The XML document as a string.
        message_type: A supported ISO 20022 pain message type.

    Returns:
        ``{"valid": bool, "message_type": str, "error": str?}`` -
        ``error`` is present only when ``valid`` is ``False``.
    """
    try:
        _check_message_type(message_type)
        xsd = Path(TEMPLATES_DIR) / message_type / f"{message_type}.xsd"
        if not xsd.is_file():  # pragma: no cover - all valid types ship XSD
            return {"error": f"No XSD bundled for {message_type}"}
        try:
            ok = validate_xml_string_via_xsd(xml_content, str(xsd))
        except Exception as exc:  # pragma: no cover - underlying API returns False, not raises
            return {
                "valid": False,
                "message_type": message_type,
                "error": str(exc),
            }
        return {"valid": bool(ok), "message_type": message_type}
    except ValueError as exc:
        return {"error": str(exc)}


@server.tool()
def sanitize_to_iso20022_charset(value: str) -> dict:
    """Sanitise a free-text field to the ISO 20022 Latin character set.

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


def main() -> None:
    """Run the pain001 MCP server over stdio (the ``pain001-mcp`` entry point)."""
    server.run()


if __name__ == "__main__":
    main()
