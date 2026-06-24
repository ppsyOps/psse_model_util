"""Compare two PSS/E power flow models (RAW or RAWX).

The main class, :class:`ModelComparison`, loads two :class:`~psse_model_util.model.Model`
instances and compares them, surfacing network dataframe differences, topology
changes, alternate-path analysis, and bus renumbering between the two models.

Key features:
    - Comparison of large power system models.
    - Analysis of network topology changes.
    - Identification of added, removed, and modified equipment.
    - Path analysis for changes in network connectivity (sectionalizations and bypasses).
    - Export of comparison results to CSV.

The implementation uses pandas for dataframe manipulation, networkx for graph
operations, and pickle caching to avoid redundant recalculation of expensive
comparisons.

Examples:
    Compare two models and export the results to CSV::

        from psse_model_util.compare import ModelComparison
        from psse_model_util.model import Model

        model1 = Model('path/to/model1.raw')
        model2 = Model('path/to/model2.raw')

        comparison = ModelComparison(model1, model2)
        comparison.compare_network_dfs()
        comparison.compare_graph()
        comparison.to_csv(df_comparison_to_csv=True)
"""

from __future__ import annotations

import argparse
import pickle
import warnings
from collections import namedtuple
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Dict, List, Optional

import networkx as nx
import numpy as np
import pandas as pd

from psse_model_util.common.constants import (
    ALT_PATH_MAX_PATH_LENGTH,
    DEFAULT_KV_FILTER,
    INCLUDE_AREAS,
    NETWORK_DF_COMPARISON_QUERIES,
)
from psse_model_util.common.dirs import site_cache_dir, site_data_dir
from psse_model_util.common.file_util import to_pickle
from psse_model_util.model import Model

# Define named tuples for storing comparison results
FpPickleType = namedtuple('FpPickleType',
                          ['file_path', 'object'])
PathComparison = namedtuple('PathComparison',
                            ['path_sectionalizations', 'path_bypasses', 'added_edges',
                             'removed_edges', 'added_nodes', 'removed_nodes'])
ComparisonDF = namedtuple('ComparisonDF',
                          ['changed', 'added', 'removed'])
EdgePathInfo = namedtuple('EdgePathInfo',
                          ['section', 'branch', 'edge_name', 'valid_paths'])
EdgeInfo = namedtuple('EdgeInfo',
                      ['from_bus', 'to_bus', 'equip', 'edge_type', 'edge_name'])

# Bus splits/sectionalizations and merges/bypasses
# ModelComparison.compare_graph._find_alt_paths()
#   Sectionalize: branch split, like A-C becomes A-B-C.
#   Bypass: branch merged, like A-B-C becomes A-C.
GraphComparison = namedtuple('GraphComparison',
                             ['path_sectionalizations', 'path_bypasses', 'added_edges',
                              'removed_edges', 'added_nodes', 'removed_nodes'])

COMMAND_LINE_HELP_TEXT = """
PSSE Model Comparison Tool
--------------------------

This tool compares two PSSE RAW or RAWX models and provides detailed analysis of
their differences.

Usage:
    python compare.py <raw1_path> <raw2_path> [options]

Arguments:
    raw1_path (p1)              : Path to the first RAW or RAWX file
    raw2_path (p2)              : Path to the second RAW or RAWX file

Options:
    -f, --force_recalculation   : Force recalculation even if cached results exist
    -e, --export_format {csv,none}
                                : Format to export results (default: csv)
    -b, --add_bus_info_to_branches
                                : Add bus information to branch DataFrames
    -a, --areas AREAS           : Comma-separated list of area numbers to
                                  include (e.g., "101,102,103")

Example:
    python compare.py path/to/model1.rawx path/to/model2.rawx -f -e csv -b -a 101,102,103

This example compares model1.rawx and model2.rawx, forces recalculation, exports
results to CSV, adds bus information to branches, and includes only areas 101,
102, and 103 in the comparison.
"""


class ModelComparison:
    """Compare two PSS/E power flow models.

    Loads two :class:`~psse_model_util.model.Model` instances and compares them.
    Call :meth:`compare_network_dfs` for a column-by-column comparison of the
    per-section network dataframes, :meth:`compare_graph` for topology
    differences (added/removed edges and nodes, sectionalizations, and bypasses),
    and :meth:`to_csv` to export the results. Results are cached to a pickle
    (``.modcomp``) file via :meth:`to_pickle` / :meth:`read_pickle`.

    Attributes:
        model1 (Model): The first model for comparison.
        model2 (Model): The second model for comparison.
        network_df_comparison (dict): Results of the dataframe comparison, keyed
            by network section name.
        graph_comparison (GraphComparison): Results of the graph comparison.
        max_path_length (int): Maximum path length for alternate-path search.
    """

    def __init__(self, model1: Model = None,
                 model2: Model = None,
                 model_comp_file: Path | str = None,
                 max_path_length: int = ALT_PATH_MAX_PATH_LENGTH):
        """Initialize the comparison from two models or a cached comparison file.

        Provide either both ``model1`` and ``model2``, or ``model_comp_file``
        pointing at a previously cached ``.modcomp`` pickle.

        Args:
            model1: The first model for comparison.
            model2: The second model for comparison.
            model_comp_file: Path to a pre-existing ``.modcomp`` comparison file.
                When given, ``model1`` and ``model2`` must both be ``None``.
            max_path_length: Maximum path length for alternate-path search.

        Raises:
            AssertionError: If a comparison file is given alongside models, or if
                the supplied models are not :class:`~psse_model_util.model.Model`
                instances.
        """
        if model_comp_file:
            assert model1 is None and model2 is None
            self.pickle_path = Path(model_comp_file)
            if self.pickle_path.exists():
                self.read_pickle(self.pickle_path)
        else:
            assert isinstance(model1, Model)
            model1.network.graph(regenerate=False, empty_ok=False)
            self.model1: Model = model1
            assert isinstance(model2, Model)
            model2.network.graph(regenerate=False, empty_ok=False)
            self.model2: Model = model2

            self.network_df_comparison: dict = dict()
            self.graph_comparison: GraphComparison = None
            self.max_path_length: int = max_path_length

        if not hasattr(self, "_csv_folder"):
            self._csv_folder = None
        if not hasattr(self, "_pickle_path"):
            self._pickle_path = None
        if not hasattr(self, "_bus_num_changes"):
            self._bus_num_changes: pd.DataFrame = pd.DataFrame()
            self._bus_num_changes._metadata = {'join_columns': []}

        self.pickle_path  # Set the pickle file path for the model comparison
        self.csv_folder  # Set the CSV file path for the model comparison

        if not model_comp_file:
            print('Saving to:', self.pickle_path)
            self.to_pickle()

    def bus_num_changes(self, join_columns: list = ['name', 'area', 'baskv']) \
            -> Optional[pd.DataFrame]:
        """Find buses common to both models whose bus number changed.

        Inner-joins the bus dataframes from ``model1`` and ``model2`` on
        ``join_columns``, then keeps only the rows where the bus number (``ibus``)
        differs between the two models. The result is cached in memory; a repeat
        call with the same ``join_columns`` returns the cached frame.

        Args:
            join_columns: Bus columns to match buses on across the two models.
                Must not include the index column ``ibus``.

        Returns:
            A DataFrame of the bus number changes, with columns suffixed
            ``_model1`` / ``_model2`` as applicable, or ``None`` if no changes
            are found.

        Raises:
            AssertionError: If ``ibus`` is present in ``join_columns``.
            ValueError: If any ``join_columns`` entry is not present in both bus
                dataframes.

        Note:
            The result includes only buses present in both models (inner join).
        """
        # If cached results exist and join columns haven't changed, return
        # cached results.
        # If (1) bus_num_changes has already been run (and results saved to
        # self._bus_num_changes) # and (2) join_columns is the same as used to
        # create that cache, then use the cached results.  Else, start from
        # scratch.
        if not self._bus_num_changes.empty and \
                self._bus_num_changes._metadata['join_columns'] == join_columns:
            return self._bus_num_changes

        # Do not join on index column, 'ibus'.
        assert 'ibus' not in join_columns, "'ibus' not permitted in join_columns."

        # Remove duplicates from join_columns
        join_columns = list(dict.fromkeys(join_columns))

        # Get bus dataframes from both models
        bus_df1 = self.model1.network.bus.reset_index()
        bus_df2 = self.model2.network.bus.reset_index()

        # Ensure required columns exist in both dataframes
        if not all(col in bus_df1.columns and col in bus_df2.columns
                   for col in ['ibus'] + join_columns):
            print('bus_df1:', bus_df1.columns)
            print('bus_df1:', bus_df2.columns)
            print('join_columns:', join_columns)
            raise ValueError(f"join_columns ({join_columns}) contains column "
                             f"names not found in bus dataframes.")

        # Perform inner join on 'name' and 'area'
        bypassd_df = pd.merge(
            bus_df1,
            bus_df2,
            on=join_columns,
            suffixes=('_model1', '_model2')
        )

        # Filter to show only records where bus numbers differ
        changes_df = bypassd_df[bypassd_df['ibus_model1'] != bypassd_df['ibus_model2']]

        # If there are changes, prepare the result DataFrame
        if not changes_df.empty:
            result_columns = ['ibus_model1', 'ibus_model2'] + join_columns
            self._bus_num_changes = changes_df[result_columns].copy()
            if not self._bus_num_changes._metadata:
                self._bus_num_changes._metadata = {}
            self._bus_num_changes._metadata['join_columns'] = join_columns
            return self._bus_num_changes
        else:
            # If no changes, return None or an empty DataFrame based on your preference
            return None  # or return pd.DataFrame()

        # Note: The 'presence' column is not added here as it's not relevant for bus number changes

    def compare_network_dfs(self) -> Dict[str, pd.DataFrame]:
        """Compare the per-section network dataframes column by column.

        Compares corresponding dataframes from both models, identifying changed
        values, added rows, and removed rows. Each merged frame gains
        ``<column>_delta`` columns and a ``presence`` indicator column. Results
        are stored in :attr:`network_df_comparison`.

        Returns:
            A dictionary mapping each network section name to its comparison
            DataFrame.
        """

        def _column_delta(column1, column2):
            """Calculate the difference between two columns."""
            if isinstance(column1, pd.DataFrame) and isinstance(column2, pd.DataFrame):
                result = pd.DataFrame(index=column1.index)
                for col in column1.columns:
                    if col in column2.columns:
                        result[col] = _compare_values(column1[col], column2[col])
                    else:
                        result[col] = None
                return result
            else:
                return _compare_values(column1, column2)

        def _compare_values(series1, series2):
            """Compare two series element-wise."""
            if series1.dtype != series2.dtype:
                return series1 != series2

            # np.issubdtype raises TypeError on pandas extension dtypes (e.g.
            # StringDtype).  Fall back to object-style comparison for those.
            try:
                is_numeric = np.issubdtype(series1.dtype, np.number)
            except TypeError:
                is_numeric = False

            if is_numeric:
                return series2 - series1
            else:
                return (series1 != series2).astype(bool)

        # Enrich both models' DataFrames with bus info (name, baskv, area, etc.)
        # before the merge, so the joined columns appear naturally in every
        # network_*.csv without any additional post-processing.
        self.model1.network.append_bus_info_to_dfs()
        self.model2.network.append_bus_info_to_dfs()

        result: Dict[str, pd.DataFrame] = {}
        df1_names = [_ for _ in dir(self.model1.network)
                     if isinstance(getattr(self.model1.network, _), pd.DataFrame)]
        df2_names = [_ for _ in dir(self.model2.network)
                     if isinstance(getattr(self.model2.network, _), pd.DataFrame)]

        removed_dfs = set(df1_names) - set(df2_names)
        if removed_dfs:
            result['removed_equip_types'] = pd.DataFrame(removed_dfs, columns=['equip_type'])
        added_dfs = set(df2_names) - set(df1_names)
        if added_dfs:
            result['added_equip_types'] = pd.DataFrame(added_dfs, columns=['equip_type'])

        common_df_names = set(df1_names) & set(df2_names)
        for df_name in common_df_names:
            df1 = getattr(self.model1.network, df_name)
            df2 = getattr(self.model2.network, df_name)

            # Some sections (e.g. ntermdc, whose sub-records are flattened into
            # one frame) carry duplicate column names. Per-column delta/presence
            # selection on those raises a cryptic 2D-broadcast error that was
            # previously swallowed, silently dropping the enrichment. Detect it
            # up front: include the outer-merged frame but skip enrichment, with
            # a clear warning rather than a buried numpy traceback.
            if df1.columns.duplicated().any() or df2.columns.duplicated().any():
                warnings.warn(
                    f"Section '{df_name}' has duplicate column names; including "
                    f"the merged frame but skipping _delta/presence columns.")
                result[df_name] = pd.merge(
                    df1, df2, how='outer', left_index=True, right_index=True,
                    suffixes=('_model1', '_model2'))
                continue
            try:
                bypassd_df = pd.merge(df1, df2, how='outer', left_index=True,
                                      right_index=True, suffixes=('_model1', '_model2'))
            except Exception as e:
                print(f'Could not bypass dataframes: {df_name}. Exception: {str(e)}')
                print('Model 1 columns:', df1.columns)
                print('Model 2 columns:', df2.columns)
                continue

            columns = list(set(df1.columns) | set(df2.columns))
            new_columns: Dict[str, Any] = {}

            # Add "_delta" columns to bypassd_df
            for column in columns:
                col1, col2 = f'{column}_model1', f'{column}_model2'
                if col1 in bypassd_df.columns and col2 in bypassd_df.columns:
                    try:
                        new_columns[f'{column}_delta'] = _column_delta(bypassd_df[col1],
                                                                       bypassd_df[col2])
                    except ValueError as e:
                        print(f'Dataframe "{df_name}" comparison error. {str(e)}')
                        raise e

            # Add an indicator column to show which model(s) each row is present in.
            indicator_col1 = f'{columns[0]}_model1' if f'{columns[0]}_model1' in bypassd_df.columns else \
                bypassd_df.columns[0]
            indicator_col2 = f'{columns[0]}_model2' if f'{columns[0]}_model2' in bypassd_df.columns else \
                bypassd_df.columns[-1]

            new_columns['presence'] = np.select(
                [bypassd_df[indicator_col1].notna() & bypassd_df[indicator_col2].notna(),
                 bypassd_df[indicator_col1].notna(),
                 bypassd_df[indicator_col2].notna()],
                ['both', 'model1_only', 'model2_only'],
                default='neither'
            )

            # Add all new columns at once
            try:
                new_columns_df = pd.DataFrame(new_columns, index=bypassd_df.index)
                bypassd_df = pd.concat([bypassd_df, new_columns_df], axis=1)
            except ValueError as e:
                print(
                    f"Error adding new columns to bypassed DataFrame for {df_name}. Exception: {str(e)}.")

                # Attempt to add columns individually
                for col, values in new_columns.items():
                    try:
                        bypassd_df[col] = values
                    except Exception as col_e:
                        print(f"Failed to add column {col}. Error: {str(col_e)}")

            result[df_name] = bypassd_df

        # Add bus number changes to the result
        result['bus_num_changes'] = self.bus_num_changes()

        self.network_df_comparison = result
        return self.network_df_comparison

    def compare_graph(self, max_path_length: int = None, sort: bool = True,
                      regenerate=False) -> dict:
        """Compare the network topology (graph) of the two models.

        Identifies changes in network topology, including added and removed edges
        and nodes, plus path sectionalizations (a branch split, e.g. A-C becomes
        A-B-C) and path bypasses (a branch merge, e.g. A-B-C becomes A-C).
        Results are stored in :attr:`graph_comparison`.

        Args:
            max_path_length: Maximum path length for alternate-path search.
                Defaults to :attr:`max_path_length` when ``None``.
            sort: Whether to sort the alternate paths by length.
            regenerate: Whether to rebuild each model's graph before comparison.

        Returns:
            A dictionary of graph comparison results, with keys
            ``removed_edges``, ``removed_nodes``, ``added_edges``,
            ``added_nodes``, ``path_sectionalizations``, and ``path_bypasses``.

        Examples:
            ::

                comparison = ModelComparison(model1, model2)
                graph_changes = comparison.compare_graph(max_path_length=5)
                added_edges = graph_changes['added_edges']
        """

        def _get_removed_edges() -> list:
            """Get edges that exist in graph1 but not in graph2."""
            # graph1 = self.model1.network_graph
            # graph2 = self.model2.network_graph
            g1 = self.model1.network.graph(regenerate=regenerate)
            g2 = self.model2.network.graph(regenerate=regenerate)
            return [(u, v) for u, v in g1.edges
                    if not g2.has_edge(u, v)]

        def _get_added_edges() -> list:
            """Get edges that exist in graph2 but not in graph1."""
            graph1 = self.model1.network.graph(regenerate=regenerate)
            graph2 = self.model2.network.graph(regenerate=regenerate)
            return [(u, v) for u, v in graph2.edges
                    if not graph1.has_edge(u, v)]

        def _find_alt_paths(sectionalize_edges, g1: nx.Graph, g2: nx.Graph,
                            max_path_length=max_path_length,
                            sort=sort, as_dataframe: bool = True) -> pd.DataFrame:
            """Find alternative paths in g2 for edges in g1 that are not in g2."""
            max_path_length = max_path_length or self.max_path_length

            sectionalizes_dict = {}
            for idx, edge in enumerate(sectionalize_edges):
                if not idx % 1000:
                    print(f'    alt paths: evaluating {idx} of {len(sectionalize_edges) + 1} paths')
                node_a, node_b, *_ = edge
                if node_a not in g2.nodes or node_b not in g2.nodes:
                    continue

                try:
                    edge = g1.edges[node_a, node_b]
                except KeyError:
                    # TODO: Add logging
                    continue

                # branch = '-'.join([node_a[0], node_b[0]])
                section = edge['section'] if 'section' in edge else ''

                paths = nx.all_simple_paths(g2, node_a, node_b, cutoff=max_path_length)
                valid_paths = [path for path in paths if
                               all(node not in g1.nodes for node in path[1:-1])]

                if valid_paths:
                    if sort:
                        valid_paths.sort(key=len)
                    edge['type'] = section
                    sectionalizes_dict[(node_a, node_b)] = valid_paths

            # Update sectionalizes_dict to keep only the shortest paths for each edge
            for edge, paths in sectionalizes_dict.items():
                shortest_length = min(len(path) for path in paths)
                sectionalizes_dict[edge] = [path for path in paths if len(path) == shortest_length]

            if as_dataframe:
                # Convert sectionalizes_dict to DataFrame
                df = pd.DataFrame(list(sectionalizes_dict.items()), columns=['path', 'alt_paths'])
                return df

            return sectionalizes_dict

        max_path_length = max_path_length or self.max_path_length
        graph1 = self.model1.network.graph(regenerate=regenerate, empty_ok=False)
        graph2 = self.model2.network.graph(regenerate=regenerate, empty_ok=False)
        result = {}

        print('Finding removed edges...')
        result['removed_edges'] = _get_removed_edges()
        result['removed_nodes'] = set(graph1.nodes) - set(graph2.nodes)
        print('Finding added edges...')
        result['added_edges'] = _get_added_edges()
        result['added_nodes'] = set(graph2.nodes) - set(graph1.nodes)

        # Build a bus_num → attribute dict from graph node data (both models).
        # Graph nodes carry all bus DataFrame columns as attributes, e.g.
        # graph.nodes[('bus', 101)] == {'name': 'NUC-A', 'baskv': 21.6, 'ide': 2, ...}
        # Storing full attrs (not just name) lets _bus_label expose baskv and ide.
        # model2 fills in buses that only exist in the updated topology.
        bus_node_attrs: dict[int, dict] = {}
        for node, attrs in graph1.nodes(data=True):
            if isinstance(node, tuple) and node[0] == 'bus':
                bus_node_attrs[node[1]] = dict(attrs)
        for node, attrs in graph2.nodes(data=True):
            if isinstance(node, tuple) and node[0] == 'bus' and node[1] not in bus_node_attrs:
                bus_node_attrs[node[1]] = dict(attrs)

        def _bus_label(bus_num: int) -> str:
            """Return 'NAME (bus_num, baskv kV, ide)' for a single bus number.

            Includes the three fields a user needs to identify a bus at a glance:
              - name   : bus name string
              - baskv  : nominal voltage in kV
              - ide    : bus type code (1=load, 2=gen, 3=swing, 4=isolated)
            """
            attrs = bus_node_attrs.get(bus_num, {})
            name = str(attrs.get('name', f'BUS {bus_num}')).strip()
            baskv = attrs.get('baskv', '')
            ide = attrs.get('ide', '')
            kv_str = f'{baskv} kV' if baskv != '' else ''
            ide_str = f'ide={ide}' if ide != '' else ''
            detail = ', '.join(filter(None, [kv_str, ide_str]))
            suffix = f' [{detail}]' if detail else ''
            return f'{name} ({bus_num}){suffix}'

        def format_edge(edge) -> str:
            """Format an edge tuple (('bus', A), ('bus', B)) with bus names.

            Edges are non-directional; the label is ordered lower-bus-number first
            for consistency regardless of which direction the edge was stored.
            """
            try:
                a, b = sorted([edge[0][1], edge[1][1]])
                return f'{_bus_label(a)} - {_bus_label(b)}'
            except (IndexError, TypeError):
                return str(edge)

        def format_alt_paths(list_of_paths) -> str:
            """Format a list of alternative paths as a ' | '-delimited string."""
            formatted: list[str] = []
            try:
                for path in list_of_paths:
                    nodes_str = ' -> '.join(_bus_label(node[1]) for node in path)
                    formatted.append(nodes_str)
                return ' | '.join(formatted)
            except (IndexError, TypeError, AttributeError):
                return str(list_of_paths)

        print('Finding path sectionalizes...')
        df_sec = _find_alt_paths(result['removed_edges'], g1=graph1, g2=graph2)
        if not df_sec.empty:
            df_sec.columns = ['original_path', 'alternate_paths']
            df_sec['original_path_named'] = df_sec['original_path'].apply(format_edge)
            df_sec['alternate_paths_named'] = df_sec['alternate_paths'].apply(format_alt_paths)
        result['path_sectionalizations'] = df_sec

        print('Finding path bypass...')
        df_byp = _find_alt_paths(result['added_edges'], g1=graph2, g2=graph1)
        if not df_byp.empty:
            df_byp.columns = ['original_path', 'alternate_paths']
            df_byp['original_path_named'] = df_byp['original_path'].apply(format_edge)
            df_byp['alternate_paths_named'] = df_byp['alternate_paths'].apply(format_alt_paths)
        result['path_bypasses'] = df_byp

        self.graph_comparison = result
        return self.graph_comparison

    @property
    def pickle_path(self) -> Path:
        """Path to the comparison pickle (``.modcomp``) cache file.

        On first access, derives a default path under the site cache directory
        from the two model names. The setter requires a ``.modcomp`` suffix and
        creates the parent directory.

        Returns:
            The path to the pickle file.
        """

        if not hasattr(self, '_pickle_path') or not self._pickle_path:
            stem1 = self.model1.name or Path(self.model1.pickle_path).stem
            stem2 = self.model2.name or Path(self.model2.pickle_path).stem
            self._pickle_path = site_cache_dir / f'{stem1}_{stem2}.modcomp'
            self._pickle_path.parent.mkdir(parents=True, exist_ok=True)
        return self._pickle_path

    @pickle_path.setter
    def pickle_path(self, new_path: Path | str):
        new_path = Path(new_path)
        assert new_path.suffix == '.modcomp'
        self._pickle_path = Path(new_path)
        self._pickle_path.parent.mkdir(parents=True, exist_ok=True)

    def to_pickle(self, resilient: bool = True) -> bool:
        """Cache this comparison to its pickle (``.modcomp``) file.

        Args:
            resilient: If ``True``, suppress (warn on) pickling failures instead
                of raising.

        Returns:
            The path the comparison was written to.
        """
        to_pickle(pickle_path=self.pickle_path, data=self, resilient=resilient)
        print('Saved: ', self.pickle_path)
        return self.pickle_path

    def read_pickle(self, pickle_path: Path | str = None,
                    mode: str = 'rb', resilient: bool = True) -> FpPickleType:
        """Load a cached comparison from a pickle file into this instance.

        Reads the pickled object and copies its attributes onto ``self``.

        Args:
            pickle_path: Path to the pickle file. Defaults to :attr:`pickle_path`.
            mode: File open mode; should always be ``'rb'``.
            resilient: If ``True``, warn instead of raising on load failure.

        Returns:
            A named tuple of ``(file_path, object)``. Both are ``None`` when the
            file is missing or unreadable and ``resilient`` is ``True``.

        Raises:
            FileNotFoundError: If the pickle file is not found and ``resilient``
                is ``False``.
        """
        self.pickle_path = pickle_path or self.pickle_path
        if not self.pickle_path.exists():
            # Pickle file not found.  Retrun (None, None).
            if resilient:
                return FpPickleType(None, None)
            else:
                raise FileNotFoundError(f'Could not find file {str(self.pickle_path)}')
        obj = None
        try:
            with open(self.pickle_path, mode) as file:
                obj = pickle.load(file)
            attr_names = [attr for attr in dir(obj) if not attr.startswith('__')]
            for attr_name in attr_names:
                try:
                    setattr(self, attr_name, getattr(obj, attr_name))
                except Exception as e:
                    warnings.warn(f'Unable to load attribute "{attr_name}" '
                                  f'from cache. {str(e)}')
            print(f'Data loaded from cache: "{self.pickle_path}".')
            return FpPickleType(self.pickle_path, obj)
        except Exception as e:
            if resilient:
                warnings.warn(f'Could not load file {str(self.pickle_path)}. {str(e)}')
                return FpPickleType(None, None)
            else:
                raise e

    @property
    def csv_folder(self) -> Path:
        """Folder where CSV exports are written.

        On first access, derives a default folder under the site data directory
        from the pickle path stem. The setter creates the folder.

        Returns:
            The path to the CSV export folder.
        """

        if not hasattr(self, '_csv_folder') or not self._csv_folder:
            self._csv_folder = site_data_dir / f"{self.pickle_path.stem}"
            self._csv_folder.parent.mkdir(parents=True, exist_ok=True)
        return self._csv_folder

    @csv_folder.setter
    def csv_folder(self, new_folder: Path | str):
        self._csv_folder = Path(new_folder)
        self._csv_folder.mkdir(parents=True, exist_ok=True)

    def __getstate__(self):
        """Prepare object for pickling."""
        state = self.__dict__.copy()
        for attribute_name in ['_pickle_path', '_csv_folder']:
            if state.get(attribute_name):
                state[attribute_name] = str(state[attribute_name])
        return state

    def __setstate__(self, state):
        """Restore object from pickling."""
        # Convert string paths back to Path objects
        for attribute_name in ['_pickle_path', '_csv_folder']:
            if attribute_name in state and state[attribute_name]:
                state[attribute_name] = Path(state[attribute_name])
        self.__dict__.update(state)

    def to_csv(self, models_to_csv: bool = False,
               df_comparison_to_csv: bool = False,
               graph_comparison_to_csv: bool = False):
        """Export comparison results to CSV files.

        Args:
            models_to_csv: Whether to export each individual model's data to CSV.
            df_comparison_to_csv: Whether to export the dataframe comparison.
            graph_comparison_to_csv: Whether to export the graph comparison.

        Examples:
            ::

                comparison = ModelComparison(model1, model2)
                comparison.to_csv(df_comparison_to_csv=True,
                                  graph_comparison_to_csv=True)
        """
        self.csv_folder.mkdir(parents=True, exist_ok=True)

        if models_to_csv:
            self.model1.to_csv()
            self.model2.to_csv()

        if df_comparison_to_csv:
            self._df_comparison_to_csv()

        if graph_comparison_to_csv:
            self._graph_comparison_to_csv()

    @staticmethod
    def _write_csv(csv_path: [Path | str], df: pd.DataFrame) -> None:
        """Helper method to write a DataFrame to CSV.  Prevents hard exception.

        The index is included when it carries meaningful field names (i.e. when
        any entry in ``df.index.names`` is not None).  A plain RangeIndex has
        ``index.names == [None]`` and is excluded to avoid a spurious unnamed
        column in the output.

        Note: ``df.index.name`` is always ``None`` for a MultiIndex — using it
        as the sole check caused bus/branch identifier columns to be silently
        dropped from every composite-key section (acline, generator, load, …).
        """
        # Include the index only when it holds named fields.
        # MultiIndex.name is always None, so we must inspect .names instead.
        index = any(name is not None for name in df.index.names)
        try:
            df.to_csv(csv_path, index=index)
        except OSError as e:
            # OSError covers PermissionError (Windows) and IsADirectoryError
            # (POSIX) when csv_path is unwritable.
            warnings.warn(f'Unable to write general information to {csv_path}.  {str(e)}')

    @staticmethod
    def _reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Reorder DataFrame columns so that bus-info and *_named columns are
        placed immediately after the base identifier columns they annotate.

        Rules applied (in priority order):
        1. ``<base>_named`` is inserted right after ``<base>`` (e.g.
           ``original_path_named`` after ``original_path``).
        2. ``<bus_col>_<suffix>`` columns produced by
           ``append_bus_info_to_dfs`` / ``section_with_bus`` (e.g.
           ``ibus_name_model1``) are inserted right after the matching
           ``<bus_col>_<suffix>`` numeric column (e.g. after ``ibus_model1``).
        3. Any remaining columns keep their current order.
        """
        if df.empty:
            return df

        cols = list(df.columns)
        ordered: list[str] = []
        placed: set[str] = set()

        for col in cols:
            if col in placed:
                continue
            ordered.append(col)
            placed.add(col)
            # Rule 1: <base>_named immediately after <base>
            named_col = f'{col}_named'
            if named_col in cols and named_col not in placed:
                ordered.append(named_col)
                placed.add(named_col)
            # Rule 2: bus info columns (e.g. ibus_name_model1) after ibus_model1
            # Pattern: col is like 'ibus_model1'; companion is 'ibus_name_model1'
            for suffix in ('_model1', '_model2'):
                if col.endswith(suffix):
                    base = col[: -len(suffix)]
                    for companion in [f'{base}_name{suffix}',
                                      f'{base}_baskv{suffix}',
                                      f'{base}_area{suffix}']:
                        if companion in cols and companion not in placed:
                            ordered.append(companion)
                            placed.add(companion)

        # Append anything not yet placed (should be empty, but safe-guard)
        for col in cols:
            if col not in placed:
                ordered.append(col)

        return df[ordered]

    def _df_comparison_to_csv(self):
        """Export comparison results to CSV."""

        # Export general information
        info = [('model1', str(self.model1.raw_file_path)),
                ('model2', str(self.model2.raw_file_path))]
        df_info = pd.DataFrame(info, columns=['Setting', 'Value'])
        csv_path = self.csv_folder / 'info.csv'
        self._write_csv(csv_path, df_info)

        if not self.network_df_comparison:
            self.compare_network_dfs()
        for section, df in self.network_df_comparison.items():
            if section.startswith('sub') or section == 'gne':
                continue
            csv_path = self.csv_folder / f'network_{section}.csv'
            if isinstance(df, pd.DataFrame):
                if df.empty:
                    warnings.warn("Dataframe is empty: " + section)
                else:
                    self._write_csv(csv_path, self._reorder_columns(df))
            else:
                warnings.warn("Dataframe not found: " + section)

    def flatten_and_stringify(self, item):
        """Flatten a nested list/tuple into a comma-separated string.

        Recurses through nested lists and tuples; scalars are stringified as-is.

        Args:
            item: The value to flatten and stringify.

        Returns:
            The flattened, comma-separated string representation.
        """
        if isinstance(item, (list, tuple)):
            return ', '.join(self.flatten_and_stringify(i) for i in item)
        return str(item)

    def process_graph_data(self, data):
        """Flatten the keys and values of a graph-comparison mapping for CSV export.

        Used by :meth:`_graph_comparison_to_csv`.

        Args:
            data: A mapping whose keys and values may be nested lists/tuples.

        Returns:
            A dict with both keys and values flattened to strings via
            :meth:`flatten_and_stringify`.
        """
        return {self.flatten_and_stringify(key): self.flatten_and_stringify(value)
                for key, value in data.items()}

    def _graph_comparison_to_csv(self):
        """Export path sectionalizes and bypass to CSV."""
        if not self.graph_comparison:
            self.compare_graph()

        for sheet, data in self.graph_comparison.items():
            try:
                # Try the original method first
                df = pd.DataFrame(data=data)
            except ValueError:
                # If ValueError occurs, use the flattened and stringified data
                processed_data = self.process_graph_data(data)
                df = pd.DataFrame(list(processed_data.items()), columns=['Path', 'Alternate_Paths'])

            # df = pd.DataFrame(data=data)
            csv_path = self.csv_folder / f'graph_{sheet}.csv'
            self._write_csv(csv_path, df)

    def bus_kv_filter(self) -> List[int]:
        """Identify generator/load buses meeting the voltage filter criteria.

        Selects buses that carry a generator or load and whose nominal voltage
        (``baskv``) in either model falls within ``DEFAULT_KV_FILTER``.

        Returns:
            The bus numbers meeting the criteria.

        Examples:
            >>> model_comp = ModelComparison(model1, model2)
            >>> filtered_buses = model_comp.bus_kv_filter()
            >>> print(len(filtered_buses))
            1000
        """
        bus_df = self.network_df_comparison['bus']
        gen_df = self.network_df_comparison['generator']
        load_df = self.network_df_comparison['load']

        # Extract 'ibus' from multi-index
        gen_buses = gen_df.index.get_level_values(
            'ibus') if 'ibus' in gen_df.index.names else pd.Series()
        load_buses = load_df.index.get_level_values(
            'ibus') if 'ibus' in load_df.index.names else pd.Series()

        # Combine generator and load buses
        all_buses = set(gen_buses) | set(load_buses)

        # Filter buses based on voltage criteria
        mask = (((bus_df['baskv_model1'] >= DEFAULT_KV_FILTER.min) &
                 (bus_df['baskv_model1'] <= DEFAULT_KV_FILTER.max)) |
                ((bus_df['baskv_model2'] >= DEFAULT_KV_FILTER.min) &
                 (bus_df['baskv_model2'] <= DEFAULT_KV_FILTER.max))
                ) & (bus_df.index.isin(all_buses))

        return bus_df[mask].index.tolist()

    def query_network_df_comparison(self, inplace: bool = True,
                                    queries: dict = NETWORK_DF_COMPARISON_QUERIES
                                    ) -> Dict[str, pd.DataFrame]:
        """Filter the network comparison dataframes by voltage and custom queries.

        Filtering proceeds in stages: buses are first filtered by voltage via
        :meth:`bus_kv_filter`, equipment dataframes are then filtered to those
        connected to the surviving buses, and finally any custom pandas query
        strings in ``queries`` are applied. Intended for narrowing results down
        to the records needed for INCH/IDEV file creation (not yet finished).

        Args:
            inplace: If ``True``, update :attr:`network_df_comparison` with the
                filtered dataframes.
            queries: Mapping of dataframe name to a pandas query string for
                additional filtering. Defaults to
                ``NETWORK_DF_COMPARISON_QUERIES``.

        Returns:
            The filtered dataframes, keyed by section name.

        Examples:
            ::

                modelcomp = ModelComparison(model1, model2)

                # Use default queries
                filtered_dfs = modelcomp.query_network_df_comparison()

                # Use custom queries
                custom_queries = {
                    'bus': 'baskv >= 345',
                    'generator': 'pg > 100',
                    'load': 'pl > 50',
                }
                filtered_dfs = modelcomp.query_network_df_comparison(
                    queries=custom_queries
                )

        Note:
            Voltage filtering is always applied first; custom queries run after.
            Equipment dataframes are filtered by bus connectivity, and a failed
            query generates a warning but does not stop execution.
        """
        # Get a list of bus IDs where bus voltage (baskv) is between
        # DEFAULT_KV_FILTER.min & DEFAULT_KV_FILTER.max)
        filtered_bus_ids = self.bus_kv_filter()

        # Get dict of network dataframes that we want to filter (from
        # NETWORK_DF_COMPARISON_QUERIES.keys, i.e. bus, generator, load, branch
        # and transformer)
        dfs_to_filter = {k: self.network_df_comparison[k] for k in
                         NETWORK_DF_COMPARISON_QUERIES.keys()}
        # dfs_to_filter = {
        #     'bus': self.network_df_comparison['bus'],
        #     'generator': self.network_df_comparison['generator'],
        #     'load': self.network_df_comparison['load'],
        #     'branch': self.network_df_comparison['acline'],
        #     'transformer': self.network_df_comparison['transformer']
        # }

        filtered_dfs = {}

        for df_name, df in dfs_to_filter.items():
            if df_name == 'bus':
                filtered_dfs[df_name] = df[df.index.isin(filtered_bus_ids)]
            else:
                bus_cols = [col for col in ['ibus', 'jbus', 'kbus'] if col in df.columns]
                if bus_cols:
                    mask = df[bus_cols].isin(filtered_bus_ids).any(axis=1)
                    filtered_dfs[df_name] = df[mask]
                else:
                    filtered_dfs[df_name] = df  # Keep original if no bus columns found

        # Apply user-defined filters from INI file
        for df_name, query in queries.items():
            if df_name in filtered_dfs and query:
                try:
                    filtered_dfs[df_name] = filtered_dfs[df_name].query(query)
                except Exception as e:
                    warnings.warn(f"Error applying filter for {df_name}.  "
                                  f"Update filter in common.constants.NETWORK_DF_COMPARISON_QUERIES. "
                                  f"{str(e)}.")

        if inplace:
            # Update the network_df_comparison with the filtered dataframes
            for df_name, filtered_df in filtered_dfs.items():
                self.network_df_comparison[df_name] = filtered_df

        return filtered_dfs


def main(raw1_path: Path | str,
         raw2_path: Path | str,
         force_recalculation: bool = True,
         export_format: str | None = 'csv',
         add_bus_info_to_branches: bool = True,
         areas=None):
    """Compare two PSS/E RAW or RAWX models end to end.

    Loads both models, filters them by area, optionally appends bus information
    to branch dataframes, runs the dataframe and graph comparisons, caches the
    result to a ``.modcomp`` pickle, and optionally exports to CSV.

    Args:
        raw1_path: Path to the first RAW or RAWX file.
        raw2_path: Path to the second RAW or RAWX file.
        force_recalculation: If ``True``, recompute even if cached results exist.
        export_format: Result export format; ``'csv'`` to export CSV or ``None``
            for no export.
        add_bus_info_to_branches: If ``True``, append bus information to branch
            dataframes.
        areas: Area numbers to include in the comparison.

    Examples:
        >>> main("path/to/model1.rawx", "path/to/model2.rawx",
        ...      force_recalculation=True, export_format='csv',
        ...      areas=[101, 102, 103])
    """
    if areas is None:
        areas = []
    start_time = perf_counter_ns()
    print('Starting model comparison...')

    include_areas = INCLUDE_AREAS
    raw1_path, raw2_path = Path(raw1_path), Path(raw2_path)
    # Path to the model comparison cache file (.modcomp).
    model_comparison_file = Path(
        f'/cache/{raw1_path.stem}_{raw1_path.stem}.modcomp')
    if not force_recalculation and model_comparison_file.exists():
        # Get the cached model comparison object from disk.
        comparison = ModelComparison(model_comp_file=model_comparison_file)
    else:
        # Load the
        # Load & filter your RAW or RAWX models from disk to Model objects.
        print('Loading model1...')
        model1 = Model(raw1_path)

        # Filter the models to a subset of areas (native + first-tier neighbors)
        print('Filtering model1...')
        native_model1 = model1.filter_by_area(areas=include_areas)
        print('Loading model2...')
        model2 = Model(raw2_path)
        print('Filtering model2...')
        native_model2 = model2.filter_by_area(areas=include_areas)

        # Optionally, add bus data directly to branch dataframe
        # (model.network.acline).  This is not necessary but can be helpful to
        # the end user, since this info will be in the exported
        # network_acline.csv file.
        if add_bus_info_to_branches:
            print('Model1: adding bus info to edges/branches...')
            native_model1.network.append_bus_info_to_dfs()
            print('Model2: adding bus info to edges/branches...')
            native_model2.network.append_bus_info_to_dfs()

        # Load the models into a ModelComparison instance
        print('Comparing models...')
        comparison = ModelComparison(native_model1, native_model2)

    if force_recalculation or not comparison.network_df_comparison or not comparison.graph_comparison:
        # Run the comparison of the Model.network pandas dataframes.
        print('Comparing network dataframes...')
        comparison.compare_network_dfs()  # sets comparison.network_df_comparison

        # Run the comparison of the Model.network.graph edges and
        # nodes (built from the dataframes)
        print('Comparing graphs...')
        comparison.compare_graph()  # sets comparison.graph_comparison

        # Cache the updated ModelComparison object to a pickle file (.modcomp)
        print(f'Saving model comparison to {comparison.pickle_path}...')
        comparison.to_pickle()  # cache comparison results to disk.

    if export_format == 'csv':
        # Export comparison results to CSV
        print('Export to CSV ...')
        comparison.to_csv(models_to_csv=False,
                          df_comparison_to_csv=True,
                          graph_comparison_to_csv=True)
        print('CSV folder:', comparison.csv_folder)

    print('ModelComparison cache file:', comparison.pickle_path)

    print(f'Model comparison finished: '
          f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds')


if __name__ == '__main__':
    """
    Run "python compare.py -h" for help.

    For sample use inside of an IDE, run "tests/example_compare.py"
    """

    parser = argparse.ArgumentParser(description='Compare two PSSE RAW or RAWX models.',
                                     add_help=False)
    # make p1 optional
    parser.add_argument('-p1', '--raw1_path', type=str, default='',
                        help='Path to the first RAW or RAWX file')
    parser.add_argument('-p2', '--raw2_path', type=str, help='Path to the second RAW or RAWX file',
                        default='')
    parser.add_argument('-f', '--force_recalculation', action='store_true',
                        help='Force recalculation even if cached results exist')
    parser.add_argument('-e', '--export_format', type=str, choices=['csv', 'none'], default='csv',
                        help='Format to export results')
    parser.add_argument(
        '-b', '--no-bus-info',
        dest='add_bus_info_to_branches',
        action='store_false',
        help='Do NOT add bus information to branch DataFrames'
    )
    parser.add_argument('-a', '--areas', type=str, default='',
                        help='Comma-separated list of area numbers to include (e.g., "101,102,103")')
    parser.add_argument('-h', '--help', action='store_true', help=COMMAND_LINE_HELP_TEXT)

    args = parser.parse_args()

    # If p1 or p2 not provided, prompt user to enter p1 and/or p2.
    if args.raw1_path == '':
        args.raw1_path = input('Enter the path to the first RAW or RAWX file: ').strip()
    if args.raw2_path == '':
        args.raw2_path = input('Enter the path to the second RAW or RAWX file: ').strip()

    # Convert 'none' to None for export_format
    export_format = None if args.export_format.lower() == 'none' else args.export_format

    # Parse the areas argument
    areas = [int(area.strip()) for area in args.areas.sectionalize(',')] if args.areas else []

    main(args.raw1_path,
         args.raw2_path,
         args.force_recalculation,
         export_format,
         args.add_bus_info_to_branches)
