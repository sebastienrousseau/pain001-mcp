#!/usr/bin/env python3
"""Example: parse a camt.053 statement and a pain.002 status report.

Usage:
    pip install pain001-mcp     # requires Python 3.10+
    python examples/03_parse_bank_replies.py \\
        path/to/camt053.xml path/to/pain002.xml

When run without arguments, the script falls back to the bundled fixtures
shipped under ``tests/fixtures/`` so it remains self-contained.
"""

import json
import sys
from pathlib import Path

from pain001_mcp.server import parse_camt053, parse_pain002

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
DEFAULT_CAMT053 = FIXTURES / "camt053_sample.xml"
DEFAULT_PAIN002 = FIXTURES / "pain002_sample.xml"


def main() -> None:
    """Parse the camt.053 statement and pain.002 report and print summaries."""
    if len(sys.argv) >= 3:
        camt053_path, pain002_path = sys.argv[1], sys.argv[2]
    else:
        camt053_path = str(DEFAULT_CAMT053)
        pain002_path = str(DEFAULT_PAIN002)

    camt053 = parse_camt053(camt053_path)
    pain002 = parse_pain002(pain002_path)

    print(f"camt.053 ({camt053_path}):")
    print(json.dumps(camt053, indent=2, default=str)[:400], "…")

    print()
    print(f"pain.002 ({pain002_path}):")
    print(json.dumps(pain002, indent=2, default=str)[:400], "…")


if __name__ == "__main__":
    main()
