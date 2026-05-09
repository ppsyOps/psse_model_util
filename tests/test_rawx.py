"""
test_rawx.py — RAWX-format model section tests.

Ported from tests/legacy_tests/rawx/test_model-1.py; updated for the current
API and project layout after refactoring.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sample_model():
    return Model(DATA_DIR / "sample_v35.rawx")


# ---------------------------------------------------------------------------
# General section
# ---------------------------------------------------------------------------

def test_general_section(sample_model):
    assert hasattr(sample_model.general, "version")
    assert sample_model.general.version == 35.4


# ---------------------------------------------------------------------------
# Network sections
# ---------------------------------------------------------------------------

def test_network_section(sample_model):
    assert hasattr(sample_model.network, "caseid")
    assert hasattr(sample_model.network, "rating")


def test_caseid(sample_model):
    caseid_df = sample_model.network.caseid
    assert isinstance(caseid_df, pd.DataFrame)
    assert len(caseid_df) == 1
    assert "ic" in caseid_df.columns


def test_rating(sample_model):
    rating_df = sample_model.network.rating
    assert isinstance(rating_df, pd.DataFrame)
    assert len(rating_df) > 1
    assert "irate" in rating_df.columns


def test_solver(sample_model):
    solver_df = sample_model.network.solver
    assert isinstance(solver_df, pd.DataFrame)
    assert len(solver_df) == 1
    assert "method" in solver_df.columns
    assert "nondiv" in solver_df.columns
    assert pd.isna(solver_df["nondiv"].iloc[0])


def test_all_network_dataframes(sample_model):
    # Sections that may legitimately be empty in this fixture
    allowed_empty = {"gne"}
    for attr_name in dir(sample_model.network):
        if attr_name.startswith("_"):
            continue
        attr = getattr(sample_model.network, attr_name)
        if not isinstance(attr, pd.DataFrame):
            continue
        assert len(attr.columns) == len(set(attr.columns)), \
            f"{attr_name} has duplicate column names"
        if attr_name not in allowed_empty and not attr_name.startswith("sub"):
            assert not attr.empty, f"{attr_name} DataFrame is empty"
