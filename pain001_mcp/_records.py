# SPDX-FileCopyrightText: 2023-2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Record tools: schema checks, identifiers, fixes, migration, charset, MT101.

Each tool works on the records or text it is given; none reads or
writes a file.
"""

import unicodedata
from typing import Annotated, Any, Literal

from pain001 import sanitize_to_charset
from pain001.migration import VersionMapper
from pain001.validation import validate_bic, validate_iban
from pain001.validation.charset import ISO20022_ALLOWED_CHARACTERS
from pain001_loader_mt101.loader import parse_mt101
from pydantic import Field

from pain001_mcp._common import (
    _check_message_type,
    _IdentifierChecks,
    _MessageType,
)
from pain001_mcp._ladder import verdict
from pain001_mcp._shapes import (
    MigrateResult,
    SanitiseResult,
    ValidateIdentifierResult,
    ValidateRecordsResult,
)

# SWIFT extended ("Z") character set. The pain001 library only implements the
# SWIFT basic ("X") set (``ISO20022_ALLOWED_CHARACTERS``). The Z set is a strict
# superset that additionally permits the following 13 punctuation characters,
# per the SWIFT Standards MT General Information character-set definitions:
#
#     = ! " % & * < > ; { @ # _
#
# (Note: the Z set does NOT include the vertical bar ``|`` or the closing brace
# ``}`` — a ``}`` in a Z-charset field raises SWIFT error M60.) Deriving the Z
# set from the library's X set keeps the two in lockstep if pain001 ever revises
# its base table.
_SWIFT_Z_EXTRA_CHARACTERS: frozenset[str] = frozenset('=!"%&*<>;{@#_')
_SWIFT_Z_ALLOWED_CHARACTERS: frozenset[str] = (
    ISO20022_ALLOWED_CHARACTERS | _SWIFT_Z_EXTRA_CHARACTERS
)


def _sanitize_to_swift_z(value: str, replacement: str = " ") -> str:
    """Transliterate ``value`` into the SWIFT extended ("Z") character set.

    Mirrors :func:`pain001.sanitize_to_charset` (NFKD-decompose, drop combining
    marks, then replace anything outside the permitted set) but validates
    against the wider SWIFT Z set rather than the basic X set, so extended
    punctuation such as ``@``, ``&`` and ``_`` survives.

    Args:
        value: The text to transliterate.
        replacement: The string substituted for characters that are outside
            the Z set even after transliteration (default: a single space).

    Returns:
        A string containing only SWIFT Z permitted characters.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    return "".join(
        ch if ch in _SWIFT_Z_ALLOWED_CHARACTERS else replacement
        for ch in stripped
    )


_RecordsToValidate = Annotated[
    list[dict],
    Field(
        description=(
            "One or more flat payment records to validate, each a dict "
            "of field name → value (see get_input_schema for the fields "
            "and get_required_fields for the mandatory ones)."
        )
    ),
]


def validate_records(
    message_type: _MessageType,
    records: _RecordsToValidate,
    identifier_checks: _IdentifierChecks = True,
) -> ValidateRecordsResult:
    """Validate flat records the way the pain001 CLI and REST API do.

    Use this before ``generate_message``: it runs the core's validation
    ladder (pain001.validate), so a batch it accepts is one the CLI,
    the REST API and ``generate_message`` accept, and a batch it
    refuses is refused there too. The ladder checks the row contract
    (required fields, amounts, booleans, dates), every IBAN and BIC
    (unless ``identifier_checks`` is false), that the rows form one
    payment information block, then the message type's JSON Schema
    (for example an ISO 4217 currency). For payment-scheme rulebook
    checks (SEPA field lengths, charset, etc.) also run
    ``validate_payment_scheme``.

    The row contract and identifier checks refuse the batch as a whole
    (``valid_count`` 0) and name the first problems; the schema check
    then reports every row. Each error carries ``row`` (from 0),
    ``line`` (from 1), ``path`` (the field), ``code`` (the core's
    stable ``P001-E...`` issue code) and ``message``, which never
    repeats the value.

    Returns a report ``{"valid": bool, "total": int, "valid_count": int,
    "errors": [...]}``, or ``{"error": ...}`` for rows that do not form
    one batch, an empty list or an unknown message type.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records to validate.
        identifier_checks: If false, skip the IBAN and BIC checks.
    """
    try:
        message_type = _check_message_type(message_type)
    except ValueError as exc:
        return {"error": str(exc)}
    return verdict(message_type, records, identifier_checks)


def suggest_record_fix(
    record: Annotated[
        dict[str, Any],
        Field(description="One flat payment record; never modified."),
    ],
    validation_error: Annotated[
        dict[str, Any],
        Field(description="Finding with field (or path) and rule keys."),
    ],
    message_type: _MessageType = "pain.001.001.03",
) -> dict[str, Any]:
    """Suggest deterministic, review-only fixes to non-financial fields.

    Returns patches or a cannot_autofix reason. Never changes IBANs, BICs,
    accounts, amounts or currencies, even for whitespace. Review every
    candidate and validate the full record before generating a payment.

    Args:
        record: A flat payment record, left unchanged.
        validation_error: Finding with field (or path) and rule keys.
        message_type: Supported schema supplying trusted field bounds.
    """
    try:
        from pain001.validation.corrections import (
            suggest_record_fix as suggest,
        )
    except ImportError:
        return {
            "error": "This tool requires the matching core feature build with record corrections."
        }
    try:
        return suggest(
            record, validation_error, _check_message_type(message_type)
        )
    except ValueError as exc:
        return {"error": str(exc)}


def validate_identifier(
    kind: Annotated[
        str,
        Field(
            description=(
                "Which identifier to validate: 'iban' or 'bic' "
                "(case-insensitive). Any other value returns an error."
            )
        ),
    ],
    value: Annotated[
        str,
        Field(
            description=(
                "The identifier string to check — an IBAN or BIC/SWIFT code "
                "matching the chosen kind."
            )
        ),
    ],
) -> ValidateIdentifierResult:
    """Validate a single financial identifier (IBAN or BIC).

    Use this for a one-off identifier check with a clear pass/fail and
    reason. To validate identifiers embedded across a whole batch, prefer
    ``validate_records`` / ``validate_payment_scheme`` instead of calling
    this per field.

    Returns ``{"kind": str, "value": str, "valid": bool, "error": str}``
    (the ``error`` key is present only when ``valid`` is ``False``).

    Args:
        kind: One of ``"iban"`` or ``"bic"`` (case-insensitive).
        value: The identifier value to check.
    """
    try:
        kind_norm = kind.lower()
        if kind_norm == "iban":
            ok, err = validate_iban(value, strict=False)
        elif kind_norm == "bic":
            ok, err = validate_bic(value, strict=False)
        else:
            raise ValueError(
                f"Unsupported identifier kind: {kind!r} "
                f"(expected 'iban' or 'bic')"
            )
        payload: ValidateIdentifierResult = {
            "kind": kind_norm,
            "value": value,
            "valid": bool(ok),
        }
        if not ok and err:
            payload["error"] = err
        return payload
    except ValueError as exc:
        return {"error": str(exc)}


_RecordsToMigrate = Annotated[
    list[dict],
    Field(
        description=(
            "Flat payment records in the from_version shape, each a dict "
            "of field name → value, to transform to to_version."
        )
    ),
]
_FromVersion = Annotated[
    str,
    Field(
        description=(
            "Source pain.001 schema version the records currently use, "
            "e.g. 'pain.001.001.03' — see list_message_types."
        )
    ),
]
_ToVersion = Annotated[
    str,
    Field(
        description=(
            "Target pain.001 schema version to migrate the records to, "
            "e.g. 'pain.001.001.09' — see list_message_types."
        )
    ),
]


def migrate_records(
    records: _RecordsToMigrate,
    from_version: _FromVersion,
    to_version: _ToVersion,
) -> MigrateResult:
    """Migrate flat payment records between two pain.001 schema versions.

    Use this to upgrade/downgrade records when your bank requires a
    different pain.001 version than your source data uses (e.g. move
    ``.03`` rows to ``.09``); it reports which fields were renamed, derived,
    or dropped. This transforms records only — run ``validate_records``
    afterwards, then ``generate_message`` to emit XML.

    Wraps :class:`pain001.migration.VersionMapper`. Returns the
    migrated rows plus a summary of which fields were renamed,
    derived, or dropped; ``{"error": ...}`` if either version is
    unsupported.

    Args:
        records: Records in the ``from_version`` shape.
        from_version: Source pain.001 version (e.g. ``"pain.001.001.03"``).
        to_version: Target pain.001 version (e.g. ``"pain.001.001.09"``).

    Returns:
        ``{"records": [...], "migrated": int, "from": str, "to": str}``
        or ``{"error": ...}``.
    """
    try:
        mapper = VersionMapper()
        migrated = mapper.migrate_rows(records, from_version, to_version)
        return {
            "records": migrated,
            "migrated": len(migrated),
            "from": from_version,
            "to": to_version,
        }
    except Exception as exc:  # noqa: BLE001 - DataSourceError + others
        return {"error": str(exc)}


_FreeText = Annotated[
    str,
    Field(
        description=(
            "A single free-text field value (e.g. a name or remittance "
            "line) to transliterate to the ISO 20022 Latin character set."
        )
    ),
]
_Charset = Annotated[
    Literal["SWIFT_X", "SWIFT_Z"],
    Field(
        description=(
            "Which SWIFT character set to sanitise against. 'SWIFT_X' "
            "(default) is the basic set permitted in most ISO 20022 / "
            "pain.001 fields: letters, digits, space and the punctuation "
            "/ - ? : ( ) . , ' + . 'SWIFT_Z' is the extended superset that "
            'additionally allows = ! " % & * < > ; { @ # _ (used in '
            "narrative / envelope fields); it does NOT allow | or }. Pick "
            "SWIFT_Z only when the target field is documented as Z-set."
        )
    ),
]


def sanitize_to_iso20022_charset(
    value: _FreeText,
    charset: _Charset = "SWIFT_X",
) -> SanitiseResult:
    """Sanitise one free-text field to a SWIFT / ISO 20022 character set.

    Use this on a single free-text value (name, remittance info) to
    transliterate accents and drop unsupported symbols before placing it in
    a record, and to see whether the value changed. Operates on one string;
    to check a whole batch's rulebook compliance use ``validate_payment_scheme``.

    Two character sets are supported via ``charset``:

    * ``"SWIFT_X"`` (default, backward-compatible) - the basic set used in
      most ISO 20022 / pain.001 fields. Delegates to
      :func:`pain001.sanitize_to_charset`.
    * ``"SWIFT_Z"`` - the SWIFT extended set, a strict superset of X that also
      permits ``= ! " % & * < > ; { @ # _`` (used in narrative / envelope
      fields). It does not permit ``|`` or ``}``.

    In both cases accents are transliterated (``é`` -> ``e``) and any remaining
    out-of-set character is replaced with a space. The result includes flags
    for whether the original was already valid and whether it changed - useful
    for surfacing the change to the user before writing it back to a record.

    Args:
        value: The text to sanitise.
        charset: ``"SWIFT_X"`` (default) or ``"SWIFT_Z"``.

    Returns:
        ``{"value": str, "sanitised": str, "was_valid": bool, "changed": bool}``.
    """
    if charset == "SWIFT_Z":
        cleaned = _sanitize_to_swift_z(value)
    else:
        cleaned = sanitize_to_charset(value)
    return {
        "value": value,
        "sanitised": cleaned,
        "was_valid": cleaned == value,
        "changed": cleaned != value,
    }


def convert_mt101(
    mt101_text: Annotated[
        str,
        Field(
            description=(
                "A legacy SWIFT MT101 (Request for Transfer) message as text "
                "— a bare ':tag:' field list or a raw '{4:...-}' block-4 "
                "envelope. An MT101 may carry several sequence-B transfers; "
                "each becomes its own record."
            )
        ),
    ],
) -> list[dict] | dict:
    """Convert a legacy SWIFT MT101 message into pain.001-ready records.

    Use this to bridge the Nov-2025+ SWIFT MT→MX migration: parse an MT101
    (*Request for Transfer*) into the flat records the other tools consume —
    feed the result straight to ``validate_records`` /
    ``validate_payment_scheme`` and then ``generate_message`` to emit
    pain.001.001.09 XML. An MT101 can request many transfers (repeating
    sequence B), so this returns *one record per transaction*. Operates on
    the supplied text only; no file is read or written.

    Wraps :func:`pain001_loader_mt101.loader.parse_mt101`. Sequence-A
    ordering-customer / account-servicing fields apply to every transaction
    unless a sequence-B block overrides them; fields the MT101 does not
    carry are synthesised to schema defaults (``payment_method`` ``"TRF"``,
    ``service_level_code`` ``"SEPA"``, etc.).

    Args:
        mt101_text: The MT101 payload as a string.

    Returns:
        A list of flat pain.001 records (one per transaction), or an
        ``{"error": ...}`` dict if the MT101 is missing a mandatory field
        (``:20:``, ``:30:``, or per transaction ``:21:`` / ``:32B:`` /
        a named beneficiary) or is otherwise malformed.
    """
    try:
        return parse_mt101(mt101_text)
    except ValueError as exc:
        return {"error": str(exc)}
