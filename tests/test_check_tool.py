# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Tests for ``check_payment_file``, the core's check over MCP.

The checker ships in pain001 0.0.82. ``_check_api`` is driven through
``importlib`` so the absent branch is covered whichever pain001 is
installed; the other tests run against the real library and are
skipped without it.
"""

from __future__ import annotations

import asyncio
import importlib
import json

import pytest
from pain001.corpus import list_files

import pain001_mcp.server as server
from pain001_mcp import _check

real = pytest.mark.skipif(
    _check._check_api() is None, reason="installed pain001 has no checker"
)


def _coverage(version: str) -> str:
    path = next(
        f.path
        for f in list_files("coverage")
        if f.version == version and f.path.name.startswith("01-")
    )
    return path.read_text(encoding="utf-8")


def test_check_api_without_the_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> None:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", missing)
    assert _check._check_api() is None


def test_an_older_core_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_check, "_check_api", lambda: None)
    assert _check.check_payment_file("<x/>") == {"error": _check.CHECK_MISSING}


@real
@pytest.mark.parametrize("version", ["pain.001.001.09", "pain.008.001.08"])
def test_a_valid_file_passes(version: str) -> None:
    result = _check.check_payment_file(_coverage(version))
    assert result["message_type"] == version
    assert result["passed"] is True
    assert result["rungs"] == ["xsd", "mdr"]
    assert result["findings"] == []


@real
def test_every_problem_comes_back_at_once() -> None:
    bad = _coverage("pain.001.001.09").replace(
        "<NbOfTxs>", "<Foo>x</Foo><NbOfTxs>", 1
    )
    result = _check.check_payment_file(bad, scheme="sepa-sct")
    assert result["passed"] is False
    assert result["rungs"] == ["xsd", "mdr", "scheme"]
    rungs = {finding["rung"] for finding in result["findings"]}
    assert {"xsd", "scheme"} <= rungs


@real
def test_a_schematron_preset_runs() -> None:
    result = _check.check_payment_file(
        _coverage("pain.001.001.09"), schematron="sepa"
    )
    assert "schematron" in result["rungs"]


@pytest.mark.parametrize("value", ["/etc/passwd", "rules.sch", "nope"])
def test_a_schematron_path_is_refused(value: str) -> None:
    result = _check.check_payment_file("<x/>", schematron=value)
    assert result["error"].startswith("schematron must be a preset")


@real
@pytest.mark.parametrize(
    ("document", "scheme", "reason"),
    [
        ("<root/>", None, "not a pain.001 or pain.008 Document"),
        (
            '<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>',
            None,
            "DTDs and entities are not allowed",
        ),
        (None, "no-such-scheme", "no-such-scheme"),
    ],
)
def test_a_file_that_cannot_be_checked_is_an_error(
    document: str | None, scheme: str | None, reason: str
) -> None:
    xml = document or _coverage("pain.001.001.09")
    result = _check.check_payment_file(xml, scheme=scheme)
    assert reason in result["error"]


@real
def test_the_tool_is_registered_with_an_output_schema() -> None:
    tools = {
        tool.name: tool for tool in asyncio.run(server.server.list_tools())
    }
    tool = tools["check_payment_file"]
    # The SDK names the fields outputSchema or output_schema by version.
    output = getattr(tool, "outputSchema", None) or getattr(
        tool, "output_schema", None
    )
    assert output is not None
    inputs = getattr(tool, "inputSchema", None) or tool.input_schema
    properties = inputs["properties"]
    assert set(properties) == {"xml_content", "scheme", "schematron"}
    assert "sepa" in json.dumps(properties["schematron"])
