"""Sphinx configuration for the psse_model_util API documentation.

The reference is generated from the in-source Google-style docstrings via
``sphinx.ext.autodoc`` + ``sphinx.ext.napoleon``. Both ship in Sphinx core, so
the only docs dependency is Sphinx itself (see ``docs/requirements.txt``).

Build locally with::

    pip install -e .
    pip install -r docs/requirements.txt
    sphinx-build -W -b html docs docs/_build/html

``-W`` turns warnings (a malformed docstring, a broken cross-reference) into
build failures, keeping the generated reference honest against the code.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# -- Path setup --------------------------------------------------------------
# Make the package importable for autodoc without requiring an editable install
# (CI installs the package anyway; this keeps local `sphinx-build` working too).
_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))


def _read_version() -> str:
    """Read the version string from ``__about__.py`` without importing the package."""
    about = (_SRC / "psse_model_util" / "__about__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', about)
    return match.group(1) if match else "0.0.0"


# -- Project information ------------------------------------------------------
project = "psse_model_util"
author = "cadvena"
copyright = "2026, cadvena"  # noqa: A001 - Sphinx requires this exact name
release = _read_version()
version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosummary",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Autodoc / Napoleon ------------------------------------------------------
# Google-style docstrings only (NumPy-style parsing off keeps section detection
# unambiguous now that all docstrings have been converted to Google style).
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_rtype = True
napoleon_use_param = True

autosummary_generate = True
autoclass_content = "class"
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# Members are requested explicitly per-directive in the api/ stubs so that the
# package __init__ overview pages do not duplicate descriptions of names that
# are also documented on their defining submodule (which would warn under -W).
autodoc_default_options: dict[str, object] = {}

# -- HTML output -------------------------------------------------------------
# Alabaster ships with Sphinx, so the build needs no extra theme dependency.
html_theme = "alabaster"
html_static_path = ["_static"]
