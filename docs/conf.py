"""Sphinx configuration for yoker-chat documentation."""

project = "yoker-chat"
copyright = "2026, Christophe VG"
author = "Christophe VG"

extensions = [
  "myst_parser",
  "sphinx.ext.autodoc",
  "sphinx.ext.napoleon",
  "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]