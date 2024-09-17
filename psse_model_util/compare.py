"""
This module provides functionality to compare two PSSE v35 RAWX models.
It uses the Model class from model.py to load and process the models.

The main class, ModelComparison, handles the comparison of two models,
including network differences, path changes, and equipment variations.

Key Features:
1. Efficient comparison of large power system models
2. Detailed analysis of network topology changes
3. Identification of added, removed, and modified equipment
4. Path analysis for changes in network connectivity
5. Export capabilities for comparison results (CSV)

Performance Considerations:
- Uses pandas for efficient data manipulation
- Employs networkx for graph operations
- Implements caching to avoid redundant calculations

Usage:
    from psse_model_util.rawx.compare import ModelComparison
    from psse_model_util.rawx.model import Model

    model1 = Model('path/to/model1.raw')
    model2 = Model('path/to/model2.raw')

    comparison = ModelComparison(model1, model2)
    comparison.compare_network_dfs()
    comparison.compare_graph()
    comparison.to_csv('comparison_results.csv')

Note: This module is designed to handle large power system models efficiently.
"""

import argparse
import sys
from time import perf_counter_ns
import warnings
from pathlib import Path
from collections import namedtuple
import pickle
from typing import Dict, Any, Optional, List
import configparser

import networkx as nx
import numpy as np
import pandas as pd

from psse_model_util.model import Model
from psse_model_util.common import dirs
from psse_model_util.common.constants import INCLUDE_AREAS, \
    ALT_PATH_MAX_PATH_LENGTH, DEFAULT_KV_FILTER, NETWORK_DF_COMPARISON_QUERIES
from psse_model_util.common.file_util import to_pickle
from psse_model_util.common.dirs import site_cache_dir, site_data_dir

# Define named tuples for storing comparison results
FpPickleType = namedtuple('FpPickleType', ['file_path', 'object'])
PathComparison = namedtuple('PathComparison', ['path_splits', 'path_merges',
                                               'added_edges', 'removed_edges',
                                               'added_nodes', 'removed_nodes'])
GraphComparison = namedtuple('GraphComparison', ['path_splits', 'path_merges',
                                                 'added_edges', 'removed_edges',
                                                 'added_nodes', 'removed_nodes'])
ComparisonDF = namedtuple('ComparisonDF', ['changed', 'added', 'removed'])
EdgePathInfo = namedtuple('EdgePathInfo', ['section', 'branch', 'edge_name', 'valid_paths'])
EdgeInfo = namedtuple('EdgeInfo', ['from_bus', 'to_bus', 'equip', 'edge_type', 'edge_name'])

COMMAND_LINE_HELP_TEXT = """
PSSE Model Comparison Tool
--------------------------

This tool compares two PSSE RAW or RAWX models and provides detailed analysis of their differences.

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
    -a, --areas AREAS           : Comma-separated list of area numbers to include (e.g., "101,102,103")

Example:
    python compare.py path/to/model1.rawx path/to/model2.rawx -f -e csv -b -a 101,102,103

This example compares model1.rawx and model2.rawx, forces recalculation, exports results to CSV,
adds bus information to branches, and includes only areas 101, 102, and 103 in the comparison.
"""


class ModelComparison:
    """
    A class to compare two PSSE v35 models (psse_util.model.ModelRawx).

    This class provides methods to compare network dataframes, graph structures,
    and export comparison results.

    Attributes:
        model1 (Model): The first model for comparison.
        model2 (Model): The second model for comparison.
        network_df_comparison (dict): Stores the results of dataframe comparisons.
        graph_comparison (GraphComparison): Stores the results of graph comparisons.
        max_path_length (int): Maximum path length for alternative path search.
        pickle_path (Path): Path to save/load the comparison results.

    Methods:
        compare_network_dfs: Compare network dataframes between the two models.
        compare_graph: Compare graph structures between the two models.
        to_pickle: Save comparison results to a pickle file.
        read_pickle: Load comparison results from a pickle file.
        to_csv: Export comparison results to CSV files.
    """
    def __init__(self, model1: Model = None,
                 model2: Model = None,
                 model_comp_file: Path | str = None,
                 max_path_length: int = ALT_PATH_MAX_PATH_LENGTH):
        """
        Initialize the ModelComparison instance.

        Args:
            model1 (Model, optional): The first model for comparison.
            model2 (Model, optional): The second model for comparison.
            model_comp_file (Path or str, optional): Path to a pre-existing comparison file.
            max_path_length (int): Maximum path length for alternative path search.

        Usage:
            from psse_model_util.rawx.compare import ModelComparison
            from psse_model_util.rawx.model import Model

            model1 = Model('path/to/model1.raw')
            model2 = Model('path/to/model2.raw')

            comparison = ModelComparison(model1, model2)
            comparison.compare_network_dfs()
            comparison.compare_graph()
            comparison.to_csv('comparison_results.csv')

        Raises:
            AssertionError: If neither models nor comparison file is provided.
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
        """
        Find buses that are the same in both models but for which the bus number
        Changed.

        This function performs the following steps:
        1. Inner joins the bus dataframes from model1 and model2 on join_columns,
            (default: ['name', 'area', 'baskv']).
        2. Filters the result to show only records where the bus numbers (ibus)
            differ.
        3. Remembers (caches to memory) the results to self._bus_num_changes.
        4. Returns a DataFrame with values (including bus numbers) from each
            model, with prefixed column names.

        Returns:
            Optional[pd.DataFrame]: A DataFrame containing the bus number changes,
                                    or None if no changes are found.
            Columns are prefixed with 'model1_' or 'model2_' as applicable.

        Performance Considerations:
            - Uses pandas merge for efficient joining of DataFrames.
            - Applies filtering after merging to reduce data processing.
            - Renames columns in a single operation for efficiency.

        Notes:
            - Assumes that 'ibus', 'name', and 'area' columns exist in both bus
                dataframes.
            - The resulting DataFrame will only include buses that exist in both
                models (inner join).
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
        merged_df = pd.merge(
            bus_df1,
            bus_df2,
            on=join_columns,
            suffixes=('_model1', '_model2')
        )

        # Filter to show only records where bus numbers differ
        changes_df = merged_df[merged_df['ibus_model1'] != merged_df['ibus_model2']]

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
        """
        Compare network dataframes between the two models.

        This method compares corresponding dataframes from both models,
        identifying changes, additions, and removals.

        Returns:
            Dict[str, pd.DataFrame]: A dictionary containing comparison results
                                     for each network component.
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

            if np.issubdtype(series1.dtype, np.number):
                return series2 - series1
            else:
                return (series1 != series2).astype(bool)

        result: Dict[str, pd.DataFrame] = {}
        df1_names = [_ for _ in dir(self.model1.network) if isinstance(getattr(self.model1.network, _), pd.DataFrame)]
        df2_names = [_ for _ in dir(self.model2.network) if isinstance(getattr(self.model2.network, _), pd.DataFrame)]

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
            try:
                merged_df = pd.merge(df1, df2, how='outer', left_index=True, right_index=True,
                                     suffixes=('_model1', '_model2'))
            except Exception as e:
                print(f'Could not merge dataframes: {df_name}. Exception: {str(e)}')
                print(f'Model 1 columns:', df1.columns)
                print(f'Model 2 columns:', df2.columns)
                continue

            columns = list(set(df1.columns) | set(df2.columns))
            new_columns: Dict[str, Any] = {}

            # Add "_delta" columns to merged_df
            for column in columns:
                col1, col2 = f'{column}_model1', f'{column}_model2'
                if col1 in merged_df.columns and col2 in merged_df.columns:
                    new_columns[f'{column}_delta'] = _column_delta(merged_df[col1], merged_df[col2])

            # Add an indicator column to show which model(s) each row is present in.
            indicator_col1 = f'{columns[0]}_model1' if f'{columns[0]}_model1' in merged_df.columns else \
            merged_df.columns[0]
            indicator_col2 = f'{columns[0]}_model2' if f'{columns[0]}_model2' in merged_df.columns else \
            merged_df.columns[-1]

            new_columns['presence'] = np.select(
                [merged_df[indicator_col1].notna() & merged_df[indicator_col2].notna(),
                 merged_df[indicator_col1].notna(),
                 merged_df[indicator_col2].notna()],
                ['both', 'model1_only', 'model2_only'],
                default='neither'
            )

            # Add all new columns at once
            try:
                new_columns_df = pd.DataFrame(new_columns, index=merged_df.index)
                merged_df = pd.concat([merged_df, new_columns_df], axis=1)
            except ValueError as e:
                print(f"Error adding new columns to merged DataFrame for {df_name}. Exception: {str(e)}.")
                print(f"merged_df shape: {merged_df.shape}, new_columns shape: {new_columns_df.shape}")
                print(f"merged_df index: {merged_df.index}")
                print(f"new_columns_df index: {new_columns_df.index}")

                # Attempt to add columns individually
                for col, values in new_columns.items():
                    try:
                        merged_df[col] = values
                    except Exception as col_e:
                        print(f"Failed to add column {col}. Error: {str(col_e)}")

            result[df_name] = merged_df

        # Add bus number changes to the result
        result['bus_num_changes'] = self.bus_num_changes()

        self.network_df_comparison = result
        return self.network_df_comparison
    def compare_graph(self, max_path_length: int = None, sort: bool = True, regenerate=False) -> dict:
        """
        Compare graph structures between the two models.

        This method identifies changes in network topology, including added and
        removed edges and nodes, as well as path splits and merges.

        Args:
            max_path_length (int, optional): Maximum path length for alternative path search.
            sort (bool): Whether to sort the alternative paths by length.
            regenerate (bool): Whether to regenerate the graphs before comparison.

        Returns:
            dict: A dictionary containing graph comparison results.

        Example:
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

        def _find_alt_paths(split_edges, g1: nx.Graph = None, g2: nx.Graph = None,
                            max_path_length=max_path_length,
                            sort=sort, as_dataframe: bool = True) -> pd.DataFrame:
            """Find alternative paths in g2 for edges in g1 that are not in g2."""
            max_path_length = max_path_length or self.max_path_length

            splits_dict = {}
            for idx, edge in enumerate(split_edges):
                if not idx % 1000:
                    print(f'    alt paths: evaluating {idx} of {len(split_edges) + 1} paths')
                node_a, node_b, *_ = edge
                if node_a not in g2.nodes or node_b not in g2.nodes:
                    continue

                try:
                    edge = g1.edges[node_a, node_b]
                except KeyError as e:
                    # TODO: Add logging
                    continue

                # branch = '-'.join([node_a[0], node_b[0]])
                section = edge['section'] if 'section' in edge else ''

                paths = nx.all_simple_paths(g2, node_a, node_b, cutoff=max_path_length)
                valid_paths = [path for path in paths if all(node not in g1.nodes for node in path[1:-1])]

                if valid_paths:
                    if sort:
                        valid_paths.sort(key=len)
                    edge['type'] = section
                    splits_dict[(node_a, node_b)] = valid_paths

            # Update splits_dict to keep only the shortest paths for each edge
            for edge, paths in splits_dict.items():
                shortest_length = min(len(path) for path in paths)
                splits_dict[edge] = [path for path in paths if len(path) == shortest_length]

            if as_dataframe:
                # Convert splits_dict to DataFrame
                df = pd.DataFrame(list(splits_dict.items()), columns=['path', 'alt_paths'])
                return df

            return splits_dict

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

        print('Finding path splits...')
        df = _find_alt_paths(result['removed_edges'], g1=graph1, g2=graph2)
        df.columns = [self.model1.name, self.model2.name]
        result['path_splits'] = df
        print('Finding path merges...')
        df = _find_alt_paths(result['added_edges'], g1=graph2, g2=graph1)
        df.columns = [self.model2.name, self.model1.name]
        result['path_merges'] = df[[self.model1.name, self.model2.name]]

        self.graph_comparison = result
        return self.graph_comparison

    @property
    def pickle_path(self) -> Path:
        """
        Get or set the pickle file path for the model comparison.

        Returns:
            Path: The path to the pickle file.

        Example:
            comparison = ModelComparison(model1, model2)
            print(comparison.pickle_path)
            comparison.pickle_path = Path('/new/path/to/comparison.pickle')
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
        """
        Cache the ModelComparison to a pickle file.

        Args:
            resilient (bool): If True, return False if pickling fails instead of raising an exception

        Returns:
            bool: True if caching was successful, False otherwise

        Example:
            comparison = ModelComparison(model1, model2)
            success = comparison.to_pickle()
            if success:
                print("Comparison saved successfully")
        """
        to_pickle(pickle_path=self.pickle_path, data=self, resilient=resilient)
        print('Saved: ', self.pickle_path)
        return self.pickle_path

    def read_pickle(self, pickle_path: Path | str = None,
                    mode: str = 'rb', resilient: bool = True) -> FpPickleType:
        """
        Read the ModelComparison from a pickle file.

        Args:
            pickle_path (Path or str, optional): Path to the pickle file.
            mode (str): File open mode, should always be 'rb'.
            resilient (bool): If True, warn instead of raising an exception on failure.

        Returns:
            FpPickleType: A named tuple containing the file path and loaded object.

        Raises:
            FileNotFoundError: If the pickle file is not found and resilient is False.

        Example:
            comparison = ModelComparison()
            loaded_data = comparison.read_pickle('path/to/comparison.pickle')
            if loaded_data.object:
                print(f"Loaded comparison from {loaded_data.file_path}")
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
        """
        Get the folder path for CSV exports.

        Returns:
            Path: The path to the folder where CSV files will be exported.

        Example:
            comparison = ModelComparison(model1, model2)
            csv_path = comparison.csv_folder()
            print(f"CSV files will be exported to: {csv_path}")
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
        """
        Export comparison results to CSV files.

        Args:
            models_to_csv (bool): Whether to export individual model data to CSV.
            df_comparison_to_csv (bool): Whether to export dataframe comparison data to CSV.
            graph_comparison_to_csv (bool): Whether to export graph comparison data to CSV.

        Example:
            comparison = ModelComparison(model1, model2)
            comparison.to_csv(df_comparison_to_csv=True, graph_comparison_to_csv=True)
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
        """Helper method to write a DataFrame to CSV.  Prevents hard exception."""
        # Assuming df is your DataFrame
        index = True if df.index.name is not None else False
        try:
            df.to_csv(csv_path, index=index)
        except PermissionError as e:
            warnings.warn(f'Unable to write general information to {csv_path}.  {str(e)}')

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
            sheet_name = f'compare_{section}'
            csv_path = self.csv_folder / f'network_{section}.csv'
            if isinstance(df, pd.DataFrame):
                if df.empty:
                    warnings.warn("Dataframe is empty: " + section)
                self._write_csv(csv_path, df)
            else:
                warnings.warn("Dataframe not found: " + section)

    def flatten_and_stringify(self, item):
        """Helper method to flatten and stringify complex data structures."""
        if isinstance(item, (list, tuple)):
            result = ', '.join(self.flatten_and_stringify(i) for i in item)
        result = str(item)
        return "[" + result + "]"

    def process_graph_data(self, data):
        """Process graph comparison data for CSV export.
        Used by _graph_comparison_to_csv"""
        processed_data = {}
        for key, value in data.items():
            key_str = self.flatten_and_stringify(key)
            value_str = self.flatten_and_stringify(value)
            processed_data[key_str] = value_str
        processed_data = {k[1:-1]: v[2:-2] for k, v in processed_data.items()}
        return processed_data

    def _graph_comparison_to_csv(self):
        """Export path splits and merges to CSV."""
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
        """
        Identify buses meeting specific voltage criteria for generators and loads.

        Returns:
            List[int]: List of bus_id values meeting the criteria.

        Example:
            >>> model_comp = ModelComparison(model1, model2)
            >>> filtered_buses = model_comp.bus_kv_filter()
            >>> print(len(filtered_buses))
            1000
        """
        bus_df = self.network_df_comparison['bus']
        gen_df = self.network_df_comparison['generator']
        load_df = self.network_df_comparison['load']

        # Extract 'ibus' from multi-index
        gen_buses = gen_df.index.get_level_values('ibus') if 'ibus' in gen_df.index.names else pd.Series()
        load_buses = load_df.index.get_level_values('ibus') if 'ibus' in load_df.index.names else pd.Series()

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
                                    queries: dict = NETWORK_DF_COMPARISON_QUERIES) -> Dict[str, pd.DataFrame]:
        """
        Filter and return network dataframes based on voltage criteria.

        Args:
            inplace (bool): If True, update the network_df_comparison with the filtered dataframes. Defaults to True.

        Returns:
            Dict[str, pd.DataFrame]: Dictionary of filtered dataframes.

        Example:
            >>> model_comp = ModelComparison(model1, model2)
            >>> filtered_dfs = model_comp.query_network_df_comparison()
            >>> print(filtered_dfs.keys())
            dict_keys(['bus', 'generator', 'load', 'branch'])
        """
        # network_df_comparison
        filtered_bus_ids = self.bus_kv_filter()

        dfs_to_filter = {k: self.network_df_comparison[k] for k in NETWORK_DF_COMPARISON_QUERIES.keys()}
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
    """
    Main function to compare two PSSE RAW or RAWX models.

    This function loads two models, filters them by area, optionally adds bus information
    to branches, performs a comparison, and exports the results.

    Args:
        raw1_path (Path | str): Path to the first RAW or RAWX file.
        raw2_path (Path | str): Path to the second RAW or RAWX file.
        force_recalculation (bool): If True, forces recalculation even if cached results exist.
        export_format (str | None): Format to export results. Use 'csv' for CSV export or None for no export.
        add_bus_info_to_branches (bool): If True, adds bus information to branch DataFrames.
        include_areas (str): Comma-separated list of area numbers to include in the comparison.

    Returns:
        None

    Example:
        >>> main("path/to/model1.rawx", "path/to/model2.rawx", force_recalculation=True, export_format='csv', areas=[101, 102, 103])

    """
    if areas is None:
        areas = []
    start_time = perf_counter_ns()
    print(f'Starting model comparison...')

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

        # Filter the models to a subset of areas (PJM + 1st tier)
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
        comparison.compare_network_dfs()

        # Run the comparison of the Model.network.graph edges and
        # nodes (built from the dataframes)
        print('Comparing graphs...')
        comparison.compare_graph()

        # Cache the updated ModelComparison object to a pickle file (.modcomp)
        print(f'Saving model comparison to {comparison.pickle_path}...')
        comparison.to_pickle()

    if export_format == 'csv':
        # Export comparison results to CSV
        print(f'Export to CSV ...')
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
    # if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help', '?']:
    #     print_comand_line_help()
    #     sys.exit(0)

    parser = argparse.ArgumentParser(description='Compare two PSSE RAW or RAWX models.', add_help=False)
    parser.add_argument('raw1_path', metavar='p1', type=str, help='Path to the first RAW or RAWX file')
    parser.add_argument('raw2_path', metavar='p2', type=str, help='Path to the second RAW or RAWX file')
    parser.add_argument('-f', '--force_recalculation', action='store_true', help='Force recalculation even if cached results exist')
    parser.add_argument('-e', '--export_format', type=str, choices=['csv', 'none'], default='csv', help='Format to export results')
    parser.add_argument('-b', '--add_bus_info_to_branches', action='store_true', help='Add bus information to branch DataFrames')
    parser.add_argument('-a', '--areas', type=str, default='', help='Comma-separated list of area numbers to include (e.g., "101,102,103")')
    parser.add_argument('-h', '--help', action='store_true', help=COMMAND_LINE_HELP_TEXT)

    args = parser.parse_args()

    # Convert 'none' to None for export_format
    export_format = None if args.export_format.lower() == 'none' else args.export_format

    # Parse the areas argument
    areas = [int(area.strip()) for area in args.areas.split(',')] if args.areas else []

    main(args.raw1_path,
         args.raw2_path,
         args.force_recalculation,
         export_format,
         args.add_bus_info_to_branches)

