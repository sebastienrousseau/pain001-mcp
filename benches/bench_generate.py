#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""What generating and validating a pain.001 costs, as the batch grows.

A payment batch is not one record. A payroll run is thousands, and it is
submitted once, under a cut-off, by a job that must not still be running
when the window closes. So the question is how the cost grows and where
the time actually goes.

Three things are measured:

* **``generate_message`` across batch sizes.** The result is XSD-validated
  before it is returned, so this number includes validation. Read
  ``us/record``: flat means linear and a payroll batch is fine.

* **``validate_records`` beside ``generate_message``.** Both touch the
  schema, so a rough parity is what you would expect. It is not what
  happens: at 1,000 records the standalone validator costs several times
  generation, even though generation validates its own output before
  returning. Whatever the reason — extra checks, or a cheaper path being
  missed — the two are not doing the same work, and the ratio is worth
  watching rather than assuming.

* **First call against later ones.** The XSD compiles once per process and
  is then cached, so the first generation in a fresh interpreter costs far
  more than the rest. That decides a deployment question: a worker that
  generates one batch per invocation pays it every time; a long-lived one
  pays it once. A benchmark reporting only a mean hides it completely.

Run::

    python benches/bench_generate.py
    python benches/bench_generate.py --json
    python benches/bench_generate.py --quick     # what CI runs

Nothing here asserts a threshold: wall-clock is not comparable between
machines, and a flaky performance gate teaches people to ignore red. CI
runs ``--quick`` so a benchmark that has stopped compiling against the
current API fails the build instead of rotting into a file that reads as
verified and is not.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pain001_mcp import server  # noqa: E402

MESSAGE_TYPE = "pain.001.001.09"

_RECORD = {
    "id": "MSG-0001",
    "date": "2026-01-15T10:30:00",
    "nb_of_txs": 1,
    "ctrl_sum": 100.00,
    "initiator_name": "Acme Embedded Finance Ltd",
    "payment_information_id": "PMT-INFO-0001",
    "payment_method": "TRF",
    "batch_booking": False,
    "service_level_code": "SEPA",
    "requested_execution_date": "2026-01-20",
    "debtor_name": "Acme Embedded Finance Ltd",
    "debtor_account_IBAN": "DE89370400440532013000",
    "debtor_agent_BIC": "DEUTDEFFXXX",
    "charge_bearer": "SLEV",
    "payment_id": "PAY-0001",
    "payment_amount": 100.00,
    "currency": "EUR",
    "creditor_agent_BIC": "NWBKGB2LXXX",
    "creditor_name": "National Westminster Bank",
    "creditor_account_IBAN": "GB29NWBK60161331926819",
    "remittance_information": "Invoice 0001",
}


def batch(records: int) -> list[dict]:
    """``records`` payment records, each with its own end-to-end id."""
    out = []
    for i in range(records):
        row = dict(_RECORD)
        row["payment_id"] = f"PAY-{i:07d}"
        row["remittance_information"] = f"Invoice {i}"
        out.append(row)
    return out


def _best(call, repeats: int) -> float:
    """Best-of timing after one untimed warm-up.

    The warm-up matters more than usual here: the XSD compiles on first
    use, so without it the first sample measures schema compilation rather
    than generation. That cost is real and is reported separately below,
    not smuggled into the per-record number.
    """
    call()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        call()
        samples.append(time.perf_counter() - start)
    return min(samples)


def measure(records: int, repeats: int) -> dict:
    rows = batch(records)
    generate = _best(
        lambda: server.generate_message(MESSAGE_TYPE, rows), repeats
    )
    validate = _best(
        lambda: server.validate_records(MESSAGE_TYPE, rows), repeats
    )
    return {
        "records": records,
        "generate_ms": generate * 1e3,
        "validate_ms": validate * 1e3,
        "us_per_record": generate * 1e6 / records,
        "validate_over_generate": validate / generate if generate else 0.0,
    }


def measure_cold(records: int) -> dict:
    """First call in a fresh interpreter against the second.

    Run as a subprocess on purpose: measuring in-process would report a
    warm cache and miss the entire point.
    """
    script = (
        "import sys, time, json\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from pain001_mcp import server\n"
        "rows = json.loads(sys.stdin.read())\n"
        f"mt = {MESSAGE_TYPE!r}\n"
        "t0 = time.perf_counter(); server.generate_message(mt, rows)\n"
        "cold = time.perf_counter() - t0\n"
        "t1 = time.perf_counter(); server.generate_message(mt, rows)\n"
        "warm = time.perf_counter() - t1\n"
        "print(json.dumps({'cold': cold, 'warm': warm}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(batch(records)),
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        return {"error": result.stderr[-300:]}
    timings = json.loads(result.stdout.strip().splitlines()[-1])
    return {
        "records": records,
        "cold_ms": timings["cold"] * 1e3,
        "warm_ms": timings["warm"] * 1e3,
        "cold_over_warm": (
            timings["cold"] / timings["warm"] if timings["warm"] else 0.0
        ),
    }


def run(quick: bool) -> dict:
    sizes = [1, 25] if quick else [1, 25, 250, 1_000]
    repeats = 2 if quick else 5
    return {
        "sizes": [measure(n, repeats) for n in sizes],
        "cold": measure_cold(sizes[0]),
    }


def render(results: dict) -> None:
    print(
        f"{'records':>9}{'generate ms':>13}{'validate ms':>13}"
        f"{'us/record':>11}{'validate/gen':>14}"
    )
    for row in results["sizes"]:
        print(
            f"{row['records']:>9}{row['generate_ms']:>13.2f}"
            f"{row['validate_ms']:>13.2f}{row['us_per_record']:>11.1f}"
            f"{row['validate_over_generate']:>13.2f}x"
        )
    rows = results["sizes"]
    if len(rows) >= 3 and rows[-2]["us_per_record"]:
        # Compared against the second-largest size, not the smallest. At one
        # record the fixed per-call cost is the entire measurement, so using
        # it as the baseline reports a huge fall and says nothing about
        # scaling.
        drift = rows[-1]["us_per_record"] / rows[-2]["us_per_record"]
        print(
            f"\n  us/record at {rows[-1]['records']:,} is {drift:.2f}x the "
            f"cost at {rows[-2]['records']:,}. Near 1.00 is linear once the "
            f"fixed per-call cost has amortised, and a payroll batch "
            f"finishes inside its window. The first row is almost entirely "
            f"that fixed cost, which is why it looks so expensive per "
            f"record."
        )
    if rows:
        worst = max(r["validate_over_generate"] for r in rows)
        if worst > 1.0:
            print(
                f"\n  validate_records costs up to {worst:.1f}x "
                f"generate_message. That is worth a second look: "
                f"generate_message already XSD-validates its output before "
                f"returning, so the standalone validator being several times "
                f"dearer means the two are not doing the same work. Either "
                f"the extra is checking something generation does not, or "
                f"there is a cheaper path being missed."
            )
        else:
            print(
                f"\n  validate_records costs up to {worst:.2f}x "
                f"generate_message, which already validates its output. A "
                f"caller that validates first and then generates pays for "
                f"the schema twice."
            )

    cold = results["cold"]
    print("\nfirst call in a fresh interpreter against the second")
    if "error" in cold:
        print(f"  failed: {cold['error']}")
    else:
        print(
            f"  cold {cold['cold_ms']:,.0f} ms, warm {cold['warm_ms']:,.2f} "
            f"ms — {cold['cold_over_warm']:,.0f}x"
        )
        print(
            "  The XSD compiles once per process. A worker generating one\n"
            "  batch per invocation pays that every time; a long-lived one\n"
            "  pays it once. Worth knowing before choosing a deployment\n"
            "  shape, and invisible to any benchmark reporting a mean."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--quick", action="store_true", help="small sizes, as CI runs"
    )
    args = parser.parse_args()

    results = run(quick=args.quick)
    if args.json:
        json.dump(results, sys.stdout, indent=1)
        print()
    else:
        render(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
