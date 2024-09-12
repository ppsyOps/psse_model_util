"""
Test script for compare.py

This script contains unit tests for the ModelComparison class and its methods
in the compare.py module. It uses pytest for testing and includes boundary/edge
cases for argument testing.

Usage:
    pytest test_compare.py

Note: This script assumes the project structure as described in psse_model_util_dir.txt.
"""

import pytest
from pathlib import Path
import pandas as pd
import networkx as nx
from unittest.mock import patch, MagicMock
import numpy as np
import time

# Adjust the import path based on the project structure
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from psse_model_util.compare import ModelComparison, Model
from psse_model_util.common.constants import INCLUDE_AREAS, DEFAULT_KV_FILTER, NETWORK_DF_COMPARISON_QUERIES


# Mock data for testing
@pytest.fixture
def raw_models():
    """
    Uses sample models file for testing.
    """
    raw1_path = Path(__file__).parent / 'data/sample_v35.rawx'
    raw2_path = Path(__file__).parent / 'data/sample2_v35.rawx'

    model1 = Model(raw1_path)
    model2 = Model(raw2_path)

    return model1, model2


@pytest.fixture
def mock_model():
    """
    Creates a mock Model object for testing.

    Returns:
        MagicMock: A mock Model object with necessary attributes and methods.
    """
    mock = MagicMock(spec=Model)
    mock.name = "TestModel"
    mock.raw_file_path = Path("/path/to/test_model.rawx")
    mock.network.bus = pd.DataFrame({
        'ibus': [1, 2, 3],
        'name': ['Bus1', 'Bus2', 'Bus3'],
        'area': [1, 1, 2],
        'baskv': [138, 230, 345]
    })
    mock.network.bus.set_index('ibus', inplace=True)
    mock.network.graph.return_value = nx.Graph()
    return mock


@pytest.fixture
def model_comparison(mock_model):
    """
    Creates a ModelComparison instance for testing.

    Args:
        mock_model (MagicMock): A mock Model object.

    Returns:
        ModelComparison: An instance of ModelComparison for testing.
    """
    model1, model2 = raw_models()
    return ModelComparison(model1, model2)


def test_init(model_comparison):
    """
    Test the initialization of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
    """
    assert isinstance(model_comparison, ModelComparison)
    assert model_comparison.model1.name == "sample_v35"
    assert model_comparison.model2.name == "sample2_v35"


def test_bus_num_changes(model_comparison):
    """
    Test the bus_num_changes method of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
    """
    model1, model2 = raw_models()
    # Modify model2's bus data to create a difference
    model_comparison.model2.network.bus = pd.DataFrame({
        'ibus': [1, 2, 4],
        'name': ['Bus1', 'Bus2', 'Bus3'],
        'area': [1, 1, 2],
        'baskv': [138, 230, 345]
    })
    model_comparison.model2.network.bus.set_index('ibus', inplace=True)

    changes = model_comparison.bus_num_changes()
    assert changes is not None
    assert len(changes) == 1
    assert changes.iloc[0]['ibus_model1'] == 3
    assert changes.iloc[0]['ibus_model2'] == 4


def test_compare_network_dfs(model_comparison):
    """
    Test the compare_network_dfs method of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
    """
    # Add a mock DataFrame to both models
    df1 = pd.DataFrame({'col1': [1, 2, 3], 'col2': ['a', 'b', 'c']})
    df2 = pd.DataFrame({'col1': [1, 2, 4], 'col2': ['a', 'b', 'd']})
    model_comparison.model1.network.test_df = df1
    model_comparison.model2.network.test_df = df2

    result = model_comparison.compare_network_dfs()
    assert 'test_df' in result
    assert 'col1_delta' in result['test_df'].columns
    assert 'col2_delta' in result['test_df'].columns
    assert 'presence' in result['test_df'].columns


def test_compare_graph(model_comparison):
    """
    Test the compare_graph method of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
    """
    # Create different graphs for model1 and model2
    g1 = nx.Graph()
    g1.add_edge(1, 2)
    g1.add_edge(2, 3)
    g2 = nx.Graph()
    g2.add_edge(1, 2)
    g2.add_edge(2, 4)

    model_comparison.model1.network.graph.return_value = g1
    model_comparison.model2.network.graph.return_value = g2

    result = model_comparison.compare_graph()
    assert 'added_edges' in result
    assert 'removed_edges' in result
    assert (2, 4) in result['added_edges']
    assert (2, 3) in result['removed_edges']


def test_to_csv(model_comparison, tmp_path):
    """
    Test the to_csv method of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
        tmp_path (Path): A temporary directory path provided by pytest.
    """
    model_comparison.csv_folder = tmp_path
    model_comparison.network_df_comparison = {
        'test_df': pd.DataFrame({'col1': [1, 2, 3], 'col2': ['a', 'b', 'c']})
    }
    model_comparison.graph_comparison = {
        'added_edges': [(1, 2)],
        'removed_edges': [(3, 4)]
    }

    model_comparison.to_csv(df_comparison_to_csv=True, graph_comparison_to_csv=True)

    assert (tmp_path / 'network_test_df.csv').exists()
    assert (tmp_path / 'graph_added_edges.csv').exists()
    assert (tmp_path / 'graph_removed_edges.csv').exists()


def test_empty_models():
    """Test ModelComparison with empty models."""
    empty_model = MagicMock(spec=Model)
    empty_model.network.bus = pd.DataFrame()
    empty_model.network.graph.return_value = nx.Graph()

    comparison = ModelComparison(empty_model, empty_model)
    assert comparison.bus_num_changes().empty
    assert len(comparison.compare_network_dfs()) == 0
    assert all(len(v) == 0 for v in comparison.compare_graph().values())


def test_large_model_performance():
    """Test performance with a large number of buses."""
    large_model = MagicMock(spec=Model)
    large_model.network.bus = pd.DataFrame({
        'ibus': range(100000),
        'name': [f'Bus{i}' for i in range(100000)],
        'area': [i % 10 for i in range(100000)],
        'baskv': np.random.uniform(100, 500, 100000)
    })
    large_model.network.bus.set_index('ibus', inplace=True)
    large_model.network.graph.return_value = nx.Graph()

    comparison = ModelComparison(large_model, large_model)
    start_time = time.time()
    comparison.bus_num_changes()
    assert time.time() - start_time < 1, "Bus number comparison took too long"


def test_filter_by_area():
    """Test filter_by_area method with various inputs."""
    model = MagicMock(spec=Model)
    model.network.bus = pd.DataFrame({
        'ibus': [1, 2, 3, 4],
        'name': ['Bus1', 'Bus2', 'Bus3', 'Bus4'],
        'area': [1, 1, 2, 3],
        'baskv': [138, 230, 345, 500]
    })
    model.network.bus.set_index('ibus', inplace=True)

    comparison = ModelComparison(model, model)

    # Test with default areas
    filtered_model = comparison.model1.filter_by_area()
    assert set(filtered_model.network.bus.index) == set(INCLUDE_AREAS.keys())

    # Test with custom areas
    custom_areas = {1: 'Area1', 2: 'Area2'}
    filtered_model = comparison.model1.filter_by_area(areas=custom_areas)
    assert set(filtered_model.network.bus.index) == {1, 2, 3}

    # Test with empty areas
    with pytest.raises(ValueError):
        comparison.model1.filter_by_area(areas={})


def test_bus_kV_filter(model_comparison):
    """Test the bus_kV_filter method."""
    filtered_buses = model_comparison.bus_kv_filter()
    assert isinstance(filtered_buses, list)
    assert all(isinstance(bus_id, int) for bus_id in filtered_buses)

    # Test with empty dataframes
    model_comparison.network_df_comparison['bus'] = pd.DataFrame()
    model_comparison.network_df_comparison['generator'] = pd.DataFrame()
    model_comparison.network_df_comparison['load'] = pd.DataFrame()
    assert len(model_comparison.bus_kv_filter()) == 0


def test_inch_dataframes(model_comparison):
    """Test the inch_dataframes property."""
    inch_dfs = model_comparison.query_network_df_comparison()
    assert isinstance(inch_dfs, dict)
    assert all(isinstance(df, pd.DataFrame) for df in inch_dfs.values())

    # Test with missing dataframes
    del model_comparison.network_df_comparison['bus']
    with pytest.raises(KeyError):
        _ = model_comparison.query_network_df_comparison()


# def test_load_inch_filters(model_comparison):
#     """Test the _load_inch_filters method."""
#     filters = NETWORK_DF_COMPARISON_QUERIES
#     assert isinstance(filters, dict)
#     assert 'bus' in filters
#     assert 'generator' in filters
#
#     # Test with non-existent INI file
#     original_path = Path(__file__).parent / 'inch_filters.ini'
#     if original_path.exists():
#         Path(__file__).parent.joinpath('inch_filters.ini').rename(Path(__file__).parent / 'temp.ini')
#         assert NETWORK_DF_COMPARISON_QUERIES == {}
#         Path(__file__).parent.joinpath('temp.ini').rename(original_path)


def test_inch_dataframes_with_filters(model_comparison):
    """Test inch_dataframes with custom filters."""
    # # Mock the _load_inch_filters method to return a test configuration
    # model_comparison._load_inch_filters = lambda: {
    #     'generator': 'pg > 50',
    #     'load': 'pl > 20'
    # }


    inch_dfs = model_comparison.query_network_df_comparison()
    assert 'generator' in inch_dfs
    assert 'load' in inch_dfs
    if 'pg' in inch_dfs['generator'].columns:
        assert (inch_dfs['generator']['pg'] > 50).all()
    if 'pl' in inch_dfs['load'].columns:
        assert (inch_dfs['load']['pl'] > 20).all()


def test_inch_dataframes_performance(model_comparison):
    """Test performance of inch_dataframes with large datasets."""
    # Create large sample dataframes
    num_rows = 1_000_000
    model_comparison.network_df_comparison = {
        'bus': pd.DataFrame({
            'baskv': np.random.uniform(100, 500, num_rows),
            'area': np.random.randint(1, 10, num_rows)
        }),
        'generator': pd.DataFrame({
            'ibus': np.random.randint(1, num_rows, num_rows),
            'pg': np.random.uniform(0, 1000, num_rows)
        }),
        'load': pd.DataFrame({
            'ibus': np.random.randint(1, num_rows, num_rows),
            'pl': np.random.uniform(0, 500, num_rows)
        })
    }

    start_time = time.time()
    _ = model_comparison.query_network_df_comparison()
    end_time = time.time()

    assert end_time - start_time < 5  # Assuming it should take less than 5 seconds


def test_idc_cases():
    """Test ModelComparison with IDC cases."""
    # Use the specific models mentioned in compare.py
    raw1_path = Path(__file__).parent / 'data/IDC_2324W_win24idctr6p3.raw'
    raw2_path = Path(__file__).parent / 'data/IDC_24S_sum24idctr1p8.raw'

    print(f"Loading model1 {raw1_path}...")
    model1 = Model(raw1_path)
    print(f"Filtering model1 {model1.name}...")
    native_model1 = model1.filter_by_area(areas=INCLUDE_AREAS)

    print(f"Loading model2 {raw2_path}...")
    model2 = Model(raw2_path)
    print(f"Filtering model2 {model2.name}...")
    native_model2 = model2.filter_by_area(areas=INCLUDE_AREAS)

    print("Creating ModelComparison...")
    comparison = ModelComparison(native_model1, native_model2)
    print(f"ModelComparison cached to: {comparison.pickle_path}")

    print("Comparing network dataframes...")
    df_comparison = comparison.compare_network_dfs()

    print("Comparing graphs...")
    graph_comparison = comparison.compare_graph()

    print(f"Exporting to CSV: {comparison.csv_folder} ...")
    comparison.to_csv(df_comparison_to_csv=True, graph_comparison_to_csv=True)

    print("Test scenarios completed.")

    # Add assertions
    assert isinstance(df_comparison, dict)
    assert isinstance(graph_comparison, dict)
    assert comparison.pickle_path.exists()
    assert comparison.csv_folder.exists()