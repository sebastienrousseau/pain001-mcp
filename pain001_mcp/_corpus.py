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

"""Example corpus tools (pain001 >= 0.0.67).

Four read-only tools over :mod:`pain001.corpus`: the index, one file, a
file's provenance sidecar, and an edition's schema coverage. An older
core without the corpus gets a clear error payload, never an import
failure.
"""

import importlib
from typing import Annotated, Any, cast

from pydantic import Field

from pain001_mcp._shapes import (
    CorpusCoverageResult,
    CorpusFileEntry,
    CorpusFileResult,
    CorpusListResult,
    CorpusProvenanceResult,
)

_CORPUS_MISSING = (
    "the example corpus needs pain001 >= 0.0.67; the installed pain001 "
    "has no pain001.corpus module"
)


def _corpus_api() -> Any | None:
    """Return :mod:`pain001.corpus`, or ``None`` when the library predates it.

    The corpus shipped in pain001 0.0.67; older releases are still valid
    peers of this server, so the four corpus tools report a clear error
    instead of failing at import time.
    """
    try:
        return importlib.import_module("pain001.corpus")
    except ImportError:
        return None


_CorpusKind = Annotated[
    str | None,
    Field(
        description=(
            "'market' for the realistic per-country scenarios, "
            "'coverage' for the schema coverage sets, or omit for both."
        )
    ),
]
_CorpusCountry = Annotated[
    str | None,
    Field(
        description=(
            "Two-letter country code to keep one market pack only, "
            "e.g. 'GB' or 'CH'. Ignored for coverage files."
        )
    ),
]
_CorpusVersion = Annotated[
    str | None,
    Field(
        description=(
            "Keep only files of this message type, e.g. 'pain.001.001.09'."
        )
    ),
]


def _entry(entry: Any) -> CorpusFileEntry:
    """Return the index row the tool reports for one corpus file."""
    return {
        "kind": entry.kind,
        "scenario_id": entry.scenario_id,
        "version": entry.version,
        "country": entry.country,
        "family": entry.family,
        "variant": entry.variant,
        "file": entry.path.name,
    }


def list_corpus_files(
    kind: _CorpusKind = None,
    country: _CorpusCountry = None,
    version: _CorpusVersion = None,
) -> CorpusListResult:
    """List the example files pain001 ships: market scenarios and coverage sets.

    Use this to discover what ready-made, validated ISO 20022 files exist
    before calling ``get_corpus_file`` or ``get_corpus_provenance``. Market
    files are realistic payments per country and rail (``scenario_id``
    like ``gb.chaps.property-purchase``); a ``variant`` names the bank
    overlay a file was built with. Coverage files exercise every element
    and choice branch of one message type and carry no scenario.

    Delegates to :func:`pain001.corpus.list_files`.

    Args:
        kind: ``market``, ``coverage`` or ``None`` for both.
        country: Optional two-letter country filter for market files.
        version: Optional message-type filter.

    Returns:
        ``{"count", "files": [{"kind", "scenario_id", "version", "country",
        "family", "variant", "file"}, ...]}``, or ``{"error": ...}`` when
        the installed pain001 has no corpus.
    """
    corpus = _corpus_api()
    if corpus is None:
        return {"error": _CORPUS_MISSING}
    wanted_country = country.upper() if country else None
    files: list[CorpusFileEntry] = [
        _entry(entry)
        for entry in corpus.list_files(kind)
        if not (wanted_country and entry.country != wanted_country)
        and not (version and entry.version != version)
    ]
    return {"count": len(files), "files": files}


def get_corpus_file(
    scenario_id: Annotated[
        str,
        Field(
            description=(
                "The market scenario, e.g. 'gb.chaps.property-purchase' "
                "(from list_corpus_files)."
            )
        ),
    ],
    version: Annotated[
        str,
        Field(description="The message type, e.g. 'pain.001.001.09'."),
    ],
    variant: Annotated[
        str | None,
        Field(
            description=(
                "An overlay id for the bank variant, e.g. "
                "'gb.example.priority'; omit for the generic file."
            )
        ),
    ] = None,
) -> CorpusFileResult:
    """Return the XML of one validated example file from the market corpus.

    Use this to show a model, a tester or a mapping exercise what a
    correct file for a given country and rail looks like in a given
    edition. The text is exactly what pain001 ships; it passed the XSD,
    the ISO MDR rules, the rail profile and the overlay when it was built.

    Delegates to :func:`pain001.corpus.get_file`.

    Args:
        scenario_id: The scenario.
        version: The message type.
        variant: The overlay id of a bank variant, else ``None``.

    Returns:
        ``{"scenario_id", "version", "variant", "xml"}``, or
        ``{"error": ...}`` when there is no such file or no corpus.
    """
    corpus = _corpus_api()
    if corpus is None:
        return {"error": _CORPUS_MISSING}
    try:
        xml = corpus.get_file(scenario_id, version, variant)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return {
        "scenario_id": scenario_id,
        "version": version,
        "variant": variant,
        "xml": xml,
    }


def get_corpus_provenance(
    scenario_id: Annotated[
        str,
        Field(description="The market scenario (from list_corpus_files)."),
    ],
    version: Annotated[
        str,
        Field(description="The message type, e.g. 'pain.001.001.09'."),
    ],
    variant: Annotated[
        str | None,
        Field(
            description=(
                "An overlay id for the bank variant; omit for the generic "
                "file."
            )
        ),
    ] = None,
) -> CorpusProvenanceResult:
    """Return the provenance sidecar of one example file.

    Use this to know how far to trust a file: the sources it was derived
    from, the confidence of the evidence (``verified``, ``derived`` or
    ``assumed``), the validation ladder result per rung, what the builder
    renamed or dropped to fit the edition, and the file's SHA-256.

    Delegates to :func:`pain001.corpus.provenance`.

    Args:
        scenario_id: The scenario.
        version: The message type.
        variant: The overlay id of a bank variant, else ``None``.

    Returns:
        The parsed sidecar as a dict, or ``{"error": ...}`` when there is
        no such file or no corpus.
    """
    corpus = _corpus_api()
    if corpus is None:
        return {"error": _CORPUS_MISSING}
    try:
        record: dict = corpus.provenance(scenario_id, version, variant)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return cast(CorpusProvenanceResult, record)


def get_corpus_coverage(
    version: Annotated[
        str,
        Field(description="The message type, e.g. 'pain.001.001.13'."),
    ],
) -> CorpusCoverageResult:
    """Return the schema coverage verdict of one message type's coverage set.

    Use this to check that the shipped coverage files reach every element
    path and choice branch of an edition's XSD before relying on them to
    smoke a parser or a mapping.

    Delegates to :func:`pain001.corpus.coverage_report`.

    Args:
        version: The message type.

    Returns:
        The ``coverage.json`` content (path and branch counts and
        percentages, completeness, missing and exempt lists), or
        ``{"error": ...}`` when the edition has no set or there is no
        corpus.
    """
    corpus = _corpus_api()
    if corpus is None:
        return {"error": _CORPUS_MISSING}
    try:
        report: dict = corpus.coverage_report(version)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return cast(CorpusCoverageResult, report)
