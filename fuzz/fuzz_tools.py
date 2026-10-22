# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Coverage-guided fuzzing of the text-taking MCP tools with Atheris.

Each input is split into a message type, an identifier, a list of flat
records and a free-text payload, and fed to every tool that takes
untrusted text: identifier, record and XSD validation, charset
sanitising, record migration, fix suggestions and MT101 conversion. A
tool must answer with a dict or a list -- a result or an ``{"error":
...}`` payload -- and never raise; anything else is a crash libFuzzer
reports and minimises.

Run (Linux x86_64, Python 3.12)::

    pip install --require-hashes -r requirements/fuzz.txt
    pip install --no-deps -e .
    python fuzz/fuzz_tools.py -max_total_time=60
"""

import sys

import atheris

with atheris.instrument_imports():
    import pain001_mcp.server as srv

# Real message types and charsets, so validation is reached as well as
# rejected.
MESSAGE_TYPES = ("pain.001.001.03", "pain.001.001.09", "pain.008.001.02", "")
CHARSETS = ("SWIFT_X", "SWIFT_Z", "")
KINDS = ("iban", "bic", "")


def _records(fdp: atheris.FuzzedDataProvider) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for _ in range(fdp.ConsumeIntInRange(0, 3)):
        record: dict[str, object] = {}
        for _ in range(fdp.ConsumeIntInRange(0, 6)):
            key = fdp.ConsumeUnicodeNoSurrogates(20)
            record[key] = fdp.PickValueInList(
                [
                    None,
                    fdp.ConsumeBool(),
                    fdp.ConsumeInt(8),
                    fdp.ConsumeUnicodeNoSurrogates(40),
                ]
            )
        out.append(record)
    return out


def test_one_input(data: bytes) -> None:
    """Drive every text-taking tool with one fuzzer input."""
    fdp = atheris.FuzzedDataProvider(data)
    message_type = fdp.PickValueInList(list(MESSAGE_TYPES))
    message_type += fdp.ConsumeUnicodeNoSurrogates(4)
    kind = fdp.PickValueInList(list(KINDS))
    charset = fdp.PickValueInList(list(CHARSETS))
    value = fdp.ConsumeUnicodeNoSurrogates(64)
    records = _records(fdp)
    text = fdp.ConsumeUnicodeNoSurrogates(4096)

    for result in (
        srv.validate_identifier(kind, value),
        srv.validate_records(message_type, records),
        srv.validate_xml_against_schema(text, message_type),
        srv.sanitize_to_iso20022_charset(value, charset),
        srv.migrate_records(records, message_type, "pain.001.001.09"),
        srv.suggest_record_fix(
            records[0] if records else {}, {"field": value, "rule": kind}
        ),
        srv.convert_mt101(text),
    ):
        if not isinstance(result, (dict, list)):
            raise TypeError(f"tool returned {type(result).__name__}")


def main() -> None:
    """Hand the harness to libFuzzer."""
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
