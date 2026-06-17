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


def test_collect_returns_three_dataframes(model_1, synthetic_seeds):
    """collect_key_facilities returns 3 DataFrames (branches, generators,
    transformers_3w). The 'unresolved' DataFrame comes from resolve_elements
    and is composed into the final dict by callers."""
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert set(out.keys()) == {"branches", "generators", "transformers_3w"}
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


def test_collect_generators_mw_filter_default(model_1, synthetic_seeds):
    """Every generator in the output must have come from a (ibus, machid) whose
    source row has pt >= DEFAULT_GEN_MIN_MW."""
    from psse_model_util.flowgate import DEFAULT_GEN_MIN_MW, collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    gens = out["generators"]
    if gens.empty:
        pytest.skip("No generators in PJM neighborhood; nothing to verify")

    # Build a (bus_name, volt, machid) -> pt lookup from the source
    bus_attrs = model_1.network.bus.reset_index()[["ibus", "name", "baskv"]]
    gen_src = model_1.network.generator.reset_index().merge(
        bus_attrs, on="ibus", how="left"
    )
    gen_src["name"] = gen_src["name"].astype(str).str.strip()
    gen_src["machid"] = gen_src["machid"].astype(str).str.strip()
    pt_lookup = {
        (row["name"], float(row["baskv"]), row["machid"]): float(row["pt"])
        for _, row in gen_src.iterrows()
    }

    for _, row in gens.iterrows():
        key = (str(row["bus_name"]).strip(), float(row["volt"]), str(row["ckt_id"]).strip())
        assert key in pt_lookup, f"output gen {key} not found in source"
        assert pt_lookup[key] >= DEFAULT_GEN_MIN_MW


def test_collect_generators_threshold_override(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out_default = collect_key_facilities(model_1, synthetic_seeds)
    out_high = collect_key_facilities(model_1, synthetic_seeds, gen_min_mw=10000.0)
    assert len(out_high["generators"]) <= len(out_default["generators"])
    assert len(out_high["generators"]) == 0  # no real gen reaches 10 GW


def test_collect_3w_transformers_shape(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    xf3 = out["transformers_3w"]
    # Skip if Model_1 has none
    if xf3.empty:
        pytest.skip("Model_1 has no 3W transformers in the PJM neighborhoods")
    for _, row in xf3.iterrows():
        assert row["w1_bus_name"]
        assert row["w2_bus_name"]
        assert row["w3_bus_name"]
        assert row["w1_volt"] > 0
        assert row["w2_volt"] > 0
        assert row["w3_volt"] > 0


def test_collect_3w_transformers_kv_filter(model_1, synthetic_seeds):
    from psse_model_util.flowgate import DEFAULT_KV_MAX, DEFAULT_KV_MIN, collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    xf3 = out["transformers_3w"]
    if xf3.empty:
        pytest.skip("no 3W xfmrs to filter")
    in_range = (
        xf3["w1_volt"].between(DEFAULT_KV_MIN, DEFAULT_KV_MAX)
        | xf3["w2_volt"].between(DEFAULT_KV_MIN, DEFAULT_KV_MAX)
        | xf3["w3_volt"].between(DEFAULT_KV_MIN, DEFAULT_KV_MAX)
    )
    assert in_range.all()


def test_branches_role_column_values(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert set(out["branches"]["role"]).issubset({"monitor", "contingency"})


def test_branches_have_at_least_one_monitor_and_contingency_row(model_1, synthetic_seeds):
    """The synthetic fixture has both monitor and contingency seeds in PJM areas;
    at least one of each role should appear in the branches output."""
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    roles = set(out["branches"]["role"])
    assert "monitor" in roles
    assert "contingency" in roles


def test_equipment_in_two_flowgates_produces_two_rows(model_1, tmp_path):
    """Spec contract: equipment reached by N flowgates produces N rows.

    Construct an inline .mon with TWO flowgates that monitor the SAME branch;
    confirm that branch appears as a row under each flowgate_id.
    """
    from psse_model_util.flowgate import (
        collect_key_facilities,
        filter_by_sc,
        parse_mon_file,
        resolve_elements,
    )

    # Borrow FG 1001's monitor BRANCH line from the synthetic fixture so the
    # bus tokens resolve cleanly against Model_1.raw.
    fixture_text = (DATA_DIR / "synthetic_pjm.mon").read_text()
    import re
    # Extract the first BRANCH FROM BUS '...' TO BUS '...' CKT <id> line.
    m = re.search(
        r"BRANCH FROM BUS '([^']{18})' TO BUS '([^']{18})' CKT (\S+)",
        fixture_text,
    )
    assert m, "could not locate a BRANCH line in synthetic_pjm.mon"
    from_token, to_token, ckt = m.group(1), m.group(2), m.group(3)

    shared_branch_mon = (
        "BUSNAMES\n"
        "\n"
        f"MONITOR FLOWGATE 7001  'shared branch FG A'\n"
        f"         BRANCH FROM BUS '{from_token}' TO BUS '{to_token}' CKT {ckt}\n"
        " CONTINGENCY 7001\n"
        f"    OPEN BRANCH FROM BUS '{from_token}' TO BUS '{to_token}' CKT {ckt}\n"
        " END\n"
        "    SC PJM\n"
        "END\n"
        "\n"
        f"MONITOR FLOWGATE 7002  'shared branch FG B'\n"
        f"         BRANCH FROM BUS '{from_token}' TO BUS '{to_token}' CKT {ckt}\n"
        " CONTINGENCY 7002\n"
        f"    OPEN BRANCH FROM BUS '{from_token}' TO BUS '{to_token}' CKT {ckt}\n"
        " END\n"
        "    SC PJM\n"
        "END\n"
    )

    p = tmp_path / "shared.mon"
    p.write_text(shared_branch_mon)
    fgs = filter_by_sc(parse_mon_file(p), sc="PJM")
    seeds, unresolved = resolve_elements(fgs, model_1)
    assert unresolved.empty, f"unexpected unresolved:\n{unresolved}"

    out = collect_key_facilities(model_1, seeds)
    df = out["branches"]
    assert not df.empty

    # The shared branch must appear under both flowgate_ids (7001 and 7002).
    counts_per_branch = df.groupby(
        ["from_name", "from_volt", "to_name", "to_volt", "ckt_id"]
    )["flowgate_id"].nunique()
    assert counts_per_branch.max() >= 2, (
        f"expected at least one branch to appear under 2 flowgate_ids; got\n{counts_per_branch}"
    )


def test_end_to_end_synthetic_to_dataframes(model_1):
    from psse_model_util.flowgate import (
        collect_key_facilities,
        filter_by_sc,
        parse_mon_file,
        resolve_elements,
    )

    fgs = parse_mon_file(DATA_DIR / "synthetic_pjm.mon")
    pjm = filter_by_sc(fgs, sc="PJM")
    assert [fg.flowgate_id for fg in pjm] == [1001, 1002, 1003]

    seeds, unresolved = resolve_elements(pjm, model_1)
    assert unresolved.empty, f"unexpected unresolved rows:\n{unresolved}"

    out = collect_key_facilities(model_1, seeds)
    # Sanity: branches non-empty (synthetic PJM seeds are 345 kV)
    assert len(out["branches"]) > 0
    # The collect function returns 3 keys; unresolved is composed in by callers.
    assert set(out.keys()) == {"branches", "generators", "transformers_3w"}
    # Verify the documented composition pattern works.
    full = {**out, "unresolved": unresolved}
    assert set(full.keys()) == {"branches", "generators", "transformers_3w", "unresolved"}


def test_extract_key_facilities_full_pipeline():
    """The convenience wrapper produces the same 4-key dict as composing the
    four stages by hand."""
    from psse_model_util.flowgate import extract_key_facilities

    out = extract_key_facilities(
        mon_path=DATA_DIR / "synthetic_pjm.mon",
        raw_path=DATA_DIR / "Model_1.raw",
        sc="PJM",
    )
    assert set(out.keys()) == {"branches", "generators", "transformers_3w", "unresolved"}
    assert len(out["branches"]) > 0
    assert out["unresolved"].empty


def test_extract_key_facilities_with_areas_filter():
    """Passing areas=[9999] (no equipment) yields empty branches/gens/3W and
    pushes all seeds into unresolved."""
    from psse_model_util.flowgate import extract_key_facilities

    out = extract_key_facilities(
        mon_path=DATA_DIR / "synthetic_pjm.mon",
        raw_path=DATA_DIR / "Model_1.raw",
        sc="PJM",
        areas=[9999],
    )
    assert len(out["branches"]) == 0
    assert len(out["generators"]) == 0
    assert len(out["transformers_3w"]) == 0
    assert len(out["unresolved"]) > 0
