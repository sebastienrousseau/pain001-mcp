# Copyright (C) 2023-2026 Pain001. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Tests for the faces tools, ``list_faces`` and ``project_face``.

Faces ship in pain001 0.0.78. ``_faces_api`` is driven through
``importlib`` so the absent branches (no module, or a module from before
``project_face_text``) are covered whichever pain001 is installed; the
other tests run against the real library and are skipped without it.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from pain001.corpus import get_file, list_files

from pain001_mcp import _faces

SALARY_09 = get_file("de.sepa.sct-salary", "pain.001.001.09")

real = pytest.mark.skipif(
    _faces._faces_api() is None, reason="installed pain001 has no faces"
)


def _every_element_09() -> str:
    """The .09 coverage file the UK Open Banking face accepts."""
    path = next(
        f.path
        for f in list_files("coverage")
        if f.version == "pain.001.001.09"
        and f.path.name.startswith("01-transfer-every-element")
    )
    return path.read_text(encoding="utf-8")


@pytest.fixture
def absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pain001 without faces."""
    monkeypatch.setattr(_faces, "_faces_api", lambda: None)


def test_faces_api_without_the_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ImportError means no faces."""

    def missing(name: str) -> None:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", missing)
    assert _faces._faces_api() is None
    assert _faces._face_names() == []


def test_faces_api_before_project_face_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pain.faces without the text entry point is treated as absent."""
    monkeypatch.setattr(
        importlib, "import_module", lambda name: SimpleNamespace()
    )
    assert _faces._faces_api() is None


def test_tools_report_missing_library(absent: None) -> None:
    """With a pain001 that predates faces every tool says so."""
    expected = {"error": _faces.FACES_MISSING}
    assert _faces.list_faces() == expected
    assert _faces.project_face(SALARY_09, "berlin_group") == expected
    assert "0.0.78" in _faces.FACES_MISSING


@real
def test_list_faces_is_the_library_list() -> None:
    """Each face with its description and bindings."""
    from pain001.faces import list_supported_faces

    result = _faces.list_faces()
    assert result == {
        "count": len(list_supported_faces()),
        "faces": list_supported_faces(),
    }
    names = [face["name"] for face in result["faces"]]
    assert names == _faces._FACE_NAMES == _faces._face_names() == sorted(names)
    assert all(f"'{name}'" in _faces._FACE_LIST for name in names)


@real
def test_project_face_matches_the_library() -> None:
    """The payload and loss report are the library's own."""
    from pain001.faces import project_face

    expected = project_face(SALARY_09, face="berlin_group").to_dict()
    assert _faces.project_face(SALARY_09, "berlin_group") == expected
    assert expected["loss_report"]["unmapped_paths"]


@real
def test_project_face_passes_version_and_bindings() -> None:
    """A ConsentId binding turns the UK body into OBWriteDomestic2."""
    result = _faces.project_face(
        _every_element_09(),
        "uk_open_banking",
        version="pain.001.001.09",
        bindings={"ConsentId": "consent-mcp-1"},
    )
    assert result["version"] == "pain.001.001.09"
    assert result["payload"]["Data"]["ConsentId"] == "consent-mcp-1"


@real
def test_project_face_uses_the_given_version() -> None:
    """An explicit edition is honoured, not re-detected: .09 is not a .03."""
    result = _faces.project_face(
        SALARY_09, "berlin_group", version="pain.001.001.03"
    )
    assert list(result) == ["error"]
    assert "pain.001.001.03" in result["error"]


@real
@pytest.mark.parametrize(
    ("xml", "face", "bindings", "reason"),
    [
        (SALARY_09, "uk_open_banking", None, "uk_open_banking"),
        (SALARY_09, "berlin_group", {"ConsentId": "c"}, "unknown binding"),
        (SALARY_09, "nope", None, "unknown face 'nope'"),
        ("/etc/passwd", "iso_2018", None, "expected the pain.001 document"),
        (
            '<!DOCTYPE d [<!ENTITY a "a">]><d>&a;</d>',
            "iso_2018",
            None,
            "refused XML",
        ),
    ],
    ids=["refused", "binding", "unknown-face", "path", "entity"],
)
def test_refusals_are_error_payloads(
    xml: str, face: str, bindings: dict[str, str] | None, reason: str
) -> None:
    """A refusal is data with the face's reason, never an exception."""
    result = _faces.project_face(xml, face, bindings=bindings)
    assert list(result) == ["error"]
    assert reason in result["error"]
