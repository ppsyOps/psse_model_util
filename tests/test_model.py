"""
test_model.py — Model and Network method tests.

Ported from tests/legacy_tests/test_model.py; updated for the current API
and project layout after refactoring.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from psse_model_util.dataformat.section_schema import SectionSchema
from psse_model_util.model import AbstractSection, Model, ModelDecoder, ModelEncoder, Network
from psse_model_util.raw_to_rawx import raw_file_to_rawx_dict

DATA_DIR = Path(__file__).resolve().parent / "data"
TEST_RAWX_FILE = DATA_DIR / "sample_v35.rawx"
MODEL1_RAW = DATA_DIR / "Model_1.raw"

# Area numbers matching tests/data/sample_v35.rawx
NATIVE_AREAS = {1: "CENTRAL", 2: "EAST", 3: "CENTRAL_DC"}
NEIGHBOR_AREAS = {4: "EAST_COGEN1", 5: "WEST"}
INCLUDE_AREAS = NEIGHBOR_AREAS | NATIVE_AREAS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_model():
    return Model(file_path_or_json=TEST_RAWX_FILE, force_recalculate=True)


@pytest.fixture
def model1_network():
    model = Model(DATA_DIR / "Model_1.raw", force_recalculate=True)
    return model.network


@pytest.fixture
def empty_network():
    network = Network.__new__(Network)
    network.bus = pd.DataFrame(columns=["ibus", "baskv"])
    network._section_schemas = {
        "bus": SectionSchema(bus_cols=["ibus"], id_cols=["ibus"], data_type={}),
    }
    network._graph = None
    return network


@pytest.fixture
def filtered_model(sample_model):
    return sample_model.filter_by_area(areas=INCLUDE_AREAS, inplace=False)


# ---------------------------------------------------------------------------
# filter_section
# ---------------------------------------------------------------------------

class TestFilterSection:

    def test_basic(self, model1_network):
        result = model1_network.filter_section("bus", "baskv >= 345")
        assert len(result.bus) < len(model1_network.bus)
        assert all(result.bus["baskv"] >= 345)

    def test_inplace(self, model1_network):
        original_len = len(model1_network.bus)
        model1_network.filter_section("bus", "baskv >= 345", inplace=True)
        assert len(model1_network.bus) < original_len
        assert all(model1_network.bus["baskv"] >= 345)

    def test_invalid_where_clause(self, model1_network):
        with pytest.raises(ValueError):
            model1_network.filter_section("bus", "invalid_column > 100")

    def test_nonexistent_section(self, model1_network):
        with pytest.raises(ValueError):
            model1_network.filter_section("nonexistent", "col > 0")

    def test_empty_result(self, model1_network):
        result = model1_network.filter_section("bus", "baskv > 1_000_000")
        assert len(result.bus) == 0

    def test_graph_effect_clear(self, model1_network):
        result = model1_network.filter_section("bus", "baskv >= 345", graph_effect="clear")
        assert len(result._graph.nodes) == 0

    def test_graph_effect_regenerate(self, model1_network):
        result = model1_network.filter_section("bus", "baskv >= 345", graph_effect="regenerate")
        assert len(result._graph.nodes) > 0

    def test_graph_effect_leave(self, model1_network):
        model1_network.graph(regenerate=True)
        original_nodes = len(model1_network._graph.nodes)
        result = model1_network.filter_section("bus", "baskv >= 345", graph_effect="leave")
        assert len(result._graph.nodes) == original_nodes


# ---------------------------------------------------------------------------
# filter_by_kv
# ---------------------------------------------------------------------------

class TestFilterByKv:

    def test_basic(self, model1_network):
        result = model1_network.filter_by_kv(230, 500)
        assert all(result.bus["baskv"] >= 230)
        assert all(result.bus["baskv"] < 500)

    def test_invalid_negative_low(self, model1_network):
        with pytest.raises(ValueError):
            model1_network.filter_by_kv(-100, 500)

    def test_invalid_inverted_range(self, model1_network):
        with pytest.raises(ValueError):
            model1_network.filter_by_kv(500, 100)

    def test_edge_values(self, model1_network):
        exact_kv = 230.0
        result = model1_network.filter_by_kv(exact_kv, exact_kv + 0.1)
        assert all(result.bus["baskv"] >= exact_kv)
        assert all(result.bus["baskv"] < exact_kv + 0.1)

    def test_empty_network(self, empty_network):
        result = empty_network.filter_by_kv(100, 200)
        assert len(result.bus) == 0

    def test_metadata_preservation(self, model1_network):
        original = model1_network._section_schemas
        result = model1_network.filter_by_kv(230, 500)
        assert result._section_schemas == original

    def test_inplace(self, model1_network):
        original_bus_count = len(model1_network.bus)
        model1_network.filter_by_kv(230, 500, inplace=True)
        assert len(model1_network.bus) < original_bus_count
        assert all(model1_network.bus["baskv"] >= 230)
        assert all(model1_network.bus["baskv"] < 500)


# ---------------------------------------------------------------------------
# Model-level tests
# ---------------------------------------------------------------------------

def test_model_initialization(sample_model):
    assert isinstance(sample_model, Model)
    assert sample_model.raw_file_path == TEST_RAWX_FILE
    assert sample_model.version is not None


def test_filter_by_area(sample_model):
    assert hasattr(sample_model.network, "filter_by_area")
    filtered = sample_model.filter_by_area(areas=NATIVE_AREAS, inplace=False)
    assert isinstance(filtered, Model)
    assert filtered is not sample_model
    assert len(filtered.network.bus) < len(sample_model.network.bus)


@pytest.mark.parametrize("areas", [NATIVE_AREAS, INCLUDE_AREAS, list(NATIVE_AREAS.keys())])
def test_filter_by_area_different_inputs(sample_model, areas):
    filtered = sample_model.filter_by_area(areas=areas, inplace=False)
    assert isinstance(filtered, Model)
    assert len(filtered.network.bus) < len(sample_model.network.bus)


def test_network_attribute(sample_model):
    assert hasattr(sample_model, "network")
    assert isinstance(sample_model.network, Network)


def test_network_graph(filtered_model):
    graph = filtered_model.network.graph(regenerate=True)
    assert isinstance(graph, nx.Graph)
    assert graph.number_of_nodes() > 0
    assert graph.number_of_edges() > 0


def test_append_bus_info_to_dfs(filtered_model):
    net = filtered_model.network
    net.append_bus_info_to_dfs()
    for df_name, df in net.model_dfs().items():
        if df_name != "bus":
            # Only assert on sections where the registry records bus_cols AND
            # append_bus_info_to_dfs() actually processed the section (which it
            # does when _metadata['bus_cols'] is non-empty — the src predicate
            # during this coexistence period).
            reg_bus_cols = net.bus_cols(df_name)
            meta = getattr(df, "_metadata", {})
            meta_bus_cols = meta.get("bus_cols", []) if isinstance(meta, dict) else []
            for bus_col in reg_bus_cols:
                if bus_col in meta_bus_cols:
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


def test_to_csv(filtered_model, tmp_path):
    filtered_model.csv_folder = tmp_path
    filtered_model.to_csv()
    assert (tmp_path / "general.csv").exists()
    assert (tmp_path / "network_bus.csv").exists()


def test_model_dfs(filtered_model):
    actual_dfs = filtered_model.network.model_dfs()
    assert isinstance(actual_dfs, dict)
    assert all(isinstance(df, pd.DataFrame) for df in actual_dfs.values())

    # Core sections that must always be present
    required = {"bus", "load", "generator", "acline", "transformer", "area", "zone", "owner"}
    missing = required - set(actual_dfs.keys())
    assert not missing, f"Missing required DataFrames: {missing}"

    assert "ibus" in actual_dfs["bus"].index.names
    assert "ibus" in actual_dfs["generator"].index.names
    assert "ibus" in actual_dfs["acline"].index.names


def test_force_recalculate():
    model1 = Model(file_path_or_json=TEST_RAWX_FILE)
    model1.to_pickle()

    model2 = Model(file_path_or_json=TEST_RAWX_FILE)
    model3 = Model(file_path_or_json=TEST_RAWX_FILE, force_recalculate=True)

    assert model1.pickle_path == model2.pickle_path == model3.pickle_path
    assert model1.raw_file_path == model2.raw_file_path == model3.raw_file_path
    assert model2.network is not None
    assert model3.network is not None
    assert id(model2.network) != id(model3.network)


def test_model_name_assignment():
    explicit_name = "Test_Model_Name"
    model1 = Model(file_path_or_json=MODEL1_RAW, name=explicit_name)
    assert model1.name == explicit_name

    model2 = Model(file_path_or_json=MODEL1_RAW)
    assert model2.name == "Model_1"

    model_json = model2.to_json()
    model3 = Model(file_path_or_json=model_json, name="JSON_Model")
    assert model3.name == "JSON_Model"

    model4 = Model(file_path_or_json=model_json)
    expected_name = f"PSSE-{model4.version}, {len(model4.network.bus)}-bus model"
    assert model4.name == expected_name

    def _dfs_equal(a: Model, b: Model, msg: str):
        dfs_a = a.network.model_dfs()
        dfs_b = b.network.model_dfs()
        assert set(dfs_a.keys()) == set(dfs_b.keys()), f"{msg}: different DataFrame sets"
        for name, df_a in dfs_a.items():
            df_b = dfs_b[name]
            assert df_a.astype(str).sort_index().to_string() == df_b.astype(str).sort_index().to_string(), \
                f"{msg}: DataFrame '{name}' differs"

    _dfs_equal(model1, model2, "name assignment affects model data")
    _dfs_equal(model3, model4, "JSON model name assignment affects data")

    model5 = Model(file_path_or_json=MODEL1_RAW, name=explicit_name)
    _dfs_equal(model1, model5, "models with same name differ in data")


# ---------------------------------------------------------------------------
# ModelEncoder
# ---------------------------------------------------------------------------

class TestModelEncoder:
    """Verify every branch of ModelEncoder.default()."""

    def test_numpy_integer(self):
        result = json.loads(json.dumps(np.int64(42), cls=ModelEncoder))
        assert result == 42
        assert isinstance(result, int)

    def test_numpy_float(self):
        result = json.loads(json.dumps(np.float64(3.14), cls=ModelEncoder))
        assert result == pytest.approx(3.14)
        assert isinstance(result, float)

    def test_numpy_float_default_direct(self):
        """Call default() directly so the np.floating branch executes regardless
        of whether json.dumps treats np.float64 as a native type in Python 3.14."""
        encoder = ModelEncoder()
        result = encoder.default(np.float64(3.14))
        assert result == pytest.approx(3.14)
        assert isinstance(result, float)

    def test_numpy_array(self):
        result = json.loads(json.dumps(np.array([1, 2, 3]), cls=ModelEncoder))
        assert result == [1, 2, 3]

    def test_dataframe(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        result = json.loads(json.dumps(df, cls=ModelEncoder))
        assert isinstance(result, dict)
        assert set(result.keys()) >= {"columns", "data"}
        assert result["columns"] == ["a", "b"]

    def test_nan(self):
        # json.dumps never calls default() for a native Python float (even NaN),
        # so we invoke default() directly to test the pd.isna branch.
        encoder = ModelEncoder()
        assert encoder.default(float("nan")) is None

    def test_numpy_nan(self):
        # np.nan is float('nan') — same direct invocation as above.
        encoder = ModelEncoder()
        assert encoder.default(np.nan) is None

    def test_pandas_nat(self):
        # pd.NaT is not a native JSON type, so default() IS called via json.dumps.
        import pandas as pd
        result = json.loads(json.dumps({"v": pd.NaT}, cls=ModelEncoder))
        assert result["v"] is None

    def test_unknown_type_falls_back_to_str(self):
        class _Unserializable:
            def __str__(self):
                return "fallback_repr"

        result = json.loads(json.dumps(_Unserializable(), cls=ModelEncoder))
        assert result == "fallback_repr"


# ---------------------------------------------------------------------------
# ModelDecoder
# ---------------------------------------------------------------------------

class TestModelDecoder:
    """Verify ModelDecoder.object_hook() reconstructs DataFrames."""

    def test_reconstructs_dataframe_from_split_format(self):
        df = pd.DataFrame({"x": [10, 20], "y": [30, 40]})
        # Encode via split-format dict (what ModelEncoder produces for DataFrames)
        payload = df.to_dict(orient="split")
        json_str = json.dumps(payload)
        result = json.loads(json_str, cls=ModelDecoder)
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["x", "y"]
        assert result["x"].tolist() == [10, 20]

    def test_plain_dict_passes_through_unchanged(self):
        data = {"alpha": 1, "beta": "two"}
        result = json.loads(json.dumps(data), cls=ModelDecoder)
        assert result == data

    def test_round_trip_model_with_dataframe_value(self):
        """Encoding a DataFrame inside a dict and decoding restores a DataFrame."""
        df = pd.DataFrame({"ibus": [101, 102], "baskv": [230.0, 345.0]})
        encoded = json.dumps({"bus": df}, cls=ModelEncoder)
        decoded = json.loads(encoded, cls=ModelDecoder)
        assert isinstance(decoded["bus"], pd.DataFrame)
        assert decoded["bus"]["ibus"].tolist() == [101, 102]


# ---------------------------------------------------------------------------
# Model.to_json with file_path
# ---------------------------------------------------------------------------

def test_to_json_writes_file(sample_model, tmp_path):
    """to_json(file_path=...) must write valid JSON and return the same string."""
    json_path = tmp_path / "model_out.json"
    json_str = sample_model.to_json(file_path=json_path)

    assert json_path.exists()
    assert isinstance(json_str, str)

    # File content must match the returned string
    assert json_path.read_text(encoding="utf-8") == json_str

    # Parsed content must contain the top-level network key
    loaded = json.loads(json_str)
    assert "network" in loaded


def test_to_json_file_parent_created_automatically(sample_model, tmp_path):
    """to_json must create intermediate directories if they don't exist."""
    json_path = tmp_path / "subdir" / "nested" / "model.json"
    sample_model.to_json(file_path=json_path)
    assert json_path.exists()


# ---------------------------------------------------------------------------
# Model._read_json() — dict and JSON-string input paths
# ---------------------------------------------------------------------------

def test_model_from_rawx_dict():
    """Model(file_path_or_json=dict) exercises the dict branch of _read_json."""
    rawx_dict = raw_file_to_rawx_dict(MODEL1_RAW)
    model = Model(file_path_or_json=rawx_dict)

    assert isinstance(model, Model)
    assert not model.network.bus.empty
    # dict input sets raw_file_path to None
    assert model.raw_file_path is None


def test_model_from_rawx_dict_bus_count_matches():
    """Bus count from dict-loaded model must equal the file-loaded model."""
    file_model = Model(file_path_or_json=MODEL1_RAW, force_recalculate=True)
    rawx_dict = raw_file_to_rawx_dict(MODEL1_RAW)
    dict_model = Model(file_path_or_json=rawx_dict)

    assert len(dict_model.network.bus) == len(file_model.network.bus)


def test_model_from_json_string():
    """Model(file_path_or_json=json_str) exercises the JSON-string branch of _read_json.

    NOTE: model.to_json() has a known defect — _create_dataframe() calls
    data.pop('fields') / data.pop('data') which mutates json_data in-place
    during __init__, so a subsequent to_json() call sees empty section dicts.
    We avoid this by serialising the fresh rawx_dict directly (before any
    Model is constructed from it) rather than round-tripping through a Model.
    """
    rawx_dict = raw_file_to_rawx_dict(MODEL1_RAW)
    json_str = json.dumps(rawx_dict)           # fresh, un-mutated dict
    model = Model(file_path_or_json=json_str, name="from_json_str")

    assert isinstance(model, Model)
    assert model.name == "from_json_str"
    assert not model.network.bus.empty


# ---------------------------------------------------------------------------
# Network._create_dataframe — missing 'fields' error path
# ---------------------------------------------------------------------------

def test_create_dataframe_missing_fields_raises(model1_network):
    """_create_dataframe must raise ValueError when the 'fields' key is absent."""
    model1_network.subsection = 'bus'
    with pytest.raises(ValueError, match='"fields"'):
        model1_network._create_dataframe({'data': [[101, 'BUS_A']]})


# ---------------------------------------------------------------------------
# Network.section_with_bus — error paths and filter_condition branch
# ---------------------------------------------------------------------------

def test_section_with_bus_no_bus_cols_raises(model1_network):
    """section_with_bus raises ValueError for a section with no bus_cols metadata."""
    # caseid has no bus_cols in the rawx_json_template
    with pytest.raises(ValueError, match="No bus columns"):
        model1_network.section_with_bus('caseid')


def test_section_with_bus_with_filter_condition(model1_network):
    """filter_condition argument filters rows before bus info is joined."""
    first_ibus = model1_network.acline.index.get_level_values('ibus')[0]
    result = model1_network.section_with_bus(
        'acline', filter_condition=f'ibus == {first_ibus}'
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) >= 1
    assert any('ibus_' in col for col in result.columns)


# ---------------------------------------------------------------------------
# Network.filter_by_area — edge cases
# ---------------------------------------------------------------------------

def test_filter_by_area_invalid_graph_effect_raises(model1_network):
    """filter_by_area must raise ValueError for an unrecognised graph_effect value."""
    with pytest.raises(ValueError, match="Invalid value for graph_effect"):
        model1_network.filter_by_area({1: 'AREA'}, graph_effect='bad_value')


def test_filter_by_area_graph_effect_regenerate(model1_network):
    """filter_by_area with graph_effect='regenerate' rebuilds the graph immediately."""
    result = model1_network.filter_by_area({1: 'AREA'}, graph_effect='regenerate')
    # Graph should be populated (regenerated) rather than empty
    assert isinstance(result._graph, nx.Graph)


def test_filter_by_area_graph_effect_leave(model1_network):
    """filter_by_area with graph_effect='leave' preserves the original graph state."""
    model1_network.graph(regenerate=True)
    original_node_count = len(model1_network._graph.nodes)
    result = model1_network.filter_by_area({1: 'AREA'}, graph_effect='leave')
    # Graph is left unchanged — it still reflects the pre-filter topology
    assert isinstance(result._graph, nx.Graph)
    assert len(result._graph.nodes) == original_node_count


def test_filter_by_area_no_matching_bus_cols_warns(model1_network):
    """filter_by_area warns (and keeps all rows) when bus_cols declared in metadata
    but none of those columns appear in the DataFrame's index or columns."""
    import copy as copy_mod
    phantom_df = pd.DataFrame({'col_a': [1, 2]})
    phantom_df._metadata = {'bus_cols': ['phantom_col']}
    net = copy_mod.deepcopy(model1_network)
    net.phantom = phantom_df
    with pytest.warns(UserWarning, match="no bus columns found"):
        net.filter_by_area({1: 'AREA'}, graph_effect='clear')


# ---------------------------------------------------------------------------
# Network.copy(deep=False) — shallow-copy path
# ---------------------------------------------------------------------------

def test_network_copy_shallow(model1_network):
    """copy(deep=False) produces a distinct Network whose DataFrames are new
    objects and whose section schemas are shared references (not deepcopied)."""
    shallow = model1_network.copy(deep=False)
    assert shallow is not model1_network
    assert shallow.bus is not model1_network.bus
    # Immutable schema objects are shared in shallow mode
    assert shallow.section_schema("bus") is model1_network.section_schema("bus")


# ---------------------------------------------------------------------------
# Model.__init__ — version fallback from caseid['rev']
# ---------------------------------------------------------------------------

def test_model_version_fallback_from_caseid():
    """When the rawx dict has no 'general' section, __init__ falls back to
    reading the version from network.caseid['rev']."""
    rawx_dict = raw_file_to_rawx_dict(MODEL1_RAW)
    rawx_dict.pop('general', None)          # force the AttributeError path
    model = Model(file_path_or_json=rawx_dict, name='version_fallback_test')
    assert model.version is not None
    assert isinstance(model.version, float)


# ---------------------------------------------------------------------------
# Model.read_pickle — error paths
# ---------------------------------------------------------------------------

def test_read_pickle_missing_file_resilient(tmp_path):
    """read_pickle(resilient=True) returns FpPickleType(None, None) for a missing file."""
    model = Model(file_path_or_json=MODEL1_RAW, force_recalculate=True)
    model.pickle_path = tmp_path / "nonexistent.model"
    result = model.read_pickle(resilient=True)
    assert result.file_path is None
    assert result.object is None


def test_read_pickle_missing_file_not_resilient(tmp_path):
    """read_pickle(resilient=False) raises FileNotFoundError for a missing file."""
    model = Model(file_path_or_json=MODEL1_RAW, force_recalculate=True)
    model.pickle_path = tmp_path / "nonexistent.model"
    with pytest.raises(FileNotFoundError):
        model.read_pickle(resilient=False)


def test_read_pickle_corrupt_file_resilient(tmp_path):
    """read_pickle(resilient=True) warns and returns (None, None) for a corrupt pickle."""
    corrupt_path = tmp_path / "corrupt.model"
    corrupt_path.write_bytes(b"this is not a valid pickle")
    model = Model(file_path_or_json=MODEL1_RAW, force_recalculate=True)
    model.pickle_path = corrupt_path
    with pytest.warns(UserWarning, match="Could not load"):
        result = model.read_pickle(resilient=True)
    assert result.file_path is None
    assert result.object is None


def test_read_pickle_corrupt_file_not_resilient(tmp_path):
    """read_pickle(resilient=False) re-raises the exception for a corrupt pickle."""
    corrupt_path = tmp_path / "corrupt.model"
    corrupt_path.write_bytes(b"this is not a valid pickle")
    model = Model(file_path_or_json=MODEL1_RAW, force_recalculate=True)
    model.pickle_path = corrupt_path
    with pytest.raises(Exception):
        model.read_pickle(resilient=False)


# ---------------------------------------------------------------------------
# Network.filter_section — non-DataFrame and invalid graph_effect paths
# ---------------------------------------------------------------------------

def test_filter_section_non_dataframe_raises(model1_network):
    """filter_section raises AttributeError when the named attribute is not a DataFrame."""
    with pytest.raises(AttributeError, match="is not a DataFrame"):
        model1_network.filter_section('_graph', 'ibus > 0')


def test_filter_section_invalid_graph_effect_raises(model1_network):
    """filter_section propagates ValueError from _handle_graph_effect for bad values."""
    with pytest.raises(ValueError):
        model1_network.filter_section('bus', 'baskv >= 345', graph_effect='invalid_effect')


# ---------------------------------------------------------------------------
# Model.copy(deep=False) — shallow copy exercises the scalar-attribute else branch
# ---------------------------------------------------------------------------

def test_model_copy_shallow(sample_model):
    """Model.copy(deep=False) returns a distinct Model with the same scalar attributes."""
    shallow = sample_model.copy(deep=False)
    assert shallow is not sample_model
    assert shallow.name == sample_model.name
    assert shallow.version == sample_model.version
    assert isinstance(shallow.network, Network)


# ---------------------------------------------------------------------------
# Model.__init__ — unrecognized rawx section is set as an attribute
# ---------------------------------------------------------------------------

def test_model_with_unknown_section():
    """An unrecognized top-level key in the rawx dict is set as a Model attribute."""
    rawx_dict = raw_file_to_rawx_dict(MODEL1_RAW)
    rawx_dict['unknown_custom_section'] = {'custom_key': 'custom_value'}
    model = Model(file_path_or_json=rawx_dict, name='unknown_section_test')
    assert hasattr(model, 'unknown_custom_section')


# ---------------------------------------------------------------------------
# Model._prepare_json_data — scalar (non-dict) top-level value passes through
# ---------------------------------------------------------------------------

def test_prepare_json_data_scalar_value(sample_model):
    """_prepare_json_data passes non-dict top-level values through unchanged."""
    data = {
        'network': {'bus': {'fields': ['ibus'], 'data': [[101]]}},
        'scalar_int': 35,
        'scalar_str': 'metadata',
    }
    result = sample_model._prepare_json_data(data)
    assert result['scalar_int'] == 35
    assert result['scalar_str'] == 'metadata'


# ---------------------------------------------------------------------------
# Model.csv_folder — string _csv_folder is converted to Path
# ---------------------------------------------------------------------------

def test_csv_folder_converts_string_to_path(sample_model, tmp_path):
    """csv_folder getter coerces a string _csv_folder value to a Path object."""
    # Bypass the setter and inject a raw string directly
    sample_model._csv_folder = str(tmp_path / "export_dir")
    result = sample_model.csv_folder
    from pathlib import Path as _Path
    assert isinstance(result, _Path)


# ---------------------------------------------------------------------------
# AbstractSection._create_dataframe — list data_type and single-row data
# ---------------------------------------------------------------------------

def test_abstract_section_list_data_type():
    """_create_dataframe converts list data_type to a field→type dict (line 222)."""
    section_data = {
        'dummy': {
            'fields': ['ibus', 'name', 'baskv'],
            'data': [[101, 'BUS_A', 230.0], [102, 'BUS_B', 115.0]],
            'data_type': [int, str, float],   # list form → should be converted
        }
    }
    obj = AbstractSection(section_data)
    assert hasattr(obj, 'dummy')
    assert len(obj.dummy) == 2


def test_abstract_section_single_row_data():
    """_create_dataframe handles a flat (non-nested) single-row list (line 237)."""
    section_data = {
        'caseid': {
            'fields': ['ic', 'sbase', 'rev'],
            'data': [0, 100.0, 35],           # flat list → single-row path
        }
    }
    obj = AbstractSection(section_data)
    assert hasattr(obj, 'caseid')
    assert len(obj.caseid) == 1


# ---------------------------------------------------------------------------
# AbstractSection.copy(deep=False) — covers the shallow metadata/scalar paths
# ---------------------------------------------------------------------------

def test_abstract_section_copy_shallow():
    """AbstractSection.copy(deep=False) deep-copies DataFrames and shallow-copies
    scalar attributes."""
    section_data = {
        'test_sec': {
            'fields': ['col_a', 'col_b'],
            'data': [[1, 'x'], [2, 'y']],
        }
    }
    obj = AbstractSection(section_data)
    obj.marker = "shared"  # an immutable non-DataFrame attribute
    shallow = obj.copy(deep=False)
    assert shallow is not obj
    assert shallow.test_sec is not obj.test_sec          # df always deep-copied
    assert shallow.marker is obj.marker                  # copy.copy() of an immutable returns the same object


# ---------------------------------------------------------------------------
# Network.load_node_positions
# ---------------------------------------------------------------------------

def test_load_node_positions_no_cache(model1_network):
    """load_node_positions returns an empty dict when no cache file exists."""
    result = model1_network.load_node_positions()
    assert isinstance(result, dict)


def test_load_node_positions_with_cache(model1_network, tmp_path, monkeypatch):
    """load_node_positions reads positions from cache when file exists."""
    cache_dir = tmp_path / '.cache' / 'psse_model_util'
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / 'node_positions.json'
    positions = {'("bus", 101)': [0.5, 1.2]}
    cache_file.write_text(json.dumps(positions))

    # Redirect Path.home() so the method finds our fake cache
    monkeypatch.setattr('psse_model_util.model.Path.home', staticmethod(lambda: tmp_path))

    result = model1_network.load_node_positions()
    assert result == positions


# ---------------------------------------------------------------------------
# Network._section_schemas registry and accessors
# ---------------------------------------------------------------------------

class TestSectionSchemaRegistry:
    def test_known_section_returns_populated_schema(self, model1_network):
        s = model1_network.section_schema("acline")
        assert s.bus_cols == ("ibus", "jbus")
        assert s.id_cols == ("ibus", "jbus", "ckt")
        assert "rpu" in s.data_type

    def test_unknown_section_returns_empty_schema(self, model1_network):
        s = model1_network.section_schema("does_not_exist")
        assert s == SectionSchema()
        assert s.bus_cols == ()

    def test_bus_cols_and_id_cols_conveniences(self, model1_network):
        assert model1_network.bus_cols("bus") == ("ibus",)
        assert model1_network.id_cols("load") == ("ibus", "loadid")
        assert model1_network.bus_cols("area") == ()  # section exists, no bus_cols

    def test_section_schemas_survive_pickle(self, model1_network):
        import pickle
        rt = pickle.loads(pickle.dumps(model1_network))
        assert rt.bus_cols("acline") == ("ibus", "jbus")
        assert rt.id_cols("load") == ("ibus", "loadid")
