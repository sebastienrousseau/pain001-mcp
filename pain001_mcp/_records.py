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

"""Record tools: schema checks, identifiers, fixes, migration, charset, MT101.

Each tool works on the records or text it is given; none reads or
writes a file.
"""

import unicodedata
from typing import Annotated, Any, Literal

from jsonschema import Draft7Validator
from pain001 import canonicalize_payment_record, sanitize_to_charset
from pain001.exceptions import PaymentValidationError
from pain001.migration import VersionMapper
from pain001.validation import validate_bic, validate_iban
from pain001.validation.charset import ISO20022_ALLOWED_CHARACTERS
from pain001_loader_mt101.loader import parse_mt101
from pydantic import Field

from pain001_mcp._common import (
    _check_message_type,
    _identifier_findings,
    _IdentifierChecks,
    _load_schema,
    _MessageType,
    _refuse_mixed_batch,
)
from pain001_mcp._shapes import (
    MigrateResult,
    RecordError,
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


def _record_errors(
    validator: Draft7Validator, row: int, record: dict
) -> list[RecordError]:
    """Return one entry per schema violation in ``record``, by path."""
    return [
        {
            "row": row,
            "path": ".".join(str(p) for p in err.path),
            "message": err.message,
        }
        for err in sorted(
            validator.iter_errors(record), key=lambda e: list(e.path)
        )
    ]


def _identifier_record_errors(records: list[dict]) -> list[RecordError]:
    """Return one row error per invalid IBAN or BIC column."""
    return [
        {"row": row, "path": column, "message": reason}
        for row, column, reason in _identifier_findings(records)
    ]


def validate_records(
    message_type: _MessageType,
    records: _RecordsToValidate,
    identifier_checks: _IdentifierChecks = True,
) -> ValidateRecordsResult:
    """Validate flat records against a message type's input JSON Schema.

    Use this before ``generate_message`` to catch structural/type errors
    per record and get a row-by-row error report. Like the pain001 CLI,
    it also checks every IBAN and BIC (unless ``identifier_checks`` is
    false) and refuses rows that would not share one payment information
    block. For payment-scheme rulebook checks (SEPA field lengths,
    charset, etc.) also run ``validate_payment_scheme``.

    Returns a report ``{"valid": bool, "total": int, "valid_count": int,
    "errors": [...]}``, or ``{"error": ...}`` for a mixed batch.

    Args:
        message_type: A supported ISO 20022 pain message type.
        records: One or more flat payment records to validate.
        identifier_checks: If false, skip the IBAN and BIC checks.
    """
    try:
        schema = _load_schema(message_type)
        _refuse_mixed_batch(records, _check_message_type(message_type))
    except (ValueError, PaymentValidationError) as exc:
        return {"error": str(exc)}

    # Map alias keys ('amount', 'currency', lower-case IBAN/BIC spellings)
    # to their canonical names, exactly as generate_message will, so a
    # record that generates cleanly also validates cleanly. Values keep
    # their JSON types; only key names are rewritten.
    records = [canonicalize_payment_record(record) for record in records]

    validator = Draft7Validator(schema)
    errors = [
        error
        for row, record in enumerate(records)
        for error in _record_errors(validator, row, record)
    ]
    if identifier_checks:
        errors += _identifier_record_errors(records)
        errors.sort(key=lambda error: error["row"])
    invalid_rows = {error["row"] for error in errors}
    return {
        "valid": not errors,
        "total": len(records),
        "valid_count": len(records) - len(invalid_rows),
        "errors": errors,
    }


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
