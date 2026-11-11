# SPDX-FileCopyrightText: 2023-2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Generation tools: pain XML from records in memory or from a CSV file.

Every result is XSD-validated by the core before it is returned; no tool
here writes a file. ``validate_xml_against_schema`` runs the same XSD
check on an XML string the caller already holds.
"""

import json
from typing import Annotated

from pain001 import generate_xml_string
from pain001.async_adapter import generate_xml_string_async
from pain001.csv.load_csv_data import load_csv_data
from pain001.exceptions import Pain001Error
from pain001.xml.validate_via_xsd import validate_xml_string_via_xsd
from pydantic import Field

from pain001_mcp._common import (
    _RECORDS_FIELD_GUIDE,
    _check_message_type,
    _IdentifierChecks,
    _MessageType,
    _refuse_bad_identifiers,
    _template_bundle,
    _template_dir,
)
from pain001_mcp._shapes import XsdResult


def generate_message(
    message_type: _MessageType,
    records: Annotated[
        list[dict],
        Field(description=_RECORDS_FIELD_GUIDE),
    ],
    identifier_checks: _IdentifierChecks = True,
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
    once. Every IBAN (mod-97) and BIC (ISO 9362) is checked first, as the
    pain001 CLI checks it, unless ``identifier_checks`` is false; values
    are never coerced.

    Returns the validated XML document as a string, or a JSON-encoded
    ``{"error": ...}`` payload if generation fails.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records.
        identifier_checks: If false, skip the IBAN and BIC checks.
    """
    try:
        message_type = _check_message_type(message_type)
        if identifier_checks:
            _refuse_bad_identifiers(records)
        template_xml, xsd_schema = _template_bundle(message_type)
        return generate_xml_string(
            records, message_type, template_xml, xsd_schema
        )
    except (ValueError, RuntimeError, Pain001Error) as exc:
        return json.dumps({"error": str(exc)})


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
    identifier_checks: _IdentifierChecks = True,
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
        identifier_checks: If false, skip the IBAN and BIC checks.
    """
    try:
        message_type = _check_message_type(message_type)
        if identifier_checks:
            _refuse_bad_identifiers(records)
        template_xml, xsd_schema = _template_bundle(message_type)
        return await generate_xml_string_async(
            records, message_type, template_xml, xsd_schema
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
        xsd = _template_dir(message_type) / f"{message_type}.xsd"
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
