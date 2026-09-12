# Copyright (C) 2023-2026 Pain001. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Tests for the example-corpus tools.

The corpus ships in pain001 0.0.67. The lockfile may pin an older
library, so every test drives ``_corpus_api`` through a stub module and
covers both the present and the absent branches regardless of which
pain001 is installed. ``test_real_corpus_when_available`` runs the same
calls against the real library when it has the corpus.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

import pain001_mcp.server as server


@dataclass
class _File:
    kind: str
    version: str
    path: Path
    scenario_id: str | None = None
    country: str | None = None
    family: str | None = None
    variant: str | None = None


_FILES = [
    _File(
        "market",
        "pain.001.001.03",
        Path(
            "gb/priority-payment/gb.chaps.property-purchase.pain.001.001.03.xml"
        ),
        "gb.chaps.property-purchase",
        "GB",
        "priority-payment",
    ),
    _File(
        "market",
        "pain.001.001.03",
        Path(
            "gb/priority-payment/gb.chaps.property-purchase__gb.example.priority.pain.001.001.03.xml"
        ),
        "gb.chaps.property-purchase",
        "GB",
        "priority-payment",
        "gb.example.priority",
    ),
    _File(
        "market",
        "pain.001.001.09",
        Path("ch/domestic-credit-transfer/ch.sps.qr-bill.pain.001.001.09.xml"),
        "ch.sps.qr-bill",
        "CH",
        "domestic-credit-transfer",
    ),
    _File("coverage", "pain.001.001.13", Path("pain.001.001.13/set-01.xml")),
]


def _stub_corpus() -> SimpleNamespace:
    def list_files(kind=None):
        return [f for f in _FILES if kind in (None, f.kind)]

    def get_file(scenario_id, version, variant=None):
        for f in _FILES:
            if (f.scenario_id, f.version, f.variant) == (
                scenario_id,
                version,
                variant,
            ):
                return f"<Document>{f.path.name}</Document>"
        raise FileNotFoundError(
            f"no market file for {scenario_id} in {version}"
        )

    def provenance(scenario_id, version, variant=None):
        get_file(scenario_id, version, variant)
        return {
            "scenario": scenario_id,
            "message_type": version,
            "variant": variant,
        }

    def coverage_report(version):
        if version != "pain.001.001.13":
            raise FileNotFoundError(f"no coverage set for {version}")
        return {"message_type": version, "complete": True}

    return SimpleNamespace(
        list_files=list_files,
        get_file=get_file,
        provenance=provenance,
        coverage_report=coverage_report,
    )


@pytest.fixture
def stub(monkeypatch):
    """Make ``pain001.corpus`` resolve to the stub."""
    fake = _stub_corpus()
    real = importlib.import_module

    def fake_import(name, package=None):
        if name == "pain001.corpus":
            return fake
        return real(name, package)

    monkeypatch.setattr(server.importlib, "import_module", fake_import)
    return fake


@pytest.fixture
def absent(monkeypatch):
    """Make ``pain001.corpus`` unimportable."""
    real = importlib.import_module

    def fake_import(name, package=None):
        if name == "pain001.corpus":
            raise ImportError("No module named 'pain001.corpus'")
        return real(name, package)

    monkeypatch.setattr(server.importlib, "import_module", fake_import)


def test_list_corpus_files_returns_every_kind(stub):
    """No filter lists market and coverage files with their metadata."""
    out = server.list_corpus_files()
    assert out["count"] == 4
    first = out["files"][0]
    assert first["scenario_id"] == "gb.chaps.property-purchase"
    assert first["variant"] is None
    assert first["file"].endswith(".xml")
    assert out["files"][-1] == {
        "kind": "coverage",
        "scenario_id": None,
        "version": "pain.001.001.13",
        "country": None,
        "family": None,
        "variant": None,
        "file": "set-01.xml",
    }


def test_list_corpus_files_filters_by_kind_country_and_version(stub):
    """Filters combine; the country filter is case-insensitive."""
    assert server.list_corpus_files(kind="coverage")["count"] == 1
    gb = server.list_corpus_files(country="gb")
    assert gb["count"] == 2
    assert {f["variant"] for f in gb["files"]} == {None, "gb.example.priority"}
    v09 = server.list_corpus_files(kind="market", version="pain.001.001.09")
    assert [f["scenario_id"] for f in v09["files"]] == ["ch.sps.qr-bill"]
    assert server.list_corpus_files(country="SE")["count"] == 0


def test_get_corpus_file_returns_xml_for_generic_and_variant(stub):
    """The generic file and the bank variant are distinct files."""
    generic = server.get_corpus_file(
        "gb.chaps.property-purchase", "pain.001.001.03"
    )
    variant = server.get_corpus_file(
        "gb.chaps.property-purchase", "pain.001.001.03", "gb.example.priority"
    )
    assert generic["variant"] is None and "__" not in generic["xml"]
    assert (
        variant["variant"] == "gb.example.priority" and "__" in variant["xml"]
    )


def test_get_corpus_file_unknown_returns_error(stub):
    """A missing edition yields an error payload, not an exception."""
    out = server.get_corpus_file(
        "gb.chaps.property-purchase", "pain.001.001.13"
    )
    assert "no market file" in out["error"]


def test_get_corpus_provenance_returns_sidecar(stub):
    """The sidecar comes back as a dict; a missing file is an error."""
    out = server.get_corpus_provenance("ch.sps.qr-bill", "pain.001.001.09")
    assert out["scenario"] == "ch.sps.qr-bill"
    assert "error" in server.get_corpus_provenance("nope", "pain.001.001.09")


def test_get_corpus_coverage_returns_report(stub):
    """The coverage verdict comes back; an unknown edition is an error."""
    assert server.get_corpus_coverage("pain.001.001.13")["complete"] is True
    assert "error" in server.get_corpus_coverage("pain.001.001.02")


def test_corpus_tools_report_missing_library(absent):
    """With a pain001 that predates the corpus every tool says so."""
    expected = {"error": server._CORPUS_MISSING}
    assert server.list_corpus_files() == expected
    assert server.get_corpus_file("x", "pain.001.001.09") == expected
    assert server.get_corpus_provenance("x", "pain.001.001.09") == expected
    assert server.get_corpus_coverage("pain.001.001.09") == expected
    assert "0.0.67" in server._CORPUS_MISSING


def test_real_corpus_when_available():
    """Against a pain001 that ships the corpus, the tools return real data."""
    if server._corpus_api() is None:
        pytest.skip("installed pain001 has no example corpus")
    files = server.list_corpus_files(kind="market", country="GB")
    assert files["count"] > 0
    first = files["files"][0]
    xml = server.get_corpus_file(
        first["scenario_id"], first["version"], first["variant"]
    )
    assert xml["xml"].startswith("<?xml")
    record = server.get_corpus_provenance(
        first["scenario_id"], first["version"], first["variant"]
    )
    assert record["validation"]["xsd"]["errors"] == 0
    assert server.get_corpus_coverage("pain.001.001.13")["complete"] is True


def test_variant_lookup_on_a_core_without_the_argument(monkeypatch):
    """pain001 0.0.67 has no variant argument: a variant asks for 0.0.68."""
    from pain001_mcp import server

    class OldCorpus:
        @staticmethod
        def get_file(scenario_id, version):
            return f"<xml {scenario_id} {version}/>"

        @staticmethod
        def provenance(scenario_id, version):
            return {"scenario_id": scenario_id, "version": version}

    monkeypatch.setattr(server, "_corpus_api", lambda: OldCorpus())
    generic = server.get_corpus_file("gb.chaps.property-purchase", "09")
    assert generic["xml"].startswith("<xml ")
    assert "scenario_id" in server.get_corpus_provenance(
        "gb.chaps.property-purchase", "09"
    )
    variant = server.get_corpus_file(
        "gb.chaps.property-purchase", "09", variant="some-bank"
    )
    assert "pain001 >= 0.0.68" in variant["error"]
    assert (
        "pain001 >= 0.0.68"
        in server.get_corpus_provenance(
            "gb.chaps.property-purchase", "09", variant="some-bank"
        )["error"]
    )
