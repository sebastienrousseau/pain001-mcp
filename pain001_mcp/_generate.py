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

"""Generation tools: pain XML from records in memory or from a CSV file.

Every result is XSD-validated by the core before it is returned; no tool
here writes a file.
"""

import json
from typing import Annotated

from pain001 import generate_xml_string
from pain001.async_adapter import generate_xml_string_async
from pain001.csv.load_csv_data import load_csv_data
from pain001.exceptions import Pain001Error
from pydantic import Field

from pain001_mcp._common import (
    _RECORDS_FIELD_GUIDE,
    _check_message_type,
    _MessageType,
    _template_bundle,
)


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
