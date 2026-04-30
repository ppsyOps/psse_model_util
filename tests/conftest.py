"""
conftest.py — pytest configuration and shared fixtures.

Adds the project's parent directory to sys.path so that the package
is importable as `psse_model_util` (e.g. `from psse_model_util.raw_to_rawx import ...`).
"""
import sys
from pathlib import Path

import pytest

# /opt/openclaw-workspace/projects/psse_model_util  → parent = /opt/.../projects
PROJECT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = PROJECT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

# Shared fixture: path to the test data directory


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Return the path to tests/data/."""
    return Path(__file__).resolve().parent / "data"
