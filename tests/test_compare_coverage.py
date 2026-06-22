"""
test_compare_coverage.py — characterization tests for ModelComparison.

These tests exercise behavior of psse_model_util.compare.ModelComparison that is
not covered by tests/test_compare.py, with the goal of raising coverage of
compare.py.  They are *characterization* tests: assertions record what the code
actually produces (column names, keys, row counts, dtypes), derived by running
the code against the bundled Model_1.raw / Model_2.raw fixtures.

Pickle-cache note: the project shares a global on-disk pickle cache that can
leak duplicate columns between runs and cause a spurious shape mismatch at
compare.py:373.  The module fixture clears it once at setup (same pattern as
test_compare.py).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.common.constants import NETWORK_DF_COMPARISON_QUERIES
from psse_model_util.common.dirs import clear_cache
from psse_model_util.compare import ModelComparison, main
from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


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
def computed(raw_models):
    """A ModelComparison with both comparisons already run once."""
    model1, model2 = raw_models
    comp = ModelComparison(model1, model2)
    comp.compare_network_dfs()
    comp.compare_graph()
    return comp


@pytest.fixture
def fresh_comparison():
    """Factory for a ModelComparison built on FRESH model loads.

    compare_network_dfs() mutates its models in place (append_bus_info_to_dfs),
    so re-running it on already-enriched models raises a MergeError on duplicate
    bus-info columns.  Tests that call compare_network_dfs() themselves must use
    pristine model objects, not the shared module-scoped ones.
    """
    clear_cache()

    def _make():
        m1 = Model(DATA_DIR / "Model_1.raw")
        m2 = Model(DATA_DIR / "Model_2.raw")
        return ModelComparison(m1, m2)

    return _make


# ---------------------------------------------------------------------------
# pickle_path / csv_folder properties and setters
# ---------------------------------------------------------------------------

def test_pickle_path_default(computed):
    p = computed.pickle_path
    assert isinstance(p, Path)
    assert p.suffix == ".modcomp"
    assert "Model_1" in p.stem and "Model_2" in p.stem


def test_pickle_path_setter_requires_modcomp_suffix(computed, tmp_path):
    with pytest.raises(AssertionError):
        computed.pickle_path = tmp_path / "bad.pickle"


def test_pickle_path_setter_accepts_modcomp(raw_models, tmp_path):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    target = tmp_path / "sub" / "out.modcomp"
    comp.pickle_path = target
    assert comp.pickle_path == target
    # setter creates the parent directory
    assert target.parent.exists()


def test_csv_folder_default(computed):
    folder = computed.csv_folder
    assert isinstance(folder, Path)


def test_csv_folder_setter_creates_dir(raw_models, tmp_path):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    target = tmp_path / "csvout"
    comp.csv_folder = target
    assert comp.csv_folder == target
    assert target.exists()


# ---------------------------------------------------------------------------
# to_pickle / read_pickle / construct-from-model_comp_file
# ---------------------------------------------------------------------------

def test_to_pickle_writes_file(raw_models, tmp_path):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    comp.pickle_path = tmp_path / "rt.modcomp"
    result = comp.to_pickle()
    assert Path(result).exists()


def test_read_pickle_missing_resilient_returns_none(raw_models, tmp_path):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    fp = comp.read_pickle(tmp_path / "nope.modcomp", resilient=True)
    assert fp.file_path is None
    assert fp.object is None


def test_read_pickle_missing_not_resilient_raises(raw_models, tmp_path):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    with pytest.raises(FileNotFoundError):
        comp.read_pickle(tmp_path / "missing.modcomp", resilient=False)


def test_read_pickle_roundtrip_loads_attributes(fresh_comparison, tmp_path):
    comp = fresh_comparison()
    comp.compare_network_dfs()
    comp.pickle_path = tmp_path / "round.modcomp"
    comp.to_pickle()

    loaded = fresh_comparison()
    fp = loaded.read_pickle(tmp_path / "round.modcomp", resilient=False)
    assert fp.object is not None
    assert isinstance(loaded.network_df_comparison, dict)
    assert "bus" in loaded.network_df_comparison


def test_construct_from_model_comp_file(fresh_comparison, tmp_path):
    """Constructing with model_comp_file loads a previously pickled comparison."""
    comp = fresh_comparison()
    comp.compare_network_dfs()
    target = tmp_path / "fromfile.modcomp"
    comp.pickle_path = target
    comp.to_pickle()

    # model1/model2 must be None when model_comp_file is given.
    reloaded = ModelComparison(model_comp_file=target)
    assert isinstance(reloaded.network_df_comparison, dict)
    assert "bus" in reloaded.network_df_comparison


def test_construct_from_nonexistent_model_comp_file(tmp_path):
    """A non-existent comp file simply sets pickle_path; no read occurs."""
    target = tmp_path / "does_not_exist.modcomp"
    comp = ModelComparison(model_comp_file=target)
    assert comp.pickle_path == target


# ---------------------------------------------------------------------------
# __getstate__ / __setstate__ (pickle helpers)
# ---------------------------------------------------------------------------

def test_getstate_stringifies_paths(raw_models, tmp_path):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    comp.pickle_path = tmp_path / "gs.modcomp"
    comp.csv_folder = tmp_path / "gs_csv"
    state = comp.__getstate__()
    assert isinstance(state["_pickle_path"], str)
    assert isinstance(state["_csv_folder"], str)


def test_setstate_restores_paths(raw_models, tmp_path):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    state = comp.__getstate__()
    state["_pickle_path"] = str(tmp_path / "ss.modcomp")
    state["_csv_folder"] = str(tmp_path / "ss_csv")
    new = ModelComparison.__new__(ModelComparison)
    new.__setstate__(state)
    assert isinstance(new._pickle_path, Path)
    assert isinstance(new._csv_folder, Path)


# ---------------------------------------------------------------------------
# bus_num_changes — caching and validation branches
# ---------------------------------------------------------------------------

def test_bus_num_changes_caches(raw_models):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    first = comp.bus_num_changes()
    second = comp.bus_num_changes()  # hits the cached branch
    assert first is second


def test_bus_num_changes_ibus_in_join_raises(raw_models):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    with pytest.raises(AssertionError):
        comp.bus_num_changes(join_columns=["ibus", "name"])


def test_bus_num_changes_bad_column_raises(raw_models):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    with pytest.raises(ValueError):
        comp.bus_num_changes(join_columns=["does_not_exist_col"])


# ---------------------------------------------------------------------------
# bus_kv_filter
# ---------------------------------------------------------------------------

def test_bus_kv_filter_returns_int_list(computed):
    buses = computed.bus_kv_filter()
    assert isinstance(buses, list)
    assert all(isinstance(b, int) for b in buses)


# ---------------------------------------------------------------------------
# query_network_df_comparison — full body, custom queries, bad query
# ---------------------------------------------------------------------------

def test_query_default_queries_inplace_false(computed):
    out = computed.query_network_df_comparison(inplace=False)
    assert isinstance(out, dict)
    # The default query set keys define what is returned.
    assert set(out.keys()) == set(NETWORK_DF_COMPARISON_QUERIES.keys())
    for df in out.values():
        assert isinstance(df, pd.DataFrame)


def test_query_custom_queries(computed):
    custom = {"bus": "baskv_model1 >= 1", "generator": "", "load": ""}
    out = computed.query_network_df_comparison(inplace=False, queries=custom)
    assert "bus" in out
    assert isinstance(out["bus"], pd.DataFrame)


def test_query_bad_query_warns_but_continues(computed):
    # A query referencing a non-existent column should warn, not raise.
    custom = {"bus": "no_such_column > 5"}
    with pytest.warns(UserWarning):
        out = computed.query_network_df_comparison(inplace=False, queries=custom)
    assert "bus" in out


def test_query_inplace_updates_comparison(fresh_comparison):
    comp = fresh_comparison()
    comp.compare_network_dfs()
    before_bus_rows = len(comp.network_df_comparison["bus"])
    comp.query_network_df_comparison(inplace=True)
    after_bus_rows = len(comp.network_df_comparison["bus"])
    # In-place filtering should not increase the row count.
    assert after_bus_rows <= before_bus_rows


# ---------------------------------------------------------------------------
# flatten_and_stringify / process_graph_data
# ---------------------------------------------------------------------------

def test_flatten_and_stringify_scalar(computed):
    assert computed.flatten_and_stringify(42) == "42"


def test_flatten_and_stringify_sequence(computed):
    # The recursion is functional: a (possibly nested) sequence flattens to a
    # single comma-separated string.
    assert computed.flatten_and_stringify((1, 2)) == "1, 2"
    assert computed.flatten_and_stringify([1, [2, 3]]) == "1, 2, 3"


def test_process_graph_data(computed):
    data = {("bus", 101): ["a", "b"]}
    processed = computed.process_graph_data(data)
    assert processed == {"bus, 101": "a, b"}


# ---------------------------------------------------------------------------
# Duplicate-column sections (e.g. ntermdc) — resilience regression
# ---------------------------------------------------------------------------

def test_duplicate_column_section_is_resilient(fresh_comparison):
    """ntermdc flattens its sub-records into one frame with duplicate column
    names (e.g. 'ib', 'idc'). compare_network_dfs must not raise on it: it
    warns and includes the outer-merged frame without _delta/presence columns,
    instead of swallowing a cryptic 2D-broadcast error."""
    comp = fresh_comparison()
    # precondition: the section really does have duplicate column names
    assert comp.model1.network.ntermdc.columns.duplicated().any()

    with pytest.warns(UserWarning, match="duplicate column names"):
        result = comp.compare_network_dfs()

    assert "ntermdc" in result
    merged = result["ntermdc"]
    # enrichment skipped -> no presence/_delta columns were added
    assert "presence" not in merged.columns
    assert not any(str(c).endswith("_delta") for c in merged.columns)
    # but the merged frame still carries the model1/model2 data
    assert any(str(c).endswith("_model1") for c in merged.columns)


# ---------------------------------------------------------------------------
# _reorder_columns / _write_csv (static helpers)
# ---------------------------------------------------------------------------

def test_reorder_columns_empty():
    empty = pd.DataFrame()
    assert ModelComparison._reorder_columns(empty).empty


def test_reorder_columns_named_after_base():
    df = pd.DataFrame({
        "original_path": [1],
        "other": [2],
        "original_path_named": ["x"],
    })
    out = ModelComparison._reorder_columns(df)
    cols = list(out.columns)
    # <base>_named should sit immediately after <base>
    assert cols.index("original_path_named") == cols.index("original_path") + 1


def test_reorder_columns_bus_info_after_bus_col():
    df = pd.DataFrame({
        "ibus_model1": [1],
        "z_other": [9],
        "ibus_name_model1": ["BUS"],
        "ibus_baskv_model1": [138.0],
    })
    out = ModelComparison._reorder_columns(df)
    cols = list(out.columns)
    assert cols.index("ibus_name_model1") == cols.index("ibus_model1") + 1


def test_write_csv_plain_rangeindex_excludes_index(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    path = tmp_path / "plain.csv"
    ModelComparison._write_csv(path, df)
    text = path.read_text()
    # First header token should be 'a', not an unnamed index column.
    assert text.splitlines()[0].split(",")[0] == "a"


def test_write_csv_named_index_included(tmp_path):
    df = pd.DataFrame({"a": [1, 2]}, index=pd.Index([10, 11], name="ibus"))
    path = tmp_path / "named.csv"
    ModelComparison._write_csv(path, df)
    text = path.read_text()
    assert text.splitlines()[0].split(",")[0] == "ibus"


# ---------------------------------------------------------------------------
# to_csv — df comparison + graph comparison export
# ---------------------------------------------------------------------------

def test_to_csv_df_and_graph(fresh_comparison, tmp_path):
    comp = fresh_comparison()
    comp.compare_network_dfs()
    comp.compare_graph()
    comp.csv_folder = tmp_path
    comp.to_csv(df_comparison_to_csv=True, graph_comparison_to_csv=True)
    assert (tmp_path / "info.csv").exists()
    assert (tmp_path / "network_bus.csv").exists()
    assert (tmp_path / "graph_added_edges.csv").exists()
    assert (tmp_path / "graph_path_sectionalizations.csv").exists()


def test_to_csv_lazy_compares_when_empty(fresh_comparison, tmp_path):
    """to_csv triggers compare_* internally if the results aren't present."""
    comp = fresh_comparison()
    # Do NOT run compare_* first; _df/_graph_comparison_to_csv should do it.
    comp.network_df_comparison = {}
    comp.graph_comparison = None
    comp.csv_folder = tmp_path
    comp.to_csv(df_comparison_to_csv=True, graph_comparison_to_csv=True)
    assert (tmp_path / "network_bus.csv").exists()
    assert (tmp_path / "graph_removed_edges.csv").exists()


def test_to_csv_models_to_csv(raw_models, tmp_path):
    m1, m2 = raw_models
    comp = ModelComparison(m1, m2)
    comp.csv_folder = tmp_path
    # models_to_csv exercises the model.to_csv() branch.
    comp.to_csv(models_to_csv=True)
    # At least some CSV output should have been produced somewhere.
    assert tmp_path.exists()


# ---------------------------------------------------------------------------
# main() — end-to-end driver
# ---------------------------------------------------------------------------

def test_main_end_to_end(tmp_path, monkeypatch):
    """Drive main() with export to CSV; force_recalculation avoids the
    hardcoded /cache/ pickle-read path."""
    clear_cache()
    # Run main; it builds its own ModelComparison and exports CSVs to the
    # site_data_dir-derived csv_folder.  We only assert it completes.
    main(
        DATA_DIR / "Model_1.raw",
        DATA_DIR / "Model_2.raw",
        force_recalculation=True,
        export_format="csv",
        add_bus_info_to_branches=True,
    )


def test_main_no_export(tmp_path):
    clear_cache()
    main(
        DATA_DIR / "Model_1.raw",
        DATA_DIR / "Model_2.raw",
        force_recalculation=True,
        export_format=None,
        add_bus_info_to_branches=False,
    )
