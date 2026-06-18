#!/usr/bin/env python3
"""Example: progressively validate a payment record with the MCP tools.

Usage:
    pip install pain001-mcp     # requires Python 3.10+
    python examples/02_validate_pipeline.py

Shows how an agent would chain three tools to give a user fine-grained
feedback before generating XML:

1. ``get_required_fields`` — confirm we know the input contract.
2. ``validate_records`` — surface every schema violation.
3. ``validate_identifier`` — double-check IBAN and BIC values one by one.
"""

from pain001_mcp.server import (
    get_required_fields,
    validate_identifier,
    validate_records,
)

MESSAGE_TYPE = "pain.001.001.09"

incomplete_record = {
    "id": "MSG-0001",
    "date": "2026-01-15T10:30:00",
    "nb_of_txs": 1,
    "ctrl_sum": 100.00,
    "debtor_account_IBAN": "NOTANIBAN",
    "creditor_agent_BIC": "TOOSHORT",
}


def main() -> None:
    """Demonstrate a validate-then-fix loop."""
    required = get_required_fields(MESSAGE_TYPE)
    missing = [
        field for field in required if field not in incomplete_record
    ]
    print(f"missing required fields: {len(missing)} (first 5: {missing[:5]})")

    report = validate_records(MESSAGE_TYPE, [incomplete_record])
    print(f"schema errors: {len(report['errors'])} (valid={report['valid']})")

    for field, kind in [
        ("debtor_account_IBAN", "iban"),
        ("creditor_agent_BIC", "bic"),
    ]:
        result = validate_identifier(kind, incomplete_record[field])
        marker = "OK" if result["valid"] else "ERR"
        print(f"  [{marker}] {field}={incomplete_record[field]!r}")


if __name__ == "__main__":
    main()
