import pytest
from pathlib import Path
import pandas as pd
import networkx as nx

from psse_model_util.model import Model, Network


# Setup the path to the test RAWX file
TEST_DATA_DIR = Path(__file__).parent.parent / 'tests' / 'data'
TEST_RAWX_FILE = TEST_DATA_DIR / 'sample_v35.rawx'

# Dictionary of native PJM areas with their area numbers as keys and names as values
NATIVE_AREAS = {1: 'CENTRAL', 2: 'EAST', 3: 'CENTRAL_DC'}

# Dictionary of neighboring areas to PJM with their area numbers as keys and names as values
NEIGHBOR_AREAS = {4: 'EAST_COGEN1', 5: 'WEST'}

# Combined dictionary of native and neighboring areas, used for filtering models
INCLUDE_AREAS = NEIGHBOR_AREAS.copy() | NATIVE_AREAS.copy()


@pytest.fixture
def model():
    return Model(file_path_or_json=TEST_RAWX_FILE, force_recalculate=True)


@pytest.fixture
def filtered_model(model):
    return model.filter_by_area(areas=INCLUDE_AREAS, inplace=False)


def test_model_initialization(model):
    assert isinstance(model, Model)
    assert model.raw_file_path == TEST_RAWX_FILE
    assert model.version is not None


def test_filter_by_area(model):
    assert hasattr(model.network, 'filter_by_area'), "Network object should have 'filter_by_area' method"
    filtered = model.filter_by_area(areas=NATIVE_AREAS, inplace=False)
    assert isinstance(filtered, Model)
    assert filtered is not model  # Ensure a new object is returned when inplace=False
    assert len(filtered.network.bus) < len(model.network.bus)


@pytest.mark.parametrize("areas", [NATIVE_AREAS, INCLUDE_AREAS, list(NATIVE_AREAS.keys())])
def test_filter_by_area_different_inputs(model, areas):
    filtered = model.filter_by_area(areas=areas, inplace=False)
    assert isinstance(filtered, Model)
    assert len(filtered.network.bus) < len(model.network.bus)


def test_network_attribute(model):
    assert hasattr(model, 'network'), "Model should have a 'network' attribute"
    assert isinstance(model.network, Network), "The 'network' attribute should be an instance of Network"


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


def test_read_pickle(filtered_model, tmp_path):
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
    filtered_model.csv_folder = lambda: tmp_path
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


def test_force_recalculate(tmp_path):
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


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
