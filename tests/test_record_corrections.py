# SPDX-License-Identifier: Apache-2.0 OR MIT
"""The correction tool delegates to core and never edits financial fields."""

import copy
import sys

import pytest

from pain001_mcp.server import suggest_record_fix


@pytest.mark.parametrize(
    "field",
    [
        "debtor_account_IBAN",
        "creditor_agent_BIC",
        "payment_amount",
        "currency",
    ],
)
def test_financial_refusal(field):
    """Hard refusals cover even harmless-looking whitespace edits."""
    record = {field: " example "}
    before = copy.deepcopy(record)
    assert suggest_record_fix(record, {"field": field, "rule": "CHARSET"}) == {
        "patches": [],
        "cannot_autofix": "protected_financial_field",
    }
    assert record == before


def test_safe_suggestion():
    """A deterministic charset candidate is marked for review."""
    result = suggest_record_fix(
        {"debtor_name": "Example™"},
        {"field": "debtor_name", "rule": "CHARSET"},
    )
    assert result["patches"][0]["requires_review"] is True


def test_invalid_type():
    """Unsupported message types use the established error envelope."""
    assert "error" in suggest_record_fix({}, {}, "not-a-message")


def test_old_core(monkeypatch):
    """Older core builds retain other tools and explain the missing feature."""
    monkeypatch.setitem(sys.modules, "pain001.validation.corrections", None)
    assert "matching core feature build" in suggest_record_fix({}, {})["error"]
