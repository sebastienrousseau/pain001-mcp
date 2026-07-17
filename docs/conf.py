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

# Allow myst_parser to ingest the top-level README.md.
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Furo theme: lightweight, modern, mobile-friendly.
html_theme = "furo"
html_title = f"pain001-mcp {release}"

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
