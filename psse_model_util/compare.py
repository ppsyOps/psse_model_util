import warnings
from pathlib import Path
import time
from collections import namedtuple
from time import perf_counter
import pickle

import networkx
import pandas as pd

# Example data structure

from psse_model_util.model import Model, Equipment, get_bus_info
from psse_model_util.common import dirs
from psse_model_util.common.dataframe_util import df_to_excel_worksheet
from psse_model_util.constants import BUS_TYPES, NATIVE_AREAS, DEFAULT_KV_FILTER, RangeFilterType, RESILIENT
from psse_model_util.common.pyqt5 import file_browser
from psse_model_util.common.file_util import is_file_locked, to_pickle, read_pickle
# from psse_model_util import dataformat34

import networkx as nx

# Define default paths and filenames for data storage and reports
DATA_FOLDER = dirs.site_data_dir
DEFAULT_DIRECTORY = DATA_FOLDER

# Named tuples for path comparison and edge information storage
PathComparison = namedtuple('PathComparison', ['path_splits', 'path_merges',
                                               'added_edges', 'removed_edges',
                                               'added_nodes', 'removed_nodes'])
ComparisonDF = namedtuple('ComparisonDF', ['changed', 'added', 'removed'])
EdgePathInfo = namedtuple('EdgePathInfo', ['equip', 'edge_type', 'edge_name', 'valid_paths'])
EdgeInfo = namedtuple('EdgeInfo', ['from_bus', 'to_bus', 'equip', 'edge_type', 'edge_name'])


# class Connection:
#     """
#     Represents a connection between two buses in an electrical network, containing
#     equipment and bus information for a specific edge in a NetworkX graph.
#
#     :param model: The PSSE model object this connection belongs to.
#     :param from_bus_id: The ID of the starting bus.
#     :param to_bus_id: The ID of the ending bus.
#     :param equip_type: The type of equipment this connection represents, if known.
#     """
#
#     def __init__(self, model: Model, from_bus_id: int, to_bus_id: int, equip_type: str = None):
#         self._model: Model = model
#         self.from_bus_id: int = from_bus_id
#         self.to_bus_id: int = to_bus_id
#         self._from_bus: dict = dict()  # dictionary containing details of the "from" bus.
#         self._to_bus: dict = dict()  # dictionary containing details of the "to" bus.
#         self._type: str = equip_type
#         self._equipment: Equipment = self.equipment
#
#     @property
#     def type(self) -> str:
#         if self._type:
#             return self._type
#
#         # Logic to infer the equipment type based on available data in the model
#         model, i, j = self._model, self.from_bus_id, self.to_bus_id
#         t: str = ''
#         for t, df in (('branch', model.branch_df),
#                       ('facts_device', model.facts_device_df),
#                       ('multi_section_line', model.multi_section_line_df),
#                       ('system_switching_device', model.system_switching_device_df)):
#             df = df[(df['I'].isin(i, j)) & (df['J'].isin(i, j))].copy()
#             if not df.empty:
#                 self._type = t
#                 return self._type
#
#         # vsc_dc_line_df bus name are slightly different.
#         df = model.vsc_dc_line_df[(model.vsc_dc_line_df['IBUS'].isin(i, j)) &
#                                   (model.vsc_dc_line_df['JBUS'].isin(i, j))].copy()
#         if not df.empty:
#             self._type = 'vsc_dc_line'
#             return self._type
#
#         # Transformers have 3 buses, I, J and K, so slightly different logic is needed.
#         xdf = model.transformer_df
#         df = xdf[(xdf['I'].isin(i, j)) & (xdf['J'].isin(i, j))].copy()
#         if df.empty:
#             df = xdf[(xdf['J'].isin(i, j)) & (xdf['K'].isin(i, j))].copy()
#         if df.empty:
#             df = xdf[(xdf['K'].isin(i, j)) & (xdf['I'].isin(i, j))].copy()
#         if not df.empty:
#             self._type = 'transformer'
#             return self._type
#
#         raise NotImplementedError(f'Unable to determine Connection equipment type '
#                                   f'for {i}-{j}')
#
#     @property
#     def equipment(self) -> Equipment:
#         """Lazily loads and returns the Equipment object associated with this
#         connection; derived from self._model, self._equipment type,
#         self.from_bus_id and self.to_bus_id.
#
#
#         :return: An Equipment object populated with the connection's equipment details.
#         """
#         if self._equipment:
#             return self._equipment
#
#         model, i, j = self._model, self.from_bus_id, self.to_bus_id
#         bus_df = model.bus_df
#
#         # If self._type is not known, figure it out.
#         self._type = self._type or self.type
#
#         # Get equipment info from one of the model.*_df DataFrames.
#         match self._type:
#             case 'branch' | 'facts_device' | 'multi_section_line' | 'system_switching_device':
#                 match self._type:
#                     case 'branch':
#                         df = model.branch_df
#                     case 'facts_device':
#                         df = model.branch_df
#                     case 'multi_section_line':
#                         df = model.branch_df
#                     case 'system_switching_device':
#                         df = model.branch_df
#                 df = df[(df['I'].isin(i, j)) & (df['J'].isin(i, j))].copy()
#             case 'vsc_dc_line':
#                 # Correct operation for filtering where 'abc' column equals 20
#                 df = model.vsc_dc_line_df[(model.vsc_dc_line_df['IBUS'].isin(i, j)) &
#                                           (model.vsc_dc_line_df['JBUS'].isin(i, j))].copy()
#             case 'transformer':
#                 # Correct operation for filtering where 'abc' column equals 20
#                 xdf = model.transformer_df
#                 df = xdf[(xdf['I'].isin(i, j)) & (xdf['J'].isin(i, j))].copy()
#                 if df.empty:
#                     df = xdf[(xdf['I'].isin(i, j)) & (xdf['J'].isin(i, j))].copy()
#                 if df.empty:
#                     df = xdf[(xdf['I'].isin(i, j)) & (xdf['J'].isin(i, j))].copy()
#                 if df.empty:
#                     raise IndexError(f'{i}-{j} not found in model.transformer_df')
#             case _:
#                 raise NotImplementedError(f'equipment is not implemented for type {self._type}')
#         props_in = df.iloc[0].to_dict()
#         self._equipment = Equipment(equip_type=self._type, props_in=props_in)
#         return self._equipment
#
#     @property
#     def from_bus(self):
#         """
#         Lazily loads and returns the dictionary containing information about the "from" bus
#         of this connection.
#
#         :return: A dictionary containing details of the "from" bus.
#         """
#         self._from_bus = self._from_bus or self._model.get_bus(self.from_bus_id)
#         return self._from_bus
#
#     @property
#     def to_bus(self):
#         """
#         Lazily loads and returns the dictionary containing information about the "to" bus
#         of this connection.
#
#         :return: A dictionary containing details of the "to" bus.
#         """
#         self._to_bus = self._to_bus or self._model.get_bus(self.to_bus_id)
#         return self._to_bus
#
#
# def get_connection_info(model: Model, from_bus_id: int, to_bus_id: int,
#                         equip_type: str = None) -> Connection:
#     return Connection(model=model, from_bus_id=from_bus_id,
#                       to_bus_id=to_bus_id, equip_type=equip_type)
#
#
# def get_bus_info(bus_id: int, model_or_bus_df: Model | pd.DataFrame,
#                  resilient: bool = RESILIENT) -> dict:
#     """
#     Gets
#     :param bus_id: Bus number
#     :param resilient: if True, return empty dict if bus not found, else raise
#                 exception if bus not found.
#     :return: dict of bus information from model.bus_df
#     """
#     if isinstance(model_or_bus_df, Model):
#         return model_or_bus_df.get_bus(bus_id)
#     elif isinstance(model_or_bus_df, pd.DataFrame):
#         return model_or_bus_df[model_or_bus_df['I'] == bus_id].to_dict('records')[0]
#     else:
#         if resilient:
#             return dict()
#         else:
#             raise TypeError(f"Expected model_or_bus_df to be of type Model or "
#                             f"pd.DataFrame, not {type(model_or_bus_df)}")


class ModelComparison:
    def __init__(self, model1: Model | Path | str,
                 model2: Model | Path | str,
                 report_dir: str | Path = None,
                 cache_dir: Path | str = None,
                 kv_range: tuple[int | float] = DEFAULT_KV_FILTER,
                 areas: dict[int, str] = NATIVE_AREAS,
                 force_recalculation: bool = False,
                 max_path_length: int = 4,
                 ):
        self.timer = []
        self.print_time(step_name='Starting ModelComparison')

        # If we have this ModelComparison object cached to disk, read it from
        # disk to save time.
        self.cache_dir = Path(cache_dir or model1.pickle_path.parent)
        if isinstance(model1, Model):
            self.pickle_path = cache_dir / f'{model1.file_path.stem}_{model2.file_path.stem}.modcomp'
        else:  # elif isinstance(model1, (Path, str)):
            stem1 = Path(model1).stem
            stem2 = Path(model2).stem
            self.pickle_path = cache_dir / f'{stem1}_{stem2}.modcomp'

        self.kv_range: tuple[int | float] = kv_range
        self.areas: dict[int, str] = areas

        if self.pickle_path.exists() and not force_recalculation:
            # Attempt to read ModelComparison cached data from disk.
            try:
                self.read_pickle()
            except Exception as e:
                warnings.warn(f'Unable to read ModelComparison cache.')
        else:
            # Load model 1
            self.print_time(step_name='Loading model 1...')
            if not isinstance(model1, Model):
                self.model1: Model = Model(file_path=model1,
                                           force_recalculation=force_recalculation)
            else:
                self.model1: Model = model1
            if self.kv_range or self.areas:
                self.model1.filter_model(kv_range=self.kv_range, areas=self.areas)
            self.print_time(step_name='Finished loading model 1.')

            # Load model 2
            self.print_time(step_name='Loading model 1...')
            if not isinstance(model2, Model):
                self.model2: Model = Model(file_path=model2,
                                           force_recalculation=force_recalculation)
            else:
                self.model2: Model = model2
            if self.kv_range or self.areas:
                self.model2.filter_model(kv_range=self.kv_range, areas=self.areas)
            self.print_time(step_name='Finished loading model 2.')

            # File paths for cache and reports.
            self.report_dir = Path(report_dir or dirs.site_data_dir)
            self.report_path = report_dir / f'{self.model1.file_path.stem}_{self.model2.file_path.stem}.xlsx'
            self.model1_report_path: Path | str | None = report_dir / f'{self.model1.file_path.stem}.xlsx'
            self.model2_report_path: Path | str | None = report_dir / f'{self.model2.file_path.stem}.xlsx'

            # Results of model comparisons are saved to these variables:
            self._path_comparison: PathComparison = \
                PathComparison(None, None, None, None, None, None)
            self._equip_comparison = {}

            # Assign __init__ arguments to class attributes.
            self.force_recalculation: bool = force_recalculation
            self.max_path_length: int = max_path_length

        if any(kv_range) or areas:
            if not self.model1.filtered and not self.model2.filtered:
                self.filter_models()

    def mark_time(self, step_name: str):
        self.timer.append([step_name, perf_counter()])

    def print_time(self, step_name: str):
        self.timer.append([step_name, perf_counter()])
        if len(self.timer) > 1:
            step = round(self.timer[-1][-1] - self.timer[-2][-1], 2)
            elapsed = round(self.timer[-1][-1] - self.timer[0][-1], 2)
            print(f'{step_name}: step: {step}, elapsed: {elapsed}')
        else:
            print(step_name)

    # def to_pickle(self):
    #     self.mark_time(step_name='Pickling ModelComparison...')
    #     to_pickle(pickle_path=self.file_path, data=self)
    #     self.print_time(step_name='Finished pickling ModelComparison.')

    def to_pickle(self, resilient: bool = RESILIENT) -> bool:
        """
        Cache the parsed model data (dict[dict]) to a pickle file, so it can be
        loaded in future runs without the need to parse the raw file.
        :param resilient: If True, return False if loading pickle fails.
                          If False, raise error if loading pickle fails.
        :return: True is data was read
        """
        self.mark_time(step_name='Pickling ModelComparison...')
        self.pickle_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.pickle_path, 'wb') as file:
                pickle.dump(self, file)
                print(f'Cached ModelComparison to disk as "{self.pickle_path}".')
                return True
        except Exception as e:
            if resilient:
                warnings.warn(f'Unable to cache Model to disk as '
                              f'"{self.pickle_path}".  {str(e)}')
                return False
            else:
                raise e
        self.print_time(step_name='Finished pickling ModelComparison.')

    def read_pickle(self, mode: str = 'rb', resilient: bool = RESILIENT):
        """
        Read the model from a pickle file.
        :param mode: Should always be 'rb'.
        :return: FpPickleType(pickle_path, obj), where obj is the
                    unpickled object.
        """
        self.mark_time(step_name='Reading ModelComparison Pickle...')
        temp = self.timer
        if not self.pickle_path.exists():
            # Pickle file not found.  Return (None, None).
            if resilient:
                self.mark_time(step_name='Failed reading ModelComparison Pickle.')
                return
            else:
                raise FileNotFoundError(f'Could not find file \
                {str(self.file_path)}')
        obj = None
        try:
            with open(self.pickle_path, mode) as file:
                obj = pickle.load(file)
            attr_names = [attr for attr in dir(obj)
                          if not attr.startswith('__')]
            for attr_name in attr_names:
                try:
                    setattr(self, attr_name, getattr(obj, attr_name))
                except Exception as e:
                    warnings.warn(f'Unable to load attribute "{attr_name}" '
                                  f'from cache. {str(e)}')
            print(f'Data loaded from cache: "{self.pickle_path}".')
        except Exception as e:
            if resilient:
                warnings.warn(f'Could not load file '
                              f'{str(self.pickle_path)}. {str(e)}')
            else:
                raise e
        self.timer = temp
        self.mark_time(step_name='Finished reading ModelComparison Pickle.')

    def compare_paths(self, max_path_length=4, sort: bool = False) -> PathComparison:
        if any(self._path_comparison) and not force_recalculation:
            return self._path_comparison
        """
        For any removed edges (pair of nodes) in source_graph that are not in
        target_graph, find an alternative path in target_graph that contains at
        least one new node (i.e., a node in target_graph that is not in
        source_graph).

        :param max_path_length: The longest path length to consider as an
                    alternative path.
        :param sort: (bool) Whether to sort the resulting paths by length.
        :return: List of alternative paths.
        """
        self.print_time('Finding path changes between models...')
        graph1 = self.model1.network_graph()
        graph2 = self.model2.network_graph()

        print(f'Comparing path changes from {self.model1.file_path.stem} '
              f'to {self.model2.file_path.stem}.')
        # Find edges in the source graph not in the target graph
        removed_edges = [(u, v, graph1.edges[u, v]['equip'].type,
                          graph1.edges[u, v]['equip']) for u, v in
                         graph1.edges if not graph2.has_edge(u, v)]
        # Find nodes in the target graph not in the source graph
        removed_nodes = set(graph1.nodes) - set(graph2.nodes)
        added_edges = [(u, v, graph2.edges[u, v]['equip'].type,
                        graph2.edges[u, v]['equip']) for u, v in
                       graph2.edges if not graph1.has_edge(u, v)]
        # Find nodes in the target graph not in the source graph
        added_nodes = set(graph2.nodes) - set(graph1.nodes)

        def find_splits(g1, g2, split_edges) -> dict[tuple, EdgePathInfo]:
            splits_dict = dict()
            for edge in split_edges:
                node_a, node_b, *_ = edge
                equip = g1.edges[(node_a, node_b)]['equip']
                edge_type = g1.edges[(node_a, node_b)]['equip'].type
                edge_name = g1.edges[(node_a, node_b)]['equip'].name

                # If either a or b node of the split edge is not in g2, skip it.
                if node_a not in g2.nodes or node_b not in g2.nodes:
                    continue

                # Find all simple paths between node_a and node_b in the g2 graph,
                # with a maximum length.
                paths = nx.all_simple_paths(g2, node_a, node_b,
                                            cutoff=max_path_length)

                # Filter paths to include only those where all intermediate nodes
                # are not in the g1 graph.
                valid_paths = [path for path in paths
                               if all(node not in g1.nodes
                                      for node in path[1:-1])]

                if valid_paths:
                    splits_dict[edge] = EdgePathInfo(equip, edge_type,
                                                     edge_name, valid_paths)
                if sort:
                    # Optionally, sort paths by length to get the shortest first
                    valid_paths.sort(key=len)
            return splits_dict

        path_splits: dict = find_splits(graph1, graph2, removed_edges)
        path_merges: dict = find_splits(graph2, graph1, added_edges)

        # Add 'from' and 'to' bus names to edge names.
        for edge, edge_info in path_splits.items():
            # Lookup the bus names from model1.buses_df to build a pseudonym
            edge_name = edge_info.edge_name.strip()
            # Get from_bus and to_bus names and kVs.
            temp = (f'{self.model1.get_bus_name_kv(edge[0]).strip()} '
                    f'- {self.model1.get_bus_name_kv(edge[1]).strip()}')
            # Append from_bus and to_bus names and kVs to edge_name.
            if len(temp) > 3:
                edge_name += f': [{temp}]'.strip(': ')
            path_splits[edge] = EdgePathInfo(edge_info.equip,
                                             edge_info.equip.type, edge_name,
                                             edge_info.valid_paths)
        for edge, edge_info in path_merges.items():
            edge_name = edge_info.edge_name.strip()
            # edge_name = self.model1.get_extended_name(equip_name=edge_info.edge_name,
            #                                           bus_nums=[edge[0], edge[1]],
            #                                           suffix='')
            # Get from_bus and to_bus names and kVs.
            temp = (f'{self.model1.get_bus_name_kv(edge[0]).strip()} '
                    f'- {self.model1.get_bus_name_kv(edge[1]).strip()}')
            # Append from_bus and to_bus names and kVs to edge_name.
            if len(temp) > 3:
                edge_name += f': [{temp}]'.strip(': ')
            path_merges[edge] = EdgePathInfo(edge_info.equip,
                                             edge_info.equip.type, edge_name,
                                             edge_info.valid_paths)

        self._path_comparison = PathComparison(path_splits, path_merges,
                                               added_edges, removed_edges,
                                               added_nodes, removed_nodes)

        self.print_time('Finished finding path changes between models.')
        self.print_time('Pickling ModelComparison...')
        self.to_pickle()
        self.print_time('Finished pickling ModelComparison...')

        return self._path_comparison

    @staticmethod
    def _delta(column1, column2):
        """
        Find the difference between two columns. If "-" operation cannot be
        used: if values are equal, return None, else return value from column2.
        :param column1: Pandas Series or DataFrame column
        :param column2: Pandas Series or DataFrame column
        :return: Pandas Series representing the difference between the columns
        """
        # Check if both inputs are pandas Series or DataFrames
        if not isinstance(column1, (pd.Series, pd.DataFrame)) \
                or not isinstance(column2, (pd.Series, pd.DataFrame)):
            raise ValueError("Inputs must be Pandas Series or DataFrames")

        # Initialize result series
        result = pd.Series(index=column1.index)

        # Handle case where both inputs are DataFrames
        if isinstance(column1, pd.DataFrame) \
                and isinstance(column2, pd.DataFrame):
            for col in column1.columns:
                if col in column2.columns:
                    result[col] = column2[col] - column1[col]
                else:
                    result[col] = None
        else:
            # Handle case where both inputs are Series
            try:
                result = column2 - column1
            except TypeError:
                # If "-" operation cannot be used, compare values
                result = column2 != column1

        return result

    def compare_equip(self, equip_type: str,
                      columns: list | None = None) -> pd.DataFrame:
        """
        Compare the model1 and model2 dataframes for this specified equip_type.
        :param columns: Which Model.generator_df.columns to compare.  Default
                        is all columns.
        :return:
        """
        self.print_time(f'Comparing {equip_type} changes....')

        df_merge = pd.DataFrame()
        # If columns not provided, compare all columns.
        match equip_type:
            case 'generator':
                df1 = self.model1.generator_df
                df2 = self.model2.generator_df
            case 'branch':
                df1 = self.model1.branch_df
                df2 = self.model2.branch_df
            case 'bus':
                df1 = self.model1.bus_df
                df2 = self.model2.bus_df
            case 'facts_device':
                df1 = self.model1.facts_device_df
                df2 = self.model2.facts_device_df
            case 'fixed_shunt':
                df1 = self.model1.fixed_shunt_df
                df2 = self.model2.fixed_shunt_df
            case 'generator':
                df1 = self.model1.generator_df
                df2 = self.model2.generator_df
            case 'induction_machine':
                df1 = self.model1.induction_machine_df
                df2 = self.model2.induction_machine_df
            case 'inter_area_transfer':
                df1 = self.model1.inter_area_transfer_df
                df2 = self.model2.inter_area_transfer_df
            case 'load':
                df1 = self.model1.load_df
                df2 = self.model2.load_df
            case 'multi_section_line':
                df1 = self.model1.multi_section_line_df
                df2 = self.model2.multi_section_line_df
            case 'owner':
                df1 = self.model1.owner_df
                df2 = self.model2.owner_df
            case 'switched_shunt':
                df1 = self.model1.switched_shunt_df
                df2 = self.model2.switched_shunt_df
            case 'system_switching_device':
                df1 = self.model1.system_switching_device_df
                df2 = self.model2.system_switching_device_df
            case 'transformer':
                df1 = self.model1.transformer_df
                df2 = self.model2.transformer_df
            case 'two_terminal_dc':
                df1 = self.model1.two_terminal_dc_df
                df2 = self.model2.two_terminal_dc_df
            case 'vsc_dc_line':
                df1 = self.model1.vsc_dc_line_df
                df2 = self.model2.vsc_dc_line_df
            case 'zone':
                df1 = self.model1.zone_df
                df2 = self.model2.zone_df
            case _:
                raise ValueError(f'equip_type "{equip_type}" not recognized')
        if not columns:
            columns = df1.columns.to_list()

        if equip_type == 'bus':
            df_merge = pd.merge(left=df1, right=df2, on=['I'], how='outer',
                                suffixes=('_model1', '_model2'), indicator=True)
            df_merge = df_merge.copy()
            for column in columns:
                if column not in ['I']:
                    new_col = f'{column}_delta'
                    col1, col2 = f'{column}_model1', f'{column}_model2'
                    df_merge[new_col] = self._delta(df_merge[col1], df_merge[col2])
        elif equip_type == 'transformer' or ('I' in df1.columns and 'J'
                                             in df1.columns
                                             and 'K' in df1.columns
                                             and 'CKT' in df1.columns):
            df_merge = pd.merge(left=df1, right=df2, on=['I', 'J', 'K', 'CKT'], how='outer',
                                suffixes=('_model1', '_model2'), indicator=True)
            df_merge = df_merge.copy()
            for column in columns:
                if column not in ['I', 'J', 'K', 'CKT']:
                    new_col = f'{column}_delta'
                    col1, col2 = f'{column}_model1', f'{column}_model2'
                    df_merge[new_col] = self._delta(df_merge[col1], df_merge[col2])
        elif equip_type == 'multi_section_line' or (
                'I' in df1.columns and 'J' in df1.columns and ""'ID'"" in df1.columns):
            df_merge = pd.merge(left=df1, right=df2, on=['I', "'ID'"], how='outer',
                                suffixes=('_model1', '_model2'), indicator=True)
            df_merge = df_merge.copy()
            for column in columns:
                if column not in ['I', "'ID'"]:
                    new_col = f'{column}_delta'
                    col1, col2 = f'{column}_model1', f'{column}_model2'
                    df_merge[new_col] = self._delta(df_merge[col1], df_merge[col2])
        elif equip_type == 'branch' or ('I' in df1.columns
                                        and 'J' in df1.columns
                                        and 'CKT' in df1.columns):
            df_merge = pd.merge(left=df1, right=df2, on=['I', 'J', 'CKT'], how='outer',
                                suffixes=('_model1', '_model2'), indicator=True)
            df_merge = df_merge.copy()
            for column in columns:
                if column not in ['I', 'J', 'CKT']:
                    new_col, col1, col2 = f'{column}_delta', f'{column}_model1', f'{column}_model2'
                    df_merge[new_col] = self._delta(df_merge[col1], df_merge[col2])
            pass
        elif 'I' in df1.columns and 'J' in df1.columns:
            df_merge = pd.merge(left=df1, right=df2, on=['I', 'J'], how='outer',
                                suffixes=('_model1', '_model2'), indicator=True)
            df_merge = df_merge.copy()
            for column in columns:
                if column not in ['I', 'J']:
                    new_col, col1, col2 = f'{column}_delta', f'{column}_model1', f'{column}_model2'
                    df_merge[new_col] = self._delta(df_merge[col1], df_merge[col2])
        elif 'I' in df1.columns and 'ID' in df1.columns:
            df_merge = pd.merge(left=df1, right=df2, on=['I', 'ID'], how='outer',
                                suffixes=('_model1', '_model2'), indicator=True)
            df_merge = df_merge.copy()
            for column in columns:
                if column not in ['I', 'ID']:
                    new_col, col1, col2 = f'{column}_delta', f'{column}_model1', f'{column}_model2'
                    df_merge[new_col] = self._delta(df_merge[col1], df_merge[col2])
        elif equip_type in ['bus', 'area', 'impedance_correction']:
            df_merge = pd.merge(left=df1, right=df2, on=['I'], how='outer',
                                suffixes=('_model1', '_model2'), indicator=True)
            df_merge = df_merge.copy()
            for column in columns:
                if column not in ['I']:
                    new_col, col1, col2 = f'{column}_delta', f'{column}_model1', f'{column}_model2'
                    df_merge[new_col] = self._delta(df_merge[col1], df_merge[col2])
        elif equip_type == 'inter_area_transfer' or ('ARFROM' in df1.columns
                                                     and 'ARTO' in df1.columns):
            df_merge = pd.merge(left=df1, right=df2, on=['ARFROM', 'ARTO'], how='outer',
                                suffixes=('_model1', '_model2'), indicator=True)
            df_merge = df_merge.copy()
            for column in columns:
                if column not in ['ARFROM', 'ARTO']:
                    new_col, col1, col2 = f'{column}_delta', f'{column}_model1', f'{column}_model2'
                    df_merge[new_col] = self._delta(df_merge[col1], df_merge[col2])
        elif equip_type in ['vsc_line_data', 'two_terminal_dc',
                            'system_switching_device', 'switched_shunt',
                            'multi_terminal_dc', 'header', 'gne', 'substation']:
            # TODO: create comparisons for these sections
            print(f'Delta calculation for {equip_type} not implemented.  '
                  f'Columns: {columns}')
            df_merge = None
        else:
            print(f'Delta calculation for {equip_type} not implemented.  '
                  f'Columns: {columns}')
            df_merge = None

        if df_merge is not None and df_merge.empty:
            df_merge = pd.DataFrame(['Not Implemented'],
                                    columns=[equip_type])

        self.print_time(f'Finished comparing {equip_type} changes.')

        return df_merge

    def filter_models(self):
        # If either model is not yet filtered, after filtering,
        # pickle ModelComparison.
        pickle = not self.model1.filtered or not self.model2.filtered

        if not self.model1.filtered:
            # Filter model1 to only native facilities as specified by areas
            # and kv_range arguments.
            self.print_time('Filtering model 1...')
            self.model1.filter_model(kv_range=self.kv_range, areas=self.areas)
            self.print_time('Finished filtering model 1.')

        if not self.model2.filtered:
            # Filter model2 to only native facilities as specified by areas
            # and kv_range arguments.
            self.print_time('Filtering model 2...')
            self.model2.filter_model(kv_range=self.kv_range, areas=self.areas)
            self.print_time('Finished filtering model 2.')

        if pickle:
            # Pickle ModelComparison, which includes the filtered models.
            self.print_time('Pickling filtered ModelComparison...')
            self.to_pickle()
            self.print_time('Finished pickling filtered ModelComparison...')

    def to_excel(self, overwrite: bool = False,
                 models_to_excel: bool = False,
                 comparison_to_excel: bool = False):
        if models_to_excel:
            # Export filtered model1 info to Excel
            xl_fp = self.model1.file_path.with_suffix(".xlsx")
            if overwrite or not xl_fp.exists():
                self.print_time('Exporting model 1 to Excel...')
                self.model1.to_excel(file_path=xl_fp)
                self.print_time('Finished exporting model 1 to Excel.')

            # Export filtered model2 info to Excel
            xl_fp = self.model2.file_path.with_suffix(".xlsx")
            if overwrite or not xl_fp.exists():
                self.print_time('Exporting model 2 to Excel...')
                self.model2.to_excel(file_path=xl_fp)
                self.print_time('Finished exporting model 2 to Excel.')

        # Write results to report_file (Excel).
        if comparison_to_excel and (overwrite or not report_file.exists()):
            # Write general data about the model comparison to Excel
            self.print_time('Exporting ModelComparison summary info to Excel...')
            d = {'model1': str(self.model1.file_path.absolute()),  # Model 1 .raw file path.
                 'model2': str(self.model2.file_path.absolute()),  # Model 2 .raw file path.
                 'kv_range': self.kv_range,  # kV range included in the comparison.
                 'area_filter': self.areas}  # Areas included in the comparison
            df = pd.DataFrame(list(d.items()), columns=['Setting', 'Value'])
            df_to_excel_worksheet(dataframe=df, sheet_name='info',
                                  filepath=report_file)
            self.print_time('Finished exporting ModelComparison '
                            'summary info to Excel.')

            # Write bus info for both models.
            self.print_time('Exporting ModelComparison BUS data to Excel...')
            df_to_excel_worksheet(dataframe=self.model1.bus_df,
                                  sheet_name=f'{self.model1.file_path.stem}_buses',
                                  filepath=report_file)
            df_to_excel_worksheet(dataframe=self.model2.bus_df,
                                  sheet_name=f'{self.model2.file_path.stem}_buses',
                                  filepath=report_file)
            self.print_time('Finished exporting ModelComparison BUS '
                            'data to Excel.')

            # Write split and merged paths to Excel.
            self.print_time('Exporting path splits and merges to Excel...')
            columns = ['I', 'J', 'TYPE', 'NAME', 'ALTERNATE_PATHS']
            dicts = {'splits': self._path_comparison.path_splits,
                     'merges': self._path_comparison.path_merges}
            for sheet_name, edges in dicts.items():
                edges_list = []
                for edge, equip_info in edges.items():
                    i, j = edge[0], edge[1]
                    edge_type = equip_info.edge_type
                    edge_name = equip_info.edge_name
                    equip = equip_info.equip
                    new_paths = equip_info.valid_paths
                    edges_list.append((i, j, edge_type, edge_name, new_paths))
                df = pd.DataFrame(edges_list, columns=columns)
                if sheet_name == 'splits':
                    # Rename the column 'ALTERNATE_PATHS' to 'MODEL1_PATHS'
                    df.rename(columns={'I': 'FROM_1', 'J': 'TO_1',
                                                'ALTERNATE_PATHS': 'MODEL2_PATHS'}, inplace=True)
                else:
                    # Rename the column 'ALTERNATE_PATHS' to 'MODEL1_PATHS'
                    df.rename(columns={'ALTERNATE_PATHS': 'MODEL1_PATHS',
                                                'I': 'FROM_2', 'J': 'TO_2'}, inplace=True)
                    # Reorder the columns
                    df = df[['MODEL1_PATHS', 'TYPE', 'NAME', 'FROM_2', 'TO_2']]

                df_to_excel_worksheet(dataframe=df, sheet_name=sheet_name,
                                      filepath=report_file)
            self.print_time('Finished exporting path splits '
                            'and merges to Excel.')

            # Write added and removed edges to Excel.
            edge_sets = {'added_edges': self._path_comparison.added_edges,
                         'removed_edges': self._path_comparison.removed_edges}
            for sheet_name, edge_set in edge_sets.items():
                columns = ['FROM_BUS', 'TO_BUS', 'TYPE', 'EQUIPMENT']
                df = pd.DataFrame(edge_set, columns=columns)
                df_to_excel_worksheet(dataframe=df, sheet_name=sheet_name,
                                      filepath=report_file)

            # # Write added and removed nodes to Excel.
            # self.print_time('Exporting node changes to Excel...')
            # node_sets = {'added_nodes': self._path_comparison.added_nodes,
            #              'removed_nodes': self._path_comparison.removed_nodes}
            # for sheet_name, node_set in node_sets.items():
            #     columns = ['BUS_ID']
            #     df = pd.DataFrame(node_set, columns=columns)
            #     df_to_excel_worksheet(dataframe=df, sheet_name=sheet_name,
            #                           filepath=report_file)
            # self.print_time('Finished exporting node changes to Excel.')

            # Write equipment comparisons to Excel.
            print(f'Exporting model 1 to model 2 comparison results '
                  f'to "{str(report_file)}" ...')
            for equip_type, df in self._equip_comparison.items():
                sheet_name = f'{equip_type}_comparison'
                self.print_time(f'Exporting {sheet_name} to Excel...')
                if isinstance(df, pd.DataFrame):
                    df_to_excel_worksheet(dataframe=df, sheet_name=sheet_name,
                                          filepath=report_file)
                self.print_time(f'Finished exporting {sheet_name} to Excel.')

    def compare(self, models_to_excel: bool = False,
                comparison_to_excel: bool = False) \
            -> tuple[PathComparison, dict[pd.DataFrame]]:
        self.print_time('Starting ModelComparison.compare()...')
        # Apply kV and area filters to model.
        self.filter_models()

        # Find PATH changes between model 1 and model 2 OR use previously
        # cached model comparison data.
        print('Finding model changes between model 1 and model 2.')
        self.compare_paths(max_path_length=self.max_path_length, sort=False)

        # Find EQUIPMENT changes between model 1 and model 2
        if force_recalculation or not self._equip_comparison:
            self._equip_comparison = {}
            # Find equipment changes between model 1 and model 2; do not use cache
            for equip_type in ['bus', 'transformer', 'branch',
                               'system_switching_device', 'vsc_dc_line',
                               'multi_section_line', 'facts_device', 'load',
                               'fixed_shunt', 'generator', 'zone', 'owner',
                               'switched_shunt', 'induction_machine'
                               ]:
                self._equip_comparison[equip_type]: pd.DataFrame = \
                    self.compare_equip(equip_type=equip_type)
            self.print_time('Pickling ModelComparison with complete comparison results...')
            self.to_pickle()
            self.print_time('Finished pickling ModelComparison with complete comparison results...')
        if models_to_excel or comparison_to_excel:
            self.to_excel(overwrite=self.force_recalculation, models_to_excel=models_to_excel,
                          comparison_to_excel=comparison_to_excel)

        self.print_time('Finding ModelComparison.compare().')
        self.timer = []

        return self._path_comparison, self._equip_comparison


if __name__ == '__main__':
    # User Inputs:
    force_recalculation = True  # 30 to 45 seconds
    models_to_excel = False  # Can take up to 10 minutes per model
    comparison_to_excel = True  # Can take 5 to 7 minutes
    raw1_path = DEFAULT_DIRECTORY / "IDC_2324W_win24idctr6p3.raw"
    raw2_path = DEFAULT_DIRECTORY / "IDC_24S_sum24idctr1p8.raw"
    report_file = DATA_FOLDER / f'{raw1_path.stem}_{raw2_path.stem}.xlsx'
    kv_range = DEFAULT_KV_FILTER  # RangeFilterType(69, 10000)
    native_areas = NATIVE_AREAS
    cache_dir = dirs.site_cache_dir

    if force_recalculation:
        ans = input('Are you sure you want to clear cache and force '
                    'recalculation? [y/n]: ').strip().lower()
        if ans != 'y':
            force_recalculation = False

    # Run main()
    if report_file.exists() and is_file_locked(report_file):
        raise OSError(f'Report file "{report_file}" is locked.  '
                      f'Close/unlock the file and try again.')

    mc = ModelComparison(model1=raw1_path,
                         model2=raw2_path,
                         report_dir=dirs.site_data_dir,
                         cache_dir=cache_dir,
                         kv_range=kv_range,
                         areas=native_areas,
                         force_recalculation=force_recalculation,
                         max_path_length=4)

    path_comparison, equip_comparison = \
        mc.compare(models_to_excel=models_to_excel, comparison_to_excel=comparison_to_excel)

    print(mc.timer)

    print('\n\n!!! MODEL COMPARISON COMPLETE !!!')
