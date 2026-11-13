# SPDX-FileCopyrightText: 2023-2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Generation tools: pain XML from records in memory or from a data file.

The rows climb the core's validation ladder first, as ``pain001
generate`` and the REST API's generate route make them, so nothing is
generated that those refuse; the XML is then XSD-validated by the core
before it is returned. No tool here writes a file.
``validate_xml_against_schema`` runs the same XSD check on an XML string
the caller already holds.
"""

import asyncio
from typing import Annotated, Any

from pain001 import generate_xml_string
from pain001.async_adapter import generate_xml_string_async
from pain001.exceptions import Pain001Error
from pain001.validation.ladder import load_valid
from pain001.xml.validate_via_xsd import validate_xml_string_via_xsd
from pydantic import Field

from pain001_mcp._common import (
    _RECORDS_FIELD_GUIDE,
    _check_message_type,
    _IdentifierChecks,
    _MessageType,
    _template_bundle,
    _template_dir,
)
from pain001_mcp._ladder import error_payload, prepared
from pain001_mcp._shapes import XsdResult


def _admit(
    message_type: str, source: str | list[dict[str, Any]], checks: bool
) -> tuple[str, str, str, list[dict[str, Any]]]:
    """Resolve the type and return its bundle and the admitted rows.

    Args:
        message_type: The type as the caller gave it (aliases allowed).
        source: A data file path, or records already ``prepared``.
        checks: If false, skip the IBAN, BIC and LEI checks.

    Returns:
        ``(message type, template path, XSD path, rows)``.

    A ``ValueError`` for an unknown type and the ladder's
    ``PaymentValidationError`` propagate.
    """
    message_type = _check_message_type(message_type)
    template_xml, xsd_schema = _template_bundle(message_type)
    rows = load_valid(source, message_type, checks)
    return message_type, template_xml, xsd_schema, rows


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
    once. The records are validated first exactly as ``validate_records``
    and the pain001 CLI validate them (row contract, every IBAN and BIC
    unless ``identifier_checks`` is false, one payment information
    block, the JSON Schema); values are never coerced.

    Returns the validated XML document as a string, or a JSON-encoded
    ``{"error": ..., "issues": [...]}`` payload if generation fails;
    ``issues`` (present when the validation refused the rows) lists each
    finding's ``line``, ``column``, ``P001-E...`` ``code`` and
    ``message``.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records.
        identifier_checks: If false, skip the IBAN and BIC checks.
    """
    try:
        message_type, template_xml, xsd_schema, rows = _admit(
            message_type, prepared(records), identifier_checks
        )
        return generate_xml_string(
            rows, message_type, template_xml, xsd_schema
        )
    except (ValueError, RuntimeError, Pain001Error) as exc:
        return error_payload(exc)


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

    Validates in a worker thread, then delegates to
    :func:`pain001.async_adapter.generate_xml_string_async`. Returns the
    validated XML, or the same JSON-encoded ``{"error", "issues"?}``
    payload as ``generate_message``.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records.
        identifier_checks: If false, skip the IBAN and BIC checks.
    """
    try:
        message_type, template_xml, xsd_schema, rows = await asyncio.to_thread(
            _admit, message_type, prepared(records), identifier_checks
        )
        return await generate_xml_string_async(
            rows, message_type, template_xml, xsd_schema
        )
    except (ValueError, RuntimeError, Pain001Error) as exc:
        return error_payload(exc)


def generate_message_from_file(
    message_type: _MessageType,
    data_file_path: Annotated[
        str,
        Field(
            description=(
                "Local filesystem path, below the server's working "
                "directory, to a payment data file: CSV (one record per "
                "row, a header matching the template columns, see "
                "inspect_template), SQLite, JSON, JSONL or Parquet (see "
                "list_supported_formats)."
            )
        ),
    ],
) -> str:
    """Generate validated pain XML from a payment data file on the local disk.

    Use this when the records live in a file rather than in memory; if
    you already have them as dicts, call ``generate_message``. The file
    is read and validated by the core's own loader and validation
    ladder, exactly as ``pain001 generate`` reads it, so the same
    path-safety guards apply and the same files are refused; an issue's
    ``line`` is the file's line (a CSV header is line 1).

    Args:
        message_type: A supported ISO 20022 pain message type.
        data_file_path: Path to the payment data file.

    Returns:
        The validated XML, or a JSON-encoded ``{"error", "issues"?}``
        payload as ``generate_message`` returns it.
    """
    try:
        message_type, template_xml, xsd_schema, rows = _admit(
            message_type, data_file_path, True
        )
        return generate_xml_string(
            rows, message_type, template_xml, xsd_schema
        )
    except Exception as exc:  # noqa: BLE001 - many concrete types possible
        return error_payload(exc)


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
