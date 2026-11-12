# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""One verdict per payload: the core's CLI, its REST API and the MCP tools.

Each case is the core's bundled pain.001.001.03 sample with one value
changed, the fixtures of the core's own ``tests/test_verdict_parity.py``
plus a mixed batch and a row with a stray value. Every surface either
accepts the payload or refuses it, and where a surface names the
problem with a ``P001-E...`` issue code, every surface names the same
codes. An agent told a payment is valid when the CLI would refuse it
is the inconsistency this file exists to catch.

The file tools read the case as a file; the record tools take the
same rows as an agent would send them, one dict per CSV row with the
values as text.
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from pain001.api.app import app
from pain001.cli.cli import cli
from pain001.constants import TEMPLATES_DIR

import pain001_mcp.server as server

MESSAGE_TYPE = "pain.001.001.03"
SAMPLE = TEMPLATES_DIR / MESSAGE_TYPE / "template.csv"
CODE = re.compile(r"P001-E\d{3}")

# (case id, edits as (row, column, value), accepted?, issue codes)
CASES = [
    ("sample", [], True, set()),
    ("currency-euro", [(1, "currency", "EURO")], False, {"P001-E030"}),
    ("currency-lowercase", [(1, "currency", "eur")], False, {"P001-E030"}),
    (
        "bad-iban",
        [(1, "creditor_account_IBAN", "DE00000000000000000000")],
        False,
        {"P001-E020"},
    ),
    ("bad-bic", [(1, "debtor_agent_BIC", "NOTABIC")], False, {"P001-E021"}),
    (
        "amount-not-decimal",
        [(1, "payment_amount", "abc")],
        False,
        {"P001-E012"},
    ),
    ("missing-debtor-name", [(1, "debtor_name", "")], False, {"P001-E010"}),
    # Two payment information blocks in one file: refused, with no code.
    ("two-batches", [(2, "debtor_name", "Other Corp")], False, set()),
]

Verdict = tuple[bool, set[str] | None]


def _write_case(directory: Path, edits: list[tuple[int, str, str]]) -> Path:
    """Write the sample with each ``(row, column, value)`` edit applied."""
    with SAMPLE.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    for row, column, value in edits:
        rows[row][rows[0].index(column)] = value
    path = directory / "payments.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rows)
    return path


def _records(path: Path) -> list[dict]:
    """Return the file's rows as an agent would send them: text values."""
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _codes(text: str) -> set[str]:
    return set(CODE.findall(text))


def _cli(command: str, path: Path) -> Verdict:
    args = [command, "-t", MESSAGE_TYPE, "-d", str(path), "--format", "json"]
    if command == "generate":
        args += ["-o", str(path.parent / "cli-out")]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code in (0, 1), result.output
    body = json.loads(result.stdout)
    return body["ok"], _codes(body.get("error") or "")


def _cli_validate(path: Path) -> Verdict:
    return _cli("validate", path)


def _cli_generate(path: Path) -> Verdict:
    return _cli("generate", path)


def _rest(route: str, path: Path) -> Verdict:
    # Without PAIN001_API_KEY the core API answers only loopback hosts
    # (pain001 0.0.87), and TestClient's default host is "testserver".
    response = TestClient(app, base_url="http://localhost").post(
        route,
        json={
            "file_path": str(path),
            "data_source": "csv",
            "message_type": MESSAGE_TYPE,
            "output_dir": str(path.parent / "rest-out"),
        },
    )
    assert response.status_code in (200, 400, 422), response.text
    body = response.json()
    if response.status_code == 400:
        return False, _codes(body["detail"])
    # A schema refusal (200 from validate, 422 from generate) lists the
    # JSON Schema findings without codes, so its codes are not compared.
    accepted = bool(body.get("is_valid", body.get("success")))
    return accepted, set() if accepted else None


def _rest_validate(path: Path) -> Verdict:
    return _rest("/api/v1/validate", path)


def _rest_generate(path: Path) -> Verdict:
    return _rest("/api/v1/generate", path)


def _xml_or_error(result: str) -> Verdict:
    if result.lstrip().startswith("<?xml"):
        return True, set()
    body = json.loads(result)
    return False, _codes(body["error"])


def _mcp_validate_records(path: Path) -> Verdict:
    report = server.validate_records(MESSAGE_TYPE, _records(path))
    codes = {e.get("code") for e in report.get("errors", [])} - {None}
    return report.get("valid", False), codes


def _mcp_generate_message(path: Path) -> Verdict:
    return _xml_or_error(server.generate_message(MESSAGE_TYPE, _records(path)))


def _mcp_generate_message_async(path: Path) -> Verdict:
    return _xml_or_error(
        asyncio.run(
            server.generate_message_async(MESSAGE_TYPE, _records(path))
        )
    )


def _mcp_generate_message_from_file(path: Path) -> Verdict:
    return _xml_or_error(
        server.generate_message_from_file(MESSAGE_TYPE, str(path))
    )


def _mcp_simulate_payment_batch(path: Path) -> Verdict:
    report = server.simulate_payment_batch(MESSAGE_TYPE, _records(path))
    codes = {e.get("code") for e in report.get("schema_errors", [])}
    return report.get("valid", False), codes - {None}


def _mcp_stage_payment_batch(path: Path) -> Verdict:
    staged = server.stage_payment_batch(MESSAGE_TYPE, _records(path))
    return "error" not in staged, None


SURFACES: dict[str, Callable[[Path], Verdict]] = {
    "cli-validate": _cli_validate,
    "cli-generate": _cli_generate,
    "rest-validate": _rest_validate,
    "rest-generate": _rest_generate,
    "mcp-validate_records": _mcp_validate_records,
    "mcp-generate_message": _mcp_generate_message,
    "mcp-generate_message_async": _mcp_generate_message_async,
    "mcp-generate_message_from_file": _mcp_generate_message_from_file,
    "mcp-simulate_payment_batch": _mcp_simulate_payment_batch,
    "mcp-stage_payment_batch": _mcp_stage_payment_batch,
}


@pytest.mark.parametrize(
    ("edits", "accepted", "codes"),
    [pytest.param(e, a, c, id=i) for i, e, a, c in CASES],
)
def test_every_surface_gives_the_same_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    edits: list[tuple[int, str, str]],
    accepted: bool,
    codes: set[str],
) -> None:
    # The REST API and the file loaders read below the working directory.
    monkeypatch.chdir(tmp_path)
    path = _write_case(tmp_path, edits)
    verdicts = {name: surface(path) for name, surface in SURFACES.items()}
    assert {name: v[0] for name, v in verdicts.items()} == dict.fromkeys(
        SURFACES, accepted
    )
    named = {name: v[1] for name, v in verdicts.items() if v[1] is not None}
    assert named == dict.fromkeys(named, codes)


@pytest.mark.parametrize(
    "surface",
    ["cli-validate", "rest-validate", "mcp-generate_message_from_file"],
)
def test_a_stray_value_is_refused_on_every_file_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, surface: str
) -> None:
    """More values than columns: ``P001-E002`` from the CLI, REST and MCP."""
    monkeypatch.chdir(tmp_path)
    path = _write_case(tmp_path, [])
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[2] += ",stray"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert SURFACES[surface](path) == (False, {"P001-E002"})
