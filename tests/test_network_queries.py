"""
test_network_queries.py — Tests for Network.find_tie_lines, _buses_within_n_hops,
neighborhood, and tie_line_neighborhood.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.model import Model, Network

DATA_DIR = Path(__file__).resolve().parent / "data"
MODEL1_RAW = DATA_DIR / "Model_1.raw"

# Model_1.raw uses areas 1-6. INCLUDE_AREAS uses PJM numbers (200+).
# Always pass explicit native_areas in tests.
NATIVE_AREAS = {1: "CENTRAL", 2: "EAST", 3: "CENTRAL_DC"}


@pytest.fixture(scope="module")
def net():
    m = Model(file_path_or_json=MODEL1_RAW, force_recalculate=True)
    return m.network


# ---------------------------------------------------------------------------
# find_tie_lines
# ---------------------------------------------------------------------------

def test_find_tie_lines_returns_dataframe(net):
    result = net.find_tie_lines(native_areas=NATIVE_AREAS)
    assert isinstance(result, pd.DataFrame)


def test_find_tie_lines_xor_logic(net):
    result = net.find_tie_lines(native_areas=NATIVE_AREAS)
    # All 4 expected tie lines: 152→3004, 154→3008, 213→2000, 2000→214
    assert len(result) == 4
    native_set = set(NATIVE_AREAS.keys())
    ibus_native = result["ibus_area"].isin(native_set)
    jbus_native = result["jbus_area"].isin(native_set)
    # XOR: exactly one end must be in native areas
    assert (ibus_native ^ jbus_native).all()


def test_find_tie_lines_enriched_columns(net):
    result = net.find_tie_lines(native_areas=NATIVE_AREAS)
    for col in ("ibus_area", "jbus_area", "ibus_baskv", "jbus_baskv", "ibus_name", "jbus_name"):
        assert col in result.columns, f"Missing column: {col}"


def test_find_tie_lines_kv_filter(net):
    result = net.find_tie_lines(native_areas=NATIVE_AREAS, kv_min=345)
    # Only 152→3004 has both ends at 500 kV
    assert len(result) == 1
    assert result["ibus_baskv"].iloc[0] >= 345
    assert result["jbus_baskv"].iloc[0] >= 345


def test_find_tie_lines_no_internal_lines(net):
    # Lines 152→202, 154→203, 154→205 connect areas 1 and 2 — both native, should be excluded
    result = net.find_tie_lines(native_areas=NATIVE_AREAS)
    native_set = set(NATIVE_AREAS.keys())
    # No row should have BOTH ends in native areas
    both_native = result["ibus_area"].isin(native_set) & result["jbus_area"].isin(native_set)
    assert not both_native.any()


def test_find_tie_lines_empty_when_no_match(net):
    # area 99 doesn't exist in the model
    result = net.find_tie_lines(native_areas={99: "GHOST"})
    assert result.empty


# ---------------------------------------------------------------------------
# _buses_within_n_hops
# ---------------------------------------------------------------------------

def test_buses_within_n_hops_zero(net):
    # n=0 returns exactly the seed set
    result = net._buses_within_n_hops({152}, 0)
    assert result == {152}


def test_buses_within_n_hops_one_direct(net):
    # Bus 152 has direct bus edges to 151, 202, 3004
    # and reaches 153, 3021, 3022 through transformer synthetic nodes
    result = net._buses_within_n_hops({152}, 1)
    assert result == {152, 151, 202, 3004, 153, 3021, 3022}


def test_buses_within_n_hops_includes_seed(net):
    result = net._buses_within_n_hops({152, 154}, 0)
    assert 152 in result
    assert 154 in result


def test_buses_within_n_hops_missing_bus_silently_skipped(net):
    # Bus 99999 does not exist — should not raise
    result = net._buses_within_n_hops({99999}, 1)
    assert isinstance(result, set)
    assert 99999 not in result
    # n=0 must also filter out buses absent from the graph
    result_n0 = net._buses_within_n_hops({99999}, 0)
    assert result_n0 == set()


def test_buses_within_n_hops_two_hops_superset_of_one(net):
    one_hop = net._buses_within_n_hops({152}, 1)
    two_hop = net._buses_within_n_hops({152}, 2)
    assert one_hop.issubset(two_hop)
    assert len(two_hop) >= len(one_hop)


def test_buses_within_n_hops_through_transformer_synthetic_node(net):
    # Bus 101 has NO direct bus edges — only connects through a transformer
    # synthetic node ('transformer', 101, 151) to bus 151.
    # At n=1, bus 151 should be reachable from bus 101.
    result = net._buses_within_n_hops({101}, 1)
    assert 101 in result   # seed always included
    assert 151 in result   # reached through transformer pass-through
