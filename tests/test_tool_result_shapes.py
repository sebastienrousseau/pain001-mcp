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
"""The exact shape of every tool result an agent reads.

Mutation testing showed the handlers' payload keys and messages were
never asserted: a mutant renaming ``"valid"`` to ``"VALID"`` or
``"row"`` to ``"ROW"`` passed every test, and an agent reading the
result would have silently got nothing. These tests pin the keys and
the wording, so a change to a tool's contract is a deliberate test
change, never an accident.
"""

import pytest

pytest.importorskip("mcp")

import pain001_mcp.server as server  # noqa: E402

MT = "pain.001.001.09"


def _valid_record() -> dict:
    return {
        "id": "MSG-1",
        "date": "2026-09-18T09:00:00",
        "nb_of_txs": 1,
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


class TestValidateRecords:
    """``validate_records`` returns a summary and one entry per error."""

    def test_valid_batch_has_exactly_the_summary_keys(self):
        out = server.validate_records(MT, [_valid_record()])
        assert set(out) == {"valid", "total", "valid_count", "errors"}
        assert out == {
            "valid": True,
            "total": 1,
            "valid_count": 1,
            "errors": [],
        }

    def test_each_error_names_row_path_and_message(self):
        bad = dict(_valid_record())
        bad["payment_amount"] = "not-a-number"
        bad.pop("creditor_name")
        out = server.validate_records(MT, [_valid_record(), bad])
        assert out["valid"] is False
        assert out["total"] == 2
        assert out["valid_count"] == 1
        assert out["errors"], "the broken row must produce errors"
        for entry in out["errors"]:
            assert set(entry) == {"row", "path", "message"}
            assert entry["row"] == 1
            assert isinstance(entry["path"], str)
            assert entry["message"]
        assert any(e["path"] == "payment_amount" for e in out["errors"])

    def test_unknown_message_type_is_an_error_payload(self):
        out = server.validate_records("pain.999.001.01", [_valid_record()])
        assert set(out) == {"error"}
        assert "pain.999.001.01" in out["error"]


class TestSimulatePaymentBatch:
    """``simulate_payment_batch`` returns pre-flight analysis with exact keys."""

    def test_valid_batch_payload_shape(self):
        out = server.simulate_payment_batch(MT, [_valid_record()])
        assert set(out) == {
            "valid",
            "total",
            "valid_count",
            "control_sum_by_currency",
            "unique_debtors",
            "unique_creditors",
            "duplicates",
            "schema_errors",
            "scheme_violations",
        }
        assert out["valid"] is True
        assert out["total"] == 1
        assert out["valid_count"] == 1
        assert out["control_sum_by_currency"] == {"EUR": "100.00"}
        assert out["unique_debtors"] == 1
        assert out["unique_creditors"] == 1
        assert out["duplicates"] == []
        assert out["schema_errors"] == []
        assert out["scheme_violations"] == []

    def test_duplicate_transaction_shape(self):
        rec1 = _valid_record()
        rec2 = dict(_valid_record())
        rec2["id"] = "MSG-2"
        rec2["payment_id"] = "E2E-2"
        out = server.simulate_payment_batch(MT, [rec1, rec2])
        assert out["valid"] is False
        assert len(out["duplicates"]) == 1
        dup = out["duplicates"][0]
        assert set(dup) == {
            "row",
            "matching_row",
            "debtor_account_IBAN",
            "creditor_account_IBAN",
            "amount",
            "currency",
            "requested_execution_date",
        }
        assert dup["row"] == 1
        assert dup["matching_row"] == 0
        assert dup["debtor_account_IBAN"] == rec1["debtor_account_IBAN"]
        assert dup["creditor_account_IBAN"] == rec1["creditor_account_IBAN"]
        assert dup["amount"] == "100.00"
        assert dup["currency"] == "EUR"
        assert (
            dup["requested_execution_date"] == rec1["requested_execution_date"]
        )

    def test_unknown_message_type_is_an_error_payload(self):
        out = server.simulate_payment_batch(
            "pain.999.001.01", [_valid_record()]
        )
        assert set(out) == {"error"}
        assert "pain.999.001.01" in out["error"]

    def test_unknown_scheme_profile_is_an_error_payload(self):
        out = server.simulate_payment_batch(
            MT, [_valid_record()], scheme="invalid-scheme"
        )
        assert set(out) == {"error"}
        assert out["error"]


class TestValidateIdentifier:
    """``validate_identifier`` returns kind, value and verdict, plus the error."""

    def test_valid_iban_payload_has_exactly_three_keys(self):
        out = server.validate_identifier("IBAN", "DE89370400440532013000")
        assert out == {
            "kind": "iban",
            "value": "DE89370400440532013000",
            "valid": True,
        }

    def test_invalid_iban_adds_the_error_and_keeps_the_value(self):
        out = server.validate_identifier("iban", "DE89370400440532013001")
        assert set(out) == {"kind", "value", "valid", "error"}
        assert out["kind"] == "iban"
        assert out["value"] == "DE89370400440532013001"
        assert out["valid"] is False
        assert out["error"]

    def test_bic_payload_shape(self):
        out = server.validate_identifier("bic", "COBADEFFXXX")
        assert out == {"kind": "bic", "value": "COBADEFFXXX", "valid": True}

    def test_unsupported_kind_message_is_exact(self):
        out = server.validate_identifier("lei", "x")
        assert out == {
            "error": "Unsupported identifier kind: 'lei' (expected 'iban' or 'bic')"
        }


class TestValidateXmlAgainstSchema:
    """``validate_xml_against_schema`` returns a verdict keyed on ``valid``."""

    def test_generated_xml_validates_with_exactly_two_keys(self):
        xml = server.generate_message(MT, [_valid_record()])
        out = server.validate_xml_against_schema(xml, MT)
        assert out == {"valid": True, "message_type": MT}

    def test_broken_xml_is_reported_invalid_not_raised(self):
        out = server.validate_xml_against_schema(
            "<Document><Broken/></Document>", MT
        )
        assert set(out) >= {"valid", "message_type"}
        assert out["valid"] is False
        assert out["message_type"] == MT

    def test_unknown_message_type_is_an_error_payload(self):
        out = server.validate_xml_against_schema("<x/>", "pain.999.001.01")
        assert set(out) == {"error"}
        assert "pain.999.001.01" in out["error"]


class TestInspectTemplate:
    """``inspect_template`` returns the message type and its column list."""

    def test_columns_payload_shape(self):
        out = server.inspect_template(MT)
        assert set(out) == {"message_type", "columns"}
        assert out["message_type"] == MT
        assert isinstance(out["columns"], list)
        assert "payment_amount" in out["columns"]
        assert out["columns"][0] == "id"

    def test_unknown_message_type_is_an_error_payload(self):
        out = server.inspect_template("pain.999.001.01")
        assert set(out) == {"error"}
        assert "pain.999.001.01" in out["error"]


class TestListMessageTypes:
    """``list_message_types`` returns one row per type, with its human name."""

    def test_rows_have_exactly_message_type_and_name(self):
        rows = server.list_message_types()
        assert rows, "the bundled templates must list at least one type"
        for row in rows:
            assert set(row) == {"message_type", "name"}
        by_type = {row["message_type"]: row["name"] for row in rows}
        assert by_type[MT] == server._HUMAN_NAMES[MT]
        assert (
            by_type[MT] != MT
        ), "a known type carries its human name, not its code"


class TestGetCorpusFile:
    """``get_corpus_file`` echoes the request beside the XML."""

    def test_payload_shape_for_a_known_scenario(self):
        listing = server.list_corpus_files()
        if "error" in listing:  # pragma: no cover - corpus extra absent
            pytest.skip(listing["error"])
        first = (
            listing["files"][0]
            if "files" in listing
            else listing["scenarios"][0]
        )
        scenario = (
            first["scenario_id"] if "scenario_id" in first else first["id"]
        )
        version = first.get("version") or first.get("versions", [MT])[0]
        out = server.get_corpus_file(scenario, version)
        assert set(out) == {"scenario_id", "version", "variant", "xml"}
        assert out["scenario_id"] == scenario
        assert out["version"] == version
        assert out["variant"] is None
        assert out["xml"].lstrip().startswith("<")

    def test_unknown_scenario_is_an_error_payload(self):
        out = server.get_corpus_file("zz.none.none", MT)
        assert set(out) == {"error"}
        assert out["error"]
