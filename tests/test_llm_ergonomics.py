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

"""LLM-ergonomic generate-path regression tests (v0.0.56).

Mirrors the failure catalogue from a real Claude Code transcript driving
the iso20022-mcp gateway: a natural first-try call ('amount'/'currency'
keys, bare 'YYYY-MM-DD' date, JSON boolean batch_booking, no nb_of_txs)
must return schema-valid XML in one shot, message-type family aliases
must resolve, and every failure must come back as one structured
``{"error": ...}`` payload listing all problems - never a raised
KeyError per retry.
"""

import asyncio
import json

from pain001_mcp import server


def natural_record(**overrides) -> dict:
    """The user's natural prompt args: pay Acme GmbH EUR 4200 on Friday."""
    record = {
        "id": "MSG-20260716-001",
        "date": "2026-07-18",
        "initiator_name": "Sebastien Rousseau",
        "payment_id": "PMT-001",
        "batch_booking": False,
        "requested_execution_date": "2026-07-18",
        "debtor_name": "Sebastien Rousseau",
        "debtor_account_IBAN": "DE89370400440532013000",
        "debtor_agent_BIC": "DEUTDEFFXXX",
        "creditor_name": "Acme GmbH",
        "creditor_agent_BIC": "COBADEFFXXX",
        "creditor_account_IBAN": "DE75512108001245126199",
        "amount": 4200,
        "currency": "EUR",
        "remittance_information": "Invoice 2026-078",
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------
# Natural-call happy path
# ---------------------------------------------------------------------------
def test_natural_call_generates_valid_xml_first_try():
    """The exact natural-args call succeeds in ONE call, no retries."""
    xml = server.generate_message("pain.001.001.09", [natural_record()])
    assert xml.startswith("<?xml")
    assert 'Ccy="EUR"' in xml
    assert ">4200.00<" in xml
    assert "<CreDtTm>2026-07-18T00:00:00</CreDtTm>" in xml
    report = server.validate_xml_against_schema(xml, "pain.001.001.09")
    assert report == {"valid": True, "message_type": "pain.001.001.09"}


def test_natural_call_emits_no_supplementary_data_block():
    """The hardcoded empty SplmtryData block is gone by default."""
    xml = server.generate_message("pain.001.001.09", [natural_record()])
    assert "SplmtryData" not in xml


def test_natural_call_async_variant():
    """The async generator applies the same ergonomics."""
    xml = asyncio.run(
        server.generate_message_async("pain.001.001.09", [natural_record()])
    )
    assert xml.startswith("<?xml")
    assert 'Ccy="EUR"' in xml


# ---------------------------------------------------------------------------
# Message-type family aliases
# ---------------------------------------------------------------------------
def test_bare_family_alias_resolves_to_v09():
    """'pain.001' (the catalogue name) is accepted for generation."""
    xml = server.generate_message("pain.001", [natural_record()])
    assert xml.startswith("<?xml")
    assert "pain.001.001.09" in xml


def test_alias_resolves_for_schema_tools():
    """Schema discovery tools accept the bare family alias too."""
    required = server.get_required_fields("pain.001")
    assert "creditor_account_IBAN" in required
    schema = server.get_input_schema("pain.001")
    assert schema["title"].startswith("pain.001.001.09")


def test_invalid_message_type_error_lists_valid_types():
    """An unknown type names the valid options instead of a bare rejection."""
    payload = json.loads(server.generate_message("pain.999", [{}]))
    assert "Invalid XML message type" in payload["error"]
    assert "pain.001.001.09" in payload["error"]


# ---------------------------------------------------------------------------
# Structured single-shot errors (never a raised KeyError per retry)
# ---------------------------------------------------------------------------
def test_missing_fields_return_one_structured_error_listing_all():
    """A near-empty record reports every missing field in one payload."""
    payload = json.loads(
        server.generate_message(
            "pain.001.001.09",
            [{"amount": 1, "currency": "EUR", "payment_id": "X"}],
        )
    )
    for field in (
        "id",
        "date",
        "initiator_name",
        "debtor_account_IBAN",
        "creditor_agent_BIC",
        "creditor_account_IBAN",
    ):
        assert field in payload["error"]


def test_missing_currency_is_reported_by_name():
    """No silent Ccy=\"\" - a missing currency is named up front."""
    record = natural_record()
    del record["currency"]
    payload = json.loads(server.generate_message("pain.001.001.09", [record]))
    assert "currency (or payment_currency)" in payload["error"]


def test_xsd_failure_reports_element_paths():
    """An XSD-invalid value reports the offending element, not an opaque path."""
    record = natural_record(charge_bearer="INVALID")
    payload = json.loads(server.generate_message("pain.001.001.09", [record]))
    assert "ChrgBr" in payload["error"]


def test_async_variant_returns_structured_error():
    """The async generator also returns errors as payloads, not raises."""
    payload = json.loads(
        asyncio.run(
            server.generate_message_async(
                "pain.001.001.09", [{"amount": 1, "currency": "EUR"}]
            )
        )
    )
    assert "Missing required fields" in payload["error"]


# ---------------------------------------------------------------------------
# validate_records ergonomics
# ---------------------------------------------------------------------------
def test_validate_records_accepts_natural_aliases():
    """Aliased keys and computed totals validate cleanly."""
    report = server.validate_records("pain.001.001.09", [natural_record()])
    assert report["valid"] is True


def test_validate_records_invalid_message_type_returns_error():
    """An unknown message type yields an error dict, not an exception."""
    report = server.validate_records("pain.999", [natural_record()])
    assert "Invalid XML message type" in report["error"]


def test_validate_records_does_not_mutate_caller_records():
    """Key canonicalization happens on copies of the caller's records."""
    record = natural_record()
    server.validate_records("pain.001.001.09", [record])
    assert "payment_amount" not in record
    assert record["amount"] == 4200
