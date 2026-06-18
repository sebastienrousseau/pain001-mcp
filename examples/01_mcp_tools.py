#!/usr/bin/env python3
"""Example: call the pain001-mcp server's tools in-process.

Usage:
    pip install pain001-mcp     # requires Python 3.10+
    python examples/mcp_tools.py

The pain001 MCP server (launched as ``pain001-mcp`` over stdio) exposes the
pain001 library to AI agents. This example invokes the same tools directly
through the FastMCP instance, without a transport, to show what an agent
would receive.
"""

import asyncio

from pain001_mcp.server import server

# A single flat payment record rendering to a valid pain.001.001.09 XML.
record = [
    {
        "id": "MSG-0001",
        "date": "2026-01-15T10:30:47.000Z",
        "nb_of_txs": "1",
        "initiator_name": "Acme Embedded Finance Ltd",
        "initiator_street_name": "Threadneedle Street",
        "initiator_building_number": "1",
        "initiator_postal_code": "EC2R8AH",
        "initiator_town_name": "London",
        "initiator_country_code": "GB",
        "payment_information_id": "PMT-INFO-0001",
        "payment_method": "TRF",
        "batch_booking": "false",
        "requested_execution_date": "2026-01-20",
        "debtor_name": "Acme Embedded Finance Ltd",
        "debtor_street_name": "Threadneedle Street",
        "debtor_building_number": "1",
        "debtor_postal_code": "EC2R8AH",
        "debtor_town_name": "London",
        "debtor_country_code": "GB",
        "debtor_account_IBAN": "DE89370400440532013000",
        "debtor_agent_BIC": "DEUTDEFFXXX",
        "charge_bearer": "SLEV",
        "payment_id": "PAY-0001",
        "payment_amount": "100",
        "currency": "EUR",
        "payment_currency": "EUR",
        "ctrl_sum": "100",
        "creditor_agent_BIC": "NWBKGB2LXXX",
        "creditor_name": "National Westminster Bank",
        "creditor_street_name": "Bishopsgate",
        "creditor_building_number": "250",
        "creditor_postal_code": "EC2M4AA",
        "creditor_town_name": "London",
        "creditor_country_code": "GB",
        "creditor_account_IBAN": "GB29NWBK60161331926819",
        "purpose_code": "OTHR",
        "reference_number": "INV-0001",
        "reference_date": "2026-01-14",
        "service_level_code": "SEPA",
        "forwarding_agent_BIC": "DEUTDEFFXXX",
        "remittance_information": "Invoice 0001",
        "charge_account_IBAN": "DE89370400440532013000",
    }
]


async def main() -> None:
    tools = await server.list_tools()
    print("Registered MCP tools:", [t.name for t in tools])

    async def call(name, args):
        result = await server.call_tool(name, args)
        # FastMCP returns a (content, structured) tuple or content blocks;
        # pull the first text payload for display.
        content = result[0] if isinstance(result, tuple) else result
        text = content[0].text if content else ""
        return text

    print(
        "list_message_types  ->",
        (await call("list_message_types", {}))[:60],
        "…",
    )
    print(
        "validate_identifier ->",
        await call(
            "validate_identifier",
            {"kind": "iban", "value": "DE89370400440532013000"},
        ),
    )
    xml = await call(
        "generate_message",
        {"message_type": "pain.001.001.09", "records": record},
    )
    print("generate_message    ->", xml[:46], "…")


if __name__ == "__main__":
    asyncio.run(main())
