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

"""Scheme tools: rulebook validation and the batch pre-flight simulation."""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, cast

from pain001 import canonicalize_payment_record, validate_scheme
from pydantic import Field

from pain001_mcp._common import (
    _RECORDS_FIELD_GUIDE,
    _MessageType,
    _OptionalSchemeProfile,
    _SchemeProfile,
)
from pain001_mcp._records import validate_records
from pain001_mcp._shapes import (
    DuplicateTransaction,
    SchemeResult,
    SchemeViolation,
    SimulatePaymentBatchResult,
)

_SchemeRecords = Annotated[
    list[dict],
    Field(
        description=(
            "Payment records as a list of flat dicts (field name → "
            "value) to check against the scheme rulebook."
        )
    ),
]
_SimulatedRecords = Annotated[
    list[dict],
    Field(
        description=(
            "One or more flat payment records to simulate and pre-flight "
            "before generating XML. " + _RECORDS_FIELD_GUIDE
        )
    ),
]

#: Debtor, creditor, amount, currency and execution date of one payment.
_TxKey = tuple[str, str, str, str, str]


def validate_payment_scheme(
    records: _SchemeRecords,
    profile: _SchemeProfile = "sepa-sct",
) -> SchemeResult:
    """Validate records against a payment-scheme rulebook (e.g. SEPA).

    Use this after ``validate_records`` to enforce scheme-specific business
    rules (SEPA field lengths, allowed characters, currency/BIC constraints)
    that JSON-Schema validation alone does not cover. ``validate_records``
    checks structural shape; this checks rulebook compliance for one profile.

    Delegates to :func:`pain001.validate_scheme`. The ``profile``
    parameter lists every profile the installed pain001 ships.

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


def _upper(record: dict[str, Any], key: str) -> str:
    """Return ``record[key]`` as stripped upper-case text (``""`` if absent)."""
    return str(record.get(key, "")).strip().upper()


def _control_sums(sums: dict[str, Decimal]) -> dict[str, str]:
    """Return the per-currency totals as two-decimal strings, by currency."""
    return {curr: f"{total:.2f}" for curr, total in sorted(sums.items())}


def _tally(raw: Any, curr: str, sums: dict[str, Decimal]) -> str:
    """Add one amount to its currency total and return its key text.

    Args:
        raw: The record's ``payment_amount``, as given.
        curr: The record's currency; an empty one is not totalled.
        sums: Running totals by currency, updated in place.

    Returns:
        The amount to two decimals, the raw text when it is not a
        number, or ``""`` when there is no amount.
    """
    if raw is None:
        return ""
    try:
        amount = Decimal(str(raw))
        text = f"{amount:.2f}"
        if curr:
            sums[curr] = sums.get(curr, Decimal(0)) + amount
    except (InvalidOperation, TypeError):
        return str(raw).strip()
    return text


def _duplicate(row: int, key: _TxKey, first: int) -> DuplicateTransaction:
    """Return the report of row ``row`` repeating row ``first``."""
    debtor, creditor, amount, curr, date_val = key
    return {
        "row": row,
        "matching_row": first,
        "debtor_account_IBAN": debtor,
        "creditor_account_IBAN": creditor,
        "amount": amount,
        "currency": curr,
        "requested_execution_date": date_val,
    }


def _parties(records: list[dict[str, Any]], key: str) -> set[str]:
    """Return the distinct non-empty account IBANs under ``key``."""
    return {_upper(record, key) for record in records} - {""}


def _scan_batch(
    records: list[dict[str, Any]],
) -> tuple[dict[str, Decimal], list[DuplicateTransaction]]:
    """Total the amounts and find duplicates across canonical records.

    Returns:
        Totals by currency, and every row that repeats an earlier one's
        debtor, creditor, amount, currency and execution date.
    """
    sums: dict[str, Decimal] = {}
    duplicates: list[DuplicateTransaction] = []
    seen: dict[_TxKey, int] = {}
    for row, record in enumerate(records):
        debtor = _upper(record, "debtor_account_IBAN")
        creditor = _upper(record, "creditor_account_IBAN")
        curr = _upper(record, "currency")
        date_val = str(record.get("requested_execution_date", "")).strip()
        amount = _tally(record.get("payment_amount"), curr, sums)
        if not (debtor and creditor and amount and curr):
            continue
        key = (debtor, creditor, amount, curr, date_val)
        if key in seen:
            duplicates.append(_duplicate(row, key, seen[key]))
        else:
            seen[key] = row
    return sums, duplicates


def simulate_payment_batch(
    message_type: _MessageType,
    records: _SimulatedRecords,
    scheme: _OptionalSchemeProfile = None,
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
    report = validate_records(message_type, records)
    if "error" in report:
        return {"error": report["error"]}
    canonical = [canonicalize_payment_record(r) for r in records]
    sums, duplicates = _scan_batch(canonical)
    scheme_violations: list[SchemeViolation] = []
    scheme_valid = True
    if scheme is not None:
        scheme_res = validate_payment_scheme(records, profile=scheme)
        if "error" in scheme_res:
            return {"error": scheme_res["error"]}
        scheme_violations = scheme_res.get("violations", [])
        scheme_valid = scheme_res.get("is_valid", True)
    valid = report.get("valid", False) and scheme_valid and not duplicates
    return {
        "valid": bool(valid),
        "total": report.get("total", len(records)),
        "valid_count": report.get("valid_count", 0),
        "control_sum_by_currency": _control_sums(sums),
        "unique_debtors": len(_parties(canonical, "debtor_account_IBAN")),
        "unique_creditors": len(_parties(canonical, "creditor_account_IBAN")),
        "duplicates": duplicates,
        "schema_errors": report.get("errors", []),
        "scheme_violations": scheme_violations,
    }
