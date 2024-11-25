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

from psse_model_util.common.dirs import clear_cache

sys.path.append(str(Path(__file__).resolve().parent.parent))

from psse_model_util.compare import ModelComparison, Model
from psse_model_util.common.constants import RangeFilterType

# Dictionary of native PJM areas with their area numbers as keys and names as values
INCLUDE_AREAS = {1: 'CENTRAL', 2: 'EAST', 3: 'CENTRAL_DC', 4: 'EAST_COGEN1', 5: 'WEST', 6: 'EAST_COGEN2'}

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
    # raw1_path = Path(__file__).parent / 'data/sample_34.raw'
    # raw2_path = Path(__file__).parent / 'data/sample2_34.raw'
    clear_cache()
    raw1_path = Path(__file__).parent / 'data/Model_1.raw'
    raw2_path = Path(__file__).parent / 'data/Model_2.raw'

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
    assert model_comparison.model1.name == "Model_1"
    assert model_comparison.model2.name == "Model_2"


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
    assert any((changes['ibus_model1'] == 101) & (changes['ibus_model2'] == 111))
    assert any((changes['ibus_model1'] == 213) & (changes['ibus_model2'] == 219))


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

    for df_name in ['bus', 'generator', 'acline', 'load', 'transformer']:
        df = result[df_name]
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
    assert 'path_sectionalizations' in result
    assert 'path_bypasses' in result

    # Check for the specific path sectionalize we created
    """
      3008,  3013,'BRANCH_FROM_3008_TO_3013___CIRCUIT_ID__1'
      3013,  3014,'BRANCH_FROM_3013_TO_3014___CIRCUIT_ID__1'
      3014,  3009,'BRANCH_FROM_3014_TO_3009___CIRCUIT_ID__1'
    """
    print("result['added_nodes']: ", result['added_nodes'])
    assert len(result['added_nodes']) == 21, '21 new nodes should be found'

    print("result['removed_nodes']: ", result['removed_nodes'])
    assert len(result['removed_nodes']) == 18, 'Should have found 18 nodes removed.'

    print("result['path_sectionalizations']: ", result['path_sectionalizations'])
    print("result['path_sectionalizations'].keys(): ", result['path_sectionalizations'].keys())
    print("Number lines sectionalized (graph sectionalizes):", len(result['path_sectionalizations']))
    assert len(result['path_sectionalizations']) == 1, 'One sectionalize should be found.'

    # Check that sectionalize of ((bus, 3008), (bus, 3009)) from Model_1 was sectionalized.
    assert len([_[0] for _ in result['path_sectionalizations'].values if ('bus', 3008) in _[0]]) > 0

    # Check for the specific path bypass we created
    # 	AC lines ibus 213 - jbus 2000 & ibus 2000 to jbus 214 bypassd into ibus 219 - jbus 214 remvoing bus 2000 and new name BRANCH_FROM__219_TO__214___CIRCUIT_ID__1
    print("Number of lines bypassed (graph bypass) found:", len(result['path_bypasses']))
    assert len(result['path_bypasses']) == 0, 'No bypass should be found.'

    # Check that sectionalize of ((bus, 3008), (bus, 3009)) from Model_1 was sectionalized.
    assert len([_[0] for _ in result['path_bypasses'].values if ('bus', 3008) in _[0]]) == 0


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
    assert set(filtered_model.network.bus['area']) == set(INCLUDE_AREAS.keys())

    # Test with custom areas
    custom_areas = {1: 'Area1', 2: 'Area2'}
    filtered_model = comparison.model1.filter_by_area(areas=custom_areas)
    assert set(filtered_model.network.bus['area']) == {1, 2}

    # Test with empty areas
    with pytest.raises(ValueError):
        comparison.model1.filter_by_area(areas={})


def test_bus_kV_filter(model_comparison):
    """Test the bus_kV_filter method."""
    model_comparison.compare_network_dfs()
    filtered_buses = model_comparison.bus_kv_filter()
    assert isinstance(filtered_buses, list)
    assert all(isinstance(bus_id, int) for bus_id in filtered_buses)
    assert all(
        DEFAULT_KV_FILTER.min <= model_comparison.model1.network.bus.loc[bus_id, 'baskv'] <= DEFAULT_KV_FILTER.max
        for bus_id in filtered_buses
        if bus_id in model_comparison.model1.network.bus.values)


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
        assert (filtered_dfs['generator']['pg'] > float(
            NETWORK_DF_COMPARISON_QUERIES['generator'].sectionalize('>')[1])).all()
    if 'pl' in filtered_dfs['load'].columns:
        assert (filtered_dfs['load']['pl'] > float(NETWORK_DF_COMPARISON_QUERIES['load'].sectionalize('>')[1])).all()


def test_query_network_df_comparison_performance(model_comparison):
    """Test performance of query_network_df_comparison with large datasets."""
    num_rows = 1_000_000
    model_comparison.network_df_comparison = {
        'bus': pd.DataFrame({
            'baskv_model1': np.random.uniform(100, 500, num_rows),
            'baskv_model2': np.random.uniform(100, 500, num_rows),
            'area_model1': np.random.randint(1, 10, num_rows),
            'area_model2': np.random.randint(1, 10, num_rows)
        }),
        'generator': pd.DataFrame({
            'ibus': np.random.randint(1, num_rows, num_rows),
            'pg': np.random.uniform(0, 1000, num_rows)
        }),
        'load': pd.DataFrame({
            'ibus': np.random.randint(1, num_rows, num_rows),
            'pl': np.random.uniform(0, 500, num_rows)
        }),
        'acline': pd.DataFrame({
            'ibus': np.random.randint(1, num_rows, num_rows),
            'jbus': np.random.randint(1, num_rows, num_rows),
            'ckt': np.random.randint(1, num_rows, num_rows),
        }),
        'transformer': pd.DataFrame({
            'ibus': np.random.randint(1, num_rows, num_rows),
            'jbus': np.random.randint(1, num_rows, num_rows),
            'kbus': np.random.randint(1, num_rows, num_rows),
            'ckt': np.random.randint(1, num_rows, num_rows),
        }),
    }

    start_time = time.time()
    _ = model_comparison.query_network_df_comparison()
    end_time = time.time()

    assert end_time - start_time < 1  # Assuming it should take less than 5 seconds


if __name__ == "__main__":
    pytest.main(['-v', __file__])
