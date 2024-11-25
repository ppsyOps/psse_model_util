import pytest
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
from typing import Dict

from psse_model_util.model import Model, Network, ModelEncoder

# Setup the path to the test RAWX file
TEST_DATA_DIR = Path(__file__).parent.parent / 'tests' / 'data'
TEST_RAWX_FILE = TEST_DATA_DIR / 'sample_v35.rawx'
MODEL1_RAW = TEST_DATA_DIR / 'Model_1.raw'

# Dictionary of native PJM areas with their area numbers as keys and names as values
NATIVE_AREAS = {1: 'CENTRAL', 2: 'EAST', 3: 'CENTRAL_DC'}

# Dictionary of neighboring areas to PJM with their area numbers as keys and names as values
NEIGHBOR_AREAS = {4: 'EAST_COGEN1', 5: 'WEST'}

# Combined dictionary of native and neighboring areas, used for filtering models
INCLUDE_AREAS = NEIGHBOR_AREAS.copy() | NATIVE_AREAS.copy()


@pytest.fixture
def sample_model():
    return Model(file_path_or_json=TEST_RAWX_FILE, force_recalculate=True)


# Fixtures for test data
@pytest.fixture
def model1_network():
    """Create a network from MODEL1_RAW for testing."""
    # Load the model
    model_path = Path(__file__).parent / 'data/Model_1.raw'
    model = Model(model_path)
    return model.network


@pytest.fixture
def empty_network():
    """Create an empty network for edge case testing."""
    network = Network.__new__(Network)
    network.bus = pd.DataFrame(columns=['ibus', 'baskv'])
    network.bus._metadata = {'bus_cols': ['ibus']}
    network._graph = None
    return network


# Tests for filter_section
def test_filter_section_basic(model1_network):
    """Test basic filtering functionality."""
    # Filter buses above 345 kV
    result = model1_network.filter_section('bus', 'baskv >= 345')
    assert len(result.bus) < len(model1_network.bus)
    assert all(result.bus['baskv'] >= 345)


def test_filter_section_inplace(model1_network):
    """Test inplace filtering."""
    original_len = len(model1_network.bus)
    model1_network.filter_section('bus', 'baskv >= 345', inplace=True)
    assert len(model1_network.bus) < original_len
    assert all(model1_network.bus['baskv'] >= 345)


def test_filter_section_invalid_where(model1_network):
    """Test error handling for invalid where clause."""
    with pytest.raises(ValueError):
        model1_network.filter_section('bus', 'invalid_column > 100')


def test_filter_section_nonexistent_section(model1_network):
    """Test error handling for non-existent section."""
    with pytest.raises(ValueError):
        model1_network.filter_section('nonexistent', 'col > 0')


def test_filter_section_empty_result(model1_network):
    """Test filtering that results in empty DataFrame."""
    result = model1_network.filter_section('bus', 'baskv > 1000000')
    assert len(result.bus) == 0


def test_filter_section_graph_effects(model1_network):
    """Test different graph effect options."""
    # Test clear
    result = model1_network.filter_section('bus', 'baskv >= 345', graph_effect='clear')
    assert len(result._graph.nodes) == 0

    # Test regenerate
    result = model1_network.filter_section('bus', 'baskv >= 345', graph_effect='regenerate')
    assert len(result._graph.nodes) > 0

    # Test leave
    model1_network.graph(regenerate=True)
    original_nodes = len(model1_network._graph.nodes)
    result = model1_network.filter_section('bus', 'baskv >= 345', graph_effect='leave')
    assert len(result._graph.nodes) == original_nodes


# Tests for filter_by_kv
def test_filter_by_kv_basic(model1_network):
    """Test basic voltage filtering functionality."""
    result = model1_network.filter_by_kv(230, 500)
    assert all(result.bus['baskv'] >= 230)
    assert all(result.bus['baskv'] < 500)


def test_filter_by_kv_invalid_range(model1_network):
    """Test error handling for invalid voltage ranges."""
    with pytest.raises(ValueError):
        model1_network.filter_by_kv(-100, 500)

    with pytest.raises(ValueError):
        model1_network.filter_by_kv(500, 100)


def test_filter_by_kv_edge_values(model1_network):
    """Test filtering at boundary voltage values."""
    # Test exact voltage match
    exact_kv = 230.0
    result = model1_network.filter_by_kv(exact_kv, exact_kv + 0.1)
    assert all(result.bus['baskv'] >= exact_kv)
    assert all(result.bus['baskv'] < exact_kv + 0.1)


# def test_filter_by_kv_equipment_connections(model1_network):
#     """Test that equipment connected to filtered buses is properly handled."""
#     result = model1_network.filter_by_kv(230, 500)
#
#     # Check transformers
#     if hasattr(result, 'transformer') and len(result.transformer) > 0:
#         for idx, row in result.transformer.iterrows():
#             connected_buses = set()
#             for bus_col in result.transformer._metadata['bus_cols']:
#                 if bus_col in result.transformer.columns:
#                     connected_buses.add(row[bus_col])
#                 elif bus_col in result.transformer.index.names:
#                     connected_buses.add(idx[list(result.transformer.index.names).index(bus_col)])
#
#             # At least one connected bus should be in the voltage range
#             bus_kv = result.bus.loc[list(connected_buses)]['baskv']
#             assert any((bus_kv >= 230) & (bus_kv < 500))


def test_filter_by_kv_empty_network(empty_network):
    """Test filtering an empty network."""
    result = empty_network.filter_by_kv(100, 200)
    assert len(result.bus) == 0


def test_filter_by_kv_metadata_preservation(model1_network):
    """Test that DataFrame metadata is preserved after filtering."""
    original_metadata = {
        name: df._metadata
        for name, df in model1_network.model_dfs().items()
        if hasattr(df, '_metadata')
    }

    result = model1_network.filter_by_kv(230, 500)

    filtered_metadata = {
        name: df._metadata
        for name, df in result.model_dfs().items()
        if hasattr(df, '_metadata')
    }

    assert original_metadata == filtered_metadata


def test_filter_by_kv_inplace(model1_network):
    """Test inplace filtering by voltage."""
    original_bus_count = len(model1_network.bus)
    model1_network.filter_by_kv(230, 500, inplace=True)
    assert len(model1_network.bus) < original_bus_count
    assert all(model1_network.bus['baskv'] >= 230)
    assert all(model1_network.bus['baskv'] < 500)

@pytest.fixture
def filtered_model(sample_model):
    return sample_model.filter_by_area(areas=INCLUDE_AREAS, inplace=False)


def test_model_initialization(sample_model):
    assert isinstance(sample_model, Model)
    assert sample_model.raw_file_path == TEST_RAWX_FILE
    assert sample_model.version is not None


# def test_initialize_from_json_str(tmp_path):
#     """
#     Test initializing a Model directly from JSON string data.
#
#     This test verifies that a model created from a JSON string is equivalent
#     to one created directly from a RAW file. It performs the following steps:
#     1. Loads a model from RAW file
#     2. Extracts JSON data from that model
#     3. Creates new model from the JSON string
#     4. Compares all DataFrames between the models
#
#     Args:
#         tmp_path (Path): pytest fixture providing temporary directory path
#
#     The test verifies:
#     - All DataFrames exist in both models
#     - DataFrame contents are identical
#     - DataFrame metadata is preserved
#     - DataFrame indices are preserved
#     """
#     import json
#     from pathlib import Path
#     import pandas as pd
#
#     # Load raw file into model
#     raw_path = Path(__file__).parent / 'data' / 'Model_1.raw'
#     model = Model(file_path_or_json=raw_path, force_recalculate=True)
#
#     # Extract json data from model using custom encoder
#     model_json = json.dumps(model.json_data, cls=ModelEncoder)
#
#     # Create new model from json string
#     model_from_json = Model(file_path_or_json=model_json)
#
#     # Compare network DataFrames between models
#     raw_dfs = model.network.model_dfs()
#     json_dfs = model_from_json.network.model_dfs()
#
#     # Verify same DataFrames exist in both models
#     assert set(raw_dfs.keys()) == set(json_dfs.keys()), \
#         "Models have different DataFrame sets"
#
#     # Compare each DataFrame
#     for df_name, raw_df in raw_dfs.items():
#         json_df = json_dfs[df_name]
#
#         # Convert both to string representation to handle floating point comparison
#         raw_str = raw_df.to_string()
#         json_str = json_df.to_string()
#
#         # Compare DataFrame contents
#         assert raw_str == json_str, \
#             f"DataFrame {df_name} contents differ between models"
#
#         # Compare DataFrame metadata
#         assert raw_df._metadata == json_df._metadata, \
#             f"DataFrame {df_name} metadata differs between models"
#
#         # Compare DataFrame index names
#         assert raw_df.index.names == json_df.index.names, \
#             f"DataFrame {df_name} index differs between models"
#
#         # Compare DataFrame columns
#         assert list(raw_df.columns) == list(json_df.columns), \
#             f"DataFrame {df_name} columns differ between models"
#
#         # Compare DataFrame dtypes
#         assert raw_df.dtypes.equals(json_df.dtypes), \
#             f"DataFrame {df_name} dtypes differ between models"
#
#     # Verify pickle functionality also works for json-created model
#     json_pickle_path = tmp_path / "json_model.model"
#     model_from_json.pickle_path = json_pickle_path
#     model_from_json.to_pickle()
#     assert json_pickle_path.exists()


def test_filter_by_area(sample_model):
    assert hasattr(sample_model.network, 'filter_by_area'), "Network object should have 'filter_by_area' method"
    filtered = sample_model.filter_by_area(areas=NATIVE_AREAS, inplace=False)
    assert isinstance(filtered, Model)
    assert filtered is not sample_model  # Ensure a new object is returned when inplace=False
    assert len(filtered.network.bus) < len(sample_model.network.bus)


@pytest.mark.parametrize("areas", [NATIVE_AREAS, INCLUDE_AREAS, list(NATIVE_AREAS.keys())])
def test_filter_by_area_different_inputs(sample_model, areas):
    filtered = sample_model.filter_by_area(areas=areas, inplace=False)
    assert isinstance(filtered, Model)
    assert len(filtered.network.bus) < len(sample_model.network.bus)


def test_network_attribute(sample_model):
    assert hasattr(sample_model, 'network'), "Model should have a 'network' attribute"
    assert isinstance(sample_model.network, Network), "The 'network' attribute should be an instance of Network"


def test_network_graph(filtered_model):
    graph = filtered_model.network.graph(regenerate=True)
    assert isinstance(graph, nx.Graph)
    assert graph.number_of_nodes() > 0
    assert graph.number_of_edges() > 0


def test_append_bus_info_to_dfs(filtered_model):
    filtered_model.network.append_bus_info_to_dfs()
    for df_name, df in filtered_model.network.model_dfs().items():
        if df_name != 'bus' and hasattr(df, '_metadata') and 'bus_cols' in df._metadata:
            for bus_col in df._metadata['bus_cols']:
                assert f"{bus_col}_name" in df.columns


def test_to_pickle(filtered_model, tmp_path):
    pickle_path = tmp_path / "test_model.model"
    filtered_model.pickle_path = pickle_path
    result = filtered_model.to_pickle()
    assert result == pickle_path
    assert pickle_path.exists()


def test_read_pickle(filtered_model):
    filtered_model.pickle_path.unlink(missing_ok=True)
    filtered_model.to_pickle()
    pickle_path = filtered_model.pickle_path

    new_model = Model(pickle_path)
    new_model.pickle_path = pickle_path
    loaded_data = new_model.read_pickle()

    assert loaded_data.file_path == pickle_path
    assert isinstance(loaded_data.object, Model)
    assert new_model.raw_file_path == filtered_model.raw_file_path
    filtered_model.pickle_path.unlink(missing_ok=True)


# def test_to_excel(filtered_model, tmp_path):
#     excel_path = tmp_path / "test_model.xlsx"
#     filtered_model.to_excel(file_path=excel_path)
#     assert excel_path.exists()
#
#     # Check if the Excel file contains the expected sheets
#     with pd.ExcelFile(excel_path) as xls:
#         assert 'general' in xls.sheet_names
#         assert 'network.bus' in xls.sheet_names


def test_to_csv(filtered_model, tmp_path):
    filtered_model.csv_folder = tmp_path
    filtered_model.to_csv()

    assert (tmp_path / 'general.csv').exists()
    assert (tmp_path / 'network_bus.csv').exists()


def test_model_dfs(filtered_model):
    actual_dfs = filtered_model.network.model_dfs()
    assert isinstance(actual_dfs, dict)
    assert all(isinstance(df, pd.DataFrame) for df in actual_dfs.values())

    actual_df_names = set(actual_dfs.keys())
    expected_df_names = {
        'bus', 'load', 'fixshunt', 'generator', 'acline', 'sysswd',
        'transformer', 'area', 'twotermdc', 'vscdc', 'impcor', 'ntermdc',
        'ntermdcconv', 'ntermdcbus', 'ntermdclink', 'msline', 'zone',
        'iatrans', 'owner', 'facts', 'swshunt', 'indmach', 'newton', 'adjust',
        'rating', 'subswd', 'sub', 'subnode', 'caseid', 'gauss', 'general',
        'solver', 'gne', 'tysl', 'subterm'
    }

    # Check if all expected DataFrame names are present in the actual DataFrame names
    assert expected_df_names.issubset(actual_df_names), \
        f"Missing expected DataFrames: {expected_df_names - actual_df_names}"

    # Check for any unexpected DataFrame names
    unexpected_df_names = actual_df_names - expected_df_names
    assert not unexpected_df_names, \
        f"Unexpected DataFrames found: {unexpected_df_names}"

    # Check for specific important DataFrames
    assert 'bus' in actual_dfs, "Bus DataFrame is missing"
    assert 'generator' in actual_dfs, "Generator DataFrame is missing"
    assert 'acline' in actual_dfs, "AC line DataFrame is missing"

    # Optional: Check the structure of some key DataFrames
    assert 'ibus' in actual_dfs['bus'].index.names, "Bus DataFrame is missing 'ibus' column"
    assert 'ibus' in actual_dfs['generator'].index.names, "Generator DataFrame is missing 'ibus' column"
    assert 'ibus' in actual_dfs['acline'].index.names, "AC line DataFrame is missing 'ibus' column"


def test_force_recalculate():
    # Create a model and save it to cache
    model1 = Model(file_path_or_json=TEST_RAWX_FILE)
    model1.to_pickle()

    # Load the model from cache
    model2 = Model(file_path_or_json=TEST_RAWX_FILE)

    # Force recalculation
    model3 = Model(file_path_or_json=TEST_RAWX_FILE, force_recalculate=True)

    assert model1.pickle_path == model2.pickle_path == model3.pickle_path
    assert model1.raw_file_path == model2.raw_file_path == model3.raw_file_path

    # Check that model2 is loaded from cache (should be fast)
    assert model2.network is not None

    # Check that model3 is recalculated (should take longer and have different object ids)
    assert model3.network is not None
    assert id(model2.network) != id(model3.network)


def test_model_name_assignment():
    """
    Test Model class name assignment behavior.

    Tests both auto-generated names and explicitly provided names under different scenarios:
    1. Name provided when loading from RAW file
    2. Auto-generated name from RAW file
    3. Name provided when loading from JSON
    4. Multiple model instantiations to verify name uniqueness

    The test verifies that:
    - Provided names are preserved
    - Auto-generated names follow expected format
    - Auto-generated names include version and bus count
    - Name changes don't affect model data
    """
    from pathlib import Path
    import json

    # Test case 1: Explicit name with RAW file
    raw_path = Path(__file__).parent / 'data' / 'Model_1.raw'
    explicit_name = "Test_Model_Name"
    model1 = Model(file_path_or_json=raw_path, name=explicit_name)
    assert model1.name == explicit_name, "Explicit name not preserved"

    # Test case 2: Auto-generated name from RAW file
    model2 = Model(file_path_or_json=raw_path)
    assert model2.name == "Model_1", \
        "Auto-generated name from RAW file incorrect"

    # Test case 3: Name generation with JSON data
    model_json = model2.to_json()
    model3 = Model(file_path_or_json=model_json, name="JSON_Model")
    assert model3.name == "JSON_Model", \
        "Explicit name not preserved for JSON initialization"

    # Test case 4: Auto-generated name with JSON data
    model4 = Model(file_path_or_json=model_json)
    expected_name = f"PSSE-{model4.version}, {len(model4.network.bus)}-bus model"
    assert model4.name == expected_name, \
        "Auto-generated name for JSON initialization incorrect"

    # Verify data equivalence regardless of name
    def compare_models(model_a, model_b, msg):
        """Helper function to verify model data equivalence"""
        raw_dfs = model_a.network.model_dfs()
        compare_dfs = model_b.network.model_dfs()

        assert set(raw_dfs.keys()) == set(compare_dfs.keys()), \
            f"{msg}: Models have different DataFrame sets"

        for df_name, raw_df in raw_dfs.items():
            compare_df = compare_dfs[df_name]
            # Convert to string and sort for reliable comparison
            raw_str = raw_df.astype(str).sort_index().to_string()
            compare_str = compare_df.astype(str).sort_index().to_string()
            assert raw_str == compare_str, \
                f"{msg}: DataFrame {df_name} differs between models"

    # Verify different names don't affect data
    compare_models(model1, model2, "Name assignment affects model data")
    compare_models(model3, model4, "JSON model name assignment affects data")

    # Verify models with same name have equivalent data
    model5 = Model(file_path_or_json=raw_path, name=explicit_name)
    compare_models(model1, model5, "Models with same name differ in data")


if __name__ == "__main__":
    pytest.main([__file__, '-v'])