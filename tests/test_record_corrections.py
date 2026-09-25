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


def test_delegates_exact_arguments_and_result(monkeypatch):
    """The wrapper must preserve the record, finding, edition and response."""
    from pain001.validation import corrections

    record = {"debtor_name": "Example"}
    finding = {"field": "debtor_name", "rule": "CHARSET"}
    expected = {"patches": [{"value": "sentinel", "requires_review": True}]}
    calls = []

    def suggest(actual_record, actual_finding, message_type):
        """Capture delegated values without performing any correction."""
        calls.append((actual_record, actual_finding, message_type))
        return expected

    monkeypatch.setattr(corrections, "suggest_record_fix", suggest)
    assert suggest_record_fix(record, finding, "pain.001.001.09") is expected
    assert calls == [(record, finding, "pain.001.001.09")]
    assert calls[0][0] is record
    assert calls[0][1] is finding


def test_core_value_error_keeps_error_envelope(monkeypatch):
    """Core validation errors retain their exact diagnostic in the envelope."""
    from pain001.validation import corrections

    def reject(*args):
        """Simulate a deterministic core validation failure."""
        raise ValueError("synthetic validation failure")

    monkeypatch.setattr(corrections, "suggest_record_fix", reject)
    assert suggest_record_fix({}, {}) == {
        "error": "synthetic validation failure"
    }
