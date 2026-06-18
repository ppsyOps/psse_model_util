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
    expected_cols = {
        "flowgate_id", "role", "element_type",
        "from_token", "to_token", "ckt_id",
        "bus_token", "machine_id",
        "reason",
    }
    assert expected_cols.issubset(unresolved.columns)


def test_resolve_unresolved_branch_fills_from_to_ckt(model_1, tmp_path):
    """An unresolved branch row populates from_token/to_token/ckt_id;
    bus_token and machine_id are empty."""
    from psse_model_util.flowgate import parse_mon_file, resolve_elements

    bogus = """\
MONITOR FLOWGATE 5001  'bogus branch'
         BRANCH FROM BUS 'ZZZNOTFOUND 345.00' TO BUS 'ZZZALSOBAD  345.00' CKT 7
 CONTINGENCY 5001
    OPEN BRANCH FROM BUS 'ZZZNOTFOUND 345.00' TO BUS 'ZZZALSOBAD  345.00' CKT 7
 END
    SC PJM
END
"""
    p = tmp_path / "bogus.mon"
    p.write_text(bogus)
    _, unresolved = resolve_elements(parse_mon_file(p), model_1)
    assert len(unresolved) == 2  # monitor + contingency
    for _, row in unresolved.iterrows():
        assert row["from_token"] == "ZZZNOTFOUND 345.00"
        assert row["to_token"] == "ZZZALSOBAD  345.00"
        assert row["ckt_id"] == "7"
        assert pd.isna(row["bus_token"])
        assert pd.isna(row["machine_id"])


def test_resolve_unresolved_generator_fills_bus_machine(model_1, tmp_path):
    """An unresolved REMOVE MACHINE row populates bus_token and machine_id;
    from_token / to_token / ckt_id are empty."""
    from psse_model_util.flowgate import parse_mon_file, resolve_elements

    bogus = """\
MONITOR FLOWGATE 5002  'bogus gen'
         BRANCH FROM BUS 'ZZZNOTFOUND 345.00' TO BUS 'ZZZALSOBAD  345.00' CKT 1
 CONTINGENCY 5002
    REMOVE MACHINE ZZ9 FROM BUS 'ZZZMACHINE  22.000'
 END
    SC PJM
END
"""
    p = tmp_path / "bogus_gen.mon"
    p.write_text(bogus)
    _, unresolved = resolve_elements(parse_mon_file(p), model_1)
    gen_rows = unresolved[unresolved["element_type"] == "generator"]
    assert len(gen_rows) == 1
    row = gen_rows.iloc[0]
    assert row["bus_token"] == "ZZZMACHINE  22.000"
    assert row["machine_id"] == "ZZ9"
    assert pd.isna(row["from_token"])
    assert pd.isna(row["to_token"])
    assert pd.isna(row["ckt_id"])


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


BOGUS_MON = """\
MONITOR FLOWGATE 5000  'bogus bus test'
         BRANCH FROM BUS 'ZZZNOTFOUND 345.00' TO BUS 'ZZZALSOBAD  345.00' CKT 1
 CONTINGENCY 5000
    OPEN BRANCH FROM BUS 'ZZZNOTFOUND 345.00' TO BUS 'ZZZALSOBAD  345.00' CKT 1
 END
    SC PJM
END
"""


def test_resolve_unknown_bus_reports_bus_not_found(model_1, tmp_path):
    from psse_model_util.flowgate import parse_mon_file, resolve_elements

    p = tmp_path / "bogus.mon"
    p.write_text(BOGUS_MON)
    fgs = parse_mon_file(p)

    seeds, unresolved = resolve_elements(fgs, model_1)
    assert seeds == []
    assert len(unresolved) == 2  # one monitor, one contingency
    assert (unresolved["reason"] == "bus_not_found").all()


def test_resolve_kv_precision_three_decimals(model_1):
    """Ensure round(kv, 3) is used so 22.000 matches a bus with baskv 22.0."""
    from psse_model_util.flowgate import KV_KEY_DECIMALS, _build_bus_lookup, _split_bus_token

    lookup = _build_bus_lookup(model_1)
    # Pick any bus and round-trip it through the token format
    bus = model_1.network.bus.iloc[0]
    name = str(bus["name"]).strip()
    baskv = float(bus["baskv"])
    token = f"{name:<12}"[:12] + f"{baskv:<6.2f}"[:6]
    parsed_name, parsed_kv = _split_bus_token(token)
    assert (parsed_name, round(parsed_kv, KV_KEY_DECIMALS)) in lookup
