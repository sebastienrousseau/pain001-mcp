# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Sphinx configuration for pain001-mcp documentation."""

from __future__ import annotations

import importlib.metadata

project = "pain001-mcp"
author = "Sebastien Rousseau"
copyright = "2023-2026, Sebastien Rousseau"

try:
    release = importlib.metadata.version("pain001-mcp")
except importlib.metadata.PackageNotFoundError:
    release = "0.0.0+dev"
version = ".".join(release.split(".")[:2])

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
    "myst_parser",
]

# MyST options: enable Markdown directives without breaking standard
# CommonMark renders.
myst_enable_extensions = ["colon_fence", "deflist", "linkify"]
# Link only real URLs: fuzzy matching turned file names such as
# "ROADMAP.md" in the changelog into links to http://ROADMAP.md.
myst_linkify_fuzzy_links = False

# Allow myst_parser to ingest the top-level README.md.
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "readme-template.md"]

# Furo theme: lightweight, modern, mobile-friendly.
html_theme = "furo"
html_title = f"pain001-mcp {release}"
# The footer's copyright line, with the author link, comes from
# _templates/page.html (as in pain001-lsp); Furo's own line escapes
# HTML and would repeat it unlinked.
html_show_copyright = False
html_context = {"author_year": "2026"}

# Cross-link to pain001's docs and the Python stdlib.
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pain001": ("https://docs.pain001.com/", None),
}

# Autodoc defaults.
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

# Link check (make docs-linkcheck, docs.yml). GitHub renders README
# anchors with JavaScript, so their fragments cannot be checked.
linkcheck_anchors_ignore_for_url = [r"https://github\.com/.*"]
linkcheck_retries = 3
linkcheck_timeout = 30
