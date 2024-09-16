"""
model.py - PSSE v33-35 Model Parser and Processor

This module provides functionality to read and process PSSE RAW and RAWX files,
converting them into a structured model representation (Model class) for easy
manipulation and analysis.

The primary purpose of this module is to parse RAW and RAWX files and create a
comprehensive model object that encapsulates all the data and provides methods
for filtering, analysis, and graph creation.

Main Components:
---------------
Model : class
    The central class of the module. It reads a RAW or RAWX file, creates objects for each
    section of the file, and provides methods for data manipulation and analysis.
    The 'network' section receives special attention, with data parsed into pandas
    DataFrames and used to create a NetworkX graph for topological analysis.

the following classes are used to represent specific sections of the RAW/RAWX file.  They
are used to set attributes of the Model object, such as Model.general
and Model.network.

    General : class
        Represents the 'general' section of the RAW/RAWX file, containing overall model information.

    Network : class
        Represents the 'network' section, the core of the power system model. It contains
        multiple pandas DataFrames for different network components (buses, branches, generators, etc.)
        and methods to create and manipulate a NetworkX graph of the system.

    Harmonics : class
        Represents the 'harmonics' section of a RAWX file, containing harmonic analysis data.

    TimeSeries : class
        Represents the 'timeseries' section of a RAWX file, containing time-dependent data.

Usage:
------
To use this module, create an instance of Model by providing a path to a RAW or RAWX file:

    model = Model('path/to/rawx/file.rawx')

You can then access different sections of the model, manipulate data, filter the model,
or perform graph analysis:

    network_graph = model.network.graph()
    filtered_model = model.filter_by_area(areas=['AREA1', 'AREA2'])

This module is designed to be memory-efficient and performant, suitable for handling
large power system models such as MMWG or IDC cases used in the Eastern Interconnection.
"""

# Rest of the module code follows...
import json
import warnings
from collections import namedtuple
from typing import Dict, Any, List, Union, Callable  # Union
from pathlib import Path
from datetime import datetime as dtdt
import copy
from time import perf_counter_ns

from psse_model_util.common.dataframe_util import convert_df_column_dtypes
from psse_model_util.common.dirs import site_cache_dir, site_data_dir
from psse_model_util.common.file_util import to_pickle, read_pickle
from psse_model_util.common.json_util import load_and_clean_json
from psse_model_util.common.constants import INCLUDE_AREAS
from psse_model_util.rawx_json_template import rawx_json_template
from psse_model_util.raw_to_rawx import raw_file_to_rawx_dict

# from psse_model_util.common.classes import ModelDF
# from psse_model_util.common.dirs import site_data_dir
# from psse_model_util.common.classes import (BusId, IdStr, IdInt,
#                                             ZoneId, AreaId, OwnerId, SwShID)

import pandas as pd
import networkx as nx
import pickle
import numpy as np

FpPickleType = namedtuple('FpPickleType', ['file_path', 'object'])


class General:
    """
    Represents the 'general' section of the PSSE v35 RAWX (JSON) file or
    the version comment of a RAW file.
    """

    def __init__(self, data: Dict[str, Any]):
        """
        Initialize the General class with data from the 'general' section.

        :param data: Dictionary containing the 'general' section data
        """
        # The general section is a dict.  Turn the key/value pairs into
        # attributes and values.
        for key, value in data.items():
            setattr(self, key, self._auto_dtype(value))

    @staticmethod
    def _auto_dtype(value: Any,
                    try_dtypes: List[Union[Callable[[Any], Any], type]]
                    = (float, int, str),
                    ):
        """Try to convert a single value to specified types, otherwise
        keep as original."""
        for dtype in try_dtypes:
            try:
                if dtype == dtdt:
                    return dtdt.fromisoformat(value)
                elif dtype == int:
                    # Try to convert to int, but only if it doesn't
                    # result in data loss
                    float_value = float(value)
                    if float_value.is_integer():
                        return int(float_value)
                    else:
                        continue
                else:
                    return dtype(value)
            except (ValueError, TypeError):
                continue
        return value


class AbstractSection:
    """
    Base classs for the Network, Timeseries and Harmonics classes, each
    specific to a particular section of the PSSE v35 rawx file.  RAW files
    do not contain time series or harmonics data.
    """

    def __init__(self, section: Dict[str, Any], generate_graph: bool = False):
        """
        Initialize the class with data from a section of a rawx file.
        A rawx file is in json format, which, when read is converted to python
        dict objects.  In this __init__ we will create attributes (and their
        values) from the key/value pairs found section.

        :param section: Dictionary containing the section data
        """

        for subsection, data in section.items():
            self.subsection = subsection  # Added to aid in debugging
            df = self._create_dataframe(data)
            setattr(self, subsection, df)

    def _create_dataframe(self, data: Dict[str, Union[List[str], List[Any]]]) -> pd.DataFrame:
        """
        Create a pandas DataFrame from the given data.  Specific subsections are
        expected in a section, such as 'fields' and 'data'.  More information
        on each section can be found in rawx_json_template.rawx_json_template,
        such as 'data_type', 'bus_cols' and 'id_cols'.

        :param data: Dictionary containing 'fields' and 'data' keys
        :return: pandas DataFrame
        """
        orig_keys = tuple(data.keys())
        fields: list = data.pop('fields')
        values: list = data.pop('data')
        meta: dict = data

        # If meta['data_type'] is a list or tuple, convert it to a dict.
        if 'data_type' in meta.keys() and not isinstance(meta['data_type'], dict):
            meta['data_type'] = {k: v for k, v in zip(fields, meta['data_type'])}

        if not values:
            # data is empty.  Return empty dataframe.
            return pd.DataFrame(columns=fields)

        # If number of data columns < number of fields, then pad empty columns
        # to the end of data.
        if isinstance(values[0], list):
            # For multi-row data
            padded_values = [(row + [None] * (len(fields) - len(row)))
                             if isinstance(row, list)
                             else row for row in values]
        else:
            # For single-row data
            padded_values = [values + [None] * (len(fields) - len(values))]

        # Create pd.DataFrame
        try:
            df = pd.DataFrame(padded_values, columns=fields)
            # If 'id_cols' is provided, then set the index to those columns.
        except ValueError as e:
            print('subsection:', self.subsection)
            print('fields:', len(fields), fields)
            print('data:', len(data), data)
            print('meta:', len(meta), meta)
            raise

        # Get metadata like data_type, bus_cols, and id_cols from rawx_json_template.
        metadata = df._metadata or {}

        return df

    def copy(self, deep: bool = True):
        """
        Create a copy of the AbstractSection instance.

        This method creates a new AbstractSection instance and copies all attributes.
        If deep is True, it performs a deep copy; otherwise, it performs a shallow copy.

        :param deep: If True, create a deep copy. If False, create a shallow copy. Defaults to True.
        :return: A new AbstractSection instance with copied attributes.
        """
        # Create a new Network instance
        new_abstract_section = AbstractSection.__new__(AbstractSection)

        # Iterate through all attributes of the current instance
        for attr_name, attr_value in self.__dict__.items():
            if isinstance(attr_value, pd.DataFrame):
                # For DataFrames, use pandas copy method
                setattr(new_abstract_section, attr_name, copy.deepcopy(attr_value))

                # Copy DataFrame metadata
                new_df = getattr(new_abstract_section, attr_name)
                if deep:
                    new_df._metadata = copy.deepcopy(attr_value._metadata)
                else:
                    new_df._metadata = attr_value._metadata
            else:
                # For other attributes, use Python's copy or deepcopy
                if deep:
                    setattr(new_abstract_section, attr_name, copy.deepcopy(attr_value))
                else:
                    setattr(new_abstract_section, attr_name, copy.copy(attr_value))

        return new_abstract_section


class Network(AbstractSection):
    """
    Represents the 'network' section of the PSSE v35 RAWX (JSON) file.
    """

    def __init__(self, section: Dict[str, Any], generate_graph: bool = False):
        """
        Initialize the Network class with data from the 'network' section.

        :param section: Dictionary containing the 'network' section data
        """
        start_time = perf_counter_ns()
        print(f'Network.__init__ starting...')
        for subsection, data in section.items():
            print(f'Network.__init__ creating dataframe {subsection}...')
            self.subsection = subsection  # Added to aid in debugging
            df = self._create_dataframe(data)
            setattr(self, subsection, df)
            print(f'Network.__init__ elapsed: '
                  f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

        self._orig_dfs_cache: dict[str, pd.DataFrame] = dict()
        self._orig_dfs_cache['bus'] = copy.deepcopy(self.bus)
        self._orig_dfs_cache['bus']._metadata = self.bus._metadata

        self._graph: nx.Graph = self.graph(regenerate=True) if generate_graph else nx.Graph()
        print(f'Network.__init__  finished: '
              f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

    def _create_dataframe(self, data: Dict[str, Union[List[str], List[Any]]]) -> pd.DataFrame:
        """
        Create a pandas DataFrame from the given RAWX section data (RAW files must be 
        converted to a rawx-like dict structure using the raw_to_rawxraw_file_to_rawx_dict 
        function) with appropriate metadata.

        This method is a crucial part of the RAWX parsing process. It takes raw data from a
        section of the RAWX file and converts it into a structured pandas DataFrame, applying
        metadata from the rawx_json_template to ensure correct data types and indexing.

        The method performs the following key operations:
        1. Extracts 'fields' and 'data' from the input dictionary (extracted beforehand
           from the RAWX file)
        2. Retrieves metadata (data_type, bus_cols, id_cols) from rawx_json_template.
        3. Pads data rows if they're shorter than the number of fields. (More relevant
           to .raw files than .rawx files)
        4. Creates a pandas DataFrame with the correct column names.
        5. Applies the specified data types to each column.
        6. Sets the DataFrame index using the specified id_cols, columns that uniquely
           identify the equipment (like ibus, jbus and ckt for an AC line).
        7. Attaches metadata to the DataFrame for use in other methods.

        Parameters:
        -----------
        data : Dict[str, Union[List[str], List[Any]]]
            A dictionary containing 'fields' (column names) and 'data' (row values),
            along with any additional metadata.

        Returns:
        --------
        pd.DataFrame
            A pandas DataFrame structured according to the RAWX section specifications,
            with correct data types, index, and attached metadata.

        Notes:
        ------
        - This method is called for each section in the RAWX file during the parsing process.
        - The resulting DataFrames are stored as attributes of the Network object, which is
          in turn an attribute of the Model instance.
        - The metadata attached to each DataFrame (especially 'bus_cols' and 'id_cols') is
          used in other methods like filter_by_area and section_with_bus for efficient
          data manipulation and analysis.
        - If a section in the RAWX file is empty, this method returns an empty DataFrame
          with the correct column structure.

        Example:
        --------
        # Inside Model.__init__
        for section_name, section_data in self.json_data['network'].items():
            df = self._create_dataframe(section_data)
            setattr(self.network, section_name, df)
        """
        orig_keys = tuple(data.keys())
        fields: list = data.pop('fields')
        values: list = data.pop('data')
        meta: dict = data

        # Get metadata from "data" argument for from rawx_json_template.
        if self.subsection in rawx_json_template['network']:
            template = rawx_json_template['network'][self.subsection]
            template = {k: v for k, v in template.items() if k not in orig_keys}
            # Add metatdata from rawx_json_template to the dataframe's _metadata
            # attribute.
            for key in template:
                meta.setdefault(key, template[key])

        # If meta['data_type'] is a list or tuple, convert it to a dict.
        if 'data_type' in meta.keys() and not isinstance(meta['data_type'], dict):
            meta['data_type'] = {k: v for k, v in zip(fields, meta['data_type'])}

        if not values:
            # data is empty.  Return empty dataframe.
            return pd.DataFrame(columns=fields)

        # If number of data columns < number of fields, then pad empty columns
        # to the end of data.
        if isinstance(values[0], list):
            # For multi-row data
            padded_values = [(row + [None] * (len(fields) - len(row)))
                             if isinstance(row, list)
                             else row for row in values]
        else:
            # For single-row data
            padded_values = [values + [None] * (len(fields) - len(values))]

        # Create DataFrame
        try:
            df = pd.DataFrame(padded_values, columns=fields)
            # If 'id_cols' is provided, then set the index to those columns.
        except ValueError as e:
            print('network subsection:', self.subsection)
            print('fields:', len(fields), fields)
            print('data:', len(data), data)
            print('meta:', len(meta), meta)
            raise

        # Get metadata like data_type, bus_cols, and id_cols from rawx_json_template.
        metadata = df._metadata or {}
        if self.subsection in rawx_json_template['network']:
            template = rawx_json_template['network'][self.subsection]
            template = {k: v for k, v in template.items() if k not in orig_keys}
            # Add metatdata from rawx_json_template to the dataframe's _metadata
            # attribute.
            for key in template:
                metadata[key] = template[key]
                # id_cols = data['id_cols'] if 'id_cols' in data else None


        if 'data_type' in metadata:
            # new_dtypes = metadata['data_type']
            new_dtypes = dict(zip(fields, metadata['data_type']))
            metadata = metadata
            df = convert_df_column_dtypes(df_in=df,
                                          new_dtypes=new_dtypes,
                                          convert_all_columns=True,
                                          default_types=(int, float, str))
            df._metadata = metadata

        # Replace the default df index with the columns specified in id_cols
        # (optionally specified in rawx_json_template).
        if 'id_cols' in metadata:
            id_cols = [_ for _ in metadata['id_cols'] if _ in df.columns]  # id_cols = metadata['id_cols']
            ommited_from_index = set(id_cols) - set(df.columns)
            if len(ommited_from_index) > 0:
                msg = f'Unable to move columns to index (may be okay for models older than v35): {str(ommited_from_index)}.'
                warnings.warn(msg)
            # Set the index using the specified id_cols
            try:
                df.set_index(id_cols, inplace=True)
            except KeyError as e:
                msg = f'Error moving columns {str(id_cols)} to index. {str(e)}'
                warnings.warn(msg)
                # raise

        return df

    def section_with_bus(self, section: str,
                         filter_condition: str = None,
                         inplace: bool = False) -> pd.DataFrame:
        """
        Used in the append_bus_info_to_dfs method to join the specified section's
        DataFrame with the bus DataFrame for each bus column.

        This method enhances the specified section's DataFrame by adding bus information
        for each bus column. It uses pd.concat to efficiently add bus data columns.

        Args:
            section (str): Name of the attribute (DataFrame) in the Network class.
            filter_condition (str, optional): SQL-like query string to filter the DataFrame.
            inplace (bool, optional): If True, modify the original DataFrame. If False,
                                      return a new DataFrame. Defaults to False.

        Returns:
            pd.DataFrame: DataFrame with bus information joined for each bus column.

        Raises:
            ValueError: If the specified section is not a DataFrame attribute of Network
                        or if no bus columns are found in the section's metadata.

        Performance Note:
            This method uses pd.concat which is generally more memory-efficient than pd.merge
            for adding multiple columns to a DataFrame.
        """
        start_time = perf_counter_ns()
        print(f'Adding bus information to {section} starting...')
        # Get the specified section's DataFrame
        df = getattr(self, section)
        metadata = df._metadata
        df = copy.deepcopy(df)

        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"{section} is not a DataFrame attribute of Network.")

        # Get the bus columns from metadata
        bus_cols = metadata.setdefault('bus_cols', {})

        if not bus_cols:
            raise ValueError(f"No bus columns found in metadata for {section}.")

        # Apply filter_condition if provided
        if filter_condition:
            df = df.query(filter_condition)

        # Capture the original index, then reset_index to convert indices to columns.
        if isinstance(df.index, pd.MultiIndex):
            original_index_columns = list(df.index.names)
            df.reset_index(inplace=True)
        else:
            original_index_name = df.index.name or 'index'
            df[original_index_name] = df.index
            original_index_columns = [original_index_name]
            df.reset_index(drop=True, inplace=True)

        # Join with bus DataFrame for each bus column
        for bus_col in bus_cols:
            # If the model has been filtered inplace, then not all buses are
            # still in the model.  For this reason, Network.__init__ makes
            # a copy of Network.bus to Network.orig_bus.
            bus_df: pd.DataFrame = copy.deepcopy(self._orig_dfs_cache['bus'])
            bus_df.columns = [f"{bus_col}_{col}" for col in bus_df.columns]
            df: pd.DataFrame = pd.merge(
                df,
                bus_df,
                left_on=bus_col,
                right_index=True,
                how='left',  # left outer join
            )

        # Restore the original index
        df.set_index(original_index_columns, inplace=True)
        if not isinstance(df.index, pd.MultiIndex) and original_index_columns[0] == 'index':
            df.index.name = None

        df._metadata = metadata

        # If inplace, update the original DataFrame
        if inplace:
            setattr(self, section, df)

        print(f'Finished adding bus information to {section}: '
              f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

        return df

    def append_bus_info_to_dfs(self):
        """
        For each dataframe in self.dfs(), if the dataframe._metadata['bus_cols']
        exists and is not empty, update the dataframe to include bus info by
        running the self.section_with_bus method.

        This method modifies the dataframes in place, preserving their _metadata.

        Returns:
            None

        Note:
            This method modifies the dataframes in the Network object directly.
            It preserves the _metadata of each dataframe, including any bus_cols information.
        """
        for section, df in self.model_dfs().items():
            # Check if the dataframe has bus_cols in its metadata
            if (section != 'bus'
                    and hasattr(df, '_metadata')
                    and 'bus_cols' in df._metadata
                    and df._metadata['bus_cols']):
                # Apply section_with_bus method in place
                self.section_with_bus(section, inplace=True)

    def filter_by_area(self, areas: dict | list[str] = INCLUDE_AREAS,
                       inplace: bool = False,
                       graph_effect: str = 'clear') -> 'Network':
        """
        Filter the Network instance data by specified areas.

        Args:
            areas (dict | list[str]): Dict or list of area names or IDs to include in the filtered network.
                Defaults to INCLUDE_AREAS.
            inplace (bool): If True, filter self.Network inplace. If False, return a modified copy of the Network instance.
            graph_effect (str): 'clear' to clear the graph, 'regenerate' to regenerate the graph, 'leave' to leave the graph
                unchanged.

        Returns:
            Network: Filtered Network instance.

        Raises:
            ValueError: If the areas list is empty after preprocessing.
        """
        # Preprocess areas
        areas = list(areas.keys()) if isinstance(areas, dict) else copy.deepcopy(areas)
        if not areas:
            raise ValueError("The areas list is empty after preprocessing.")

        # If inplace network = self, else network = copy of self.
        network: 'Network' = self if inplace else self.copy()

        # Filter bus by area
        meta = network.bus._metadata
        network.bus = network.bus[network.bus['area'].isin(areas)]
        network.bus._metadata = meta
        # Get the set of buses in the filtered areas
        filtered_buses = set(network.bus.index)

        # Filter other DataFrames that have bus references
        for attr_name, df in network.__dict__.items():
            if isinstance(df, pd.DataFrame) and attr_name != 'bus':
                meta = df._metadata
                if 'bus_cols' in meta:
                    bus_cols = meta['bus_cols']

                    # Check if bus_cols are in the columns or index
                    index_bus_cols = [col for col in bus_cols if col in df.index.names]
                    column_bus_cols = [col for col in bus_cols if col in df.columns]

                    if index_bus_cols:
                        # If bus_cols are in the index
                        mask = df.index.get_level_values(index_bus_cols[0]).isin(filtered_buses)
                        for col in index_bus_cols[1:]:
                            mask |= df.index.get_level_values(col).isin(filtered_buses)
                    elif column_bus_cols:
                        # If bus_cols are in the columns
                        # mask = df[column_bus_cols].apply(lambda x: x.isin(filtered_buses)).any(axis=1)
                        mask = np.any(np.isin(df[column_bus_cols].values, list(filtered_buses)), axis=1)
                    else:
                        # If no bus columns found, keep all rows and warn
                        warnings.warn(f"No bus columns found in {attr_name}. Keeping all rows.")
                        continue
                    df = df[mask]
                    df._metadata = meta
                    setattr(network, attr_name, df)

        # Clear, regenerate or leave the graph per the "graph_effect" argument.
        if graph_effect == 'clear':
            network._graph = nx.Graph()
        elif graph_effect == 'regenerate':
            network.graph(regenerate=True)
        elif graph_effect != 'leave':
            raise ValueError(f'Invalid value of graph_effect, "{graph_effect}". '
                             f'Expected one of "clear", "regenerate" or "leave".')

        return network

    def copy(self, deep: bool = True):
        """
        Create a copy of the Network instance.

        This method creates a new Network instance and copies all attributes.
        If deep is True, it performs a deep copy; otherwise, it performs a shallow copy.

        :param deep: If True, create a deep copy. If False, create a shallow copy. Defaults to True.
        :return: A new Network instance with copied attributes.
        """
        # Create a new Network instance
        new_network = Network.__new__(Network)

        # Iterate through all attributes of the current instance
        for attr_name, attr_value in self.__dict__.items():
            if isinstance(attr_value, pd.DataFrame):
                # For DataFrames, use pandas copy method
                new_df = copy.deepcopy(attr_value)
                if deep:
                    new_df._metadata = copy.deepcopy(attr_value._metadata)
                else:
                    new_df._metadata = attr_value._metadata
                setattr(new_network, attr_name, new_df)
            else:
                # For other attributes, use Python's copy or deepcopy
                if deep:
                    setattr(new_network, attr_name, copy.deepcopy(attr_value))
                else:
                    setattr(new_network, attr_name, copy.copy(attr_value))

        return new_network

    def model_dfs(self) -> Dict[str, pd.DataFrame]:
        """
        Retrieve all pandas DataFrames stored as attributes in the Network instance.

        This method is a used for accessing and managing the various power system
        component DataFrames within the Network object. It dynamically collects all attributes
        of the Network instance that are pandas DataFrames, providing a comprehensive view of
        the network model's data.  This is important, since the structure of the "network"
        section of a RAWX file may change in future PSS/e releases.

        The method performs the following operations:
        1. Iterates through all attributes of the Network instance.
        2. Identifies attributes that are pandas DataFrames.
        3. Creates a dictionary with attribute names as keys and the corresponding
           DataFrames as values.

        Returns:
        --------
        Dict[str, pd.DataFrame]
            A dictionary where each key is the name of a network component (e.g., 'bus',
            'branch', 'generator'), and each value is the corresponding pandas DataFrame
            containing that component's data.

        Notes:
        ------
        - This method is particularly useful for bulk operations on all network components,
          such as filtering, data export, or comprehensive network analysis.
        - The returned dictionary includes all DataFrames, regardless of their size or content,
          allowing for complete access to the network model's data.
        - The method relies on the convention that all network component data in the Network
          class is stored as pandas DataFrames.
        - This method is often used in conjunction with other Network methods or in the
          Model class for operations that need to iterate over all network components.

        Example Usage:
        --------------
        # Inside a method of Model or Network class
        def some_operation(self):
            for df_name, df in self.model_dfs().items():
                # Perform some operation on each DataFrame
                print(f"{df_name} has {len(df)} rows")
        """
        return {_: getattr(self, _) for _ in dir(self)
                if isinstance(getattr(self, _), pd.DataFrame)}

    def graph(self, regenerate: bool = False,
              empty_ok: bool = False):
        """
        Create or retrieve a NetworkX Graph representation of the power system network.

        This method is central to the topological analysis capabilities of the Network class.
        It constructs a graph where nodes represent buses and other network elements, and edges
        represent connections between them (like transmission lines and transformers).

        Parameters:
        -----------
        regenerate : bool, optional (default=False)
            If True, forces the method to create a new graph even if one already exists.
            If False, returns the existing graph if available.
        empty_ok : bool, optional (default=False)
            If True, allows the method to return an empty graph if no graph exists and
            regenerate is False. If False, an empty graph will trigger regeneration.

        Returns:
        --------
        nx.Graph
            A NetworkX Graph object representing the power system network topology.

        Graph Structure:
        ----------------
        1. Nodes:
            - Bus nodes: Indexed as ('bus', bus_number)
            - Other single bus equipment nodes (e.g., generators, loads): Indexed as
              (equipment_type, bus_number, id)
            - Node attributes: All properties from the corresponding DataFrame are
              added to the node (using model.add_node(node_id, **kwargs), providing
              direct access to equipment details.

        2. Edges:
            - Represent connections between buses (e.g., transmission lines, transformers)
            - Indexed by the connected bus nodes: (('bus', from_bus_number), ('bus', to_bus_number))
            - Edge attributes: All properties from the corresponding DataFrame (e.g., 'branch')
              are added to the edge (using model.add_edge(node_id1, node_id2, **kwargs).

        3. Special Cases:
            - Three-winding transformers: Represented by a central node connected to three bus nodes
            - Index: ('transformer', primary_bus, secondary_bus, terniary_bus, circuit_id)

        Graph Creation Process:
        -----------------------
        1. Adds buses as nodes, with bus properties as node attributes.
        2. Iterates through each equipment type (e.g., generators, branches, transformers):
            - For single-bus equipment: Adds as nodes connected to their respective buses.
            - For two-bus equipment (e.g., lines): Adds as edges between the connected buses.
            - For three-winding transformers: Creates a central node connected to three buses.
        3. Adds relevant properties of each equipment as node or edge attributes.

        Notes:
        ------
        - Consider running Network.append_bus_info_to_dfs() before generating the graph to
          ensure that bus information is readily available for all equipment in the graph.
        - The resulting graph structure allows for efficient querying and analysis. For example:
            * To get all properties of a bus: graph.nodes[('bus', bus_number)]
            * To get properties of a line: graph.edges[('bus', from_bus), ('bus', to_bus)]
        - This detailed graph structure preserves the rich information from the RAWX file,
          enabling complex analyses directly on the graph without needing to reference
          the original DataFrames.
        - The graph is accessed through the "graph" method and privatley stored as
          self._graph for future access, improving performance for subsequent calls
          unless regeneration is requested.

        Example Usage:
        --------------
        # Ensure bus info is appended to all DataFrames
        self.append_bus_info_to_dfs()

        # Generate the graph
        network_graph = self.graph(regenerate=True)

        # Access bus properties
        bus_properties = network_graph.nodes[('bus', 1001)]

        # Access line properties
        line_properties = network_graph.edges[('bus', 1001), ('bus', 1002)]

        # Use NetworkX algorithms for analysis
        import networkx as nx
        shortest_path = nx.shortest_path(network_graph, ('bus', 1001), ('bus', 2001))
        """
        if not regenerate and (empty_ok or self._graph):
            return self._graph

        # Create new, empty graph.
        del self._graph
        self._graph: nx.Graph = nx.Graph()

        # 1) Add buses
        bus_df = getattr(self, 'bus')
        bus_dict = bus_df.to_dict('index')
        nodes = [(('bus', ibus), props) for ibus, props in bus_dict.items()]
        self._graph.add_nodes_from(nodes)

        # 2) Add equipment
        sections = self.model_dfs()
        for section, df in sections.items():
            # Skip buses (already done above.
            # Skip substations, as they are complex and not present in IDC models.
            if section.startswith('sub') or section == 'bus':
                # Do not add substations to model
                continue

            # print(f'{section}._metadata:', df._metadata)

            # Skip rawx sections that do not have bus information, as they
            # do nto get added to the network graph.
            if 'bus_cols' not in df._metadata or 'id_cols' not in df._metadata:
                # Do not add items to the network graph if they don't have any
                # associated buses and clear identifiers.
                continue

            # Get a list of column names that contain bus numbers or equipment IDs.
            bus_cols, id_cols = df._metadata['bus_cols'], df._metadata['id_cols']
            # Process for adding equipment from a rawx section to the network
            # graph differs for 1-bus, 2-bus and 3-bus equipment.
            match len(bus_cols):
                case 1:
                    # Add radial (1-bus) items like load, gen, etc.
                    df['section'] = section
                    section_dict = df.to_dict('index')
                    nodes = [(tuple([section] + list(idx)), props) for idx, props in section_dict.items()]
                    self._graph.add_nodes_from(nodes)

                    edges = [(node, ('bus', node[1]), props) for node, props in nodes]
                    self._graph.add_edges_from(edges)
                case 2 | 4:
                    bus_cols = bus_cols[:2]
                    # Add edges items like acline, etc.
                    # section_df = getattr(self.network, section)
                    nodes_in = None
                    if not (set(bus_cols) - set(df.columns)):
                        nodes_in = 'bus_cols'
                    elif not (set(bus_cols) - set(df.index.names)):
                        nodes_in = 'index'
                    for _, row in df.iterrows():
                        if nodes_in == 'bus_cols':
                            bus_nodes = [('bus', row[col]) for col in bus_cols]
                        elif nodes_in == 'index':
                            bus_nodes = [('bus', row.name[i]) for i, col in enumerate(df.index.names) if
                                         col in bus_cols]

                        self._graph.add_edge(bus_nodes[0], bus_nodes[1], **row.to_dict())
                case 3:
                    # Transformer
                    assert len(id_cols) == 4
                    edge_data = []
                    for row in df.itertuples():
                        props = row._asdict()
                        props.update({'section': section, 'id_cols': id_cols, 'bus_cols': bus_cols})
                        i, j, k = row.Index[:3]
                        i, j, k, ckt = row.Index
                        tx_node = (section, i, j, k)
                        self._graph.add_node(tx_node, **props)
                        self._graph.add_edge(tx_node, ('bus', i), **{'section': section})
                        self._graph.add_edge(tx_node, ('bus', j), **{'section': section})
                        self._graph.add_edge(tx_node, ('bus', k), **{'section': section})

        return self._graph


class Harmonics(AbstractSection):
    """
    Represents the 'harmonics' section of the PSSE v35 RAWX (JSON) file.
    The MMWG based .rawx files do not contain harmonics data, so this section
    has minimal functionality.
    """

    def __init__(self, section: Dict[str, Any]):
        """
        Initialize the Harmonics class with data from the 'harmonics' section.

        :param section: Dictionary containing the 'harmonics' section data
        """
        super().__init__(section)


class TimeSeries(AbstractSection):
    """
    Represents the 'timeseries' section of the PSSE v35 RAWX (JSON) file.
    The MMWG based .rawx files do not contain timeseries data, so this section
    has minimal functionality.
    """

    def __init__(self, section: Dict[str, Any]):
        """
        Initialize the TimeSeries class with data from the 'timeseries' section.

        :param section: Dictionary containing the 'timeseries' section data
        """
        super().__init__(section)


class Model:
    """
    A comprehensive representation of a PSSE v35 power system model from a RAW or RAWX file.

    The Model class serves as the primary interface for loading, processing, and
    analyzing PSSE v35 RAWX (JSON) files or PSSE v33-35 RAW files. It provides 
    a structured, object-oriented representation of the entire power system 
    model, with methods for data manipulation, filtering, and analysis.

    Attributes:
    -----------
    name : str
        Name of the model, typically derived from the input file name.
    raw_file_path : Path
        Path to the source RAW or RAWX file.
    json_data : dict
        RAWX-like JSON data loaded from the RAWX file.  Or, loaded from a RAW
        file with the rawx_to_raw.raw_file_to_rawx_dict function.
    general : General
        Object representing the 'general' section of the RAWX file.
    network : Network
        Object representing the 'network' section, containing all power system components.
    harmonics : Harmonics
        Object representing the 'harmonics' section of the RAWX file.
    timeseries : TimeSeries
        Object representing the 'timeseries' section of the RAWX file.
    version : float
        Version number of the PSSE model.

    Methods:
    --------
    __init__(file_path_or_json: Union[str, dict, Path] = None, name: str = None,
             force_recalculate: bool = False)
        Initialize the Model object by loading and processing the RAW or RAWX file.

    filter_by_area(areas: dict | list[str] = INCLUDE_AREAS, inplace: bool = False)
        Filter the model to include only specified areas.

    copy(deep: bool = True)
        Create a deep or shallow copy of the Model object.

    network_dfs()
        Return a dictionary of all DataFrames in the network section.

    to_csv()
        Export the model data to CSV files.

    to_pickle(resilient: bool = True)
        Save the Model object to a pickle file for faster future loading.

    read_pickle(mode: str = 'rb', resilient: bool = True)
        Load a Model object from a pickle file.

    Key Features:
    -------------
    1. Comprehensive Data Representation:
       Stores all aspects of the power system model in structured Python objects,
       allowing easy access and manipulation of model components.

    2. Efficient Data Processing:
       Utilizes pandas DataFrames for storing component data, enabling fast
       data operations and analyses.

    3. Network Topology Analysis:
       The Network object includes methods to generate a NetworkX graph representation
       of the power system, facilitating topological analyses.

    4. Flexible Filtering:
       Provides methods to filter the model based on areas, allowing focus on
       specific parts of the power system.

    5. Data Persistence:
       Includes methods for saving and loading the processed model to/from pickle
       files, significantly reducing load times for subsequent analyses.

    6. Export Capabilities:
       Offers methods to export model data to various formats (CSV) for
       external analysis or reporting.

    Usage Example:
    --------------
    # Load a RAW or  RAWX file into a Model object
    model = Model('path/to/rawx/file.rawx')

    # Create a filtered copy of the model including only specific areas.
    filtered_model = model.filter_by_area({101: 'AREA1', 102: 'AREA2'}, inplace=False)
    -- or --
    filtered_model = model.filter_by_area([101, 102], inplace=False)

    # Access the network graph for topological analysis
    network_graph = model.network.graph()

    # Export the model data to CSV
    model.to_csv('output_model.csv')

    # Save the processed model for faster future loading
    model.to_pickle()

    Notes:
    ------
    - The Model class is designed to handle large power system models efficiently.
    - It's recommended to use the pickle functionality for faster loading of
      previously processed models.
    - The network graph generation can be computationally intensive for very large
      models; consider using it judiciously.
    """

    def __init__(self, file_path_or_json: Union[str, dict, Path],
                 name: str = None,
                 force_recalculate: bool = False):
        """
        Initialize a Model instance by loading and processing a PSSE v35 RAWX 
        file or a PSSE v33-35 RAW file.

        This method is the entry point for creating a Model object. It handles the
        loading of RAWX data, either from a file or a pre-loaded dictionary, and sets up
        the entire model structure.

        Parameters:
        -----------
        file_path_or_json : Union[str, dict, Path], optional
            The source of the RAWX data. Can be:
            - A string path to the RAWX file
            - A Path object pointing to the RAWX file
            - A dictionary containing pre-loaded RAWX data
            - A string containing the raw JSON content of a RAWX file
            If None, an empty model will be created.

        name : str, optional
            A custom name for the model. If not provided, the name will be derived from
            the file name or set to a default value.

        force_recalculate : bool, optional (default=False)
            If True, forces the method to recalculate and reprocess the entire model,
            even if a cached version exists. This is useful when you want to ensure
            you're working with the most up-to-date data.

        Attributes Initialized:
        -----------------------
        name : str
            Name of the model, either provided or derived.
        raw_file_path : Path
            Path to the source RAW or RAWX file (if applicable).
        json_data : dict
            RAWX-like JSON data loaded from the RAWX file.  Or, loaded from a RAW
            file with the rawx_to_raw.raw_file_to_rawx_dict function.
        general : General
            Object representing the 'general' section of the RAWX data.
        network : Network
            Object representing the 'network' section, containing all power system components.
        harmonics : Harmonics
            Object representing the 'harmonics' section of the RAWX data.
        timeseries : TimeSeries
            Object representing the 'timeseries' section of the RAWX data.
        version : float
            Version number of the PSSE model.

        Process:
        --------
        1. Loads the RAW or RAWX data from the provided source.
        2. Attempts to load a cached version of the model if available and not forced to recalculate.
        3. If no cache is available or recalculation is forced:
           a. Parses the JSON data into structured Python objects (General, Network, Harmonics, TimeSeries).
           b. Builds pandas DataFrames for each component in the Network section.
           c. Generates a NetworkX graph representation of the power system (if specified).
        4. Caches the processed model for future fast loading.

        Raises:
        -------
        FileNotFoundError
            If the specified RAW or RAWX file does not exist.
        JSONDecodeError
            If the provided JSON data is invalid.
        ValueError
            If the input format is unrecognized or invalid.

        Notes:
        ------
        - This method can be time-consuming for large models, especially when
          force_recalculate is True or no cache exists.
        - The caching mechanism significantly speeds up subsequent loads of the same model.
        - The NetworkX graph is not generated by default to save time and memory. Use
          the network.graph() method to generate it when needed.

        Example:
        --------
        # Load from a file
        model = Model("path/to/model.rawx", name="MyModel")

        # Load from pre-loaded JSON data
        with open("path/to/model.rawx", "r") as f:
            json_data = json.load(f)
        model = Model(json_data, name="PreloadedModel")

        # Force recalculation of a previously cached model
        model = Model("path/to/model.rawx", force_recalculate=True)
        """

        # Record the start time for performance tracking
        start_time = perf_counter_ns()
        print(f'Model __init__ starting.')

        # Initialize basic attributes
        self.name: str = name  # If not name, self._read_json will set a name.
        self.raw_file_path: Path = None  # site_data_dir / f"rawx_{dtdt.now().strftime('%Y_%m_%d_%H_%M_%S')}.model"
        self.json_data = {}

        # Load the RAW or RAWX data
        print(f'Model __init__ loading model from disk...')
        self._read_json(file_path_or_json, force_recalculate=force_recalculate)

        # Set up the pickle path for caching
        self._pickle_path = None
        self.pickle_path  # This calls the property setter to initialize the path

        # Check if we can load from a cached pickle file
        if not force_recalculate and self.pickle_path and self.pickle_path.exists():
            self.read_pickle()
            print(f'Model __init__ ({self.pickle_path}) finished: '
                  f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')
            return

        # Set up the pickle path for caching
        self._csv_folder = None
        self.csv_folder  # This calls the property setter to initialize the path

        print(f'Model __init__ elapsed time: '
              f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')
        print(f'Model __init__ building pd.DataFrames...')

        # Initialize section objects
        self.general: General = None
        self.network: Network = None
        self.harmonics: Harmonics = None
        self.timeseries: TimeSeries = None

        # Define mapping of section names to their corresponding classes
        section_class = {'general': General, 'network': Network,
                         'harmonics': Harmonics, 'timeseries': TimeSeries}

        # Parse each section of the RAWX file or JSON content (i.e., file_path_or_json).
        for section_name, data in self.json_data.items():
            if section_name in section_class.keys():
                # Create an instance of the appropriate class for this section
                Cls = section_class[section_name]
                obj = Cls(data)
                setattr(self, section_name, obj)
            else:
                # For unrecognized sections, attempt to set them as attributes
                try:
                    # self.__setattr__(section, self.json_data[section])
                    setattr(self, section_name, self.json_data[section_name])
                except Exception as e:
                    warnings.warn(f"Parsing of {section_name} failed.  str(e)")

        # Set the version attribute.  A "general" section may not be included
        # in the rawx file, so we'll use a try/catch.
        self.version = None
        try:
            self.version = self.general.version
        except AttributeError:
            # The general section did not exist in the rawx file or version is
            # not in general.  Try to get it from network.caseid['rev'].
            self.version = float(self.network.caseid['rev'].values[0])

        # Set a default name if none was provided
        if not self.name:
            self.name = f'PSSE-{self.version}, {len(self.network.bus)}-bus model'
            # self.name = self.

        # Cache the processed model for future use
        print(f'Model __init__ caching to disk...')
        self.to_pickle()

        print(f'Model __init__ elapsed time: '
              f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')
        print(f'Model __init__ ({self.raw_file_path}) finished: '
              f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

    def _read_json(self, file_path_or_json: Union[str, Path], force_recalculate: bool = False) -> Dict[str, Any]:
        """
        Called by __init__, this method reads and process the RAW or RAWX data 
        from various input formats.

        This method is responsible for loading the RAWX data into the Model object.
        It can handle multiple input formats and decides whether to use cached data
        or reprocess the input based on the force_recalculate flag.

        Parameters:
        -----------
        file_path_or_json : Union[str, Path, Dict[str, Any]]
            The source of the RAW or RAWX data. Can be:
            - A string path to the RAW or RAWX file
            - A Path object pointing to the RAW or RAWX file
            - A dictionary containing pre-loaded RAWX data
            - A string containing the JSON content of a RAWX file

        force_recalculate : bool, optional (default=False)
            If True, forces the method to reprocess the input data even if a cached
            version exists.

        Returns:
        --------
        Dict[str, Any]
            The processed JSON data representing the RAW or RAWX file contents.

        Raises:
        -------
        JSONDecodeError
            If the provided JSON data is invalid.
        FileNotFoundError
            If the specified RAW or RAWX file does not exist.
        ValueError
            If the input format is unrecognized or invalid.

        Notes:
        ------
        - This method sets several attributes of the Model instance, including
          self.json_data, self.raw_file_path, and self.name.
        - If a cached pickle file exists and force_recalculate is False, it will
          attempt to load the cached data instead of reprocessing the input.
        """
        # Check if input is a JSON string
        if isinstance(file_path_or_json, str) and "{" in file_path_or_json:
            # Attempt to parse the string as JSON
            self.json_data = json.loads(file_path_or_json)
            self.raw_file_path = None
        elif isinstance(file_path_or_json, dict):
            # Input is already a dictionary
            self.json_data = file_path_or_json
            self.raw_file_path = None
        else:
            # Assume input is a file path
            self.raw_file_path = Path(file_path_or_json)

            # Check if we can use cached data
            if not force_recalculate and self.pickle_path.exists():
                # Load model from cached pickle file instead of .raw or .rawx file.
                self.read_pickle()
                return self.json_data

            # Set the name attribute based on the file name
            self.name = self.raw_file_path.stem

            if self.raw_file_path.suffix == ".rawx":
                # Load and clean the JSON data from the file
                self.json_data = load_and_clean_json(self.raw_file_path)
            else:
                self.json_data = raw_file_to_rawx_dict(self.raw_file_path)
        return self.json_data

    def filter_by_area(self, areas: dict | list[str] = INCLUDE_AREAS,
                       inplace: bool = False):
        """
        Filter the Model.network data by specified areas.

        :param areas: Dict or list of area names or IDs to include in the filtered model. Defaults to INCLUDE_AREAS.
        :param inplace: If True, modify the current model. If False, return a new filtered model. Defaults to False.
        :return: A Model instance with data filtered by the specified areas.
        """
        start_time = perf_counter_ns()
        print(f'Model filter_by_area ({self.raw_file_path}) starting...')

        # If inplace == True, work with a copy of the model.
        model = self if inplace else self.copy(deep=True)

        # Filter the model.network by specified areas.
        if not hasattr(model.network, 'filter_by_area'):
            raise AttributeError("The 'network' object does not have a 'filter_by_area' method")
        model.network = model.network.filter_by_area(areas, inplace=inplace)

        if model.network.graph(regenerate=False, empty_ok=True):
            print(f'Model filter_by_area building graph...')
            # Rebuild the network graph only if it existed
            model.network.graph(regenerate=True, empty_ok=False)  # Rebuild the graph (this calls the property getter)
            print(f'Model filter_by_area elapsed time: '
                  f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

        print(f'Model filter_by_area finished: '
              f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

        return model

    def copy(self, deep: bool = True):
        """
        Create a copy of the Model instance.

        This method creates a new Model instance and copies all attributes.
        If deep is True, it performs a deep copy; otherwise, it performs a shallow copy.

        :param deep: If True, create a deep copy. If False, create a shallow copy. Defaults to True.
        :return: A new Model instance with copied attributes.
        """
        # Create a new Model instance
        new_model = Model.__new__(Model)

        # Iterate through all attributes of the current instance
        for attr_name, attr_value in self.__dict__.items():
            if isinstance(attr_value, pd.DataFrame):
                # For DataFrames, use pandas copy method
                new_df = copy.deepcopy(attr_value)
                new_df = getattr(new_model, attr_name)
                if deep:
                    new_df._metadata = copy.deepcopy(attr_value._metadata)
                else:
                    new_df._metadata = attr_value._metadata
                setattr(new_model, attr_name, copy.deepcopy(attr_value))
            elif isinstance(attr_value, nx.Graph):
                # For networkx Graph, use its copy method
                if deep:
                    setattr(new_model, attr_name, copy.deepcopy(attr_value))
                else:
                    setattr(new_model, attr_name, copy.deepcopy(attr_value))
            elif isinstance(attr_value, (General, Network, Harmonics, TimeSeries)):
                # For custom classes, use their copy method if available, otherwise deepcopy
                if hasattr(attr_value, 'copy'):
                    setattr(new_model, attr_name, attr_value.copy(deep=True))
                else:
                    setattr(new_model, attr_name, copy.deepcopy(attr_value) if deep else copy.copy(attr_value))
            else:
                # For other attributes, use Python's copy or deepcopy
                if deep:
                    setattr(new_model, attr_name, copy.deepcopy(attr_value))
                else:
                    setattr(new_model, attr_name, copy.copy(attr_value))

        return new_model

    def network_dfs(self):
        """
        Retrieve all pandas DataFrames stored as attributes in the Network instance.

        This method is a used for accessing and managing the various power system
        component DataFrames within the Network object. It dynamically collects all attributes
        of the Network instance that are pandas DataFrames, providing a comprehensive view of
        the network model's data.  This is important, since the structure of the "network"
        section of a RAWX file may change in future PSS/e releases.

        The method performs the following operations:
        1. Iterates through all attributes of the Network instance.
        2. Identifies attributes that are pandas DataFrames.
        3. Creates a dictionary with attribute names as keys and the corresponding
           DataFrames as values.

        Returns:
        --------
        Dict[str, pd.DataFrame]
            A dictionary where each key is the name of a network component (e.g., 'bus',
            'branch', 'generator'), and each value is the corresponding pandas DataFrame
            containing that component's data.

        Notes:
        ------
        - This method is particularly useful for bulk operations on all network components,
          such as filtering, data export, or comprehensive network analysis.
        - The returned dictionary includes all DataFrames, regardless of their size or content,
          allowing for complete access to the network model's data.
        - The method relies on the convention that all network component data in the Network
          class is stored as pandas DataFrames.
        - This method is often used in conjunction with other Network methods or in the
          Model class for operations that need to iterate over all network components.

        Example Usage:
        --------------
        # Inside a method of Model or Network class
        def some_operation(self):
            for df_name, df in self.network_dfs().items():
                # Perform some operation on each DataFrame
                print(f"{df_name} has {len(df)} rows")
        """

        return {_: getattr(self.network, _) for _ in dir(self.network)
                if isinstance(getattr(self.network, _), pd.DataFrame)}

    @property
    def csv_folder(self) -> Path:
        """
        Generate and return the path to the folder where CSV files will be exported.

        This method creates a Path object representing the folder where CSV files
        for this model will be stored. The folder name is derived from the model's
        pickle file name, ensuring a unique and identifiable location for each model's
        CSV exports.

        Returns:
        --------
        Path
            A Path object representing the folder where CSV files will be stored.
            The folder is located in the same directory as the model's CSV export path.

        Notes:
        ------
        - The method does not actually create the folder; it only generates the Path.
        - The folder name is based on the stem of the pickle file path, which typically
          includes a unique identifier for the model.
        - This method ensures consistency between different export methods (CSV)
          by using the same base path.
        - The returned path can be used directly in file operations, such as creating
          the directory or saving files.

        Example:
        --------
        model = Model('path/to/rawx/file.rawx')
        csv_folder_path = model.csv_folder
        print(csv_folder_path)
        # Might print something like:
        # /path/to/exports/rawx_file_model

        # To use the path:
        csv_folder_path.mkdir(parents=True, exist_ok=True)
        (csv_folder_path / 'some_data.csv').write_text('data')

        See Also:
        ---------
        to_csv : Method that uses this folder path to export CSV files.
        csv_filepath : Property that determines the base directory for exports.
        """
        if not hasattr(self, '_csv_folder') or self._csv_folder is None:
            self._csv_folder = site_data_dir / f"{self.pickle_path.stem}"
            self._csv_folder.parent.mkdir(parents=True, exist_ok=True)
        return self._csv_folder

    @csv_folder.setter
    def csv_folder(self, value: Path):
        self._csv_folder = value

    def __getstate__(self):
        """Prepare object for pickling."""
        state = self.__dict__.copy()
        # Ensure _csv_folder and _pickle_path are stored as strings if they exist
        if state.get('_csv_folder'):
            state['_csv_folder'] = str(state['_csv_folder'])
        if state.get('_pickle_path'):
            state['_pickle_path'] = str(state['_pickle_path'])
        return state

    def __setstate__(self, state):
        """Restore object from pickling."""
        self.__dict__.update(state)
        if '_csv_folder' in state and state['_csv_folder']:
            state['_csv_folder'] = Path(state['_csv_folder'])
        if '_pickle_path' in state and state['_pickle_path']:
            state['_pickle_path'] = Path(state['_pickle_path'])
        self.__dict__.update(state)

    def to_csv(self):
        """
        Export the Model data to a series of CSV files.

        This method exports various components of the Model object to separate CSV files.
        It creates a folder named after the model and saves individual CSV files for general
        information and each DataFrame in the network section.

        The method performs the following steps:
        1. Creates a folder to store the CSV files.
        2. Exports general information about the model.
        3. Exports each DataFrame from the network section to its own CSV file.

        Returns:
        --------
        None

        Side Effects:
        -------------
        - Creates a new folder in the file system.
        - Writes multiple CSV files to the created folder.

        Raises:
        -------
        IOError: If there are issues creating the folder or writing the files.

        Notes:
        ------
        - The folder name is derived from the model's pickle path stem.
        - Each network DataFrame is exported with its index included.
        - This method can be time-consuming for large models with many DataFrames.
        - The resulting CSV files can be used for external analysis or as a human-readable
          backup of the model data.

        Example:
        --------
        model = Model('path/to/rawx/file.rawx')
        model.to_csv()
        # This will create a folder like 'model_name' containing CSV files like:
        # - general.csv
        # - network_bus.csv
        # - network_branch.csv
        # ... and so on for each DataFrame in the network section.
        """
        start_time = perf_counter_ns()
        print(f'Exporting model ({self.pickle_path}) ...')

        # Create the folder to store CSV files
        csv_folder = self.csv_folder
        csv_folder.mkdir(parents=True, exist_ok=True)

        # Export general information
        csv_path = csv_folder / 'general.csv'
        print(f'Exporting {str(csv_path)}...')
        general_df = pd.DataFrame([self.version], columns=['version'])
        general_df.to_csv(csv_path)
        print(f'Elapsed export time: {((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

        # Export each DataFrame from the network section
        for section, df in self.network_dfs().items():
            csv_path = csv_folder / f'network_{section}.csv'
            print(f'Exporting {str(csv_path)}...')
            df.to_csv(csv_path, index=True)
            print(f'Elapsed export time: {((perf_counter_ns() - start_time) / 1e9):.9f} seconds...')
        print(f'Finished exporting to CSV files: {csv_path.parent}')

    @property
    def pickle_path(self) -> Path:
        """
        Get the path for the pickle file associated with this Model instance.

        This property manages the location where the serialized (pickled) version of the
        Model object will be stored or retrieved from. It ensures that the pickle file
        has a consistent and predictable location based on the model's attributes.

        Returns:
        --------
        Path
            A Path object representing the location of the pickle file.

        Notes:
        ------
        - If the pickle path has been previously set, it returns that path.
        - If not set, it generates a path based on the following priority:
          1. Using the stem of raw_file_path if it exists
          2. Using the model's name if it exists
        - The generated path is always within the site_cache_dir.
        - The file extension is always '.model'.
        - This method ensures the parent directory of the pickle path exists.

        Example:
        --------
        >>> model = Model('path/to/rawx/file.rawx')
        >>> print(model.pickle_path)
        /path/to/site_cache_dir/file.model
        """
        if not hasattr(self, '_pickle_path'):
            self._pickle_path = None
        if self._pickle_path is None:
            if hasattr(self, 'raw_file_path') and self.raw_file_path:
                self._pickle_path = site_cache_dir / f"{self.raw_file_path.stem}.model"
            elif hasattr(self, 'name') and self.name:
                self._pickle_path = site_cache_dir / f'{self.name}.model'
            else:
                raise ValueError("Unable to determine pickle path. Neither raw_file_path nor name is set.")
            self._pickle_path.parent.mkdir(parents=True, exist_ok=True)
        return self._pickle_path

    @pickle_path.setter
    def pickle_path(self, new_path: Path | str):
        """
        Set a custom path for the pickle file associated with this Model instance.

        This setter allows manual specification of where the serialized (pickled) version
        of the Model object should be stored or retrieved from.

        Parameters:
        -----------
        new_path : Path | str
            The new path for the pickle file. Can be either a Path object or a string.

        Raises:
        -------
        AssertionError
            If the provided path does not have a '.model' extension.

        Notes:
        ------
        - The provided path must have a '.model' extension.
        - This method ensures the parent directory of the new pickle path exists.
        - Use this setter with caution, as it overrides the default path generation logic.

        Example:
        --------
        >>> model = Model('path/to/rawx/file.rawx')
        >>> model.pickle_path = '/custom/path/mymodel.model'
        >>> print(model.pickle_path)
        /custom/path/mymodel.model
        """
        new_path = Path(new_path)
        assert new_path.suffix == '.model', "Pickle path must have a '.model' extension"
        self._pickle_path = new_path
        self._pickle_path.parent.mkdir(parents=True, exist_ok=True)

    def to_pickle(self, resilient: bool = True) -> bool:
        """
        Cache the ModelComparison to a pickle file.

        Args:
            resilient (bool): If True, return False if pickling fails instead of raising an exception

        Returns:
            bool: True if caching was successful, False otherwise
        """
        pickled: bool = to_pickle(pickle_path=self.pickle_path, data=self, resilient=resilient)
        print('Saved: ', self.pickle_path)
        return self.pickle_path if pickled else None

    def read_pickle(self, mode: str = 'rb', resilient: bool = True):
        """
        Read the Model from a pickle file.

        Args:
            mode (str): File open mode, should always be 'rb'
            resilient (bool): If True, warn instead of raising an exception on failure

        Raises:
            FileNotFoundError: If the pickle file is not found and resilient is False
        """
        # read_pickle(pickle_path=file_path, resilient=resilient)
        """
        Read the model from a pickle file.
        :param mode: Should always be 'rb'.
        :return: FpPickleType(pickle_path, obj), where obj is the unpickled object.
        """
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
        except Exception as e:
            if resilient:
                warnings.warn(f'Could not load file {str(self.pickle_path)}. {str(e)}')
            else:
                raise e
        if obj:
            return FpPickleType(self.pickle_path, obj)
        else:
            return FpPickleType(None, None)


if __name__ == '__main__':
    export_format = 'None' # 'csv' or 'None'

    print(f'Starting psse_model_util/rawx/model.py...')
    start = perf_counter_ns()

    from psse_model_util.common.dirs import clear_site_cache

    clear_site_cache()


    fp = Path(__file__).parent.parent / r'tests\data\sample_34.raw'

    pickle_path = site_cache_dir / fp.with_suffix('.model').name
    if not pickle_path.exists():
        model = Model(file_path_or_json=fp, force_recalculate=True)
        if 'sample' in model.name:
            native_model = model.copy(deep=True)
        else:
            native_model = model.filter_by_area(areas=INCLUDE_AREAS, inplace=False)
        native_model.network.append_bus_info_to_dfs()
        native_graph = native_model.network.graph(regenerate=True)
        native_model.to_pickle()
    else:
        native_model = read_pickle(pickle_path=pickle_path)
        native_graph = native_model.network.graph(regenerate=False,
                                                      empty_ok=False)

    print(f"Native Network graph: {native_graph.number_of_nodes()} nodes, "
          f"{native_graph.number_of_edges()} edges.")

    if export_format == 'csv':
        csv_folder = native_model.csv_folder
        print('CSV:', csv_folder)
        native_model.to_csv()

    print(f'Finished psse_model_util/rawx/model.py: '
          f'{((perf_counter_ns() - start) / 1e9):.9f} seconds')
