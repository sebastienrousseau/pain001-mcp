# Copyright (C) 2023-2026 Sebastien Rousseau.
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Every tool's result validates against the outputSchema it declares.

The unit tests call the handler functions directly, which never runs the
SDK's structured-output validation. This calls each tool through the
server with real arguments, the way a client does, so a declared shape
that disagrees with what the tool returns fails here rather than at an
agent's first call.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

import pain001_mcp.server as server  # noqa: E402

MT = "pain.001.001.09"
RECORD = {
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

CALLS = {
    "list_message_types": {},
    "get_required_fields": {"message_type": MT},
    "get_input_schema": {"message_type": MT},
    "validate_records": {"message_type": MT, "records": [RECORD]},
    "validate_identifier": {"kind": "iban", "value": "DE89370400440532013000"},
    "generate_message": {"message_type": MT, "records": [RECORD]},
    "list_supported_formats": {},
    "generate_message_async": {"message_type": MT, "records": [RECORD]},
    "parse_camt053": {"xml_file_path": "tests/fixtures/camt053_sample.xml"},
    "parse_pain002": {"xml_file_path": "tests/fixtures/pain002_sample.xml"},
    "inspect_template": {"message_type": MT},
    "validate_payment_scheme": {"records": [RECORD]},
    "migrate_records": {
        "from_version": "pain.001.001.03",
        "to_version": MT,
        "records": [RECORD],
    },
    "validate_xml_against_schema": {"xml_content": "<x/>", "message_type": MT},
    "sanitize_to_iso20022_charset": {"value": "Zürich"},
    "list_corpus_files": {},
    "get_corpus_file": {"scenario_id": "gb.fps.single", "version": MT},
    "get_corpus_provenance": {"scenario_id": "gb.fps.single", "version": MT},
    "get_corpus_coverage": {"version": MT},
}


def _tools() -> list[str]:
    return [t.name for t in asyncio.run(server.server.list_tools())]


def test_every_tool_declares_an_output_schema() -> None:
    """An agent reads the shape before it calls; every tool must publish one."""
    missing = [
        t.name
        for t in asyncio.run(server.server.list_tools())
        if not (
            getattr(t, "outputSchema", None)
            or getattr(t, "output_schema", None)
        )
    ]
    assert missing == []


def test_the_call_table_covers_every_tool_that_runs_in_process() -> None:
    """Tools this table skips are the ones that read a CSV path or convert MT101."""
    skipped = set(_tools()) - set(CALLS)
    assert skipped == {"generate_message_from_file", "convert_mt101"}


@pytest.mark.parametrize("name", sorted(CALLS))
def test_tool_result_validates_against_its_schema(name: str) -> None:
    """A real call through the server succeeds and carries structured content."""
    result = asyncio.run(server.server.call_tool(name, CALLS[name]))
    assert result.is_error is False, result.content[0].text[:300]
    assert result.structured_content is not None


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("get_corpus_file", {"scenario_id": "zz.none", "version": MT}),
        ("validate_identifier", {"kind": "lei", "value": "x"}),
        ("inspect_template", {"message_type": "pain.999.001.01"}),
    ],
)
def test_error_payloads_validate_too(name: str, args: dict) -> None:
    """The {"error": ...} answer is part of every declared shape."""
    result = asyncio.run(server.server.call_tool(name, args))
    assert result.is_error is False
    assert set(result.structured_content) == {"error"}
