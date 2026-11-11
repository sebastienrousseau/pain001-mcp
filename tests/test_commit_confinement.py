# SPDX-FileCopyrightText: 2023-2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""commit_payment_batch writes only inside the output root (GHSA-hqw7-q8v2-pq3m).

It used to write the XML to any path the caller named, creating parent
directories and overwriting existing files, so an agent driven by
untrusted content could create or replace files anywhere the server's
user can write.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import pain001_mcp.server as server

MT = "pain.001.001.03"


def _record() -> dict[str, object]:
    """A synthetic record that stages cleanly (valid IBANs and BICs).

    Defined here rather than imported from another test module: when the
    core is installed editable (as CI does on main), its regular
    ``tests`` package shadows this repository's, and the import fails.
    """
    return {
        "id": "MSG-TEST-1",
        "date": "2026-09-18T09:00:00",
        "initiator_name": "Acme GmbH",
        "payment_information_id": "PMT-TEST-1",
        "payment_method": "TRF",
        "batch_booking": False,
        "requested_execution_date": "2026-09-19",
        "debtor_name": "Acme GmbH",
        "debtor_account_IBAN": "DE89370400440532013000",
        "debtor_agent_BIC": "COBADEFFXXX",
        "charge_bearer": "SLEV",
        "payment_id": "E2E-TEST-1",
        "payment_amount": 100.0,
        "currency": "EUR",
        "creditor_agent_BIC": "DEUTDEFFXXX",
        "creditor_name": "Beta AG",
        "creditor_account_IBAN": "DE02120300000000202051",
        "remittance_information": "Invoice 12345 Consulting Services",
    }


def _commit(path: str) -> dict[str, object]:
    staged = server.stage_payment_batch(MT, [_record()])
    assert "error" not in staged, staged
    return dict(
        server.commit_payment_batch(
            staged["stage_id"],
            staged["confirmation_token"],
            output_file_path=path,
        )
    )


@pytest.fixture
def root(tmp_path, monkeypatch) -> Path:
    """An output root set through PAIN001_MCP_OUTPUT_DIR."""
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setenv("PAIN001_MCP_OUTPUT_DIR", str(out))
    return out.resolve()


def test_relative_path_lands_inside_the_root(root):
    res = _commit("batches/today.xml")
    assert "error" not in res, res
    written = root / "batches" / "today.xml"
    assert res["output_file_path"] == str(written)
    assert written.read_text(encoding="utf-8").startswith("<?xml")


@pytest.mark.parametrize(
    "path",
    ["../escape.xml", "batches/../../escape.xml"],
    ids=["parent", "nested-parent"],
)
def test_paths_that_leave_the_root_are_refused(root, path):
    res = _commit(path)
    assert "outside the output directory" in str(res.get("error")), res
    assert not (root.parent / "escape.xml").exists()


def test_absolute_path_outside_the_root_is_refused(root, tmp_path):
    target = tmp_path / "elsewhere" / "file.xml"
    res = _commit(str(target))
    assert "outside the output directory" in str(res.get("error")), res
    assert not target.exists()
    assert not target.parent.exists()


def test_symlink_out_of_the_root_is_refused(root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    res = _commit("link/file.xml")
    assert "outside the output directory" in str(res.get("error")), res
    assert not (outside / "file.xml").exists()


def test_existing_file_is_never_overwritten(root):
    existing = root / "keep.xml"
    existing.write_text("original", encoding="utf-8")
    res = _commit("keep.xml")
    assert "already exists" in str(res.get("error")), res
    assert existing.read_text(encoding="utf-8") == "original"


def test_only_xml_files_are_written(root):
    res = _commit("notes.txt")
    assert "must end in .xml" in str(res.get("error")), res
    assert not (root / "notes.txt").exists()


def test_working_directory_is_the_default_root(tmp_path, monkeypatch):
    monkeypatch.delenv("PAIN001_MCP_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert "error" not in _commit("here.xml")
    assert (tmp_path / "here.xml").is_file()
    res = _commit(str(tmp_path.parent / "there.xml"))
    assert "outside the output directory" in str(res.get("error")), res


def test_a_refused_write_leaves_the_batch_staged(root):
    staged = server.stage_payment_batch(MT, [_record()])
    refused = server.commit_payment_batch(
        staged["stage_id"],
        staged["confirmation_token"],
        output_file_path="../escape.xml",
    )
    assert "error" in refused
    retried = server.commit_payment_batch(
        staged["stage_id"],
        staged["confirmation_token"],
        output_file_path="ok.xml",
    )
    assert "error" not in retried, retried


def test_a_file_appearing_after_the_check_is_not_replaced(root):
    """The exclusive create is the last guard against a race."""
    from pain001_mcp._output import OutputPathError, write_new

    target = root / "race.xml"
    target.write_text("someone else's", encoding="utf-8")
    with pytest.raises(OutputPathError, match="already exists"):
        write_new(target, "<Document/>")
    assert target.read_text(encoding="utf-8") == "someone else's"
