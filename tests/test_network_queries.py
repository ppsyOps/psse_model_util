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


# ---------------------------------------------------------------------------
# neighborhood
# ---------------------------------------------------------------------------

def test_neighborhood_returns_network_by_default(net):
    result = net.neighborhood(152, n=1)
    assert isinstance(result, Network)


def test_neighborhood_accepts_single_int(net):
    # Passing a bare int should be accepted (converted to {int} internally)
    result = net.neighborhood(152, n=1)
    assert isinstance(result, Network)
    assert 152 in result.bus.index


def test_neighborhood_bus_set_correct(net):
    result = net.neighborhood(152, n=1)
    expected = {152, 151, 202, 3004, 153, 3021, 3022}
    assert set(result.bus.index) == expected


def test_neighborhood_n0_returns_seed_only(net):
    result = net.neighborhood(152, n=0)
    assert set(result.bus.index) == {152}


def test_neighborhood_includes_connected_equipment(net):
    # Bus 152 has a load and/or fixshunt — they should appear in the neighborhood
    result = net.neighborhood(152, n=0)
    assert not result.load.empty or not result.fixshunt.empty


def test_neighborhood_output_dict(net):
    result = net.neighborhood(152, n=1, output='dict')
    assert isinstance(result, dict)
    assert 'bus' in result
    assert 'acline' in result
    assert isinstance(result['bus'], pd.DataFrame)
    assert set(result['bus'].index) == {152, 151, 202, 3004, 153, 3021, 3022}


def test_neighborhood_output_dataframe(net):
    result = net.neighborhood(152, n=1, output='dataframe')
    assert isinstance(result, pd.DataFrame)
    assert 'section' in result.columns
    assert 'bus' in result['section'].values


def test_neighborhood_invalid_output_raises(net):
    with pytest.raises(ValueError, match="output"):
        net.neighborhood(152, n=1, output='excel')


def test_neighborhood_does_not_mutate_original(net):
    original_bus_count = len(net.bus)
    net.neighborhood(152, n=1)
    assert len(net.bus) == original_bus_count


# ---------------------------------------------------------------------------
# tie_line_neighborhood
# ---------------------------------------------------------------------------

def test_tie_line_neighborhood_returns_network(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS)
    assert isinstance(result, Network)


def test_tie_line_neighborhood_both_has_internal_and_external(net):
    result = net.tie_line_neighborhood(n=0, native_areas=NATIVE_AREAS, side='both')
    areas_in_result = set(result.bus['area'].unique())
    native_set = set(NATIVE_AREAS.keys())
    # n=0: only tie-line terminal buses. Some are native, some external.
    assert areas_in_result & native_set        # at least one native area present
    assert areas_in_result - native_set        # at least one external area present


def test_tie_line_neighborhood_internal_only_native_areas(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, side='internal')
    native_set = set(NATIVE_AREAS.keys())
    assert result.bus['area'].isin(native_set).all()


def test_tie_line_neighborhood_external_no_native_areas(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, side='external')
    native_set = set(NATIVE_AREAS.keys())
    assert not result.bus['area'].isin(native_set).any()


def test_tie_line_neighborhood_internal_subset_of_both(net):
    both = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, side='both')
    internal = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, side='internal')
    assert set(internal.bus.index).issubset(set(both.bus.index))


def test_tie_line_neighborhood_kv_filter_reduces_result(net):
    all_ties = net.tie_line_neighborhood(n=0, native_areas=NATIVE_AREAS)
    ehv_ties = net.tie_line_neighborhood(n=0, native_areas=NATIVE_AREAS, kv_min=345)
    assert len(ehv_ties.bus) < len(all_ties.bus)


def test_tie_line_neighborhood_empty_when_no_tie_lines(net):
    # Area 99 has no buses — no tie lines found — returns empty-section Network
    result = net.tie_line_neighborhood(n=1, native_areas={99: "GHOST"})
    assert isinstance(result, Network)
    assert result.bus.empty


def test_tie_line_neighborhood_output_dict(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, output='dict')
    assert isinstance(result, dict)
    assert 'bus' in result


def test_tie_line_neighborhood_output_dataframe(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, output='dataframe')
    assert isinstance(result, pd.DataFrame)
    assert 'section' in result.columns
