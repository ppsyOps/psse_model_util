"""
test_compare_edges_coverage.py — edge/error-branch characterization tests for
ModelComparison.

These complement tests/test_compare.py and tests/test_compare_coverage.py by
driving the defensive/edge branches of psse_model_util.compare that the happy
path never reaches: dtype-mismatch deltas, sections present in only one model,
the merge-exception guard, bypass path naming, corrupt/inconsistent pickle
loads, CSV-export skip/empty/not-found/PermissionError branches, the graph CSV
flatten fallback, the bus-column query mask, and main()'s cached-read path.

They are *characterization* tests: every expected value was derived by running
the code against the bundled Model_1.raw / Model_2.raw fixtures, not guessed.

Pickle-cache note: the project shares a global on-disk pickle cache that can
leak duplicate columns between runs. The module fixtures clear it (same pattern
as test_compare.py / test_compare_coverage.py).

In-place mutation note: compare_network_dfs() mutates its models in place via
append_bus_info_to_dfs(), so any test that calls it (or that mutates a model's
network DataFrames before calling it) builds FRESH Model objects rather than
sharing an enriched instance.
"""
from __future__ import annotations

import pickle
import warnings
from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.common.dirs import clear_cache
from psse_model_util.compare import ModelComparison
from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_models():
    """Factory for a fresh (model1, model2) pair on pristine loads.

    Cache is cleared so no enriched/duplicate-column state leaks in from a
    prior run. Each call returns brand-new Model objects, safe to mutate.
    """
    clear_cache()

    def _make():
        m1 = Model(DATA_DIR / "Model_1.raw")
        m2 = Model(DATA_DIR / "Model_2.raw")
        return m1, m2

    return _make


@pytest.fixture
def fresh_comparison(fresh_models):
    """Factory for a ModelComparison on fresh model loads."""

    def _make():
        m1, m2 = fresh_models()
        return ModelComparison(m1, m2)

    return _make


# ---------------------------------------------------------------------------
# compare_network_dfs — _compare_values dtype-mismatch branch (307)
# ---------------------------------------------------------------------------

def test_compare_values_dtype_mismatch(fresh_comparison):
    """When a column's dtype differs between the two models, the delta is a
    boolean (series1 != series2) rather than a numeric difference."""
    comp = fresh_comparison()
    # Force baskv to object dtype in model2 only; model1 keeps its numeric dtype.
    comp.model2.network.bus["baskv"] = comp.model2.network.bus["baskv"].astype(object)

    result = comp.compare_network_dfs()
    bus = result["bus"]
    assert "baskv_delta" in bus.columns
    # dtype-mismatch path returns an element-wise inequality -> boolean Series
    assert bus["baskv_delta"].dtype == bool


# ---------------------------------------------------------------------------
# compare_network_dfs — sections present in only one model (335, 338)
# ---------------------------------------------------------------------------

def test_added_and_removed_equip_types(fresh_comparison):
    """A DataFrame attribute that exists on only one model's network surfaces
    as a 'removed_equip_types' / 'added_equip_types' entry."""
    comp = fresh_comparison()
    # Sections that exist in exactly one model.
    comp.model1.network.zzz_only_in_model1 = pd.DataFrame({"a": [1]})
    comp.model2.network.zzz_only_in_model2 = pd.DataFrame({"b": [2]})

    result = comp.compare_network_dfs()

    assert "removed_equip_types" in result
    assert "added_equip_types" in result
    assert "zzz_only_in_model1" in result["removed_equip_types"]["equip_type"].tolist()
    assert "zzz_only_in_model2" in result["added_equip_types"]["equip_type"].tolist()


# ---------------------------------------------------------------------------
# compare_network_dfs — merge-exception guard (362-366)
# ---------------------------------------------------------------------------

def test_merge_exception_skips_section(fresh_comparison, capsys):
    """If the index-on-index merge raises (e.g. mismatched MultiIndex levels),
    the section is skipped (not in the result) instead of aborting the whole
    comparison."""
    comp = fresh_comparison()
    # model1.generator has a 2-level MultiIndex (ibus, machid). Give model2's
    # generator a single-level index so the index merge raises.
    gen2 = comp.model2.network.generator.copy()
    gen2.index = pd.Index(range(len(gen2)), name="single")
    comp.model2.network.generator = gen2

    result = comp.compare_network_dfs()

    # The merge raised and was caught -> the section is omitted from result.
    assert "generator" not in result
    out = capsys.readouterr().out
    assert "Could not bypass dataframes: generator" in out


# ---------------------------------------------------------------------------
# compare_graph — bypass path naming (579-581)
# ---------------------------------------------------------------------------

def test_compare_graph_bypass_naming(fresh_models):
    """Swapping the model order turns Model_1->Model_2's single sectionalization
    into a bypass, exercising the path_bypasses naming branch (581)."""
    m1, m2 = fresh_models()
    # Reverse order: old=Model_2, new=Model_1.
    comp = ModelComparison(m2, m1)
    graph = comp.compare_graph()

    byp = graph["path_bypasses"]
    assert isinstance(byp, pd.DataFrame)
    assert len(byp) == 1
    # The naming branch added the *_named companion columns.
    assert "original_path_named" in byp.columns
    assert "alternate_paths_named" in byp.columns
    # And the symmetric direction yields no sectionalizations here.
    assert len(graph["path_sectionalizations"]) == 0


# ---------------------------------------------------------------------------
# read_pickle — setattr failure during attribute load (672-673)
# ---------------------------------------------------------------------------

def test_read_pickle_attribute_setattr_failure_warns(fresh_comparison, tmp_path):
    """If a loaded attribute cannot be set on the target (the pickle_path setter
    asserts a .modcomp suffix), read_pickle warns and continues rather than
    aborting the load."""
    comp = fresh_comparison()
    # Corrupt the pickled object's _pickle_path so its pickle_path property
    # yields a non-.modcomp path; the target's setter will reject it on setattr.
    comp._pickle_path = tmp_path / "wrong_suffix.txt"
    good = tmp_path / "good.modcomp"
    with open(good, "wb") as f:
        pickle.dump(comp, f)

    target = fresh_comparison()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fp = target.read_pickle(good, resilient=False)

    assert fp.object is not None  # load completed despite the bad attribute
    assert any("Unable to load attribute" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# read_pickle — corrupt file (677-682, resilient + non-resilient)
# ---------------------------------------------------------------------------

def test_read_pickle_corrupt_resilient_warns(fresh_comparison, tmp_path):
    comp = fresh_comparison()
    bad = tmp_path / "corrupt.modcomp"
    bad.write_bytes(b"this is not a pickle")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fp = comp.read_pickle(bad, resilient=True)
    assert fp.file_path is None and fp.object is None
    assert any("Could not load file" in str(w.message) for w in caught)


def test_read_pickle_corrupt_not_resilient_raises(fresh_comparison, tmp_path):
    comp = fresh_comparison()
    bad = tmp_path / "corrupt2.modcomp"
    bad.write_bytes(b"definitely not a pickle")
    with pytest.raises(pickle.UnpicklingError):
        comp.read_pickle(bad, resilient=False)


# ---------------------------------------------------------------------------
# _write_csv — PermissionError branch (769-770)
# ---------------------------------------------------------------------------

def test_write_csv_permission_error_warns(tmp_path):
    """Writing to a path that is actually a directory raises PermissionError,
    which _write_csv catches and converts into a warning."""
    target_dir = tmp_path / "i_am_a_directory"
    target_dir.mkdir()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ModelComparison._write_csv(target_dir, pd.DataFrame({"a": [1]}))
    assert any("Unable to write" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# _df_comparison_to_csv — skip / empty / not-found branches (836, 840, 844)
# ---------------------------------------------------------------------------

def test_df_comparison_to_csv_skip_empty_and_missing(fresh_comparison, tmp_path):
    comp = fresh_comparison()
    comp.compare_network_dfs()
    comp.csv_folder = tmp_path

    # 836: a 'sub*' section is skipped (no file written).
    comp.network_df_comparison["sub_record"] = pd.DataFrame({"a": [1]})
    # 840: an empty DataFrame warns "Dataframe is empty".
    comp.network_df_comparison["empty_section"] = pd.DataFrame()
    # 844: a non-DataFrame value warns "Dataframe not found".
    comp.network_df_comparison["none_section"] = None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        comp._df_comparison_to_csv()
        messages = [str(w.message) for w in caught]

    assert not (tmp_path / "network_sub_record.csv").exists()  # skipped
    assert any("Dataframe is empty: empty_section" in m for m in messages)
    assert any("Dataframe not found: none_section" in m for m in messages)


# ---------------------------------------------------------------------------
# _graph_comparison_to_csv — ValueError flatten fallback (868-871)
# ---------------------------------------------------------------------------

def test_graph_comparison_to_csv_flatten_fallback(fresh_comparison, tmp_path):
    """When pd.DataFrame(data=data) raises ValueError, the export falls back to
    the flatten-and-stringify path and still writes a CSV."""
    comp = fresh_comparison()
    comp.csv_folder = tmp_path
    # A dict of scalars makes pd.DataFrame(data=...) raise ValueError
    # ("If using all scalar values, you must pass an index").
    comp.graph_comparison = {"weird_sheet": {"some_key": 1}}

    comp._graph_comparison_to_csv()

    out = tmp_path / "graph_weird_sheet.csv"
    assert out.exists()
    text = out.read_text()
    # Fallback writes Path/Alternate_Paths columns from the flattened dict.
    assert "Path" in text.splitlines()[0]


# ---------------------------------------------------------------------------
# query_network_df_comparison — plain-bus-column mask branch (986-987)
# ---------------------------------------------------------------------------

def test_query_uses_plain_bus_column_mask(fresh_comparison):
    """When an equipment section carries a plain 'ibus' column (rather than the
    suffixed 'ibus_model1' produced by the normal merge), the query filters it
    with a bus-membership mask."""
    comp = fresh_comparison()
    comp.compare_network_dfs()

    # Replace the generator frame with one exposing a plain 'ibus' column so the
    # bus_cols branch (986-987) is taken instead of the no-bus-columns else.
    comp.network_df_comparison["generator"] = pd.DataFrame(
        {"ibus": [101, 999999], "pg": [1.0, 2.0]}
    )

    out = comp.query_network_df_comparison(inplace=False)
    assert "generator" in out
    gen = out["generator"]
    # Only rows whose ibus is in the voltage-filtered bus set survive the mask;
    # the synthetic 999999 bus is not, so it is filtered out.
    assert 999999 not in gen["ibus"].tolist()


# ---------------------------------------------------------------------------
# main — cached-read path (1049)
# ---------------------------------------------------------------------------

def test_main_reads_cached_comparison(tmp_path, monkeypatch):
    """With force_recalculation=False and an existing /cache/<stem>_<stem>.modcomp,
    main() loads the cached ModelComparison (compare.py:1049) instead of
    rebuilding from the RAW files.

    main() builds the cache path as Path('/cache/<stem>_<stem>.modcomp'); we
    redirect that to tmp_path by monkeypatching the module-level Path used in
    compare.main, then pre-seed a valid pickle there.
    """
    import psse_model_util.compare as compare_mod

    clear_cache()
    real_path = compare_mod.Path
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    def redirecting_path(p):
        s = str(p)
        if s.startswith("/cache/"):
            return cache_dir / s[len("/cache/"):]
        return real_path(p)

    # Build and pickle a valid comparison at the cache location main() expects.
    # main() uses raw1_path.stem twice, so the file is Model_1_Model_1.modcomp.
    m1 = Model(DATA_DIR / "Model_1.raw")
    m2 = Model(DATA_DIR / "Model_2.raw")
    seed = ModelComparison(m1, m2)
    seed.compare_network_dfs()
    seed.compare_graph()
    seed.pickle_path = cache_dir / "Model_1_Model_1.modcomp"
    seed.to_pickle()
    assert (cache_dir / "Model_1_Model_1.modcomp").exists()

    monkeypatch.setattr(compare_mod, "Path", redirecting_path)

    # force_recalculation=False -> the cached-read branch (1049) is taken.
    compare_mod.main(
        DATA_DIR / "Model_1.raw",
        DATA_DIR / "Model_2.raw",
        force_recalculation=False,
        export_format=None,
    )
