# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""The core's validation ladder, as every tool that validates or generates runs it.

pain001 0.0.87 has one ladder that its CLI, Python API and REST API
climb: the row contract and the identifier checks
(:func:`pain001.validation._one_batch.load_batch`, with the one-batch
check), then the message type's JSON Schema and any validator plugin,
then an optional scheme. ``validate_records``, the ``generate_message``
tools, ``simulate_payment_batch`` and ``stage_payment_batch`` all come
through here, so an agent gets the verdict the CLI and the REST API
give for the same rows, with the same ``P001-E...`` issue codes.

Before 0.0.87 the record tools ran their own JSON Schema check on the
raw values (refusing the CLI's own sample, whose values are text) and
the generators ran none (accepting ``currency=EURO``).
"""

import json
from typing import Any, TypedDict

from pain001 import canonicalize_payment_record, normalize_payment_records
from pain001 import validate as _core_validate
from pain001.exceptions import Pain001Error, PaymentValidationError, RowIssue

from pain001_mcp._shapes import RecordError, ValidateRecordsResult

__all__ = ["error_payload", "prepared", "verdict"]

# The header totals the generator computes from the rows; a record may
# leave them out (see _RECORDS_FIELD_GUIDE), so they are filled in.
_TOTALS = ("nb_of_txs", "ctrl_sum")


class Issue(TypedDict):
    """One ladder finding, without the value that caused it."""

    line: int | None
    column: str | None
    code: str
    message: str


def prepared(records: list[dict]) -> list[dict[str, Any]]:
    """Return the records with canonical keys and their header totals.

    The ergonomics the record tools have always documented: alias keys
    (``amount``, ``payment_currency``, lower-case IBAN and BIC spellings)
    become the canonical names, and an absent or empty ``nb_of_txs`` or
    ``ctrl_sum`` is filled with the value the generator computes from
    the rows (it overwrites whatever is given). Values are not changed,
    so the ladder judges them as given. When an amount is unusable the
    totals are left out and the ladder names the amount instead.

    Args:
        records: The caller's records; not mutated.

    Returns:
        New records, one per input record.
    """
    rows = [canonicalize_payment_record(record) for record in records]
    try:
        computed = normalize_payment_records(rows)
    except PaymentValidationError:
        return rows
    for row, totals in zip(rows, computed, strict=True):
        for key in _TOTALS:
            if row.get(key) in (None, ""):
                row[key] = totals[key]
    return rows


def _issue(issue: RowIssue) -> Issue:
    """Return one finding as JSON-ready data."""
    return {
        "line": issue.line,
        "column": issue.column,
        "code": issue.code,
        "message": issue.message,
    }


def _record_error(issue: RowIssue, line: int) -> RecordError:
    """Return one finding as a row error; records are counted from 1."""
    return {
        "row": line - 1,
        "line": line,
        "path": issue.column or "",
        "code": issue.code,
        "message": issue.message,
    }


def verdict(
    message_type: str, records: list[dict], identifier_checks: bool
) -> ValidateRecordsResult:
    """Run :func:`pain001.validate` on records and report it per row.

    Args:
        message_type: A resolved message type.
        records: The caller's records.
        identifier_checks: If false, skip the IBAN, BIC and LEI checks.

    Returns:
        ``valid``, ``total``, ``valid_count`` and one row error per
        finding; ``{"error": ...}`` when the input is refused with no
        row to name (rows that do not form one batch, no rows at all).
    """
    try:
        report = _core_validate(
            prepared(records),
            message_type,
            identifier_checks=identifier_checks,
        )
    except (ValueError, Pain001Error) as exc:
        return {"error": str(exc)}
    errors = [
        _record_error(issue, issue.line)
        for issue in report.issues
        if issue.line is not None
    ]
    if not report.is_valid and not errors:
        return {"error": "\n".join(report.errors)}
    return {
        "valid": report.is_valid,
        "total": len(records),
        "valid_count": report.valid_rows,
        "errors": errors,
    }


def error_payload(exc: Exception) -> str:
    """Return a generator's failure as ``{"error", "issues"?}`` JSON.

    ``issues`` is present when the ladder refused the rows: one entry
    per finding, with its line, column and ``P001-E...`` code.
    """
    body: dict[str, Any] = {"error": str(exc)}
    if isinstance(exc, PaymentValidationError) and exc.errors:
        body["issues"] = [_issue(issue) for issue in exc.errors]
    return json.dumps(body)
