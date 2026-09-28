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

"""Unit tests for dual-control simulation MCP tools.

Covers:
- stage_payment_batch: risk scoring, fee calculation, schema/scheme checks.
- simulate_clearing: SEPA, FedNow, US-ACH, SWIFT-MX, CHAPS, BACS rails.
- commit_payment_batch: dual-control token verification and file emission.
"""

from __future__ import annotations

import time
from pathlib import Path

import pain001_mcp.server as server

MT = "pain.001.001.09"


def _sample_record(
    amount: float = 100.0,
    currency: str = "EUR",
    debtor_iban: str = "DE89370400440532013000",
    creditor_iban: str = "DE02120300000000202051",
    charge_bearer: str = "SLEV",
    debtor_bic: str = "COBADEFFXXX",
    creditor_bic: str = "DEUTDEFFXXX",
    remittance: str = "Invoice 12345 Consulting Services",
) -> dict:
    return {
        "id": "MSG-TEST-1",
        "date": "2026-09-18T09:00:00",
        "initiator_name": "Acme GmbH",
        "payment_information_id": "PMT-TEST-1",
        "payment_method": "TRF",
        "batch_booking": False,
        "requested_execution_date": "2026-09-19",
        "debtor_name": "Acme GmbH",
        "debtor_account_IBAN": debtor_iban,
        "debtor_agent_BIC": debtor_bic,
        "charge_bearer": charge_bearer,
        "payment_id": "E2E-TEST-1",
        "payment_amount": amount,
        "currency": currency,
        "creditor_agent_BIC": creditor_bic,
        "creditor_name": "Beta AG",
        "creditor_account_IBAN": creditor_iban,
        "remittance_information": remittance,
    }


class TestStagePaymentBatch:
    """Tests for stage_payment_batch execution, fees, and risk evaluation."""

    def test_stage_payment_batch_low_risk(self):
        rec = _sample_record()
        res = server.stage_payment_batch(MT, [rec])
        assert "error" not in res
        assert res["status"] == "staged"
        assert res["total_transactions"] == 1
        assert res["control_sum_by_currency"] == {"EUR": "100.00"}
        assert res["estimated_fees"] == {"EUR": "0.20"}
        assert res["risk_level"] == "LOW"
        assert res["risk_score"] == 0
        assert res["risk_factors"] == []
        assert res["stage_id"].startswith("stage_")
        assert res["confirmation_token"].startswith("tok_")

    def test_stage_payment_batch_with_alias(self):
        rec = _sample_record()
        res = server.stage_payment_batch("pain.001", [rec])
        assert "error" not in res
        assert res["status"] == "staged"

    def test_stage_payment_batch_medium_and_high_risk(self):
        # 1. High value single tx (>100,000): +25 risk
        # 2. Generic remittance: +15 risk -> total 40 (MEDIUM)
        rec_med = _sample_record(
            amount=150000.0,
            remittance="Payment",
        )
        res_med = server.stage_payment_batch(MT, [rec_med])
        assert res_med["risk_level"] == "MEDIUM"
        assert res_med["risk_score"] == 40
        assert len(res_med["risk_factors"]) == 2

        # 3. High risk: Duplicate tx (+35) + Aggregate volume > 500,000 (+20) + High single tx (+25) + generic (+15) -> 95 (HIGH)
        rec_high_1 = _sample_record(
            amount=300000.0,
            remittance="Payment",
        )
        rec_high_2 = _sample_record(
            amount=300000.0,
            remittance="Payment",
        )
        res_high = server.stage_payment_batch(MT, [rec_high_1, rec_high_2])
        assert res_high["risk_level"] == "HIGH"
        assert res_high["risk_score"] >= 61
        assert any("duplicate" in f for f in res_high["risk_factors"])
        assert any("Aggregate volume" in f for f in res_high["risk_factors"])

    def test_stage_payment_batch_fee_rates_for_currencies(self):
        usd_rec = _sample_record(
            currency="USD",
            debtor_iban="DE89370400440532013000",
            creditor_iban="DE02120300000000202051",
        )
        gbp_rec = _sample_record(
            currency="GBP",
            debtor_iban="GB29NWBK60161331926819",
            creditor_iban="GB82WEST12345698765432",
        )
        chf_rec = _sample_record(
            currency="CHF",
            debtor_iban="CH9300762011623852957",
            creditor_iban="CH9300762011623852958",
        )

        res_usd = server.stage_payment_batch(MT, [usd_rec])
        assert res_usd["estimated_fees"] == {"USD": "0.25"}

        res_gbp = server.stage_payment_batch(MT, [gbp_rec])
        assert res_gbp["estimated_fees"] == {"GBP": "0.15"}

        res_chf = server.stage_payment_batch(MT, [chf_rec])
        assert res_chf["estimated_fees"] == {"CHF": "0.50"}

    def test_stage_payment_batch_fee_fallback_empty_currency(self):
        rec = _sample_record()
        rec["currency"] = ""
        res = server.stage_payment_batch(MT, [rec])
        # Schema validation error expected because currency is required
        assert "error" in res

    def test_stage_payment_batch_invalid_amount_format(self):
        rec = _sample_record()
        rec["payment_amount"] = "invalid_num"
        res = server.stage_payment_batch(MT, [rec])
        assert "error" in res
        assert "failed schema validation" in res["error"]

    def test_stage_payment_batch_scheme_validation_success(self):
        rec = _sample_record()
        res = server.stage_payment_batch(MT, [rec], scheme="sepa-sct")
        assert "error" not in res
        assert res["status"] == "staged"

    def test_stage_payment_batch_scheme_validation_failure(self):
        # Exceeding 100k cap triggers sepa-inst violation while passing schema
        rec = _sample_record(amount=200000.0)
        res = server.stage_payment_batch(MT, [rec], scheme="sepa-inst")
        assert "error" in res
        assert "Batch failed scheme 'sepa-inst' validation" in res["error"]

    def test_stage_payment_batch_invalid_scheme_profile(self):
        rec = _sample_record()
        res = server.stage_payment_batch(MT, [rec], scheme="unknown-scheme")
        assert "error" in res

    def test_stage_payment_batch_unknown_message_type(self):
        rec = _sample_record()
        res = server.stage_payment_batch("pain.999.001.01", [rec])
        assert "error" in res


class TestSimulateClearing:
    """Tests for simulate_clearing across all payment rails."""

    def test_simulate_clearing_sepa_accepted(self):
        rec = _sample_record(currency="EUR", charge_bearer="SLEV")
        staged = server.stage_payment_batch(MT, [rec])
        res = server.simulate_clearing(staged["stage_id"], "EPC-SEPA")
        assert res["clearing_status"] == "ACCEPTED"
        assert res["clearing_system"] == "EPC-SEPA"
        assert res["settlement_window"] == "Next SEPA Cycle (Same Day / D+1)"
        assert all(c["status"] == "PASS" for c in res["checks"])

    def test_simulate_clearing_sepa_rejected_currency(self):
        rec = _sample_record(currency="USD")
        staged = server.stage_payment_batch(MT, [rec])
        res = server.simulate_clearing(staged["stage_id"], "EPC-SEPA")
        assert res["clearing_status"] == "REJECTED"
        assert any(
            c["check"].startswith("EPC-SEPA Currency Rule")
            and c["status"] == "FAIL"
            for c in res["checks"]
        )

    def test_simulate_clearing_sepa_rejected_iban_jurisdiction(self):
        # US account prefix is outside SEPA area
        rec = _sample_record(
            currency="EUR", debtor_iban="US89370400440532013000"
        )
        # Direct insert to simulate invalid IBAN passing staging or non-SEPA IBAN
        staged = server.stage_payment_batch(MT, [_sample_record()])
        server._STAGED_PAYMENTS[staged["stage_id"]].records = [rec]
        res = server.simulate_clearing(staged["stage_id"], "EPC-SEPA")
        assert res["clearing_status"] == "REJECTED"
        assert any(
            c["check"] == "SEPA-Zone Routing Eligibility"
            and c["status"] == "FAIL"
            for c in res["checks"]
        )

    def test_simulate_clearing_sepa_rejected_charge_bearer(self):
        rec = _sample_record(currency="EUR")
        staged = server.stage_payment_batch(MT, [rec])
        server._STAGED_PAYMENTS[staged["stage_id"]].records = [
            _sample_record(charge_bearer="SHAR")
        ]
        res = server.simulate_clearing(staged["stage_id"], "EPC-SEPA")
        assert res["clearing_status"] == "REJECTED"
        assert any(
            c["check"] == "EPC Charge Bearer Standard (SLEV)"
            and c["status"] == "FAIL"
            for c in res["checks"]
        )

    def test_simulate_clearing_fednow(self):
        rec_usd = _sample_record(currency="USD")
        staged = server.stage_payment_batch(MT, [rec_usd])
        res = server.simulate_clearing(staged["stage_id"], "FedNow")
        assert res["clearing_status"] == "ACCEPTED"
        assert res["settlement_window"] == "Instant (< 20 seconds)"

        rec_eur = _sample_record(currency="EUR")
        staged_eur = server.stage_payment_batch(MT, [rec_eur])
        res_eur = server.simulate_clearing(staged_eur["stage_id"], "FedNow")
        assert res_eur["clearing_status"] == "REJECTED"

    def test_simulate_clearing_us_ach(self):
        rec_usd = _sample_record(currency="USD")
        staged = server.stage_payment_batch(MT, [rec_usd])
        res = server.simulate_clearing(staged["stage_id"], "US-ACH")
        assert res["clearing_status"] == "ACCEPTED"
        assert res["settlement_window"] == "Next Business Day ACH Window"

        rec_eur = _sample_record(currency="EUR")
        staged_eur = server.stage_payment_batch(MT, [rec_eur])
        res_eur = server.simulate_clearing(staged_eur["stage_id"], "US-ACH")
        assert res_eur["clearing_status"] == "REJECTED"

    def test_simulate_clearing_swift_mx(self):
        rec_bic = _sample_record(
            debtor_bic="COBADEFFXXX", creditor_bic="DEUTDEFFXXX"
        )
        staged = server.stage_payment_batch(MT, [rec_bic])
        res = server.simulate_clearing(staged["stage_id"], "SWIFT-MX")
        assert res["clearing_status"] == "ACCEPTED"
        assert (
            res["settlement_window"]
            == "Correspondent Banking Network (D+1 to D+2)"
        )

        # Missing creditor BIC
        staged_noburo = server.stage_payment_batch(MT, [rec_bic])
        server._STAGED_PAYMENTS[staged_noburo["stage_id"]].records = [
            _sample_record(creditor_bic="")
        ]
        res_noburo = server.simulate_clearing(
            staged_noburo["stage_id"], "SWIFT-MX"
        )
        assert res_noburo["clearing_status"] == "REJECTED"

    def test_simulate_clearing_chaps(self):
        rec_gbp = _sample_record(
            currency="GBP",
            debtor_iban="GB29NWBK60161331926819",
            creditor_iban="GB82WEST12345698765432",
        )
        staged = server.stage_payment_batch(MT, [rec_gbp])
        res = server.simulate_clearing(staged["stage_id"], "CHAPS")
        assert res["clearing_status"] == "ACCEPTED"
        assert "Same Day" in res["settlement_window"]

        rec_eur = _sample_record(currency="EUR")
        staged_eur = server.stage_payment_batch(MT, [rec_eur])
        res_eur = server.simulate_clearing(staged_eur["stage_id"], "CHAPS")
        assert res_eur["clearing_status"] == "REJECTED"

    def test_simulate_clearing_bacs(self):
        rec_gbp = _sample_record(
            currency="GBP",
            debtor_iban="GB29NWBK60161331926819",
            creditor_iban="GB82WEST12345698765432",
        )
        staged = server.stage_payment_batch(MT, [rec_gbp])
        res = server.simulate_clearing(staged["stage_id"], "BACS")
        assert res["clearing_status"] == "ACCEPTED"
        assert res["settlement_window"] == "Three-Day Clearing Cycle"

        rec_eur = _sample_record(currency="EUR")
        staged_eur = server.stage_payment_batch(MT, [rec_eur])
        res_eur = server.simulate_clearing(staged_eur["stage_id"], "BACS")
        assert res_eur["clearing_status"] == "REJECTED"

    def test_simulate_clearing_errors(self):
        # Stage not found
        res_nf = server.simulate_clearing("stage_does_not_exist", "EPC-SEPA")
        assert "error" in res_nf
        assert "not found" in res_nf["error"]

        # Expired stage
        staged = server.stage_payment_batch(MT, [_sample_record()])
        server._STAGED_PAYMENTS[staged["stage_id"]].expires_at = (
            time.time() - 10
        )
        res_exp = server.simulate_clearing(staged["stage_id"], "EPC-SEPA")
        assert "error" in res_exp
        assert "has expired" in res_exp["error"]

        # Already committed
        staged2 = server.stage_payment_batch(MT, [_sample_record()])
        server.commit_payment_batch(
            staged2["stage_id"], staged2["confirmation_token"]
        )
        res_com = server.simulate_clearing(staged2["stage_id"], "EPC-SEPA")
        assert "error" in res_com
        assert "already been committed" in res_com["error"]

        # Unsupported clearing system
        staged3 = server.stage_payment_batch(MT, [_sample_record()])
        res_uns = server.simulate_clearing(staged3["stage_id"], "UNKNOWN-RAIL")  # type: ignore[arg-type]
        assert "error" in res_uns
        assert "Unsupported clearing system" in res_uns["error"]


class TestCommitPaymentBatch:
    """Tests for commit_payment_batch execution and dual-control tokens."""

    def test_commit_payment_batch_success(self, tmp_path: Path):
        staged = server.stage_payment_batch(MT, [_sample_record()])
        target_file = tmp_path / "out" / "committed.xml"

        res = server.commit_payment_batch(
            staged["stage_id"],
            staged["confirmation_token"],
            output_file_path=str(target_file),
        )
        assert "error" not in res
        assert res["status"] == "committed"
        assert res["stage_id"] == staged["stage_id"]
        assert res["sha256_fingerprint"] == staged["sha256_fingerprint"]
        assert res["output_file_path"] == str(target_file)
        assert target_file.is_file()
        assert target_file.read_text(encoding="utf-8").startswith("<?xml")

    def test_commit_payment_batch_without_file(self):
        staged = server.stage_payment_batch(MT, [_sample_record()])
        res = server.commit_payment_batch(
            staged["stage_id"],
            staged["confirmation_token"],
        )
        assert "error" not in res
        assert res["status"] == "committed"
        assert res["output_file_path"] is None

    def test_commit_payment_batch_errors(self):
        # Stage not found
        res_nf = server.commit_payment_batch("stage_unknown", "tok_any")
        assert "error" in res_nf
        assert "not found" in res_nf["error"]

        # Expired
        staged = server.stage_payment_batch(MT, [_sample_record()])
        server._STAGED_PAYMENTS[staged["stage_id"]].expires_at = (
            time.time() - 5
        )
        res_exp = server.commit_payment_batch(
            staged["stage_id"], staged["confirmation_token"]
        )
        assert "error" in res_exp
        assert "has expired" in res_exp["error"]

        # Invalid token
        staged2 = server.stage_payment_batch(MT, [_sample_record()])
        res_tok = server.commit_payment_batch(
            staged2["stage_id"], "wrong_token"
        )
        assert "error" in res_tok
        assert "Invalid confirmation token" in res_tok["error"]

        # Already committed
        server.commit_payment_batch(
            staged2["stage_id"], staged2["confirmation_token"]
        )
        res_recom = server.commit_payment_batch(
            staged2["stage_id"], staged2["confirmation_token"]
        )
        assert "error" in res_recom
        assert "already been committed" in res_recom["error"]

    def test_commit_payment_batch_file_write_error(self, monkeypatch):
        staged = server.stage_payment_batch(MT, [_sample_record()])

        def _bad_write(*args, **kwargs):
            raise OSError("Disk full")

        monkeypatch.setattr(Path, "write_text", _bad_write)
        res = server.commit_payment_batch(
            staged["stage_id"],
            staged["confirmation_token"],
            output_file_path="/tmp/test_err.xml",
        )
        assert "error" in res
        assert "Failed to write output XML file" in res["error"]


class TestStagedCleanup:
    """Tests for in-memory cleanup of expired orders."""

    def test_clean_expired_staged_orders(self):
        staged = server.stage_payment_batch(MT, [_sample_record()])
        sid = staged["stage_id"]
        assert sid in server._STAGED_PAYMENTS

        # Advance simulated time past 24h cutoff
        server._clean_expired_staged_orders(now=time.time() + 90000.0)
        assert sid not in server._STAGED_PAYMENTS
