"""Tests for psse_model_util.flowgate.resolve_elements."""
import re
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


def test_resolve_remove_machine_against_model(model_1, synthetic_fgs):
    from psse_model_util.flowgate import resolve_elements

    seeds, _ = resolve_elements(synthetic_fgs, model_1)
    gen_seeds = [s for s in seeds if s.element_type == "generator"]
    assert len(gen_seeds) == 1
    assert gen_seeds[0].flowgate_id == 1003
    assert len(gen_seeds[0].seed_buses) == 1  # generator is on a single bus


def test_resolve_unknown_machine_reports_unresolved(model_1, tmp_path):
    from psse_model_util.flowgate import parse_mon_file, resolve_elements

    # Take FG 1003 from the fixture and replace the machine id with one
    # that won't exist in Model_1.raw.
    fixture_text = (DATA_DIR / "synthetic_pjm.mon").read_text()
    mangled = re.sub(
        r"REMOVE MACHINE \S+ FROM",
        "REMOVE MACHINE ZZ9 FROM",
        fixture_text,
    )
    p = tmp_path / "mangled.mon"
    p.write_text(mangled)
    fgs = parse_mon_file(p)

    _, unresolved = resolve_elements(fgs, model_1)
    assert any(
        row["reason"] == "generator_not_found"
        for _, row in unresolved.iterrows()
    )
