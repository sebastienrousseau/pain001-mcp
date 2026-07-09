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

"""Tests for the pain001 MCP server."""

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp.server.fastmcp import FastMCP  # noqa: E402

import pain001_mcp.server as server  # noqa: E402

EXPECTED_TOOLS = {
    "list_message_types",
    "get_required_fields",
    "get_input_schema",
    "validate_records",
    "validate_identifier",
    "generate_message",
    "generate_message_async",
    "generate_message_from_file",
    "list_supported_formats",
    "parse_camt053",
    "parse_pain002",
    "inspect_template",
    "validate_payment_scheme",
    # New in v0.0.53:
    "migrate_records",
    "validate_xml_against_schema",
    "sanitize_to_iso20022_charset",
}


def _registered_tool_names() -> set[str]:
    """Return the names of every tool registered on the FastMCP server.

    Prefers the synchronous ``_tool_manager.list_tools()`` introspection;
    falls back to the async ``list_tools()`` API if unavailable.
    """
    manager = getattr(server.server, "_tool_manager", None)
    if manager is not None and hasattr(manager, "list_tools"):
        return {tool.name for tool in manager.list_tools()}
    tools = asyncio.run(server.server.list_tools())
    return {tool.name for tool in tools}


# ---------------------------------------------------------------------------
# Server module wiring
# ---------------------------------------------------------------------------
def test_server_and_main_are_well_formed():
    """The module exposes a FastMCP server and a callable ``main``."""
    assert isinstance(server.server, FastMCP)
    assert callable(server.main)


def test_all_tools_registered():
    """All nine tools are registered on the server."""
    assert _registered_tool_names() == EXPECTED_TOOLS


# ---------------------------------------------------------------------------
# Message-type discovery tools
# ---------------------------------------------------------------------------
def test_list_message_types_returns_supported_versions():
    """The list tool reports every supported message type."""
    result = server.list_message_types()
    assert isinstance(result, list)
    assert len(result) >= 9
    assert all("message_type" in row and "name" in row for row in result)
    assert any(row["message_type"] == "pain.001.001.09" for row in result)
    assert any(row["message_type"].startswith("pain.008") for row in result)


def test_get_required_fields_returns_known_field():
    """Required fields for pain.001.001.09 include known mandatory keys."""
    fields = server.get_required_fields("pain.001.001.09")
    assert "id" in fields
    assert "debtor_account_IBAN" in fields


def test_get_input_schema_returns_properties():
    """The full schema includes a ``properties`` map."""
    schema = server.get_input_schema("pain.001.001.09")
    assert "properties" in schema
    assert "debtor_account_IBAN" in schema["properties"]


# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------
def test_validate_identifier_valid_and_invalid():
    """A known-good and known-bad IBAN are classified correctly."""
    good = server.validate_identifier("iban", "DE89370400440532013000")
    assert good["valid"] is True
    assert good["kind"] == "iban"
    assert "error" not in good

    bad = server.validate_identifier("iban", "NOTANIBAN")
    assert bad["valid"] is False
    assert "error" in bad


def test_validate_identifier_bic_round_trip():
    """A valid BIC succeeds, a malformed one fails with an error message."""
    good = server.validate_identifier("bic", "DEUTDEFFXXX")
    assert good["valid"] is True

    bad = server.validate_identifier("bic", "TOOSHORT")
    assert bad["valid"] is False
    assert "error" in bad


def test_validate_identifier_unsupported_kind_returns_error():
    """An unsupported identifier kind yields an error dict, not an exception."""
    result = server.validate_identifier("lei", "5493001KJTIIGC8Y1R12")
    assert "error" in result


# ---------------------------------------------------------------------------
# Record validation
# ---------------------------------------------------------------------------
def test_validate_records_reports_missing_required_fields():
    """Empty records report each missing required field."""
    report = server.validate_records("pain.001.001.09", [{}])
    assert report["valid"] is False
    assert report["valid_count"] == 0
    assert any("required" in err["message"] for err in report["errors"])


def test_validate_records_accepts_valid_record(sample_record):
    """A complete record validates cleanly."""
    report = server.validate_records(
        "pain.001.001.09", [json_safe_record(sample_record)]
    )
    assert report["valid"] is True
    assert report["valid_count"] == report["total"]


def json_safe_record(record: dict) -> dict:
    """Return a copy of ``record`` with values coerced to schema types."""
    coerced = dict(record)
    coerced["nb_of_txs"] = int(coerced["nb_of_txs"])
    coerced["ctrl_sum"] = float(coerced["ctrl_sum"])
    coerced["payment_amount"] = float(coerced["payment_amount"])
    coerced["batch_booking"] = coerced["batch_booking"] == "true"
    coerced["date"] = "2026-01-15T10:30:00"
    return coerced


# ---------------------------------------------------------------------------
# XML generation
# ---------------------------------------------------------------------------
def test_generate_message_returns_xml(sample_record):
    """Generating pain.001.001.09 yields a validated XML document."""
    xml = server.generate_message("pain.001.001.09", [sample_record])
    assert isinstance(xml, str)
    assert xml.lstrip().startswith("<?xml")
    assert "Document" in xml


def test_invalid_message_type_returns_error_dict():
    """An unsupported message type returns an ``{"error": ...}`` dict."""
    result = server.get_required_fields("pain.999.999.99")
    schema_result = server.get_input_schema("pain.999.999.99")
    assert isinstance(schema_result, dict)
    assert "error" in schema_result
    assert any("error" in str(item) for item in result)


def test_generate_message_error_is_serializable():
    """A failed generation returns a JSON-serializable error string."""
    out = server.generate_message("pain.999.999.99", [{}])
    payload = json.loads(out)
    assert "error" in payload


# ---------------------------------------------------------------------------
# Data-format discovery
# ---------------------------------------------------------------------------
def test_list_supported_formats_includes_csv_and_parquet():
    """The supported-formats tool reports the bundled data loaders."""
    formats = server.list_supported_formats()
    ids = {fmt["id"] for fmt in formats}
    assert {"csv", "sqlite", "json", "jsonl", "parquet"} <= ids
    assert all(
        {"id", "name", "extension"} <= set(fmt.keys()) for fmt in formats
    )


# ---------------------------------------------------------------------------
# Bank-reply parsers
# ---------------------------------------------------------------------------
def test_parse_camt053_invalid_path_returns_error(tmp_path):
    """A missing path returns an error payload, not an exception."""
    result = server.parse_camt053(str(tmp_path / "nope.xml"))
    assert "error" in result


def test_parse_pain002_invalid_path_returns_error(tmp_path):
    """A missing path returns an error payload, not an exception."""
    result = server.parse_pain002(str(tmp_path / "nope.xml"))
    assert "error" in result


def test_parse_camt053_parses_bundled_sample():
    """The bundled camt.053 sample parses to a header + entries structure."""
    sample = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "camt053_sample.xml"
    )
    if not sample.is_file():
        pytest.skip("camt.053 sample fixture not present")
    parsed = server.parse_camt053(str(sample))
    assert "error" not in parsed
    assert isinstance(parsed, dict)


def test_parse_pain002_parses_bundled_sample():
    """The bundled pain.002 sample parses to a header + status structure."""
    sample = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "pain002_sample.xml"
    )
    if not sample.is_file():
        pytest.skip("pain.002 sample fixture not present")
    parsed = server.parse_pain002(str(sample))
    assert "error" not in parsed
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# FastMCP dispatch layer (end-to-end through the protocol surface)
# ---------------------------------------------------------------------------
def test_call_tool_through_fastmcp():
    """Tools are invocable through the FastMCP dispatch layer."""

    async def go():
        result = await server.server.call_tool(
            "validate_identifier",
            {"kind": "iban", "value": "DE89370400440532013000"},
        )
        block = result[0] if isinstance(result, list | tuple) else result
        text = getattr(block, "text", None)
        if text is None and isinstance(result, tuple):
            text = json.dumps(result[1])
        return json.loads(text)

    payload = asyncio.run(go())
    assert payload["valid"] is True


def test_call_tool_list_supported_formats_through_fastmcp():
    """``list_supported_formats`` dispatches through FastMCP and serializes."""

    async def go():
        result = await server.server.call_tool("list_supported_formats", {})
        block = result[0] if isinstance(result, list | tuple) else result
        text = getattr(block, "text", None)
        if text is None and isinstance(result, tuple):
            text = json.dumps(result[1])
        return json.loads(text)

    payload = asyncio.run(go())
    # Newer FastMCP wraps list returns in ``{"result": [...]}`` when
    # serializing; older versions return the raw list. Accept both.
    items = payload["result"] if isinstance(payload, dict) else payload
    assert isinstance(items, list)
    assert any(fmt["id"] == "csv" for fmt in items)


# ---------------------------------------------------------------------------
# Coverage gates: rarely-hit defensive branches
# ---------------------------------------------------------------------------
# Note: pain001 >=0.0.51 ships JSON Schemas for every entry in
# ``valid_xml_types``, so the ``_load_schema`` "no schema bundled" branch
# and the ``validate_records`` error-payload branch it backs are defensive
# only. They are marked ``# pragma: no cover`` in ``pain001_mcp/server.py``.


def test_generate_message_template_missing_returns_error(
    sample_record, monkeypatch, tmp_path
):
    """``generate_message`` reports an error when bundled templates vanish."""
    monkeypatch.setattr(server, "TEMPLATES_DIR", tmp_path)
    out = server.generate_message("pain.001.001.09", [sample_record])
    payload = json.loads(out)
    assert "error" in payload
    assert "No template bundled" in payload["error"]


def test_generate_message_template_xml_missing(
    sample_record, monkeypatch, tmp_path
):
    """The "no template" branch fires when only the XSD half is missing."""
    md = tmp_path / "pain.001.001.09"
    md.mkdir()
    # Provide the XSD but not the template.xml so the ``or not is_file()``
    # right-hand operand is the trigger.
    (md / "pain.001.001.09.xsd").write_text("<schema/>")
    monkeypatch.setattr(server, "TEMPLATES_DIR", tmp_path)
    out = server.generate_message("pain.001.001.09", [sample_record])
    assert "No template bundled" in json.loads(out)["error"]


def test_main_runs_the_fastmcp_server(monkeypatch):
    """``main()`` is a thin wrapper around ``server.run``."""
    calls: list[tuple] = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(server.server, "run", fake_run)
    server.main()
    assert calls == [((), {})]


# ---------------------------------------------------------------------------
# Async + file-driven tools
# ---------------------------------------------------------------------------
def test_generate_message_async_returns_xml(sample_record):
    """The async wrapper produces the same XML as ``generate_message``."""
    xml = asyncio.run(
        server.generate_message_async("pain.001.001.09", [sample_record])
    )
    assert xml.lstrip().startswith("<?xml")
    assert "Document" in xml


def test_generate_message_async_unknown_type_returns_error():
    """An unsupported message type yields a JSON-encoded error payload."""
    out = asyncio.run(server.generate_message_async("pain.999.999.99", [{}]))
    payload = json.loads(out)
    assert "error" in payload


def test_generate_message_async_template_missing_returns_error(
    sample_record, monkeypatch, tmp_path
):
    """``generate_message_async`` mirrors the template-missing defensive path."""
    monkeypatch.setattr(server, "TEMPLATES_DIR", tmp_path)
    out = asyncio.run(
        server.generate_message_async("pain.001.001.09", [sample_record])
    )
    payload = json.loads(out)
    assert "No template bundled" in payload["error"]


def test_generate_message_from_file_round_trip(
    sample_record, tmp_path, monkeypatch
):
    """A CSV on disk renders to the same XML as in-memory records.

    ``pain001.security.validate_path`` constrains data files to the
    current working directory, so the test ``chdir``s into ``tmp_path``
    before writing the CSV.
    """
    monkeypatch.chdir(tmp_path)
    fields = list(sample_record.keys())
    csv_path = tmp_path / "payments.csv"
    csv_path.write_text(
        ",".join(fields)
        + "\n"
        + ",".join(str(sample_record[k]) for k in fields)
        + "\n"
    )
    xml = server.generate_message_from_file("pain.001.001.09", "payments.csv")
    assert xml.lstrip().startswith("<?xml")


def test_generate_message_from_file_missing_path_returns_error(tmp_path):
    """A missing CSV path returns a JSON-encoded error, not an exception."""
    out = server.generate_message_from_file(
        "pain.001.001.09", str(tmp_path / "nope.csv")
    )
    assert "error" in json.loads(out)


# ---------------------------------------------------------------------------
# Path-traversal regression on the bank-reply parsers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "/dev/null",
    ],
)
def test_parse_camt053_rejects_traversal_paths(path):
    """The MCP parser surface never opens caller-supplied escape paths."""
    result = server.parse_camt053(path)
    assert "error" in result


@pytest.mark.parametrize(
    "path",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "/dev/null",
    ],
)
def test_parse_pain002_rejects_traversal_paths(path):
    """The MCP parser surface never opens caller-supplied escape paths."""
    result = server.parse_pain002(path)
    assert "error" in result


# ---------------------------------------------------------------------------
# Examples kept honest: import + execute so coverage catches drift
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Ported in-tree features (parity with pain001.mcp.server)
# ---------------------------------------------------------------------------
def test_inspect_template_returns_columns_for_known_type():
    """``inspect_template`` lists the bundled CSV columns."""
    result = server.inspect_template("pain.001.001.09")
    assert result["message_type"] == "pain.001.001.09"
    assert isinstance(result["columns"], list)
    assert "id" in result["columns"]
    assert "debtor_account_IBAN" in result["columns"]


def test_inspect_template_unknown_type_returns_error():
    """An unsupported type yields an ``{"error": ...}`` payload."""
    out = server.inspect_template("pain.999.999.99")
    assert "error" in out


def test_inspect_template_missing_file_returns_error(monkeypatch, tmp_path):
    """Missing bundled CSV template surfaces a defensive error."""
    monkeypatch.setattr(server, "TEMPLATES_DIR", tmp_path)
    out = server.inspect_template("pain.001.001.09")
    assert "No bundled CSV template" in out["error"]


def test_validate_payment_scheme_reports_violations_for_bad_rows():
    """A clearly invalid record set produces structured violations."""
    bad_rows = [{"id": "X", "payment_amount": "0", "currency": "EUR"}]
    out = server.validate_payment_scheme(bad_rows, "sepa-sct")
    assert out["profile"] == "sepa-sct"
    assert out["is_valid"] is False
    assert isinstance(out["violations"], list)
    assert out["violations"], "expected at least one violation"


def test_validate_payment_scheme_unknown_profile_returns_error():
    """An unknown profile yields an error payload, not an exception."""
    out = server.validate_payment_scheme([], "definitely-not-a-profile")
    assert "error" in out


def test_schema_resource_returns_xsd_text_for_known_type():
    """The resource handler returns the bundled XSD text."""
    text = server.schema_resource("pain.001.001.09")
    assert "<?xml" in text or "<xs:schema" in text


def test_schema_resource_unknown_type_raises():
    """An unsupported type raises ``ValueError`` per MCP resource semantics."""
    with pytest.raises(ValueError):
        server.schema_resource("pain.999.999.99")


def test_build_payment_batch_prompt_mentions_message_type():
    """The prompt template names the requested message type."""
    prompt = server.build_payment_batch("pain.001.001.11")
    assert "pain.001.001.11" in prompt
    assert "inspect_template" in prompt
    assert "validate_records" in prompt


def test_build_payment_batch_prompt_default_type():
    """The default prompt targets pain.001.001.09."""
    prompt = server.build_payment_batch()
    assert "pain.001.001.09" in prompt


@pytest.mark.parametrize(
    "module_path",
    [
        "examples/01_mcp_tools.py",
        "examples/02_validate_pipeline.py",
        "examples/03_parse_bank_replies.py",
    ],
)
def test_example_scripts_run_without_error(module_path, capsys):
    """Each example script imports and runs end-to-end.

    Catches breakage at the test-suite level instead of only when a
    human runs ``make examples``.
    """
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / module_path
    spec = importlib.util.spec_from_file_location(
        f"_example_{path.stem}", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        main_fn = getattr(module, "main", None)
        if callable(main_fn):
            result = main_fn()
            if asyncio.iscoroutine(result):
                asyncio.run(result)
    finally:
        sys.modules.pop(spec.name, None)
    assert capsys.readouterr().out


# ---------------------------------------------------------------------------
# New in v0.0.53: migrate / validate_xml / sanitize tools
# ---------------------------------------------------------------------------
def test_migrate_records_round_trip(sample_record):
    """Migrating a record across versions returns the migrated rows + summary."""
    result = server.migrate_records(
        records=[sample_record],
        from_version="pain.001.001.03",
        to_version="pain.001.001.09",
    )
    assert "error" not in result, result
    assert result["from"] == "pain.001.001.03"
    assert result["to"] == "pain.001.001.09"
    assert result["migrated"] == 1
    assert isinstance(result["records"], list)
    assert result["records"]


def test_migrate_records_unsupported_version_returns_error(sample_record):
    """An unknown version yields a structured error payload, not a raise."""
    result = server.migrate_records(
        records=[sample_record],
        from_version="pain.001.001.03",
        to_version="pain.999.999.99",
    )
    assert "error" in result


def test_validate_xml_against_schema_accepts_valid_doc(sample_record):
    """A freshly-generated XML validates against its bundled XSD."""
    xml = server.generate_message("pain.001.001.09", [sample_record])
    assert xml.lstrip().startswith("<?xml")
    out = server.validate_xml_against_schema(xml, "pain.001.001.09")
    assert out == {"valid": True, "message_type": "pain.001.001.09"}


def test_validate_xml_against_schema_rejects_garbage():
    """An invalid XML payload is rejected; ``error`` appears only when raised."""
    out = server.validate_xml_against_schema(
        "<not-pain001/>", "pain.001.001.09"
    )
    assert out["valid"] is False
    assert out["message_type"] == "pain.001.001.09"


def test_validate_xml_against_schema_unknown_type():
    """An unsupported message type returns an error dict, not an exception."""
    out = server.validate_xml_against_schema(
        "<?xml version='1.0'?><x/>", "pain.999.999.99"
    )
    assert "error" in out


def test_sanitize_to_iso20022_charset_passthrough_for_clean_input():
    """Already-valid input round-trips with ``changed=False``."""
    out = server.sanitize_to_iso20022_charset("Acme GmbH")
    assert out == {
        "value": "Acme GmbH",
        "sanitised": "Acme GmbH",
        "was_valid": True,
        "changed": False,
    }


def test_sanitize_to_iso20022_charset_transliterates_accents():
    """Accented input is transliterated and marked as ``changed``."""
    out = server.sanitize_to_iso20022_charset("Café Müller")
    assert out["changed"] is True
    assert out["was_valid"] is False
    # The exact transliteration is pain001's concern; the contract here
    # is that the sanitised form differs and is no longer the original.
    assert out["sanitised"] != "Café Müller"
