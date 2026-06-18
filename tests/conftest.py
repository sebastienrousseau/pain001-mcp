"""Shared fixtures for the pain001-mcp test suite."""

import pytest

_RECORD = {
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


@pytest.fixture
def sample_record() -> dict:
    """A complete payment record rendering to a valid pain.001.001.09 XML."""
    return dict(_RECORD)
