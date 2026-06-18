"""
conftest.py — pytest configuration and shared fixtures.

With the src/ layout the package is normally importable via the editable
install (`pdm install`). As a fallback for fresh checkouts or git worktrees
that have not been installed, add the `src/` directory to sys.path so that
`from psse_model_util.model import Model` resolves.
"""
import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Return the path to tests/data/."""
    return Path(__file__).resolve().parent / "data"
