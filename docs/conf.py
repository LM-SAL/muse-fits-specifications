"""
Sphinx configuration.

Mirrors the DKIST docs pattern: the keyword reference pages are generated from the
packaged specs at build time, so they cannot drift from the YAML.
"""

import sys
import tomllib
from pathlib import Path

DOCS = Path(__file__).parent
sys.path.insert(0, str(DOCS.parent / "src"))

project = "muse-fits-specifications"
copyright = "2026, LMSAL & MUSE Instrument Team"  # noqa: A001
author = "LMSAL & MUSE Instrument Team"
release = tomllib.loads((DOCS.parent / "pyproject.toml").read_text())["project"]["version"]

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]
exclude_patterns = ["_build"]

html_theme = "pydata_sphinx_theme"
html_title = f"{project} {release}"

autodoc_member_order = "bysource"

# Regenerate the keyword reference pages from the packaged specs.
from muse_fits_specifications.render import main as _render_specs

_render_specs([str(DOCS)])
