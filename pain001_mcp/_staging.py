# SPDX-FileCopyrightText: 2023-2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Staging tools: stage a batch, then commit it with its token.

A staged batch lives in memory for an hour with zero fund movement.
``simulate_clearing`` (in :mod:`pain001_mcp._clearing`) reads it, and
``commit_payment_batch`` marks it committed and may write its XML inside
the output directory (:mod:`pain001_mcp._output`). The confirmation token
guards against an accidental commit only.
"""

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from pain001 import canonicalize_payment_record
from pydantic import Field

from pain001_mcp._common import (
    _MESSAGE_TYPE_ALIASES,
    _RECORDS_FIELD_GUIDE,
    _MessageType,
    _OptionalSchemeProfile,
)
from pain001_mcp._generate import generate_message
from pain001_mcp._output import save_committed
from pain001_mcp._records import validate_records
from pain001_mcp._schemes import _control_sums, _upper, validate_payment_scheme
from pain001_mcp._shapes import CommitPaymentBatchResult, StagedBatchResult


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

#: Fee per transaction by currency; any other currency pays the fallback.
_FEE_RATES: dict[str, Decimal] = {
    "EUR": Decimal("0.20"),
    "USD": Decimal("0.25"),
    "GBP": Decimal("0.15"),
}
_FALLBACK_FEE_RATE = Decimal("0.50")
_GENERIC_REMITTANCE = {"payment", "invoice", "transfer"}

_StagedRecords = Annotated[
    list[dict],
    Field(
        description=(
            "Flat payment records to stage (zero fund movement). "
            + _RECORDS_FIELD_GUIDE
        )
    ),
]
_StageId = Annotated[
    str,
    Field(
        description="The staging identifier returned by stage_payment_batch."
    ),
]
_ConfirmationToken = Annotated[
    str,
    Field(
        description=(
            "The confirmation token stage_payment_batch returned for this batch."
        )
    ),
]
_OutputFilePath = Annotated[
    str | None,
    Field(
        description=(
            "Optional new .xml file inside the output directory (PAIN001_MCP_OUTPUT_DIR, else the working directory)."
        )
    ),
]


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


def _open_order(stage_id: str) -> tuple[_StagedOrder | None, str]:
    """Return the live, uncommitted order for ``stage_id``, or why not.

    An expired order is dropped from the store on the way.
    """
    _clean_expired_staged_orders()
    if stage_id not in _STAGED_PAYMENTS:
        return None, f"Staged payment batch '{stage_id}' not found"
    order = _STAGED_PAYMENTS[stage_id]
    if order.expires_at <= time.time():
        del _STAGED_PAYMENTS[stage_id]
        return None, f"Staged payment batch '{stage_id}' has expired"
    if order.status == "committed":
        return (
            None,
            f"Staged payment batch '{stage_id}' has already been committed",
        )
    return order, ""


def _admit(
    message_type: str, records: list[dict], scheme: str | None
) -> tuple[list[dict[str, Any]], str]:
    """Return the canonical records, or why the batch cannot be staged."""
    report = validate_records(message_type, records)
    if "error" in report:
        return [], report["error"]
    if not report.get("valid", False):
        err_count = len(report.get("errors", []))
        return [], f"Batch failed schema validation with {err_count} errors"
    canonical = [canonicalize_payment_record(r) for r in records]
    if scheme is None:
        return canonical, ""
    scheme_res = validate_payment_scheme(canonical, profile=scheme)
    if "error" in scheme_res:
        return [], scheme_res["error"]
    if not scheme_res.get("is_valid", True):
        v_count = len(scheme_res.get("violations", []))
        return (
            [],
            f"Batch failed scheme '{scheme}' validation with {v_count} violations",
        )
    return canonical, ""


def _scan(
    records: list[dict[str, Any]],
) -> tuple[dict[str, Decimal], int, int, int]:
    """Total the batch and count the rows each risk factor looks at.

    Returns:
        Totals by currency (an empty currency counts as EUR), then the
        number of duplicate rows, of rows of 100,000.00 or more, and of
        rows with missing or generic remittance information.
    """
    sums: dict[str, Decimal] = {}
    seen: set[tuple[str, str, str, str, str]] = set()
    duplicates = high_value = generic = 0
    for record in records:
        curr = _upper(record, "currency") or "EUR"
        raw = record.get("payment_amount")
        amount = Decimal(str(raw)) if raw is not None else Decimal("0.00")
        sums[curr] = sums.get(curr, Decimal(0)) + amount
        high_value += amount >= Decimal("100000.00")
        rmt = str(record.get("remittance_information", "")).strip().lower()
        generic += not rmt or rmt in _GENERIC_REMITTANCE
        key = (
            _upper(record, "debtor_account_IBAN"),
            _upper(record, "creditor_account_IBAN"),
            f"{amount:.2f}",
            curr,
            str(record.get("requested_execution_date", "")).strip(),
        )
        duplicates += key in seen
        seen.add(key)
    return sums, duplicates, high_value, generic


def _risk_level(score: int) -> str:
    """Return ``LOW`` up to 25, ``MEDIUM`` up to 60, else ``HIGH``."""
    if score <= 25:
        return "LOW"
    return "MEDIUM" if score <= 60 else "HIGH"


def _risk(
    sums: dict[str, Decimal], duplicates: int, high_value: int, generic: int
) -> tuple[int, str, list[str]]:
    """Score the batch: the score (at most 100), its level and its reasons.

    Each factor adds its points once when present; the aggregate-volume
    factor names the first currency whose total reaches 500,000.00.
    """
    heavy = next(
        (c for c, total in sums.items() if total >= Decimal("500000.00")),
        None,
    )
    factors = [
        (
            35,
            duplicates,
            f"{duplicates} duplicate transactions detected in batch",
        ),
        (
            25,
            high_value,
            f"{high_value} transactions exceed 100,000.00 threshold",
        ),
        (20, heavy, f"Aggregate volume in {heavy} exceeds 500,000.00"),
        (
            15,
            generic,
            f"{generic} transactions have missing or generic remittance information",
        ),
    ]
    hits = [(points, why) for points, present, why in factors if present]
    score = min(sum(points for points, _ in hits), 100)
    return score, _risk_level(score), [why for _, why in hits]


def _estimated_fees(sums: dict[str, Decimal], total: int) -> dict[str, str]:
    """Return the estimated fee per currency for ``total`` transactions."""
    return {
        curr: f"{_FEE_RATES.get(curr, _FALLBACK_FEE_RATE) * total:.2f}"
        for curr in sums
    }


def _compile(message_type: str, records: list[dict]) -> tuple[str, str]:
    """Render the batch's XML, or return why generation failed."""
    xml_res = generate_message(message_type, records)
    if xml_res.startswith('{"error":'):  # pragma: no cover
        try:
            err_data = json.loads(xml_res)
            return "", err_data.get("error", "XML generation failed")
        except Exception:
            return "", xml_res
    return xml_res, ""


def _store(
    message_type: str, records: list[dict], xml: str, sums: dict[str, str]
) -> _StagedOrder:
    """Keep a new staged order for an hour and return it."""
    now = time.time()
    order = _StagedOrder(
        stage_id=f"stage_{secrets.token_hex(8)}",
        confirmation_token=f"tok_{secrets.token_urlsafe(24)}",
        message_type=message_type,
        records=records,
        xml_content=xml,
        sha256_fingerprint=hashlib.sha256(xml.encode("utf-8")).hexdigest(),
        created_at=now,
        expires_at=now + 3600.0,
        total_transactions=len(records),
        control_sum_by_currency=sums,
        status="staged",
    )
    _STAGED_PAYMENTS[order.stage_id] = order
    return order


def stage_payment_batch(
    message_type: _MessageType,
    records: _StagedRecords,
    scheme: _OptionalSchemeProfile = None,
) -> StagedBatchResult:
    """Stage a payment batch for simulation and a confirmed commit.

    Creates an in-memory staged payment order with zero fund movement and
    a 1-hour expiration window. Computes:

    1. Schema validation against the message type's JSON Schema.
    2. Optional scheme compliance verification (SEPA, BACS, etc.).
    3. Multi-currency control sums and fee estimation.
    4. Multi-factor risk scoring (detecting duplicates, high transaction
       amounts, and generic remittance narratives).
    5. In-memory XML compilation and SHA-256 fingerprinting.
    6. A confirmation token that commit_payment_batch requires.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records to stage.
        scheme: Optional payment scheme profile to validate against.

    Returns:
        StagedBatchResult with staging metadata, risk assessment, fingerprint,
        and confirmation token, or {"error": ...}.
    """
    _clean_expired_staged_orders()
    canonical, problem = _admit(message_type, records, scheme)
    if problem:
        return {"error": problem}
    sums, duplicates, high_value, generic = _scan(canonical)
    score, level, factors = _risk(sums, duplicates, high_value, generic)
    resolved_mt = _MESSAGE_TYPE_ALIASES.get(message_type, message_type)
    xml, problem = _compile(resolved_mt, records)
    if problem:  # pragma: no cover - the batch was validated above
        return {"error": problem}
    order = _store(resolved_mt, records, xml, _control_sums(sums))
    return {
        "stage_id": order.stage_id,
        "sha256_fingerprint": order.sha256_fingerprint,
        "total_transactions": order.total_transactions,
        "control_sum_by_currency": order.control_sum_by_currency,
        "estimated_fees": _estimated_fees(sums, len(canonical)),
        "risk_score": score,
        "risk_level": level,
        "risk_factors": factors,
        "status": "staged",
        "confirmation_token": order.confirmation_token,
        "expires_at": datetime.fromtimestamp(
            order.expires_at, tz=UTC
        ).isoformat(),
    }


def commit_payment_batch(
    stage_id: _StageId,
    confirmation_token: _ConfirmationToken,
    output_file_path: _OutputFilePath = None,
) -> CommitPaymentBatchResult:
    """Commit a staged payment batch with its confirmation token.

    Verifies the stage ID and validates the secondary confirmation token
    using constant-time cryptographic comparison (preventing timing attacks).
    Transitions the order status from 'staged' to 'committed'. Optionally
    writes a new ``.xml`` file inside the output directory (see
    ``_output.py``). The token guards against an accidental commit only.

    Args:
        stage_id: Staging identifier from stage_payment_batch.
        confirmation_token: Secondary secret confirmation token.
        output_file_path: Optional new XML file in the output directory.

    Returns:
        CommitPaymentBatchResult with commit timestamp and fingerprint,
        or {"error": ...}.
    """
    order, problem = _open_order(stage_id)
    if order is None:
        return {"error": problem}
    if not hmac.compare_digest(order.confirmation_token, confirmation_token):
        return {"error": "Invalid confirmation token for staged payment batch"}
    written, failure = save_committed(output_file_path, order.xml_content)
    if failure is not None:
        return {"error": failure}
    order.status = "committed"
    return {
        "stage_id": stage_id,
        "status": "committed",
        "sha256_fingerprint": order.sha256_fingerprint,
        "total_transactions": order.total_transactions,
        "output_file_path": written,
        "committed_at": datetime.now(UTC).isoformat(),
    }
