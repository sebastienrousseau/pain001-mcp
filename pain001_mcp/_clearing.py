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

"""The clearing simulation over a staged batch.

Each clearing system is one row of :data:`_CLEARING`: its settlement
window and the function that returns its checks. A check passes or
fails; the batch is accepted only when every check passes.
"""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from pain001 import canonicalize_payment_record
from pydantic import Field

from pain001_mcp._schemes import _upper
from pain001_mcp._shapes import ClearingCheck, SimulateClearingResult
from pain001_mcp._staging import _open_order, _StageId

_Records = list[dict[str, Any]]

_SEPA_COUNTRY_CODES: frozenset[str] = frozenset(
    {
        "AD",
        "AT",
        "BE",
        "BG",
        "CH",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GB",
        "GI",
        "GR",
        "HR",
        "HU",
        "IE",
        "IS",
        "IT",
        "LI",
        "LT",
        "LU",
        "LV",
        "MC",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
        "SM",
        "VA",
    }
)

_ClearingSystem = Annotated[
    Literal["EPC-SEPA", "FedNow", "US-ACH", "SWIFT-MX", "CHAPS", "BACS"],
    Field(
        description=(
            "Target clearing system simulation profile to evaluate "
            "settlement eligibility, cut-off windows, and routing constraints."
        )
    ),
]


def _check(name: str, ok: bool, passed: str, failed: str) -> ClearingCheck:
    """Return one check, with the detail that matches its outcome."""
    return {
        "check": name,
        "status": "PASS" if ok else "FAIL",
        "detail": passed if ok else failed,
    }


def _currency_check(
    records: _Records, name: str, currency: str, failed: str
) -> ClearingCheck:
    """Check that every payment is denominated in ``currency``."""
    ok = all(_upper(r, "currency") == currency for r in records)
    return _check(name, ok, f"All payments denominated in {currency}", failed)


def _in_sepa(record: dict[str, Any]) -> bool:
    """Whether both IBANs of ``record`` carry a SEPA country prefix."""
    debtor = _upper(record, "debtor_account_IBAN")[:2]
    creditor = _upper(record, "creditor_account_IBAN")[:2]
    return debtor in _SEPA_COUNTRY_CODES and creditor in _SEPA_COUNTRY_CODES


def _sepa_checks(records: _Records) -> list[ClearingCheck]:
    """EUR only, SEPA-zone accounts, and the SLEV charge bearer."""
    all_slev = all(
        str(r.get("charge_bearer", "SLEV")).strip().upper() == "SLEV"
        for r in records
    )
    return [
        _currency_check(
            records,
            "EPC-SEPA Currency Rule (EUR)",
            "EUR",
            "All SEPA transfers must be denominated in EUR",
        ),
        _check(
            "SEPA-Zone Routing Eligibility",
            all(_in_sepa(r) for r in records),
            "Debtor and creditor accounts reside in SEPA member jurisdictions",
            "IBAN country prefix outside SEPA clearing jurisdiction",
        ),
        _check(
            "EPC Charge Bearer Standard (SLEV)",
            all_slev,
            "Charge bearer set to SLEV as mandated by EPC",
            "Charge bearer must be SLEV for standard SEPA credit transfers",
        ),
    ]


def _fednow_checks(records: _Records) -> list[ClearingCheck]:
    """USD only; real-time settlement is always available."""
    return [
        _currency_check(
            records,
            "FedNow Currency Rule (USD)",
            "USD",
            "FedNow instant payments must be denominated in USD",
        ),
        {
            "check": "FedNow 24/7/365 Real-Time Settlement",
            "status": "PASS",
            "detail": (
                "Participating FI connectivity active for immediate gross settlement"
            ),
        },
    ]


def _swift_checks(records: _Records) -> list[ClearingCheck]:
    """Both agent BICs present for correspondent routing."""
    has_bics = all(
        bool(str(r.get("debtor_agent_BIC", "")).strip())
        and bool(str(r.get("creditor_agent_BIC", "")).strip())
        for r in records
    )
    return [
        _check(
            "SWIFT CBPR+ BIC Routing",
            has_bics,
            "Valid debtor and creditor agent BICs present for cross-border routing",
            "Missing debtor or creditor agent BIC required for SWIFT network",
        )
    ]


def _currency_only(
    name: str, currency: str, failed: str
) -> Callable[[_Records], list[ClearingCheck]]:
    """Return the checks function of a system that only checks currency."""
    return lambda records: [_currency_check(records, name, currency, failed)]


#: Settlement window and checks of every simulated clearing system.
_CLEARING: dict[str, tuple[str, Callable[[_Records], list[ClearingCheck]]]] = {
    "EPC-SEPA": ("Next SEPA Cycle (Same Day / D+1)", _sepa_checks),
    "FedNow": ("Instant (< 20 seconds)", _fednow_checks),
    "US-ACH": (
        "Next Business Day ACH Window",
        _currency_only(
            "NACHA ACH Currency Rule (USD)",
            "USD",
            "Domestic US ACH requires USD denomination",
        ),
    ),
    "SWIFT-MX": ("Correspondent Banking Network (D+1 to D+2)", _swift_checks),
    "CHAPS": (
        "Same Day (pre-16:00 UK cut-off)",
        _currency_only(
            "CHAPS Currency Rule (GBP)",
            "GBP",
            "CHAPS high-value RTGS requires GBP denomination",
        ),
    ),
    "BACS": (
        "Three-Day Clearing Cycle",
        _currency_only(
            "BACS Currency Rule (GBP)",
            "GBP",
            "BACS direct credits require GBP denomination",
        ),
    ),
}


def simulate_clearing(
    stage_id: _StageId,
    clearing_system: _ClearingSystem = "EPC-SEPA",
) -> SimulateClearingResult:
    """Simulate settlement and clearing network execution for a staged batch.

    Evaluates network-specific rulebooks and clearing constraints:
    - EPC-SEPA: EUR currency mandate, SEPA-zone IBAN prefixes, SLEV charge bearer.
    - FedNow: USD instant gross settlement eligibility.
    - US-ACH: USD next-day clearing cycle routing.
    - SWIFT-MX: Cross-border correspondent banking BIC routing.
    - CHAPS: Same-day RTGS high-value GBP clearing.
    - BACS: Three-day GBP direct credit clearing.

    Args:
        stage_id: Staging identifier from stage_payment_batch.
        clearing_system: Clearing rail profile to simulate.

    Returns:
        SimulateClearingResult with verdict (ACCEPTED / REJECTED), detailed
        checks, and estimated settlement window, or {"error": ...}.
    """
    order, problem = _open_order(stage_id)
    if order is None:
        return {"error": problem}
    if clearing_system not in _CLEARING:
        return {"error": f"Unsupported clearing system: {clearing_system}"}
    settlement_window, run_checks = _CLEARING[clearing_system]
    records = [canonicalize_payment_record(r) for r in order.records]
    checks = run_checks(records)
    accepted = all(c["status"] == "PASS" for c in checks)
    return {
        "stage_id": stage_id,
        "clearing_system": clearing_system,
        "clearing_status": "ACCEPTED" if accepted else "REJECTED",
        "settlement_window": settlement_window,
        "checks": checks,
    }
