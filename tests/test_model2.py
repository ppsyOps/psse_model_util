"""
This is a second test script of model.py.  It was created from example_model.py
as an auxilliary test.
"""
import warnings
from pathlib import Path
from typing import Dict

import pytest
import pandas as pd
import networkx as nx

from psse_model_util.common.dirs import clear_site_cache, clear_cache, site_temp_dir
from psse_model_util.model import Model
# from psse_model_util.common.constants import INCLUDE_AREAS, NATIVE_AREAS, NEIGHBOR_AREAS


# Dictionary of native PJM areas with their area numbers as keys and names as values
NATIVE_AREAS = {1: 'CENTRAL', 2: 'EAST', 3: 'CENTRAL_DC'}

# Dictionary of neighboring areas to PJM with their area numbers as keys and names as values
NEIGHBOR_AREAS = {4: 'EAST_COGEN1', 5: 'WEST', 6: 'EAST_COGEN2'}


# Setup fixtures
@pytest.fixture(scope="session")
def test_raw_path():
    """Fixture providing path to test RAW file."""
    return Path(__file__).parent / "data" / "Model_1.raw"


@pytest.fixture(scope="function")
def clean_cache():
    """Fixture to ensure clean cache state before and after tests."""
    clear_site_cache()
    yield
    clear_site_cache()


@pytest.fixture(scope="function")
def base_model(test_raw_path, clean_cache):
    """Fixture providing a basic model instance."""
    return Model(
        file_path_or_json=test_raw_path,
        name='test_model',
        force_recalculate=True
    )


# Basic model loading tests
def test_basic_model_loading(test_raw_path, clean_cache):
    """Test basic model loading functionality."""
    model = Model(
        file_path_or_json=test_raw_path,
        name='test_model',
        force_recalculate=True
    )
    assert model is not None
    assert model.name == 'test_model'
    assert model.raw_file_path == test_raw_path


def test_model_info(base_model):
    """Test model information attributes and methods."""
    # Test basic attributes
    assert base_model.name is not None
    assert base_model.raw_file_path.exists()
    assert base_model.pickle_path.exists()

    # Test network dataframes
    network_dfs = base_model.network_dfs()
    assert isinstance(network_dfs, dict)
    assert 'bus' in network_dfs
    assert isinstance(network_dfs['bus'], pd.DataFrame)

    # Test bus dataframe structure
    assert not base_model.network.bus.empty
    assert 'area' in base_model.network.bus.columns


# Model filtering tests
def test_filter_model_inplace(base_model):
    """Test model filtering with inplace modification."""
    original_bus_count = len(base_model.network.bus)

    # Filter model inplace
    base_model.filter_by_area(areas=NATIVE_AREAS, inplace=True)
    filtered_bus_count = len(base_model.network.bus)

    assert filtered_bus_count < original_bus_count
    assert filtered_bus_count > 0


def test_filter_model_copy(base_model):
    """Test model filtering with copy creation."""
    original_bus_count = len(base_model.network.bus)

    # Create filtered copy
    areas = {1: 'CENTRAL', 2: 'EAST', 3: 'CENTRAL_DC'}
    filtered_model = base_model.filter_by_area(areas=areas, inplace=False)

    # Verify original unchanged
    assert len(base_model.network.bus) == original_bus_count
    assert len(filtered_model.network.bus) < original_bus_count
    assert filtered_model is not base_model


# Cache handling tests
def test_cache_operations(test_raw_path, clean_cache):
    """Test model caching operations."""
    # Create initial model
    model = Model(
        file_path_or_json=test_raw_path,
        name='cache_test',
        force_recalculate=True
    )

    cache_path = model.pickle_path
    assert cache_path.exists()

    # Test cache deletion
    cache_path.unlink()
    assert not cache_path.exists()

    # Test manual cache creation
    model.to_pickle()
    assert cache_path.exists()


# CSV export tests
def test_csv_export(base_model, tmp_path):
    """Test CSV export functionality."""
    # Set custom export path
    export_path = tmp_path / "model_export"
    base_model.csv_folder = export_path

    # Export and verify
    base_model.to_csv()
    assert export_path.exists()
    assert any(export_path.iterdir())  # Check if files were created

    # Verify key files exist
    assert (export_path / "network_bus.csv").exists()
    assert (export_path / "network_generator.csv").exists()


# Bus info tests
def test_section_with_bus_info(base_model):
    """Test adding bus information to network sections."""
    acline_w_bus = base_model.network.section_with_bus(section='acline', inplace=False)

    assert isinstance(acline_w_bus, pd.DataFrame)
    assert any('ibus_' in col for col in acline_w_bus.columns)
    assert any('jbus_' in col for col in acline_w_bus.columns)


def test_append_bus_info_to_all_sections(base_model):
    """Test adding bus information to all network sections."""
    base_model.network.append_bus_info_to_dfs()

    # Check key sections for bus info
    for section in ['acline', 'generator']:
        df = getattr(base_model.network, section)
        assert any(col.endswith('_name') for col in df.columns)
        assert any(col.endswith('_area') for col in df.columns)


# Graph tests
def test_graph_creation_and_paths(base_model):
    """Test network graph creation and path finding."""
    graph = base_model.network.graph(regenerate=True, empty_ok=False)
    assert isinstance(graph, nx.Graph)
    assert graph.number_of_nodes() > 0
    assert graph.number_of_edges() > 0

    # Test path finding between nodes that should exist
    try:
        paths = list(nx.all_simple_paths(
            graph,
            ('bus', 151),
            ('bus', 153),
            cutoff=7
        ))
        assert len(paths) > 0
    except nx.NodeNotFound:
        pytest.skip("Test nodes not found in graph")


def test_graph_edge_cases(base_model):
    """Test graph handling of edge cases."""
    graph = base_model.network.graph(regenerate=True, empty_ok=False)

    # Test non-existent nodes
    with pytest.raises(nx.NodeNotFound):
        list(nx.all_simple_paths(
            graph,
            ('bus', 999999),  # Non-existent bus
            ('bus', 153),
            cutoff=7
        ))

