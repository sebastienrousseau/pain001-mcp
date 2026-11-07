# Copyright (C) 2023-2026 Pain001. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""The two faces tools, called directly.

pain001 0.0.78 projects a pain.001 document into another standard's
JSON shape (UK Open Banking, Berlin Group NextGenPSD2, ISO 20022 element
names) and lists every source element the target could not carry. The
MCP server exposes it through ``list_faces`` and ``project_face``.

With a pain001 that predates faces the tools answer with an ``error``
payload instead of failing, and this script shows that path too, so it
runs against either library.

Run::

    python examples/05_faces_tools.py
"""

from __future__ import annotations

import pain001_mcp.server as server


def main() -> None:
    """List the faces, project a corpus file, and show a refusal."""
    listed = server.list_faces()
    if "error" in listed:
        print("faces unavailable:", listed["error"])
        assert "error" in server.project_face("<Document/>", "berlin_group")
        print("both faces tools return the same error payload; nothing raised")
        return

    for face in listed["faces"]:
        print(f"{face['name']}: bindings {face['bindings'] or 'none'}")

    xml = server.get_corpus_file("de.sepa.sct-salary", "pain.001.001.09")[
        "xml"
    ]
    result = server.project_face(xml, "berlin_group")
    report = result["loss_report"]
    print(
        f"project_face(berlin_group) -> {len(result['payload']['payments'])} "
        f"payments; {report['mapped_count']} of "
        f"{report['total_source_elements']} source elements carried"
    )
    print("  first not carried:", report["unmapped_paths"][0])

    refused = server.project_face(xml, "uk_open_banking")
    assert list(refused) == ["error"]
    print("project_face(uk_open_banking) ->", refused["error"])
    print("Faces tools example completed.")


if __name__ == "__main__":
    main()
