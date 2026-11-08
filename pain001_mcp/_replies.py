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

"""Bank-reply tools: camt.053 statements and pain.002 status reports.

Both read a file the caller names, through the core parsers and their
path guards, and return the parsed content or an ``{"error": ...}``
payload.
"""

from typing import Annotated, cast

from pain001 import parse_camt053_statement, parse_pain002_report
from pydantic import Field

from pain001_mcp._shapes import Camt053Result, Pain002Result


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
        The first statement's header and entries, every statement under
        ``statements``, or an ``{"error": ...}`` payload on failure.
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
