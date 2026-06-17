"""
test_compare.py — ModelComparison tests.

Ported from tests/legacy_tests/test_compare.py; updated for the current API
and project layout after refactoring.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from psse_model_util.common.constants import RangeFilterType
from psse_model_util.common.dirs import clear_cache
from psse_model_util.compare import ModelComparison
from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"

# Area numbers that exist in Model_1.raw / Model_2.raw
INCLUDE_AREAS = {1: "CENTRAL", 2: "EAST", 3: "CENTRAL_DC",
                 4: "EAST_COGEN1", 5: "WEST", 6: "EAST_COGEN2"}

# Wide voltage range so all buses in the fixture pass the filter
DEFAULT_KV_FILTER = RangeFilterType(1, 10_000)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def raw_models():
    """Load Model_1 and Model_2 from the test fixtures (cache cleared first)."""
    clear_cache()
    model1 = Model(DATA_DIR / "Model_1.raw")
    model2 = Model(DATA_DIR / "Model_2.raw")
    return model1, model2


@pytest.fixture(scope="module")
def model_comparison(raw_models):
    model1, model2 = raw_models
    return ModelComparison(model1, model2)


@pytest.fixture(scope="module")
def compared(model_comparison):
    """Run both comparisons once and return the results."""
    df_comp = model_comparison.compare_network_dfs()
    graph_comp = model_comparison.compare_graph()
    return df_comp, graph_comp


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_init(model_comparison):
    assert isinstance(model_comparison, ModelComparison)
    assert model_comparison.model1.name == "Model_1"
    assert model_comparison.model2.name == "Model_2"


# ---------------------------------------------------------------------------
# bus_num_changes
# ---------------------------------------------------------------------------

def test_bus_num_changes(model_comparison):
    changes = model_comparison.bus_num_changes()
    assert isinstance(changes, pd.DataFrame)
    assert not changes.empty
    assert {"ibus_model1", "ibus_model2"}.issubset(changes.columns)
    # Known renames documented in Model_1 and 2 differences.txt
    assert any((changes["ibus_model1"] == 101) & (changes["ibus_model2"] == 111))
    assert any((changes["ibus_model1"] == 213) & (changes["ibus_model2"] == 219))


# ---------------------------------------------------------------------------
# compare_network_dfs
# ---------------------------------------------------------------------------

class TestCompareNetworkDfs:

    def test_returns_dict(self, compared):
        df_comp, _ = compared
        assert isinstance(df_comp, dict)

    def test_required_sections_present(self, compared):
        df_comp, _ = compared
        for section in ("bus", "generator", "load", "acline", "transformer"):
            assert section in df_comp
            assert isinstance(df_comp[section], pd.DataFrame)

    def test_presence_column_exists(self, compared):
        df_comp, _ = compared
        for section in ("bus", "generator", "acline", "load", "transformer"):
            assert "presence" in df_comp[section].columns

    def test_bus_added_and_removed(self, compared):
        df_comp, _ = compared
        bus_df = df_comp["bus"]
        # Bus 156 added in Model_2; Bus 155 removed
        assert any(bus_df["presence"] == "model2_only")
        assert any(bus_df["presence"] == "model1_only")


# ---------------------------------------------------------------------------
# compare_graph
# ---------------------------------------------------------------------------

class TestCompareGraph:

    def test_returns_dict_with_required_keys(self, compared):
        _, graph_comp = compared
        assert isinstance(graph_comp, dict)
        for key in ("added_edges", "removed_edges",
                    "path_sectionalizations", "path_bypasses"):
            assert key in graph_comp

    def test_added_and_removed_nodes(self, compared):
        _, graph_comp = compared
        assert len(graph_comp["added_nodes"]) == 21
        assert len(graph_comp["removed_nodes"]) == 18

    def test_one_sectionalization(self, compared):
        _, graph_comp = compared
        sec = graph_comp["path_sectionalizations"]
        assert len(sec) == 1, "Expected exactly one path sectionalization"

    def test_sectionalization_involves_bus_3008(self, compared):
        _, graph_comp = compared
        sec = graph_comp["path_sectionalizations"]
        paths_with_3008 = [
            row[0] for row in sec.values
            if ("bus", 3008) in row[0]
        ]
        assert len(paths_with_3008) > 0

    def test_no_bypasses(self, compared):
        _, graph_comp = compared
        assert len(graph_comp["path_bypasses"]) == 0


# ---------------------------------------------------------------------------
# to_csv
# ---------------------------------------------------------------------------

def test_to_csv(model_comparison, compared, tmp_path):
    model_comparison.csv_folder = tmp_path
    model_comparison.to_csv(df_comparison_to_csv=True, graph_comparison_to_csv=True)
    assert (tmp_path / "network_bus.csv").exists()
    assert (tmp_path / "graph_added_edges.csv").exists()
    assert (tmp_path / "graph_removed_edges.csv").exists()


# ---------------------------------------------------------------------------
# filter_by_area
# ---------------------------------------------------------------------------

def test_filter_by_area_default(raw_models):
    model1, model2 = raw_models
    comp = ModelComparison(model1, model2)
    filtered = comp.model1.filter_by_area(areas=INCLUDE_AREAS)
    assert set(filtered.network.bus["area"]).issubset(set(INCLUDE_AREAS.keys()))


def test_filter_by_area_custom(raw_models):
    model1, model2 = raw_models
    comp = ModelComparison(model1, model2)
    custom_areas = {1: "Area1", 2: "Area2"}
    filtered = comp.model1.filter_by_area(areas=custom_areas)
    assert set(filtered.network.bus["area"]) == {1, 2}


def test_filter_by_area_empty_raises(raw_models):
    model1, model2 = raw_models
    comp = ModelComparison(model1, model2)
    with pytest.raises(ValueError):
        comp.model1.filter_by_area(areas={})


# ---------------------------------------------------------------------------
# bus_kv_filter
# ---------------------------------------------------------------------------

def test_bus_kv_filter(model_comparison, compared):
    filtered_buses = model_comparison.bus_kv_filter()
    assert isinstance(filtered_buses, list)
    assert all(isinstance(bus_id, int) for bus_id in filtered_buses)
    bus_index = model_comparison.model1.network.bus.index
    for bus_id in filtered_buses:
        if bus_id in bus_index:
            baskv = model_comparison.model1.network.bus.loc[bus_id, "baskv"]
            assert DEFAULT_KV_FILTER.min <= baskv <= DEFAULT_KV_FILTER.max


# ---------------------------------------------------------------------------
# query_network_df_comparison
# ---------------------------------------------------------------------------

def test_query_network_df_comparison_returns_dfs(model_comparison, compared):
    filtered = model_comparison.query_network_df_comparison()
    assert isinstance(filtered, dict)
    assert all(isinstance(df, pd.DataFrame) for df in filtered.values())


def test_query_network_df_comparison_missing_bus_raises(model_comparison, compared):
    # Re-run compare so the dict is fresh before we mutate it
    model_comparison.compare_network_dfs()
    del model_comparison.network_df_comparison["bus"]
    with pytest.raises(KeyError):
        model_comparison.query_network_df_comparison()


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

def test_bus_num_changes_performance(raw_models):
    """bus_num_changes on a 100k-bus model should complete in under 1 second."""
    model1, _ = raw_models
    large_model = model1.copy()
    num_buses = 100_000
    large_model.network.bus = pd.DataFrame({
        "ibus": range(num_buses),
        "name": [f"Bus{i}" for i in range(num_buses)],
        "area": [i % 10 for i in range(num_buses)],
        "baskv": np.random.uniform(100, 500, num_buses),
    }).set_index("ibus")
    large_model.network.bus._metadata = model1.network.bus._metadata

    comp = ModelComparison(large_model, large_model)
    start = time.perf_counter()
    comp.bus_num_changes()
    assert time.perf_counter() - start < 1.0
