# Copyright (C) 2023-2026 Pain001. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""The four example-corpus tools, called directly.

pain001 ships a corpus of validated example files from 0.0.67: realistic
payments per country and rail, schema coverage sets, and a provenance
record beside every payment file. The MCP server exposes it through
``list_corpus_files``, ``get_corpus_file``, ``get_corpus_provenance``
and ``get_corpus_coverage``.

With a pain001 that predates the corpus the tools answer with an
``error`` payload instead of failing, and this script shows that path
too, so it runs against either library.

Run::

    python examples/04_corpus_tools.py
"""

from __future__ import annotations

import pain001_mcp.server as server


def main() -> None:
    """Call each corpus tool and print what came back."""
    listed = server.list_corpus_files(kind="market")
    if "error" in listed:
        print("corpus unavailable:", listed["error"])
        for out in (
            server.get_corpus_file(
                "gb.chaps.property-purchase", "pain.001.001.09"
            ),
            server.get_corpus_provenance(
                "gb.chaps.property-purchase", "pain.001.001.09"
            ),
            server.get_corpus_coverage("pain.001.001.13"),
        ):
            assert "error" in out
        print(
            "every corpus tool returns the same error payload; nothing raised"
        )
        return

    print(f"list_corpus_files(kind='market') -> {listed['count']} files")
    first = listed["files"][0]
    print("  first:", first["scenario_id"], first["version"], first["country"])

    by_country = server.list_corpus_files(kind="market", country="gb")
    assert all(f["country"] == "GB" for f in by_country["files"])
    print(f"list_corpus_files(country='gb') -> {by_country['count']} files")

    got = server.get_corpus_file(first["scenario_id"], first["version"])
    assert got["xml"].startswith("<?xml")
    print(
        f"get_corpus_file -> {len(got['xml'])} characters of {first['version']}"
    )

    record = server.get_corpus_provenance(
        first["scenario_id"], first["version"]
    )
    assert record["validation"]["xsd"]["errors"] == 0
    print(
        "get_corpus_provenance -> confidence",
        record["provenance"]["confidence"],
        "sha256",
        record["sha256"][:12] + "…",
    )

    missing = server.get_corpus_file(first["scenario_id"], "pain.001.001.02")
    assert "error" in missing
    print("get_corpus_file (unknown edition) ->", missing["error"])

    report = server.get_corpus_coverage("pain.001.001.13")
    assert report["complete"]
    print(
        f"get_corpus_coverage('pain.001.001.13') -> {len(report['files'])} files, "
        f"first {report['files'][0]['name']}"
    )
    print("Corpus tools example completed.")


if __name__ == "__main__":
    main()
