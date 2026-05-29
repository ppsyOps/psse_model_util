"""Tests for psse_model_util.flowgate.resolve_elements."""
from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="module")
def model_1():
    return Model(DATA_DIR / "Model_1.raw")


@pytest.fixture(scope="module")
def synthetic_fgs():
    from psse_model_util.flowgate import filter_by_sc, parse_mon_file

    fgs = parse_mon_file(DATA_DIR / "synthetic_pjm.mon")
    return filter_by_sc(fgs, sc="PJM")  # drops 9001


def test_resolve_returns_two_results(model_1, synthetic_fgs):
    from psse_model_util.flowgate import resolve_elements

    result = resolve_elements(synthetic_fgs, model_1)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_resolve_seeds_have_buses(model_1, synthetic_fgs):
    from psse_model_util.flowgate import ResolvedSeed, resolve_elements

    seeds, unresolved = resolve_elements(synthetic_fgs, model_1)
    assert isinstance(unresolved, pd.DataFrame)
    assert all(isinstance(s, ResolvedSeed) for s in seeds)
    # Every PJM FG should have at least one resolved seed
    fg_ids_with_seeds = {s.flowgate_id for s in seeds}
    assert fg_ids_with_seeds == {1001, 1002, 1003}


def test_resolve_synthetic_branches_have_two_bus_seeds(model_1, synthetic_fgs):
    from psse_model_util.flowgate import resolve_elements

    seeds, _ = resolve_elements(synthetic_fgs, model_1)
    branch_seeds = [s for s in seeds if s.element_type == "branch"]
    assert branch_seeds, "expected at least one branch seed"
    for s in branch_seeds:
        assert len(s.seed_buses) == 2  # from and to bus


def test_resolve_unresolved_dataframe_columns(model_1, synthetic_fgs):
    from psse_model_util.flowgate import resolve_elements

    _, unresolved = resolve_elements(synthetic_fgs, model_1)
    expected_cols = {"flowgate_id", "role", "element_type", "raw_tokens", "reason"}
    assert expected_cols.issubset(unresolved.columns)
