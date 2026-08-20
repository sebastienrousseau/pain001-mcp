"""Performance benchmarks for the MCP tools.

An MCP server answers repeated tool calls from a model, so per-call cost
is paid over and over inside a conversation rather than once in a batch
job.

Each tool gets a measurement (recorded into a CI artifact) and a scaling
guard. The guards compare a tool against itself at two batch sizes
rather than using a wall-clock threshold: a slow or noisy runner scales
both halves equally, so the ratio holds where an absolute number would
have to be loose enough to be useless.

Measured here, both tools are linear -- 4x the records costs 4.28x for
``validate_records`` and 3.35x for ``generate_message`` -- so the
ceiling is 8 against ~16 for quadratic.

One thing deliberately *not* benchmarked: ``_load_schema`` re-reads and
re-parses the bundled JSON Schema on every call, which looks like an
obvious caching win. Measured, it costs 0.18ms, against 92ms for a
200-record ``generate_message``. Caching it would be optimising 0.2% of
the work, so it is left alone rather than traded for a cache-invalidation
question nobody needs to answer.

Most of ``generate_message`` is XSD validation inside ``pain001``, which
is where the time genuinely goes; that is a core concern rather than
something this package controls.
"""

from __future__ import annotations

import time

import pytest

from pain001_mcp import server

MESSAGE_TYPE = "pain.001.001.03"

#: Ratio ceiling for a 4x increase in record count. Measured is
#: 3.35-4.28x; quadratic would be ~16x.
MAX_SCALING_RATIO = 8.0

#: One valid flat payment record, used as the template for batches.
#:
#: The numeric and boolean fields carry real JSON types rather than
#: strings. ``validate_records`` checks records against the bundled JSON
#: Schema, which types them as number/integer/boolean, so string values
#: are rejected ("'100.00' is not of type 'number'"). ``generate_message``
#: accepts either. Typed values satisfy both tools.
RECORD: dict[str, object] = {
    "addtl_end_to_end_id": "ADDTL",
    "batch_booking": False,
    "category_purpose": "CAT",
    "charge_bearer": "DEBT",
    "creditor_account_IBAN": "DE89370400440532013000",
    "creditor_agent_BIC": "SPUEDE2UXXX",
    "creditor_building_number": "1",
    "creditor_country_code": "DE",
    "creditor_name": "Creditor",
    "creditor_postal_code": "12345",
    "creditor_street_name": "Creditor St",
    "creditor_town_name": "Creditor Town",
    "ctrl_sum": 100.00,
    "currency": "EUR",
    "date": "2023-03-10T15:30:47",
    "debtor_account_IBAN": "DE89370400440532013000",
    "debtor_agent_BIC": "BANKDEFFXXX",
    "debtor_building_number": "1",
    "debtor_country_code": "DE",
    "debtor_name": "Debtor",
    "debtor_postal_code": "12345",
    "debtor_street_name": "Debtor St",
    "debtor_town_name": "Debtor Town",
    "end_to_end_id": "E2E",
    "forwarding_agent_BIC": "SPUEDE2UXXX",
    "id": "1",
    "initiator_building_number": "1",
    "initiator_country_code": "DE",
    "initiator_name": "Test Initiator",
    "initiator_postal_code": "12345",
    "initiator_street_name": "Test St",
    "initiator_town_name": "Test Town",
    "instruction_id": "INST",
    "nb_of_txs": 1,
    "payment_amount": 100.00,
    "payment_currency": "EUR",
    "payment_id": "1",
    "payment_info_structured": "STRUCT",
    "payment_information_id": "TEST",
    "payment_instruction_id": "INSTR",
    "payment_method": "TRF",
    "purpose_code": "SCOR",
    "reference_date": "2023-03-10",
    "reference_number": "REF",
    "remittance_info_structured": "STRUCT",
    "remittance_info_unstructured": "Info",
    "remittance_information": "REM",
    "requested_execution_date": "2023-03-15",
    "service_level_code": "SEPA"
}


def build_records(count: int) -> list[dict]:
    """Build ``count`` distinct valid payment records."""
    return [
        {**RECORD, "payment_id": f"PMT-{index:06d}", "id": str(index)}
        for index in range(count)
    ]


def _best_of(call, rounds: int = 3) -> float:
    """Fastest of ``rounds`` invocations, in seconds."""
    call()
    timings = []
    for _ in range(rounds):
        started = time.perf_counter()
        call()
        timings.append(time.perf_counter() - started)
    return min(timings)


@pytest.mark.benchmark
def test_validate_records_batch(benchmark) -> None:
    """Benchmark validating a 50-record batch."""
    records = build_records(50)

    result = benchmark(server.validate_records, MESSAGE_TYPE, records)

    # Asserting the batch is clean stops a benchmark over rejected input
    # from looking fast.
    assert result["valid"] is True


@pytest.mark.benchmark
def test_generate_message_batch(benchmark) -> None:
    """Benchmark generating XML for a 50-record batch."""
    records = build_records(50)

    xml = benchmark(server.generate_message, MESSAGE_TYPE, records)

    assert xml.startswith("<?xml")
    assert "PMT-000049" in xml


@pytest.mark.benchmark
def test_validate_records_scales_linearly() -> None:
    """4x the records must not cost ~16x the validation time."""
    small = _best_of(lambda: server.validate_records(MESSAGE_TYPE, build_records(50)))
    large = _best_of(lambda: server.validate_records(MESSAGE_TYPE, build_records(200)))

    ratio = large / small
    assert ratio < MAX_SCALING_RATIO, (
        f"validating 200 records took {ratio:.1f}x validating 50 "
        f"({large * 1000:.0f}ms vs {small * 1000:.0f}ms); measured "
        f"behaviour is linear at ~4.3x"
    )


@pytest.mark.benchmark
def test_generate_message_scales_linearly() -> None:
    """4x the records must not cost ~16x the generation time."""
    small = _best_of(lambda: server.generate_message(MESSAGE_TYPE, build_records(50)))
    large = _best_of(lambda: server.generate_message(MESSAGE_TYPE, build_records(200)))

    ratio = large / small
    assert ratio < MAX_SCALING_RATIO, (
        f"generating 200 records took {ratio:.1f}x generating 50 "
        f"({large * 1000:.0f}ms vs {small * 1000:.0f}ms); measured "
        f"behaviour is linear at ~3.4x"
    )
