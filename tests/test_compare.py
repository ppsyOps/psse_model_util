"""
test_compare.py - Test script for compare.py

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
import numpy as np
import time

# Adjust the import path based on the project structure
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from psse_model_util.compare import ModelComparison, Model
from psse_model_util.common.constants import RangeFilterType

INCLUDE_AREAS = {101: 'CENTRAL     ', 206: 'EAST        ', 301: 'CENTRAL_DC  ',
                 401: 'EAST_COGEN1 ', 3011: 'WEST        ', 402: 'EAST_COGEN2 '}

DEFAULT_KV_FILTER = RangeFilterType(1, 10000)

NETWORK_DF_COMPARISON_QUERIES = {
    'bus': f'ibus.isin({list(INCLUDE_AREAS.keys())}) '
           f'and baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
           f'and (presence != "both" or evhi_delta > 0 or nvlo_delta > 0 '
           f'or va_delta > 0 or nvhi_delta > 0 or evlo_delta > 0 '
           f'or ide_delta > 0 or baskv_delta > 0 or name_delta > 0 '
           f'or zone_delta > 0 or vm_delta > 0 or owner_delta > 0 '
           f'or area_delta > 0)',
    'generator': f'pg_model2 > 1',
    'load': f'pl_model1 > 10',
    'acline': f'(ibus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
              f'or jbus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
              f'or ibus_baskv_model2 >= {DEFAULT_KV_FILTER[0]} '
              f'or jbus_baskv_model2 >= {DEFAULT_KV_FILTER[0]}) ',
    'transformer': f'ibus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
                   f'or jbus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
                   f'or kbus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
                   f'or ibus_baskv_model2 >= {DEFAULT_KV_FILTER[0]} '
                   f'or jbus_baskv_model2 >= {DEFAULT_KV_FILTER[0]} '
                   f'or kbus_baskv_model2 >= {DEFAULT_KV_FILTER[0]}'
    }

@pytest.fixture
def raw_models():
    """
    Fixture to create Model objects from sample RAW files for testing.

    Returns:
        tuple: Two Model objects created from sample RAW files.
    """
    raw1_path = Path(__file__).parent / 'data/sample_34.raw'
    raw2_path = Path(__file__).parent / 'data/sample2_34.raw'

    model1 = Model(raw1_path)
    model2 = Model(raw2_path)

    return model1, model2


@pytest.fixture
def model_comparison(raw_models):
    """
    Fixture to create a ModelComparison instance for testing.

    Args:
        raw_models (tuple): Two Model objects.

    Returns:
        ModelComparison: An instance of ModelComparison for testing.
    """
    model1, model2 = raw_models
    return ModelComparison(model1, model2)


def test_init(model_comparison):
    """
    Test the initialization of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
    """
    assert isinstance(model_comparison, ModelComparison)
    assert model_comparison.model1.name == "sample_34"
    assert model_comparison.model2.name == "sample2_34"


def test_bus_num_changes(model_comparison):
    """
    Test the bus_num_changes method of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
    """
    changes = model_comparison.bus_num_changes()
    assert changes is not None
    assert isinstance(changes, pd.DataFrame)
    assert not changes.empty
    assert all(col in changes.columns for col in ['ibus_model1', 'ibus_model2'])

    # Check for the specific bus number change we made (151 to 150)
    assert any((changes['ibus_model1'] == 151) & (changes['ibus_model2'] == 150))


def test_compare_network_dfs(model_comparison):
    """
    Test the compare_network_dfs method of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
    """
    result = model_comparison.compare_network_dfs()
    assert isinstance(result, dict)
    assert 'bus' in result
    assert 'generator' in result
    assert 'load' in result
    assert 'acline' in result

    for df in result.values():
        assert isinstance(df, pd.DataFrame)
        assert 'presence' in df.columns

    # Check for added and removed buses
    bus_df = result['bus']
    assert any(bus_df['presence'] == 'model2_only')  # Bus 156 added
    assert any(bus_df['presence'] == 'model1_only')  # Bus 155 removed

def test_compare_graph(model_comparison):
    """
    Test the compare_graph method of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
    """
    result = model_comparison.compare_graph()
    assert isinstance(result, dict)
    assert 'added_edges' in result
    assert 'removed_edges' in result
    assert 'path_splits' in result
    assert 'path_merges' in result

    # Check for the specific path split we created
    split_found = any(('bus', 152) in edge and ('bus', 3004) in edge for edge in result['removed_edges'])
    assert split_found, "Expected path split not found"

    # Check for the specific path merge we created
    merge_found = any(('bus', 3003) in edge and ('bus', 3006) in edge for edge in result['added_edges'])
    assert merge_found, "Expected path merge not found"


def test_to_csv(model_comparison, tmp_path):
    """
    Test the to_csv method of ModelComparison.

    Args:
        model_comparison (ModelComparison): An instance of ModelComparison.
        tmp_path (Path): A temporary directory path provided by pytest.
    """
    model_comparison.csv_folder = tmp_path
    model_comparison.compare_network_dfs()
    model_comparison.compare_graph()
    model_comparison.to_csv(df_comparison_to_csv=True, graph_comparison_to_csv=True)

    assert (tmp_path / 'network_bus.csv').exists()
    assert (tmp_path / 'graph_added_edges.csv').exists()
    assert (tmp_path / 'graph_removed_edges.csv').exists()


def test_empty_models(raw_models):
    """Test ModelComparison with empty models."""
    model1, model2 = raw_models
    model1.network.bus = pd.DataFrame()
    model2.network.bus = pd.DataFrame()

    comparison = ModelComparison(model1, model2)
    assert comparison.bus_num_changes().empty
    assert len(comparison.compare_network_dfs()) == 0
    assert all(len(v) == 0 for v in comparison.compare_graph().values())


def test_large_model_performance(raw_models):
    """Test performance with a large number of buses."""
    model1, _ = raw_models
    large_model = model1.copy()
    num_buses = 100000
    large_model.network.bus = pd.DataFrame({
        'ibus': range(num_buses),
        'name': [f'Bus{i}' for i in range(num_buses)],
        'area': [i % 10 for i in range(num_buses)],
        'baskv': np.random.uniform(100, 500, num_buses)
    }).set_index('ibus')

    comparison = ModelComparison(large_model, large_model)
    start_time = time.time()
    comparison.bus_num_changes()
    assert time.time() - start_time < 1, "Bus number comparison took too long"


def test_filter_by_area(raw_models):
    """Test filter_by_area method with various inputs."""
    model1, _ = raw_models
    comparison = ModelComparison(model1, model1)

    # Test with default areas
    filtered_model = comparison.model1.filter_by_area()
    assert set(filtered_model.network.bus.index) == set(INCLUDE_AREAS.keys())

    # Test with custom areas
    custom_areas = {1: 'Area1', 2: 'Area2'}
    filtered_model = comparison.model1.filter_by_area(areas=custom_areas)
    assert set(filtered_model.network.bus['area']) == {1, 2}

    # Test with empty areas
    with pytest.raises(ValueError):
        comparison.model1.filter_by_area(areas={})


def test_bus_kV_filter(model_comparison):
    """Test the bus_kV_filter method."""
    filtered_buses = model_comparison.bus_kv_filter()
    assert isinstance(filtered_buses, list)
    assert all(isinstance(bus_id, int) for bus_id in filtered_buses)
    assert all(
        DEFAULT_KV_FILTER.min <= model_comparison.model1.network.bus.loc[bus_id, 'baskv'] <= DEFAULT_KV_FILTER.max for
        bus_id in filtered_buses)


def test_query_network_df_comparison(model_comparison):
    """Test the query_network_df_comparison method."""
    model_comparison.compare_network_dfs()
    filtered_dfs = model_comparison.query_network_df_comparison()
    assert isinstance(filtered_dfs, dict)
    assert all(isinstance(df, pd.DataFrame) for df in filtered_dfs.values())

    # Test with missing dataframes
    del model_comparison.network_df_comparison['bus']
    with pytest.raises(KeyError):
        model_comparison.query_network_df_comparison()


def test_query_network_df_comparison_with_filters(model_comparison):
    """Test query_network_df_comparison with custom filters."""
    model_comparison.compare_network_dfs()
    filtered_dfs = model_comparison.query_network_df_comparison()
    assert 'generator' in filtered_dfs
    assert 'load' in filtered_dfs

    # Check if filters are applied correctly
    if 'pg' in filtered_dfs['generator'].columns:
        assert (filtered_dfs['generator']['pg'] > float(NETWORK_DF_COMPARISON_QUERIES['generator'].split('>')[1])).all()
    if 'pl' in filtered_dfs['load'].columns:
        assert (filtered_dfs['load']['pl'] > float(NETWORK_DF_COMPARISON_QUERIES['load'].split('>')[1])).all()


def test_query_network_df_comparison_performance(model_comparison):
    """Test performance of query_network_df_comparison with large datasets."""
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


if __name__ == "__main__":
    pytest.main(['-v', __file__])