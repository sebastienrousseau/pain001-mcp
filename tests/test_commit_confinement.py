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
from tests.test_dual_control_simulation import _sample_record

MT = "pain.001.001.03"


def _record() -> dict[str, object]:
    """The synthetic record the dual-control tests already stage."""
    return dict(_sample_record())


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
