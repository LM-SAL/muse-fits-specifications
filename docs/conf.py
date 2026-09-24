"""
Sphinx configuration.
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
html_sidebars = {"**": []}
html_theme_options = {
    "navbar_center": ["navbar-pages"],
    "navbar_persistent": ["search-button"],
    "secondary_sidebar_items": [],
}
html_static_path = ["_static"]
html_css_files = ["custom.css"]
templates_path = ["_templates"]

autodoc_member_order = "bysource"

# Regenerate the keyword reference pages from the packaged specs
from muse_fits_specifications.render import main as _render_specs
from muse_fits_specifications.spec import defined_levels, load_spec

_render_specs([str(DOCS)])
html_theme_options["announcement"] = (
    f"Draft {load_spec('level0').version} — Keyword definitions are still being completed. "
    "Fields without assigned FITS keywords are not validated."
)
# Header links for _templates/navbar-pages.html, in the shape of sunpy-sphinx-theme's
# navbar_links: (label, docname), or (label, [(label, docname), ...]) for a dropdown.
html_context = {
    "navbar_links": [
        ("Format", "format"),
        ("Keywords", "keywords"),
        ("Levels", [(load_spec(level).title, level) for level in defined_levels()]),
        ("API reference", "reference"),
        ("Release History", "changelog"),
    ],
}
