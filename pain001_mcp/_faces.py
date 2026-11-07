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

"""Faces: a pain.001 document projected into another standard (pain001 >= 0.0.78).

Two tools over :mod:`pain001.faces` (ADR-0005 in the core repository):
``list_faces`` names each face, its target and the bindings it accepts;
``project_face`` returns the target payload and a loss report of every
source element the target could not carry. The document arrives as XML
text and goes through :func:`pain001.faces.project_face_text`, which
never reads a server path and refuses entity declarations. The tools
are registered in :mod:`pain001_mcp.server` with the others.
"""

from __future__ import annotations

import importlib
from typing import Annotated, Any

from pydantic import Field
from typing_extensions import TypedDict

FACES_MISSING = (
    "faces need pain001 >= 0.0.78; the installed pain001 has no "
    "pain001.faces.project_face_text"
)


def _faces_api() -> Any | None:
    """Return :mod:`pain001.faces`, or ``None`` when the library predates it."""
    try:
        faces = importlib.import_module("pain001.faces")
    except ImportError:
        return None
    return faces if hasattr(faces, "project_face_text") else None


def _face_names() -> list[str]:
    """The registered face names, or none when the library has no faces."""
    faces = _faces_api()
    return [] if faces is None else list(faces.available_faces())


_FACE_NAMES = _face_names()
_FACE_LIST = ", ".join(f"'{name}'" for name in _FACE_NAMES) or "see list_faces"


_XmlContent = Annotated[
    str,
    Field(
        description=(
            "The full pain.001 document as XML text (not a file path), "
            "at most 10 MiB."
        )
    ),
]
_FaceName = Annotated[
    str,
    Field(
        description=f"The target face: one of {_FACE_LIST}.",
        json_schema_extra={"enum": _FACE_NAMES} if _FACE_NAMES else None,
    ),
]
_Version = Annotated[
    str | None,
    Field(
        description=(
            "The pain.001 edition, e.g. 'pain.001.001.09'; omit to detect "
            "it from the document's namespace."
        )
    ),
]
_Bindings = Annotated[
    dict[str, Any] | None,
    Field(
        description=(
            "Values the message does not carry, keyed as list_faces names "
            "them (e.g. {'ConsentId': '...'} for uk_open_banking); used for "
            "this call only."
        )
    ),
]


class FaceEntry(TypedDict):
    """One face: its name, its target and the binding keys it accepts."""

    name: str
    description: str
    bindings: list[str]


class FaceListResult(TypedDict, total=False):
    """Every face, or an error when the library has none."""

    error: str
    count: int
    faces: list[FaceEntry]


class LossReportResult(TypedDict):
    """Source leaves carried and not carried, by indexed path."""

    face: str
    total_source_elements: int
    mapped_count: int
    unmapped_count: int
    is_lossless: bool
    loss_ratio: float
    mapped_paths: list[str]
    unmapped_paths: list[str]


class FaceProjectionResult(TypedDict, total=False):
    """The target payload and its loss report, or the face's refusal."""

    error: str
    face: str
    version: str
    payload: dict[str, Any]
    loss_report: LossReportResult


def list_faces() -> FaceListResult:
    """List the faces: the standards a pain.001 document can be projected into.

    Use this before ``project_face`` to pick a target and to learn which
    bindings it accepts. A binding is a value the payment message does
    not carry, such as the UK Open Banking ``ConsentId`` agreed with the
    bank; any key a face does not list is refused.

    Delegates to :func:`pain001.faces.list_supported_faces`.

    Returns:
        ``{"count", "faces": [{"name", "description", "bindings"}, ...]}``,
        or ``{"error": ...}`` when the installed pain001 has no faces.
    """
    faces = _faces_api()
    if faces is None:
        return {"error": FACES_MISSING}
    entries: list[FaceEntry] = faces.list_supported_faces()
    return {"count": len(entries), "faces": entries}


def project_face(
    xml_content: _XmlContent,
    face: _FaceName,
    version: _Version = None,
    bindings: _Bindings = None,
) -> FaceProjectionResult:
    """Project a pain.001 document into another standard's JSON shape.

    Use this to turn a payment file into the request body a UK Open
    Banking or Berlin Group API expects, or into ISO 20022 element names,
    and to see exactly what the target cannot carry: the loss report
    lists every source element left out, by indexed path. A face never
    invents a value: when the target requires an element the document
    lacks, the answer is an ``{"error": ...}`` naming it. To check the
    document itself first, use ``validate_xml_against_schema``.

    Delegates to :func:`pain001.faces.project_face_text`.

    Args:
        xml_content: The pain.001 document as XML text.
        face: The target face.
        version: The edition, or ``None`` to detect it.
        bindings: Side inputs the face accepts, or ``None``.

    Returns:
        ``{"face", "version", "payload", "loss_report"}``, or
        ``{"error": ...}`` when the face refuses the document or a
        binding, or the installed pain001 has no faces.
    """
    faces = _faces_api()
    if faces is None:
        return {"error": FACES_MISSING}
    try:
        result = faces.project_face_text(
            xml_content, face, version=version, bindings=bindings
        )
    except faces.FaceError as exc:
        return {"error": str(exc)}
    projection: FaceProjectionResult = result.to_dict()
    return projection
