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

"""Discovery tools: message types, fields, schemas, templates, formats.

Also the ``pain001://schema/{message_type}`` resource and the
``build_payment_batch`` prompt, which point an agent at these tools.
"""

import csv
import io
from typing import cast

from pain001.constants import valid_xml_types

from pain001_mcp._common import (
    _check_message_type,
    _load_schema,
    _MessageType,
    _template_dir,
)
from pain001_mcp._shapes import SchemaResult, TemplateResult

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
    "pain.001.001.13": "Customer Credit Transfer Initiation V13",
    "pain.008.001.02": "Customer Direct Debit Initiation V02",
    "pain.008.001.08": "Customer Direct Debit Initiation V08",
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


def get_required_fields(message_type: _MessageType) -> list[str]:
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


def get_input_schema(message_type: _MessageType) -> SchemaResult:
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


def inspect_template(message_type: _MessageType) -> TemplateResult:
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
        sample = _template_dir(message_type) / "template.csv"
        if not sample.is_file():
            raise ValueError(f"No bundled CSV template for {message_type}")
        reader = csv.reader(io.StringIO(sample.read_text(encoding="utf-8")))
        columns = next(reader, [])
        return {"message_type": message_type, "columns": list(columns)}
    except ValueError as exc:
        return {"error": str(exc)}


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


def schema_resource(message_type: _MessageType) -> str:
    """Expose the official XSD schema text for a message type as a resource.

    MCP clients can subscribe to or fetch ``pain001://schema/{type}`` to
    pull the canonical XSD without having to install pain001 themselves.

    Args:
        message_type: A supported ISO 20022 pain message type.

    Returns:
        The XSD schema text. Raises ``ValueError`` for an unsupported type.
    """
    message_type = _check_message_type(message_type)
    xsd = _template_dir(message_type) / f"{message_type}.xsd"
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
