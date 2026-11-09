# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""``scripts/facts.py``: the release's facts, and the manifests that restate them."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

import pain001_mcp
import pain001_mcp.server as server

ROOT = Path(__file__).resolve().parents[1]


def _facts() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "facts_script", ROOT / "scripts" / "facts.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_fact_comes_from_its_source() -> None:
    facts = _facts().collect()
    tools = sorted(t.name for t in asyncio.run(server.server.list_tools()))
    assert facts["version"] == pain001_mcp.__version__
    assert facts["tools"] == tools
    assert facts["counts"]["tools"] == len(tools)
    assert facts["prompts"] == ["build_payment_batch"]
    assert facts["requires"]["pain001"].startswith(">=")


def test_the_manifests_state_the_real_tool_count() -> None:
    """glama.json and the tool catalogue restate the count; keep them true."""
    count = _facts().collect()["counts"]["tools"]
    glama = json.loads((ROOT / "glama.json").read_text(encoding="utf-8"))
    stated = re.search(r"(\d+) tools", glama["description"])
    assert stated is not None and int(stated[1]) == count
    catalogue = (ROOT / "docs" / "tools.md").read_text(encoding="utf-8")
    assert f"\n{count} tools." in catalogue


@pytest.mark.parametrize(
    ("spec", "floor"),
    [(">=0.0.81,<1", ">=0.0.81,<1"), ({"version": ">=1", "x": 1}, ">=1")],
)
def test_a_floor_reads_from_a_string_or_a_table(
    spec: object, floor: str
) -> None:
    assert _facts()._floor(spec) == floor


def test_write_check_and_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    facts = _facts()
    out = tmp_path / "facts.json"
    assert facts.main(["-o", str(out)]) == 0
    assert facts.main(["--check", str(out)]) == 0
    out.write_text("{}\n", encoding="utf-8")
    assert facts.main(["--check", str(out)]) == 1
    capsys.readouterr()
    assert facts.main([]) == 0
    assert json.loads(capsys.readouterr().out)["package"] == "pain001-mcp"


def test_the_release_uploads_the_documented_asset_name() -> None:
    """0.0.82 shipped ``pain001-mcp-v0.0.82.facts.json``: the workflow
    built the name from the tag while the docs promised the version.
    The name now lives in ``asset_name`` alone; the workflow asks the
    script for it, and the docs state the same pattern."""
    facts = _facts()
    assert facts.asset_name("0.0.83") == "pain001-mcp-0.0.83.facts.json"
    documented = facts.asset_name("<version>")
    for doc in ("scripts/facts.py", "CHANGELOG.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert f"`{documented}`" in text, doc
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert "scripts/facts.py --asset" in workflow
    assert re.findall(r"\S*\.facts\.json", workflow) == []


def test_asset_writes_the_named_file_and_prints_its_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    facts = _facts()
    monkeypatch.chdir(tmp_path)
    assert facts.main(["--asset"]) == 0
    name = facts.asset_name(pain001_mcp.__version__)
    assert capsys.readouterr().out == f"{name}\n"
    assert facts.main(["--check", name]) == 0
