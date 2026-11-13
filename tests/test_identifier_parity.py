# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""The MCP refuses what the CLI refuses (pain001 >= 0.0.81).

From 0.0.81 the core checks every IBAN and BIC column on load (mod-97,
ISO 9362) and refuses rows that would not share one PmtInf. From 0.0.87
the MCP tools run the core's own validation ladder on inline rows, so
those checks, and the ``identifier_checks`` opt-out, are the CLI's. A
row that the CLI refuses must not validate here, nor generate.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pain001.data.loader import load_payment_data
from pain001.exceptions import PaymentValidationError

import pain001_mcp.server as server

MT = "pain.001.001.09"
# Passes the XSD pattern and the JSON Schema, fails mod-97.
BAD_IBAN = "DE02120300000000202052"
# Well-formed, but QQ is not an ISO 3166 country.
BAD_BIC = "DEUTQQFFXXX"


def _record(**overrides) -> dict:
    """Return a valid pain.001.001.09 record, with ``overrides`` applied."""
    record = {
        "id": "MSG-1",
        "date": "2026-09-18T09:00:00",
        "initiator_name": "Acme GmbH",
        "payment_information_id": "PMT-1",
        "payment_method": "TRF",
        "batch_booking": False,
        "requested_execution_date": "2026-09-19",
        "debtor_name": "Acme GmbH",
        "debtor_account_IBAN": "DE89370400440532013000",
        "debtor_agent_BIC": "COBADEFFXXX",
        "charge_bearer": "SLEV",
        "payment_id": "E2E-1",
        "payment_amount": 100.0,
        "currency": "EUR",
        "creditor_agent_BIC": "DEUTDEFFXXX",
        "creditor_name": "Beta AG",
        "creditor_account_IBAN": "DE02120300000000202051",
        "remittance_information": "Invoice 1",
    }
    record.update(overrides)
    return record


_LOADER_COLUMNS = {
    "nb_of_txs": 1,
    "ctrl_sum": 100.0,
    "service_level_code": "SEPA",
    "forwarding_agent_BIC": "COBADEFFXXX",
}


def _loader_refusal(tmp_path, monkeypatch, rows: list[dict]) -> str:
    """Return the message the core's file loader refuses ``rows`` with.

    The loader only reads below the working directory, so the test moves
    there first.
    """
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "rows.json"
    # The loader wants every template column, which the tools compute or
    # default; none is an identifier column the check reads, so the
    # verdict is unchanged.
    complete = [{**row, **_LOADER_COLUMNS} for row in rows]
    path.write_text(json.dumps(complete), encoding="utf-8")
    with pytest.raises(PaymentValidationError) as caught:
        load_payment_data(str(path))
    return str(caught.value)


class TestValidateRecords:
    """``validate_records`` reports bad identifiers and mixed batches."""

    def test_a_bad_iban_is_a_row_error_naming_the_column(self):
        out = server.validate_records(
            MT, [_record(), _record(creditor_account_IBAN=BAD_IBAN)]
        )
        assert out["valid"] is False
        # The identifier rung refuses the batch as a whole, as the CLI
        # does, so no row is counted valid.
        assert out["valid_count"] == 0
        (error,) = out["errors"]
        assert (error["row"], error["line"]) == (1, 2)
        assert error["path"] == "creditor_account_IBAN"
        assert error["code"] == "P001-E020"
        assert error["message"].startswith("not a valid IBAN")
        assert BAD_IBAN not in json.dumps(out), "an IBAN is personal data"

    def test_a_bad_bic_is_a_row_error(self):
        out = server.validate_records(MT, [_record(debtor_agent_BIC=BAD_BIC)])
        assert out["valid"] is False
        (error,) = out["errors"]
        assert (error["row"], error["path"]) == (0, "debtor_agent_BIC")
        assert error["code"] == "P001-E021"
        assert error["message"].startswith("not a valid BIC")

    def test_a_lower_case_column_is_checked_too(self):
        """Any spelling the generator reads is checked, named as given."""
        record = _record()
        del record["creditor_account_IBAN"]
        record["creditor_account_iban"] = BAD_IBAN
        out = server.validate_records(MT, [record])
        assert out["valid"] is False
        assert out["errors"][0]["path"] == "creditor_account_iban"

    def test_the_opt_out_skips_the_identifier_checks(self):
        out = server.validate_records(
            MT,
            [_record(creditor_account_IBAN=BAD_IBAN)],
            identifier_checks=False,
        )
        assert out["valid"] is True
        assert out["errors"] == []

    def test_the_row_contract_is_checked_before_the_identifiers(self):
        """The CLI's order: a bad amount is named before a bad IBAN."""
        out = server.validate_records(
            MT,
            [_record(creditor_account_IBAN=BAD_IBAN, payment_amount="abc")],
        )
        assert [(e["path"], e["code"]) for e in out["errors"]] == [
            ("payment_amount", "P001-E012")
        ]

    def test_a_mixed_batch_is_refused_as_generation_refuses_it(self):
        rows = [_record(), _record(payment_id="E2E-2", debtor_name="Other")]
        out = server.validate_records(MT, rows)
        assert set(out) == {"error"}
        assert "do not share one payment information block" in out["error"]
        generated = json.loads(server.generate_message(MT, rows))
        assert out["error"] == generated["error"]

    def test_the_opt_out_does_not_skip_the_one_batch_check(self):
        rows = [_record(), _record(payment_id="E2E-2", debtor_name="Other")]
        out = server.validate_records(MT, rows, identifier_checks=False)
        assert "do not share one payment information block" in out["error"]


class TestGenerateMessage:
    """``generate_message`` refuses what the CLI loader refuses."""

    def test_a_bad_iban_is_refused_with_the_loaders_message(
        self, tmp_path, monkeypatch
    ):
        rows = [_record(creditor_account_IBAN=BAD_IBAN)]
        out = json.loads(server.generate_message(MT, rows))
        assert out["error"] == _loader_refusal(tmp_path, monkeypatch, rows)
        assert BAD_IBAN not in json.dumps(out)
        assert out["issues"] == [
            {
                "line": 1,
                "column": "creditor_account_IBAN",
                "code": "P001-E020",
                "message": out["issues"][0]["message"],
            }
        ]

    def test_the_opt_out_generates_the_file(self):
        rows = [_record(creditor_account_IBAN=BAD_IBAN)]
        xml = server.generate_message(MT, rows, identifier_checks=False)
        assert xml.lstrip().startswith("<?xml")

    def test_async_refuses_the_same_way(self, tmp_path, monkeypatch):
        rows = [_record(debtor_agent_BIC=BAD_BIC)]
        out = json.loads(asyncio.run(server.generate_message_async(MT, rows)))
        assert out["error"] == _loader_refusal(tmp_path, monkeypatch, rows)

    def test_async_opt_out_generates_the_file(self):
        rows = [_record(creditor_account_IBAN=BAD_IBAN)]
        xml = asyncio.run(
            server.generate_message_async(MT, rows, identifier_checks=False)
        )
        assert xml.lstrip().startswith("<?xml")


class TestBatchTools:
    """The pre-flight and staging tools inherit the checks."""

    def test_simulate_reports_the_bad_iban(self):
        out = server.simulate_payment_batch(
            MT, [_record(creditor_account_IBAN=BAD_IBAN)]
        )
        assert out["valid"] is False
        assert out["schema_errors"][0]["path"] == "creditor_account_IBAN"

    def test_stage_refuses_the_bad_iban(self):
        out = server.stage_payment_batch(
            MT, [_record(creditor_account_IBAN=BAD_IBAN)]
        )
        assert out == {"error": "Batch failed schema validation with 1 errors"}


@pytest.mark.parametrize(
    "tool", ["validate_records", "generate_message", "generate_message_async"]
)
def test_the_opt_out_is_a_boolean_defaulting_to_true(tool):
    """Each inline-rows tool offers ``identifier_checks``, on by default."""
    tools = {t.name: t for t in asyncio.run(server.server.list_tools())}
    schema = tools[tool].model_dump(by_alias=True)["inputSchema"]
    prop = schema["properties"]["identifier_checks"]
    assert prop["type"] == "boolean"
    assert prop["default"] is True
    assert "identifier_checks" not in schema.get("required", [])
