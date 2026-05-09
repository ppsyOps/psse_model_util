"""
test_model2.py — supplemental Model method tests.

Ported from tests/legacy_tests/test_model2.py (derived from example_model.py);
updated for the current API and project layout after refactoring.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from psse_model_util.common.dirs import clear_site_cache
from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"
MODEL1_RAW = DATA_DIR / "Model_1.raw"

NATIVE_AREAS = {1: "CENTRAL", 2: "EAST", 3: "CENTRAL_DC"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def clean_cache():
    clear_site_cache()
    yield
    clear_site_cache()


@pytest.fixture(scope="function")
def base_model(clean_cache):
    return Model(file_path_or_json=MODEL1_RAW, name="test_model", force_recalculate=True)


# ---------------------------------------------------------------------------
# Basic loading
# ---------------------------------------------------------------------------

def test_basic_model_loading(clean_cache):
    model = Model(file_path_or_json=MODEL1_RAW, name="test_model", force_recalculate=True)
    assert model is not None
    assert model.name == "test_model"
    assert model.raw_file_path == MODEL1_RAW


def test_model_info(base_model):
    assert base_model.name is not None
    assert base_model.raw_file_path.exists()
    assert base_model.pickle_path.exists()

    network_dfs = base_model.network_dfs()
    assert isinstance(network_dfs, dict)
    assert "bus" in network_dfs
    assert isinstance(network_dfs["bus"], pd.DataFrame)

    assert not base_model.network.bus.empty
    assert "area" in base_model.network.bus.columns


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def test_filter_model_inplace(base_model):
    original_bus_count = len(base_model.network.bus)
    base_model.filter_by_area(areas=NATIVE_AREAS, inplace=True)
    filtered_bus_count = len(base_model.network.bus)
    assert 0 < filtered_bus_count < original_bus_count


def test_filter_model_copy(base_model):
    original_bus_count = len(base_model.network.bus)
    filtered_model = base_model.filter_by_area(
        areas={1: "CENTRAL", 2: "EAST", 3: "CENTRAL_DC"}, inplace=False
    )
    assert len(base_model.network.bus) == original_bus_count
    assert len(filtered_model.network.bus) < original_bus_count
    assert filtered_model is not base_model


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_cache_operations(clean_cache):
    model = Model(file_path_or_json=MODEL1_RAW, name="cache_test", force_recalculate=True)
    cache_path = model.pickle_path
    assert cache_path.exists()

    cache_path.unlink()
    assert not cache_path.exists()

    model.to_pickle()
    assert cache_path.exists()


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def test_csv_export(base_model, tmp_path):
    export_path = tmp_path / "model_export"
    base_model.csv_folder = export_path
    base_model.to_csv()
    assert export_path.exists()
    assert any(export_path.iterdir())
    assert (export_path / "network_bus.csv").exists()
    assert (export_path / "network_generator.csv").exists()


# ---------------------------------------------------------------------------
# Bus info
# ---------------------------------------------------------------------------

def test_section_with_bus_info(base_model):
    acline_w_bus = base_model.network.section_with_bus(section="acline", inplace=False)
    assert isinstance(acline_w_bus, pd.DataFrame)
    assert any("ibus_" in col for col in acline_w_bus.columns)
    assert any("jbus_" in col for col in acline_w_bus.columns)


def test_append_bus_info_to_all_sections(base_model):
    base_model.network.append_bus_info_to_dfs()
    for section in ("acline", "generator"):
        df = getattr(base_model.network, section)
        assert any(col.endswith("_name") for col in df.columns)
        assert any(col.endswith("_area") for col in df.columns)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def test_graph_creation_and_paths(base_model):
    graph = base_model.network.graph(regenerate=True, empty_ok=False)
    assert isinstance(graph, nx.Graph)
    assert graph.number_of_nodes() > 0
    assert graph.number_of_edges() > 0

    try:
        paths = list(nx.all_simple_paths(graph, ("bus", 151), ("bus", 153), cutoff=7))
        assert len(paths) > 0
    except nx.NodeNotFound:
        pytest.skip("Test nodes not found in graph")


def test_graph_edge_cases(base_model):
    graph = base_model.network.graph(regenerate=True, empty_ok=False)
    with pytest.raises(nx.NodeNotFound):
        list(nx.all_simple_paths(graph, ("bus", 999999), ("bus", 153), cutoff=7))
