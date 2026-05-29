"""Tests for psse_model_util.flowgate.collect_key_facilities."""
from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="module")
def model_1():
    return Model(DATA_DIR / "Model_1.raw")


@pytest.fixture(scope="module")
def synthetic_seeds(model_1):
    from psse_model_util.flowgate import (
        filter_by_sc,
        parse_mon_file,
        resolve_elements,
    )
    fgs = filter_by_sc(parse_mon_file(DATA_DIR / "synthetic_pjm.mon"), sc="PJM")
    seeds, _ = resolve_elements(fgs, model_1)
    return seeds


BRANCH_COLS = [
    "flowgate_id", "role", "equipment_type",
    "from_name", "from_volt", "from_area",
    "to_name", "to_volt", "to_area",
    "ckt_id",
]
GEN_COLS = ["flowgate_id", "role", "bus_name", "volt", "area", "ckt_id"]
XF3_COLS = [
    "flowgate_id", "role", "transformer_name",
    "w1_bus_name", "w1_volt",
    "w2_bus_name", "w2_volt",
    "w3_bus_name", "w3_volt",
    "ckt_id",
]


def test_collect_returns_four_dataframes(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert set(out.keys()) == {"branches", "generators", "transformers_3w", "unresolved"}
    for v in out.values():
        assert isinstance(v, pd.DataFrame)


def test_collect_branches_has_expected_columns(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert list(out["branches"].columns) == BRANCH_COLS


def test_collect_generators_has_expected_columns(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert list(out["generators"].columns) == GEN_COLS


def test_collect_transformers_3w_has_expected_columns(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert list(out["transformers_3w"].columns) == XF3_COLS


def test_collect_branches_nonempty_for_pjm_seeds(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert len(out["branches"]) > 0


def test_collect_branches_kv_filter_drops_low_voltage(model_1, synthetic_seeds):
    """Every branch row must have at least one end >= kv_min and <= kv_max."""
    from psse_model_util.flowgate import (
        DEFAULT_KV_MAX,
        DEFAULT_KV_MIN,
        collect_key_facilities,
    )

    out = collect_key_facilities(model_1, synthetic_seeds)
    df = out["branches"]
    in_range = (
        ((df["from_volt"] >= DEFAULT_KV_MIN) & (df["from_volt"] <= DEFAULT_KV_MAX))
        | ((df["to_volt"] >= DEFAULT_KV_MIN) & (df["to_volt"] <= DEFAULT_KV_MAX))
    )
    assert in_range.all()


def test_collect_branches_equipment_type_values(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert set(out["branches"]["equipment_type"]).issubset({"line", "transformer_2w"})


def test_collect_branches_kv_filter_loose(model_1, synthetic_seeds):
    """Override kv_min very high to force most branches out, leaving only
    branches with at least one end >= that high voltage."""
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds, kv_min=700.0)
    df = out["branches"]
    if not df.empty:
        passes = ((df["from_volt"] >= 700.0) | (df["to_volt"] >= 700.0)).all()
        assert passes
