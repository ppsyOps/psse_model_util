"""
conftest.py — pytest configuration and shared fixtures.

Adds the project's parent directory to sys.path so that the package
is importable as `psse_model_util` (e.g. `from psse_model_util.raw_to_rawx import ...`).
"""
import importlib.machinery
import sys
import types
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = PROJECT_DIR.parent

if (PARENT_DIR / "psse_model_util").is_dir():
    # Canonical checkout: the project directory IS named psse_model_util.
    # Adding its parent to sys.path lets Python resolve the package normally.
    if str(PARENT_DIR) not in sys.path:
        sys.path.insert(0, str(PARENT_DIR))
elif "psse_model_util" not in sys.modules:
    # Git worktree: project root has a generated name, not 'psse_model_util'.
    # The editable-install .pth already adds PROJECT_DIR to sys.path so
    # individual modules are importable, but 'psse_model_util' as a namespace
    # is missing.  Register a lightweight stub so that
    #   from psse_model_util.model import Model
    # resolves through PROJECT_DIR at import time.
    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))
    pkg = types.ModuleType("psse_model_util")
    pkg.__path__ = [str(PROJECT_DIR)]
    pkg.__package__ = "psse_model_util"
    pkg.__spec__ = importlib.machinery.ModuleSpec(
        "psse_model_util", loader=None, origin=str(PROJECT_DIR)
    )
    sys.modules["psse_model_util"] = pkg

# Shared fixture: path to the test data directory


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Return the path to tests/data/."""
    return Path(__file__).resolve().parent / "data"
