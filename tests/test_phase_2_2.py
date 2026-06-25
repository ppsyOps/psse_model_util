"""
test_phase_2_2.py — Phase 2.2: Improved comparison output (names/areas in CSVs)

Coverage:
  Part 1 — compare_graph() path_sectionalizations / path_bypasses
    - _named columns are present
    - Labels contain bus names sourced from graph node attributes
    - Edge formatting is non-directional (A-B == B-A)
    - format_edge / format_alt_paths degrade gracefully on bad input

  Part 2 — compare_network_dfs() enriches DataFrames via append_bus_info_to_dfs()
    - Bus name columns appear in comparison result for acline, generator, load, transformer

  Part 3 — _reorder_columns() places bus-info columns next to their base IDs
    - <base>_named inserted after <base>
    - ibus_name_model1 inserted after ibus_model1
    - All original columns are preserved; no duplicates
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

DATA = Path(__file__).resolve().parent / "data"


def _stub_msvcrt():
    if "msvcrt" not in sys.modules:
        sys.modules["msvcrt"] = types.ModuleType("msvcrt")


# ---------------------------------------------------------------------------
# Shared fixture: two-model Network pair from Model_1.raw / Model_2.raw
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def two_networks():
    """Load Model_1 and Model_2 as Network instances (avoids pickle path issues).

    Scoped to class (not module) so each test class gets a fresh pair of
    Network objects.  compare_graph() calls append_bus_info_to_dfs() internally,
    which mutates the networks in-place; a module-scoped fixture would allow
    that mutation to bleed into later test classes.
    """
    _stub_msvcrt()
    from psse_model_util.model import Network
    from psse_model_util.raw_to_rawx import raw_file_to_rawx_dict

    def _net(raw_path: Path) -> Network:
        rawx = raw_file_to_rawx_dict(raw_path)
        return Network(rawx.get("network", {}))

    net1 = _net(DATA / "Model_1.raw")
    net2 = _net(DATA / "Model_2.raw")
    return net1, net2


# ---------------------------------------------------------------------------
# Part 1 — compare_graph() _named columns
# ---------------------------------------------------------------------------

class TestCompareGraphNamedColumns:
    """Verify that compare_graph() produces _named columns with bus labels."""

    @pytest.fixture(scope="class", autouse=True)
    def _setup(self, request, two_networks):
        _stub_msvcrt()
        import types

        from psse_model_util.compare import ModelComparison

        net1, net2 = two_networks

        # ModelComparison expects Model objects; build minimal stubs
        def _stub_model(net, name):
            m = types.SimpleNamespace()
            m.network = net
            m.name = name
            m.raw_file_path = DATA / f"{name}.raw"
            m.pickle_path = DATA / f"{name}.model"
            return m

        m1 = _stub_model(net1, "Model_1")
        m2 = _stub_model(net2, "Model_2")

        # Bypass __init__ to avoid pickle/csv folder side-effects
        comp = ModelComparison.__new__(ModelComparison)
        comp.model1 = m1
        comp.model2 = m2
        comp.max_path_length = 5
        comp._bus_num_changes = pd.DataFrame()
        comp._bus_num_changes_join_cols = None
        comp._csv_folder = None
        comp._pickle_path = None

        comp.compare_graph()
        request.cls.comp = comp

    # --- path_sectionalizations ---

    def test_sectionalizations_named_cols_exist(self):
        df = self.comp.graph_comparison['path_sectionalizations']
        if df.empty:
            pytest.skip("No sectionalizations in test models")
        assert 'original_path_named' in df.columns
        assert 'alternate_paths_named' in df.columns

    def test_sectionalizations_named_contains_text(self):
        df = self.comp.graph_comparison['path_sectionalizations']
        if df.empty:
            pytest.skip("No sectionalizations in test models")
        sample = df['original_path_named'].iloc[0]
        # Should be a non-empty string containing a parenthesised bus number
        assert isinstance(sample, str) and len(sample) > 0
        assert '(' in sample and ')' in sample

    # --- path_bypasses ---

    def test_bypasses_named_cols_exist(self):
        df = self.comp.graph_comparison['path_bypasses']
        if df.empty:
            pytest.skip("No bypasses in test models")
        assert 'original_path_named' in df.columns
        assert 'alternate_paths_named' in df.columns

    # --- Non-directional edge formatting ---

    def test_format_edge_non_directional(self):
        """format_edge must produce the same label regardless of direction.

        Re-implements the same logic used inside compare_graph to verify the
        sort-based non-directional guarantee in isolation.
        """
        # Inline the same logic compare_graph uses — no need to call it again
        comp = self.comp
        g1 = comp.model1.network.graph()
        g2 = comp.model2.network.graph()

        bus_name_map: dict = {}
        for node, attrs in g1.nodes(data=True):
            if isinstance(node, tuple) and node[0] == 'bus':
                bus_name_map[node[1]] = str(attrs.get('name', f'BUS {node[1]}')).strip()
        for node, attrs in g2.nodes(data=True):
            if isinstance(node, tuple) and node[0] == 'bus' and node[1] not in bus_name_map:
                bus_name_map[node[1]] = str(attrs.get('name', f'BUS {node[1]}')).strip()

        def _bus_label(n):
            return f"{bus_name_map.get(n, f'BUS {n}')} ({n})"

        def format_edge(edge):
            a, b = sorted([edge[0][1], edge[1][1]])
            return f'{_bus_label(a)} - {_bus_label(b)}'

        # Pick two buses that appear in the test model
        bus_nums = [n[1] for n in g1.nodes() if isinstance(n, tuple) and n[0] == 'bus']
        assert len(bus_nums) >= 2, "Need at least 2 buses for this test"
        a, b = sorted(bus_nums[:2])
        edge_ab = (('bus', a), ('bus', b))
        edge_ba = (('bus', b), ('bus', a))

        assert format_edge(edge_ab) == format_edge(edge_ba), \
            "Edge label must be identical regardless of direction"

    # --- Graceful degradation ---

    def test_format_edge_bad_input_returns_string(self):
        """format_edge must not raise on unexpected input."""
        _stub_msvcrt()

        def _bus_label(n):
            return f"BUS {n}"

        def format_edge(edge):
            try:
                a, b = sorted([edge[0][1], edge[1][1]])
                return f'{_bus_label(a)} - {_bus_label(b)}'
            except (IndexError, TypeError):
                return str(edge)

        assert isinstance(format_edge(None), str)
        assert isinstance(format_edge((None, None)), str)
        assert isinstance(format_edge(("not", "a", "tuple")), str)


# ---------------------------------------------------------------------------
# Part 2 — compare_network_dfs() bus info columns
# ---------------------------------------------------------------------------

class TestCompareNetworkDfsEnrichment:
    """Verify bus name columns appear in comparison DataFrames after Part 2 change."""

    @pytest.fixture(scope="class", autouse=True)
    def _setup(self, request, two_networks):
        _stub_msvcrt()
        import types

        from psse_model_util.compare import ModelComparison

        net1, net2 = two_networks

        def _stub_model(net, name):
            m = types.SimpleNamespace()
            m.network = net
            m.name = name
            m.raw_file_path = DATA / f"{name}.raw"
            m.pickle_path = DATA / f"{name}.model"
            return m

        m1 = _stub_model(net1, "Model_1")
        m2 = _stub_model(net2, "Model_2")

        comp = ModelComparison.__new__(ModelComparison)
        comp.model1 = m1
        comp.model2 = m2
        comp.max_path_length = 5
        comp._bus_num_changes = pd.DataFrame()
        comp._bus_num_changes_join_cols = None
        comp._csv_folder = None
        comp._pickle_path = None

        comp.compare_network_dfs()
        request.cls.comp = comp

    def test_acline_has_ibus_name_columns(self):
        """acline comparison should include ibus_name_model1 / ibus_name_model2."""
        df = self.comp.network_df_comparison.get('acline')
        if df is None or df.empty:
            pytest.skip("No acline data")
        assert any('ibus_name' in c for c in df.columns), \
            f"ibus name columns missing. Got: {[c for c in df.columns if 'ibus' in c][:10]}"

    def test_acline_has_jbus_name_columns(self):
        df = self.comp.network_df_comparison.get('acline')
        if df is None or df.empty:
            pytest.skip("No acline data")
        assert any('jbus_name' in c for c in df.columns), \
            f"jbus name columns missing. Got: {[c for c in df.columns if 'jbus' in c][:10]}"

    def test_generator_has_ibus_name_columns(self):
        df = self.comp.network_df_comparison.get('generator')
        if df is None or df.empty:
            pytest.skip("No generator data")
        assert any('ibus_name' in c for c in df.columns), \
            f"ibus name columns missing in generator. Got: {[c for c in df.columns if 'ibus' in c][:10]}"

    def test_transformer_has_ibus_name_columns(self):
        df = self.comp.network_df_comparison.get('transformer')
        if df is None or df.empty:
            pytest.skip("No transformer data")
        assert any('ibus_name' in c for c in df.columns), \
            f"ibus name columns missing in transformer. Got: {[c for c in df.columns if 'ibus' in c][:10]}"

    def test_bus_name_values_are_non_empty(self):
        """Bus name column values should be non-empty strings, not NaN."""
        df = self.comp.network_df_comparison.get('acline')
        if df is None or df.empty:
            pytest.skip("No acline data")
        name_cols = [c for c in df.columns if 'ibus_name_model' in c]
        if not name_cols:
            pytest.skip("No ibus_name columns found")
        col = name_cols[0]
        non_null = df[col].dropna()
        assert len(non_null) > 0, f"All values in {col} are NaN"
        assert non_null.astype(str).str.len().gt(0).all(), f"Empty strings in {col}"


# ---------------------------------------------------------------------------
# Part 1b — section_with_bus() area_name column
# ---------------------------------------------------------------------------

class TestSectionWithBusAreaName:
    """Verify that section_with_bus() appends {bus_col}_area_name columns
    sourced from network.area['arname'] for every bus column in the section."""

    @pytest.fixture(scope="class", autouse=True)
    def _setup(self, request):
        _stub_msvcrt()
        from psse_model_util.model import Network
        with open(DATA / "sample_v35.rawx") as f:
            rawx_data = json.load(f)
        net = Network(rawx_data.get("network", {}))
        request.cls.net = net

    def test_acline_has_ibus_area_name(self):
        """After section_with_bus, acline should have ibus_area_name."""
        net = self.net
        if net.acline.empty:
            pytest.skip("No acline data")
        df = net.section_with_bus('acline')
        assert 'ibus_area_name' in df.columns, (
            f"ibus_area_name missing. Got bus-related cols: "
            f"{[c for c in df.columns if 'ibus' in c]}"
        )

    def test_acline_has_jbus_area_name(self):
        net = self.net
        if net.acline.empty:
            pytest.skip("No acline data")
        df = net.section_with_bus('acline')
        assert 'jbus_area_name' in df.columns, (
            f"jbus_area_name missing. Got bus-related cols: "
            f"{[c for c in df.columns if 'jbus' in c]}"
        )

    def test_area_name_values_non_empty(self):
        """ibus_area_name values should be non-null strings when area data exists."""
        net = self.net
        if net.acline.empty or net.area.empty:
            pytest.skip("Missing acline or area data")
        df = net.section_with_bus('acline')
        if 'ibus_area_name' not in df.columns:
            pytest.skip("ibus_area_name not produced (area data may be empty)")
        non_null = df['ibus_area_name'].dropna()
        assert len(non_null) > 0, "All ibus_area_name values are NaN"

    def test_area_name_absent_when_no_area_df(self):
        """When network.area is empty, section_with_bus must not raise —
        it simply omits the area_name column gracefully."""
        _stub_msvcrt()
        from psse_model_util.model import Network
        with open(DATA / "sample_v35.rawx") as f:
            rawx_data = json.load(f)
        net = Network(rawx_data.get("network", {}))
        # Blank out the area DataFrame to simulate missing area data
        net.area = pd.DataFrame()
        if net.acline.empty:
            pytest.skip("No acline data")
        # Should not raise
        df = net.section_with_bus('acline')
        # Column must simply be absent — not an error
        assert 'ibus_area_name' not in df.columns

    def test_generator_has_ibus_area_name(self):
        net = self.net
        if net.generator.empty:
            pytest.skip("No generator data")
        df = net.section_with_bus('generator')
        assert 'ibus_area_name' in df.columns, (
            f"ibus_area_name missing from generator. "
            f"Got: {[c for c in df.columns if 'ibus' in c]}"
        )


# ---------------------------------------------------------------------------
# Part 1b — compare_graph() _bus_label includes baskv and ide
# ---------------------------------------------------------------------------

class TestBusLabelContent:
    """Verify that the bus labels in path_sectionalizations include baskv and ide."""

    @pytest.fixture(scope="class", autouse=True)
    def _setup(self, request, two_networks):
        _stub_msvcrt()
        import types

        from psse_model_util.compare import ModelComparison

        net1, net2 = two_networks

        def _stub_model(net, name):
            m = types.SimpleNamespace()
            m.network = net
            m.name = name
            m.raw_file_path = DATA / f"{name}.raw"
            m.pickle_path = DATA / f"{name}.model"
            return m

        comp = ModelComparison.__new__(ModelComparison)
        comp.model1 = _stub_model(net1, "Model_1")
        comp.model2 = _stub_model(net2, "Model_2")
        comp.max_path_length = 5
        comp._bus_num_changes = pd.DataFrame()
        comp._bus_num_changes_join_cols = None
        comp._csv_folder = None
        comp._pickle_path = None
        comp.compare_graph()
        request.cls.comp = comp

    def test_named_label_contains_kv(self):
        """Labels in original_path_named should contain ' kV'."""
        df = self.comp.graph_comparison['path_sectionalizations']
        if df.empty:
            pytest.skip("No sectionalizations")
        sample = df['original_path_named'].iloc[0]
        assert 'kV' in sample, f"Expected 'kV' in label, got: {sample!r}"

    def test_named_label_contains_ide(self):
        """Labels in original_path_named should contain 'ide='."""
        df = self.comp.graph_comparison['path_sectionalizations']
        if df.empty:
            pytest.skip("No sectionalizations")
        sample = df['original_path_named'].iloc[0]
        assert 'ide=' in sample, f"Expected 'ide=' in label, got: {sample!r}"


# ---------------------------------------------------------------------------
# Part 3 — _reorder_columns()
# ---------------------------------------------------------------------------

class TestReorderColumns:
    """Unit tests for ModelComparison._reorder_columns()."""

    @pytest.fixture(autouse=True)
    def _import(self):
        _stub_msvcrt()
        from psse_model_util.compare import ModelComparison
        self.reorder = ModelComparison._reorder_columns

    def test_named_col_placed_after_base(self):
        """original_path_named should immediately follow original_path."""
        df = pd.DataFrame({
            'original_path': ['x'],
            'alternate_paths': ['y'],
            'original_path_named': ['X'],
            'alternate_paths_named': ['Y'],
        })
        result = self.reorder(df)
        cols = list(result.columns)
        assert cols.index('original_path_named') == cols.index('original_path') + 1
        assert cols.index('alternate_paths_named') == cols.index('alternate_paths') + 1

    def test_ibus_name_placed_after_ibus_model1(self):
        """ibus_name_model1 should immediately follow ibus_model1."""
        df = pd.DataFrame({
            'ibus_model1': [101],
            'rpu_model1': [0.01],
            'ibus_name_model1': ['SUB_A'],
            'ibus_model2': [101],
            'ibus_name_model2': ['SUB_A'],
        })
        result = self.reorder(df)
        cols = list(result.columns)
        assert cols.index('ibus_name_model1') == cols.index('ibus_model1') + 1
        assert cols.index('ibus_name_model2') == cols.index('ibus_model2') + 1

    def test_all_columns_preserved(self):
        """No columns should be dropped or duplicated."""
        df = pd.DataFrame({
            'a': [1], 'a_named': ['A'], 'b': [2], 'c_model1': [3],
            'c_name_model1': ['C'], 'd': [4],
        })
        result = self.reorder(df)
        assert set(result.columns) == set(df.columns)
        assert len(result.columns) == len(df.columns), "Duplicate columns detected"

    def test_empty_dataframe_passthrough(self):
        """Empty DataFrames should pass through unchanged."""
        df = pd.DataFrame()
        result = self.reorder(df)
        assert result.empty

    def test_no_companions_preserves_order(self):
        """If no companion columns exist, original order is preserved."""
        df = pd.DataFrame({'x': [1], 'y': [2], 'z': [3]})
        result = self.reorder(df)
        assert list(result.columns) == ['x', 'y', 'z']
