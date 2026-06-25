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

The following classes are used to represent specific sections of the RAW/RAWX file.  They
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

    from psse_model_util.model import Model
    model = Model('path/to/rawx/file.rawx')

You can then access different sections of the model, manipulate data, filter the model,
or perform graph analysis:

    network_graph = model.network.graph()
    filtered_model = model.filter_by_area(areas=['AREA1', 'AREA2'])

This module is designed to be memory-efficient and performant, suitable for handling
large bulk-electric-system (BES) power-flow models.

If you load a model once, you can save the Model object to disk directly as a
pickle, to make loading it in the future much cheaper and much faster!
"""

# Rest of the module code follows...
import copy
import json
import pickle
import warnings
from collections import defaultdict, namedtuple
from datetime import datetime as dtdt
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Callable, Dict, List, Union  # Union

import networkx as nx
import networkx.exception

# from psse_model_util.common.dirs import site_data_dir
# from psse_model_util.common.classes import (BusId, IdStr, IdInt,
#                                             ZoneId, AreaId, OwnerId, SwShID)
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from psse_model_util.common.constants import INCLUDE_AREAS
from psse_model_util.common.dataframe_util import convert_df_column_dtypes
from psse_model_util.common.dirs import copy_doc, site_cache_dir, site_data_dir
from psse_model_util.common.file_util import read_pickle, to_pickle
from psse_model_util.common.json_util import load_and_clean_json
from psse_model_util.common.logging_config import get_log_file_path, setup_logger
from psse_model_util.dataformat.rawx_json_template import rawx_json_template
from psse_model_util.dataformat.section_schema import SectionSchema
from psse_model_util.raw_to_rawx import raw_file_to_rawx_dict

FpPickleType = namedtuple('FpPickleType', ['file_path', 'object'])
logger = setup_logger('model')


def _fmt_kv(v) -> str:
    """
    Render a base-kV value compactly with a 'kV' suffix.

    Strips meaningless trailing zeros and a bare trailing decimal point, so
    ``500.0`` -> ``'500kV'``, ``34.5`` -> ``'34.5kV'``, ``123.450`` ->
    ``'123.45kV'``. Returns ``''`` for missing values.
    """
    if pd.isna(v):
        return ''
    f = float(v)
    if f == int(f):
        s = str(int(f))
    else:
        s = f'{f:f}'.rstrip('0').rstrip('.')
    return f'{s}kV'


class ModelEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for Model class data.

    Handles serialization of:
    - NumPy types (integer, floating, arrays)
    - Pandas DataFrames
    - None/NaN values
    - Other objects via string representation

    This encoder is used for both saving models to JSON and internal JSON conversion.
    """

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient='split')
        elif pd.isna(obj):
            return None
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


class ModelDecoder(json.JSONDecoder):
    """
    Custom JSON decoder for Model class data.

    Handles deserialization of specially formatted model data, converting
    back from the JSON-safe format produced by ModelEncoder.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, dct):
        # Handle DataFrame reconstruction if the dict has the pandas split-format structure
        if all(key in dct for key in ('index', 'columns', 'data')):
            return pd.DataFrame(**dct)
        return dct


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
                elif dtype is int or (isinstance(dtype, type) and issubclass(dtype, int)):
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
    Base class for the Network, Timeseries and Harmonics classes, each
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
            logger.warning(f'Error loading model section to pd.DataFrame.  {str(e)}')
            logger.warning(f'    subsection: {self.subsection}')
            logger.warning(f'    fields: {len(fields)} {fields}')
            logger.warning(f'    data: {len(data)} {data}')
            logger.warning(f'    meta: {len(meta)} {meta}')
            raise

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
            else:
                # For other attributes, use Python's copy or deepcopy
                if deep:
                    setattr(new_abstract_section, attr_name, copy.deepcopy(attr_value))
                else:
                    setattr(new_abstract_section, attr_name, copy.copy(attr_value))

        return new_abstract_section


class Network(AbstractSection):
    """Manages power system network component data and topology analysis.

    The Network class encapsulates all power system equipment data (buses, branches,
    generators, etc.) and provides methods for filtering, analysis and topology
    exploration. It serves as the primary interface for accessing and manipulating
    network data within a Model instance.

    Args:
        section (Dict[str, Any]): Raw network data from RAWX/JSON format
        generate_graph (bool, optional): Pre-generate network topology graph

    Attributes:
        acline (pd.DataFrame): AC transmission line data
        bus (pd.DataFrame): Bus data and properties
        generator (pd.DataFrame): Generator unit data
        load (pd.DataFrame): Load data
        transformer (pd.DataFrame): Transformer data
        swshunt (pd.DataFrame): Switched shunt data
        fixshunt (pd.DataFrame): Fixed shunt data
        area (pd.DataFrame): Area definitions
        zone (pd.DataFrame): Zone definitions
        owner (pd.DataFrame): Equipment ownership data
        _graph (nx.Graph): Network topology representation

    Methods:
        filter_by_area: Filter network to specified areas
        graph: Generate/retrieve network topology graph
        append_bus_info_to_dfs: Add bus data to related equipment
        section_with_bus: Join equipment data with associated bus info
        copy: Create independent copy of network data

    Example:
        # >>> from model import Model
        >>> fp = r"path/to/Model_1.raw"
        >>> model = Model(fp, name="Summer_Peak")
        >>> network = model.network
        >>>
        >>> # Access equipment data
        >>> critical_buses = network.bus[network.bus['baskv'] >= 345]
        >>>
        >>> # Filter network
        >>> filtered = network.filter_by_area(['AREA1', 'AREA2'])
        >>>
        >>> # Analyze topology
        >>> g = network.graph()
        >>> paths = nx.all_pairs_shortest_path(g)
    """

    def __init__(self, section: Dict[str, Any], generate_graph: bool = False):
        """
        Initialize the Network class with data from the 'network' section.

        :param section: Dictionary containing the 'network' section data
        """
        start_time = perf_counter_ns()

        # These initializations are not needed as they are set in the loop below,
        # but helps developers using IDEs to see the structure.
        self.acline: pd.DataFrame = pd.DataFrame()
        self.adjust: pd.DataFrame = pd.DataFrame()
        self.area: pd.DataFrame = pd.DataFrame()
        self.bus: pd.DataFrame = pd.DataFrame()
        self.caseid: pd.DataFrame = pd.DataFrame()
        self.facts: pd.DataFrame = pd.DataFrame()
        self.fixshunt: pd.DataFrame = pd.DataFrame()
        self.general: pd.DataFrame = pd.DataFrame()
        self.generator: pd.DataFrame = pd.DataFrame()
        self.load: pd.DataFrame = pd.DataFrame()
        self.msline: pd.DataFrame = pd.DataFrame()
        self.newton: pd.DataFrame = pd.DataFrame()
        self.owner: pd.DataFrame = pd.DataFrame()
        self.rating: pd.DataFrame = pd.DataFrame()
        self.solver: pd.DataFrame = pd.DataFrame()
        self.swshunt: pd.DataFrame = pd.DataFrame()
        self.sysswd: pd.DataFrame = pd.DataFrame()
        self.transformer: pd.DataFrame = pd.DataFrame()
        self.twotermdc: pd.DataFrame = pd.DataFrame()
        self.tysl: pd.DataFrame = pd.DataFrame()
        self.vscdc: pd.DataFrame = pd.DataFrame()
        self.zone: pd.DataFrame = pd.DataFrame()

        logger.info('Network.__init__ starting...')
        self._section_schemas: dict[str, SectionSchema] = {}
        for subsection, data in section.items():
            logger.info(f'Network.__init__ creating dataframe {subsection}...')
            self.subsection = subsection  # Added to aid in debugging
            df = self._create_dataframe(data)
            setattr(self, subsection, df)
            logger.info(f'Network.__init__ elapsed: '
                        f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

        self._orig_dfs_cache: dict[str, pd.DataFrame] = dict()
        self._orig_dfs_cache['bus'] = copy.deepcopy(self.bus)

        self._graph: nx.Graph = self.graph(regenerate=True) if generate_graph else nx.Graph()
        logger.info(f'Network.__init__  finished: '
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
        if 'fields' not in data.keys():
            logger.info(f'data keys: {list(data.keys())}')
            logger.info(f'data[:100]: {str(data)[:100]} ...')
            logger.error('Error creating Model.network dataframe.  data does not contain "fields".')
            raise ValueError('Error creating Model.network dataframe.  data does not contain "fields".')
        fields: list = data.pop('fields')
        values: list = data.pop('data')
        meta: dict = data

        # Build and register the typed schema for this section (registry is the
        # new source of truth; the df._metadata writes below are legacy and are
        # removed in a later task).
        if self.subsection in rawx_json_template['network']:
            self._section_schemas[self.subsection] = SectionSchema.from_template(
                rawx_json_template['network'][self.subsection], fields)
        else:
            self._section_schemas[self.subsection] = SectionSchema()

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
            logger.warning(f'Error creating pd.DataFrame for model section, {self.subsection}.  {str(e)}')
            logger.warning(f'network subsection:, {self.subsection}')
            logger.warning(f'fields: {len(fields)} {fields}')
            logger.warning(f'data:, {len(data)}, {data}')
            logger.warning(f'meta: {len(meta)}, {meta}')
            raise

        # Coerce dtypes and set the index using the registry schema (no metadata
        # is written onto the frame).
        schema = self._section_schemas.get(self.subsection, SectionSchema())

        if schema.data_type:
            df = convert_df_column_dtypes(df_in=df,
                                          new_dtypes=dict(schema.data_type),
                                          convert_all_columns=True,
                                          default_types=(int, float, str))

        if schema.id_cols:
            id_cols = [c for c in schema.id_cols if c in df.columns]
            ommited_from_index = set(schema.id_cols) - set(df.columns)
            if ommited_from_index:
                warnings.warn(
                    f'Unable to move columns to index (may be okay for models older '
                    f'than v35): {str(ommited_from_index)}.')
            try:
                df.set_index(id_cols, inplace=True)
            except KeyError as e:
                warnings.warn(f'Error moving columns {str(id_cols)} to index. {str(e)}')

        return df

    def section_schema(self, section: str) -> SectionSchema:
        """Return the SectionSchema for a section, or an empty schema if unknown."""
        return self._section_schemas.get(section, SectionSchema())

    def bus_cols(self, section: str) -> tuple[str, ...]:
        """Bus-number columns for a section (empty tuple if none/unknown)."""
        return self.section_schema(section).bus_cols

    def id_cols(self, section: str) -> tuple[str, ...]:
        """Unique-equipment index columns for a section (empty tuple if none/unknown)."""
        return self.section_schema(section).id_cols

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
        logger.info(f'Adding bus information to {section} starting...')
        # Get the specified section's DataFrame
        df = getattr(self, section)
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"{section} is not a DataFrame attribute of Network.")
        df = copy.deepcopy(df)

        # Get the bus columns from the registry
        bus_cols = self.bus_cols(section)

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

        # Build an area-number → area-name lookup from network.area (if available).
        # Used below to produce a human-readable {bus_col}_area_name column.
        area_name_map: pd.Series | None = None
        if isinstance(self.area, pd.DataFrame) and not self.area.empty and 'arname' in self.area.columns:
            area_name_map = self.area['arname']

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

            # Add {bus_col}_area_name by mapping the joined area number through
            # the area DataFrame.  Falls back gracefully when area data is absent.
            area_col = f'{bus_col}_area'
            area_name_col = f'{bus_col}_area_name'
            if area_name_map is not None and area_col in df.columns:
                df[area_name_col] = df[area_col].map(area_name_map)

        # Build a human-readable `derived_name` from the joined bus fields plus
        # the equipment's own identifier(s):
        #   single-bus:  "<name> <kv>kV - <id>"
        #   multi-bus:   "<name> <kv>kV - <name> <kv>kV <id>"  (bare id, no label)
        # A 'ckt' identifier (acline, transformer, sysswd) is labelled "CKT".
        # Absent buses (e.g. kbus=0 on a two-winding transformer) are skipped.
        id_cols = self.id_cols(section)
        equip_id_cols = [c for c in id_cols if c not in bus_cols and c in df.columns]

        # One "<name> <kv>kV" segment per bus column; empty where the bus is absent.
        bus_segments = []
        for bus_col in bus_cols:
            name_col, baskv_col = f'{bus_col}_name', f'{bus_col}_baskv'
            if name_col in df.columns and baskv_col in df.columns:
                seg = (df[name_col].fillna('').astype(str).str.strip()
                       + ' ' + df[baskv_col].map(_fmt_kv)).str.strip()
                bus_segments.append(seg.where(df[name_col].notna(), ''))

        if bus_segments:
            # Join present segments with ' - ' (skip empty segments row-wise).
            derived = bus_segments[0]
            for seg in bus_segments[1:]:
                derived = pd.Series(
                    np.where(seg.str.len() > 0, derived + ' - ' + seg, derived),
                    index=df.index,
                )
            if equip_id_cols:
                # Render each id column; a 'ckt' column gets the "CKT" label.
                tokens = []
                for col in equip_id_cols:
                    val = df[col].fillna('').astype(str).str.strip()
                    tokens.append('CKT ' + val if col == 'ckt' else val)
                equip_id = tokens[0]
                for tok in tokens[1:]:
                    equip_id = equip_id + ' ' + tok
                # single-bus joins the id with ' - '; multi-bus with a space
                sep = ' - ' if len(bus_segments) == 1 else ' '
                derived = derived + sep + equip_id.str.strip()
            df['derived_name'] = derived.str.strip()

        # Restore the original index
        df.set_index(original_index_columns, inplace=True)
        if not isinstance(df.index, pd.MultiIndex) and original_index_columns[0] == 'index':
            df.index.name = None

        # If inplace, update the original DataFrame
        if inplace:
            setattr(self, section, df)

        logger.info(f'Finished adding bus information to {section}: '
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
            bus_cols = self.bus_cols(section)
            if (section != 'bus'
                    and bus_cols
                    and self.section_schema(section).data_type
                    and not df.empty
                    and all(c in df.columns or c in df.index.names for c in bus_cols)):
                self.section_with_bus(section, inplace=True)

    def filter_by_area(self, areas: dict | list[str] = INCLUDE_AREAS,
                       inplace: bool = False,
                       graph_effect: str = 'clear') -> 'Network':
        """
        Filter the network data by the specified areas, removing all equipment
        (not) in or connected to equipment in those areas.

        How? Filters the `bus` DataFrame based on the provided areas,
        then filters network component dfs by their bus references
        (as defined in each DataFrame's `_metadata['bus_cols']`).

        Graph: Updates the network graph according to the `graph_effect` option.

        Args:
            areas (dict | list[str], optional): Areas to retain in the filtered
                network. Defaults to INCLUDE_AREAS
            inplace (bool, optional): If True, modifies the current Network object
                If False, returns a new filtered copy. Defaults to Falsem
            graph_effect (str, optional): Determines how the network graph should
                be handled after filtering:
                    - 'clear': resets the graph to empty
                    - 'regenerate': rebuilds the graph
                    - 'leave': leaves the current graph unchanged
                Defaults to 'clear'

        Returns:
            Network: Filtered network instance (same instance if inplace=True)

        Raises:
            ValueError: If the areas list is empty after preprocessing.
        """
        logger.info("Network.filter_by_area: starting area filtering...")

        # Normalize areas argument
        areas = list(areas.keys()) if isinstance(areas, dict) else copy.deepcopy(areas)
        if not areas:
            raise ValueError("The areas list is empty after preprocessing.")

        # If inplace network = self, else network = copy of self.
        network: 'Network' = self if inplace else self.copy()

        # Filter bus DataFrame by area
        logger.info(f"Network.filter_by_area: filtering buses for areas: {areas}")
        network.bus = network.bus[network.bus['area'].isin(areas)]

        filtered_buses = set(network.bus.index)
        logger.info(f"Network.filter_by_area: retained {len(filtered_buses)} buses after area filtering.")

        # Filter all DataFrames that reference buses
        for attr_name, df in network.__dict__.items():
            if isinstance(df, pd.DataFrame) and attr_name != 'bus':
                bus_cols = network.bus_cols(attr_name)
                if not bus_cols:
                    continue  # skip DataFrames without bus references
                # Check if bus_cols are in the columns or index
                index_bus_cols = [col for col in bus_cols if col in df.index.names]
                column_bus_cols = [col for col in bus_cols if col in df.columns]

                if index_bus_cols:
                    # If bus_cols in index
                    mask = df.index.get_level_values(index_bus_cols[0]).isin(filtered_buses)
                    for col in index_bus_cols[1:]:
                        mask |= df.index.get_level_values(col).isin(filtered_buses)
                    logger.info(f"Network.filter_by_area: filtering index-based DataFrame '{attr_name}'")
                elif column_bus_cols:
                    # If bus_cols in columns
                    mask = np.any(np.isin(df[column_bus_cols].values, list(filtered_buses)), axis=1)
                    logger.info(f"Network.filter_by_area: filtering column-based DataFrame '{attr_name}'")
                else:
                    # If no bus_cols in index or columns, keep all and warn
                    warnings.warn(f"Network.filter_by_area: no bus columns found in '{attr_name}', keeping all rows.")
                    continue

                df = df[mask]
                setattr(network, attr_name, df)

        # Handle network graph based on graph_effect argument
        logger.info(f"Network.filter_by_area: applying graph_effect='{graph_effect}'")
        if graph_effect == 'clear':
            network._graph = nx.Graph()
        elif graph_effect == 'regenerate':
            network.graph(regenerate=True)
        elif graph_effect == 'leave':
            logger.info("Network.filter_by_area: leaving graph unchanged.")
        else:
            raise ValueError(f"Invalid value for graph_effect '{graph_effect}'. "
                            "Expected one of 'clear', 'regenerate', or 'leave'.")

        logger.info("Network.filter_by_area: area filtering complete.")
        return network

    def filter_section(self, section: str, where_clause: str,
                       inplace: bool = False,
                       graph_effect: str = 'clear') -> Union['Network', pd.DataFrame]:
        """
        Filter a specific section's DataFrame using a where clause.

        This method allows SQL-like filtering of any section DataFrame in the Network object.
        It can either modify the Network in place or return a filtered copy of just the
        section DataFrame or the entire Network.

        Args:
            section (str): Name of the section/DataFrame to filter (e.g., 'bus', 'acline')
            where_clause (str): SQL-like where clause to filter the DataFrame (e.g., 'baskv >= 345')
            inplace (bool): If True, modify Network in place. If False, return filtered copy.
                Defaults to False.
            graph_effect (str): How to handle the network graph after filtering:
                - 'clear': Clear the graph (must be regenerated when needed)
                - 'regenerate': Regenerate the graph immediately
                - 'leave': Leave the graph unchanged
                Defaults to 'clear'.

        Returns:
            Union[Network, pd.DataFrame]: If inplace=True, returns filtered DataFrame.
            If inplace=False, returns new Network instance with filtered data.

        Raises:
            ValueError: If section doesn't exist or where_clause is invalid
            AttributeError: If section exists but is not a DataFrame

        Examples:
            >>> # Filter buses to voltage >= 345 kV
            >>> filtered_buses = network.filter_by_section('bus', 'baskv >= 345')
            >>>
            >>> # Filter generators to certain statuses in place
            >>> network.filter_by_section('generator', 'stat == 1', inplace=True)
            >>>
            >>> # Create new Network with only large transformers
            >>> new_net = network.filter_by_section('transformer', 'mbase > 1000',
            ...                                     inplace=False)

        Notes:
            - The where_clause is passed directly to pandas.DataFrame.query()
            - For complex conditions, use parentheses: '(col1 > 0) & (col2 < 100)'
            - Column names in where_clause must exist in the section DataFrame
            - The method preserves the DataFrame's metadata
        """
        logger.info(f"Network.filter_by_section: starting filtering on section '{section}' "
                    f"with where_clause='{where_clause}' (inplace={inplace}, graph_effect='{graph_effect}')")

        # Validate section exists and is a DataFrame
        if not hasattr(self, section):
            raise ValueError(f"Section '{section}' does not exist in Network")

        df = getattr(self, section)
        if not isinstance(df, pd.DataFrame):
            raise AttributeError(f"'{section}' is not a DataFrame")

        try:
            # Apply the filter using pandas query
            filtered_df = df.query(where_clause)
            logger.info(f"Network.filter_section: filtered '{section}' down to {len(filtered_df)} rows")
        except Exception as e:
            logger.error(f"Network.filter_section: failed to filter '{section}' with error: {str(e)}")
            raise ValueError(f"Invalid where clause: '{where_clause}'. Error: {str(e)}")

        if inplace:
            # Update the section in place
            setattr(self, section, filtered_df)
            logger.info(f"Network.filter_section: updated section '{section}' in place")

            # Handle graph effects
            self._handle_graph_effect(graph_effect)

            return filtered_df
        else:
            # Create a new Network instance with the filtered section
            new_network = self.copy(deep=True)
            setattr(new_network, section, filtered_df)
            logger.info(f"Network.filter_section: created new network with filtered section '{section}'")

            # Handle graph effects for the new network
            new_network._handle_graph_effect(graph_effect)

            return new_network

    def filter_by_kv(self, low_value: float = 0.0,
                     high_value: float = float('inf'),
                     inplace: bool = False,
                     graph_effect: str = 'clear') -> 'Network':
        """
        Filter network equipment based on voltage level criteria.

        This method filters buses and related equipment based on a voltage range.
        For buses, it uses their base kV. For branches and transformers, it uses
        the highest voltage level of connected buses.

        Args:
            low_value (float): Minimum voltage in kV (inclusive). Defaults to 0.0.
            high_value (float): Maximum voltage in kV (exclusive). Defaults to infinity.
            inplace (bool): If True, modify Network in place. If False, return filtered copy.
                Defaults to False.
            graph_effect (str): How to handle the network graph after filtering:
                - 'clear': Clear the graph (must be regenerated when needed)
                - 'regenerate': Regenerate the graph immediately
                - 'leave': Leave the graph unchanged
                Defaults to 'clear'.

        Returns:
            Network: Filtered Network instance (same instance if inplace=True)

        Raises:
            ValueError: If low_value >= high_value or if values are negative

        Examples:
            >>> # Get network with only 230-500 kV equipment
            >>> high_voltage = network.filter_by_kv(230, 500)
            >>>
            >>> # Filter network to sub-transmission (69-230 kV)
            >>> network.filter_by_kv(69, 230, inplace=True)
            >>>
            >>> # Get EHV network (345+ kV)
            >>> ehv = network.filter_by_kv(345)

        Notes:
            - Buses are filtered based on their base kV (baskv column)
            - Equipment connected to multiple buses (e.g., branches) are kept if any
              connected bus is within the voltage range and exists in filtered network
            - Filtering is done efficiently using vectorized operations
            - The method preserves DataFrame metadata
        """
        # Input validation
        if low_value < 0:
            raise ValueError("low_value cannot be negative")
        if high_value <= low_value:
            raise ValueError("high_value must be greater than low_value")

        # Work on a copy if not inplace
        network = self if inplace else self.copy(deep=True)

        # First filter buses by voltage
        bus_df = network.bus
        voltage_mask = (bus_df['baskv'] >= low_value) & (bus_df['baskv'] < high_value)
        filtered_buses = bus_df[voltage_mask]

        # Save the filtered bus indices for equipment filtering
        valid_buses = set(filtered_buses.index)

        # Update bus DataFrame
        network.bus = filtered_buses

        # Filter other equipment based on bus connections
        for section_name, df in network.model_dfs().items():
            if section_name == 'bus':
                continue

            bus_cols = network.bus_cols(section_name)
            if not bus_cols:
                continue

            # Reset index if necessary to access bus columns
            if isinstance(df.index, pd.MultiIndex):
                df_reset = df.reset_index()
            else:
                df_reset = df.copy()

            # Create mask for equipment connected to valid buses
            mask = np.zeros(len(df_reset), dtype=bool)
            for bus_col in bus_cols:
                if bus_col in df_reset.columns:
                    # Only consider connections to buses that exist in filtered network
                    valid_connections = df_reset[bus_col].isin(valid_buses)
                    mask |= valid_connections

            # Apply filter
            filtered_df = df_reset[mask]

            # Restore index if needed
            if isinstance(df.index, pd.MultiIndex):
                filtered_df.set_index(df.index.names, inplace=True)

            # Update section in network
            setattr(network, section_name, filtered_df)

        # Handle graph effect
        network._handle_graph_effect(graph_effect)

        return network

    def _handle_graph_effect(self, graph_effect: str):
        """
        Handle graph modifications based on the specified effect.

        Args:
            graph_effect (str): The graph effect to apply:
                - 'clear': Clear the graph
                - 'regenerate': Regenerate the graph
                - 'leave': Leave the graph unchanged

        Raises:
            ValueError: If graph_effect is not one of the allowed values
        """
        if graph_effect == 'clear':
            self._graph = nx.Graph()
        elif graph_effect == 'regenerate':
            self.graph(regenerate=True)
        elif graph_effect == 'leave':
            pass
        else:
            raise ValueError(f"Invalid graph_effect '{graph_effect}'. "
                             f"Must be 'clear', 'regenerate', or 'leave'")

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
                new_df = copy.deepcopy(attr_value)
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
        bus_df: pd.DataFrame = getattr(self, 'bus')
        try:
            bus_dict = bus_df.to_dict('index')
        except ValueError as e:
            logger.warning('df head')
            logger.warning(bus_df.head())
            logger.warning('df describe')
            logger.warning(bus_df.describe())
            logger.warning('df info')
            logger.warning(bus_df.info())
            logger.warning('bus_df.index')
            logger.warning(bus_df.index.names)
            logger.warning(bus_df.index.values)
            logger.error(f'Error adding buses to network graph {str(e)}')
            raise e

        nodes = [(('bus', ibus), props) for ibus, props in bus_dict.items()]
        self._graph.add_nodes_from(nodes)

        # 2) Add equipment
        sections = self.model_dfs()
        for section, df in sections.items():
            # Skip buses (already done above.
            # Skip substations, as they are complex and not present in typical planning models.
            if section.startswith('sub') or section == 'bus':
                # Do not add substations to model
                continue

            schema = self.section_schema(section)
            logger.debug(f'{section} schema: {schema}')

            # Skip rawx sections that do not have bus information, as they
            # do not get added to the network graph.
            # Also skip sections without data_type: those sections did not have
            # _metadata written by _create_dataframe (legacy behaviour preserved
            # until a later task removes the _metadata writes entirely).
            if not schema.bus_cols or not schema.id_cols or not schema.data_type:
                # Do not add items to the network graph if they don't have any
                # associated buses and clear identifiers.
                continue

            # Get a list of column names that contain bus numbers or equipment IDs.
            bus_cols, id_cols = schema.bus_cols, schema.id_cols
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
                    for row in df.itertuples():
                        props = row._asdict()
                        props.update({'section': section, 'id_cols': id_cols, 'bus_cols': bus_cols})
                        i, j, k, ckt = row.Index  # for 2-winding transformer, k = 0.
                        # 3 nodes for 3-winding and 2 nodes for 2-winding transformers.
                        tx_node = (section, i, j, k) if k else (section, i, j)
                        self._graph.add_node(tx_node, **props)
                        self._graph.add_edge(tx_node, ('bus', i), **props)
                        self._graph.add_edge(tx_node, ('bus', j), **props)
                        if k:
                            tx_node = (section, i, j)
                            self._graph.add_edge(tx_node, ('bus', k), **props)

        return self._graph

    def find_tie_lines(
        self,
        native_areas: dict | list | set | None = None,
        kv_min: float | None = None,
        kv_max: float | None = None,
    ) -> pd.DataFrame:
        """Return AC lines where exactly one terminal bus is in native_areas.

        Lines where both terminals are native (internal) and lines where neither
        terminal is native (external-to-external) are excluded.

        Args:
            native_areas: Areas considered "native". Defaults to INCLUDE_AREAS.
                Accepts dict {area_num: name}, list, or set of area numbers.
            kv_min: If set, both terminal buses must have baskv >= kv_min.
            kv_max: If set, both terminal buses must have baskv <= kv_max.

        Returns:
            Enriched acline DataFrame with ibus_area, ibus_baskv, ibus_name,
            jbus_area, jbus_baskv, jbus_name columns appended.
        """
        if native_areas is None:
            native_areas = INCLUDE_AREAS
        area_set = set(native_areas.keys()) if isinstance(native_areas, dict) else set(native_areas)

        df = self.section_with_bus('acline')

        ibus_native = df['ibus_area'].isin(area_set)
        jbus_native = df['jbus_area'].isin(area_set)
        df = df[ibus_native ^ jbus_native]

        if kv_min is not None:
            df = df[(df['ibus_baskv'] >= kv_min) & (df['jbus_baskv'] >= kv_min)]
        if kv_max is not None:
            df = df[(df['ibus_baskv'] <= kv_max) & (df['jbus_baskv'] <= kv_max)]

        return df

    def _buses_within_n_hops(
        self,
        seed_buses: set | list,
        n: int,
    ) -> set[int]:
        """Return bus numbers reachable within N bus-to-bus hops from seed_buses.

        One hop = traversal from one bus to an adjacent bus through any
        connecting equipment. All connecting equipment (AC lines, transformers)
        counts as one bus hop. The synthetic node of a 3-winding transformer is
        treated as a pass-through (not a hop). Seed buses are included in the
        result (0 hops from themselves). Seed buses absent from the graph are
        silently skipped.

        Args:
            seed_buses: Iterable of ibus integers to start from.
            n: Number of bus hops to traverse.

        Returns:
            Set of ibus integers within N bus hops of any seed bus.
        """
        if n == 0:
            g = self.graph()
            return {ibus for ibus in seed_buses if ('bus', ibus) in g}

        g = self.graph()
        frontier = {('bus', ibus) for ibus in seed_buses if ('bus', ibus) in g}
        visited = set(frontier)

        for _ in range(n):
            next_frontier: set = set()
            for node in frontier:
                for neighbor in g.neighbors(node):
                    if neighbor[0] == 'bus':
                        # Direct bus-to-bus edge (AC line)
                        if neighbor not in visited:
                            next_frontier.add(neighbor)
                    else:
                        # Pass-through node (transformer) — look through it to find connected buses.
                        # Look one level further for bus nodes
                        for far in g.neighbors(neighbor):
                            if far[0] == 'bus' and far not in visited:
                                next_frontier.add(far)
            visited |= next_frontier
            frontier = next_frontier
            if not frontier:
                break

        return {node[1] for node in visited}

    def neighborhood(
        self,
        seed_buses: int | set | list,
        n: int,
        output: str = 'network',
    ) -> 'Network | dict[str, pd.DataFrame] | pd.DataFrame':
        """Return all buses within N bus-hops of seed_buses plus connected equipment.

        Calls _buses_within_n_hops to determine the bus set, then filters every
        network section to rows whose bus_cols intersect that set. The result
        includes all equipment (generators, loads, shunts, etc.) connected to
        the neighborhood buses.

        Args:
            seed_buses: Single ibus int or iterable of ibus integers.
            n: Number of bus hops to traverse.
            output: Return format.
                'network' (default) — filtered Network copy.
                'dict' — dict[str, DataFrame] keyed by section name.
                'dataframe' — flat DataFrame with 'section' column prepended;
                    intended for Excel/CSV export, not programmatic use.

        Returns:
            Filtered network data in the requested format.

        Raises:
            ValueError: If output is not 'network', 'dict', or 'dataframe'.
        """
        if output not in ('network', 'dict', 'dataframe'):
            raise ValueError(f"output must be 'network', 'dict', or 'dataframe'; got {output!r}")

        if isinstance(seed_buses, int):
            seed_buses = {seed_buses}

        bus_set = self._buses_within_n_hops(seed_buses, n)
        result = self.copy()

        for attr_name, df in result.__dict__.items():
            if not isinstance(df, pd.DataFrame):
                continue
            bus_cols = result.bus_cols(attr_name)
            if not bus_cols:
                continue

            index_bus_cols = [c for c in bus_cols if c in df.index.names]
            column_bus_cols = [c for c in bus_cols if c in df.columns]

            if index_bus_cols:
                mask = df.index.get_level_values(index_bus_cols[0]).isin(bus_set)
                for col in index_bus_cols[1:]:
                    mask |= df.index.get_level_values(col).isin(bus_set)
            elif column_bus_cols:
                mask = np.any(np.isin(df[column_bus_cols].values, list(bus_set)), axis=1)
            else:
                continue

            filtered = df[mask]
            setattr(result, attr_name, filtered)

        result._graph = nx.Graph()

        if output == 'network':
            return result
        elif output == 'dict':
            return result.model_dfs()
        else:  # 'dataframe'
            return result._to_flat_dataframe()

    def tie_line_neighborhood(
        self,
        n: int,
        native_areas: dict | list | set | None = None,
        side: str = 'both',
        kv_min: float | None = None,
        kv_max: float | None = None,
        output: str = 'network',
    ) -> 'Network | dict[str, pd.DataFrame] | pd.DataFrame':
        """Neighborhood around all tie-line terminals, optionally scoped by side.

        Convenience wrapper: finds tie lines via find_tie_lines(), seeds
        neighborhood() from their terminal buses, then optionally filters the
        result to buses on one side of the area boundary.

        Args:
            n: Number of bus hops to traverse from tie-line terminals.
            native_areas: Areas considered "native". Defaults to INCLUDE_AREAS.
            side: Which side of the boundary to return.
                'both' (default) — no area filter.
                'internal' — keep only buses in native_areas.
                'external' — keep only buses NOT in native_areas.
            kv_min: Passed to find_tie_lines(); filters by terminal bus kV.
            kv_max: Passed to find_tie_lines(); filters by terminal bus kV.
            output: 'network' (default), 'dict', or 'dataframe'.

        Returns:
            Filtered network data in the requested format. Returns an empty
            result (empty-section Network / empty dict / empty DataFrame) when
            no tie lines match the filter criteria.
        """
        if native_areas is None:
            native_areas = INCLUDE_AREAS
        area_set = set(native_areas.keys()) if isinstance(native_areas, dict) else set(native_areas)

        if side not in ('internal', 'external', 'both'):
            warnings.warn(f"Unknown side={side!r}; treating as 'both' and returning full neighborhood.")

        ties = self.find_tie_lines(native_areas=native_areas, kv_min=kv_min, kv_max=kv_max)

        if ties.empty:
            empty = self.copy()
            for attr_name, df in empty.__dict__.items():
                if isinstance(df, pd.DataFrame) and empty.bus_cols(attr_name):
                    empty_df = df.iloc[0:0].copy()
                    setattr(empty, attr_name, empty_df)
            if output == 'network':
                return empty
            elif output == 'dict':
                return empty.model_dfs()
            else:
                return pd.DataFrame()

        seed_buses: set[int] = set()
        for level in ties.index.names:
            if level in ('ibus', 'jbus'):
                seed_buses |= set(ties.index.get_level_values(level))

        result = self.neighborhood(seed_buses, n, output='network')

        if side == 'internal':
            result = result.filter_by_area(list(area_set))
        elif side == 'external':
            external_areas = set(result.bus['area'].unique()) - area_set
            if external_areas:
                result = result.filter_by_area(list(external_areas))

        if output == 'network':
            return result
        elif output == 'dict':
            return result.model_dfs()
        else:  # 'dataframe'
            return result._to_flat_dataframe()

    def _to_flat_dataframe(self) -> pd.DataFrame:
        """Flatten all sections into a single DataFrame with a leading 'section' column.

        Each section's DataFrame is reset to plain columns, given a leading
        'section' column that names the PSS/E section, and concatenated.
        Duplicate column names within a section (e.g. ntermdc) are resolved by
        appending an integer suffix so that pd.concat can align column indexes.
        """
        frames = []
        for section, df in self.model_dfs().items():
            # Drop index levels whose names clash with existing columns to avoid
            # duplicate-column errors when reset_index promotes them into columns.
            drop_levels = [name for name in df.index.names
                           if name is not None and name in df.columns]
            if drop_levels:
                df = df.reset_index(level=drop_levels, drop=True)
            df = df.reset_index()
            if 'section' in df.columns:
                df = df.rename(columns={'section': '_section'})
            df.insert(0, 'section', section)
            # Some sections (e.g. ntermdc) carry pre-existing duplicate column
            # names.  Deduplicate them by appending an integer suffix so that
            # pd.concat can align column indexes across sections.
            if df.columns.duplicated().any():
                seen: dict[str, int] = {}
                new_cols = []
                for col in df.columns:
                    if col in seen:
                        seen[col] += 1
                        new_cols.append(f"{col}_{seen[col]}")
                    else:
                        seen[col] = 0
                        new_cols.append(col)
                df.columns = new_cols
            frames.append(df)
        return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()

    def draw_one_line(self, node_id: tuple, distance: int = 2, theme: str = 'light',
                      load_positions: dict = None, save_positions: bool = True) -> None:
        """
        Create an interactive visualization of the network graph centered around a specific node.

        Parameters
        ----------
        node_id : tuple
            The identifier of the central node, e.g. ('bus', 201)
        distance : int, optional
            Number of edges to traverse from central node (default=2)
        theme : str, optional
            Color theme - 'light' or 'dark' (default='light')
        load_positions : dict, optional
            Dictionary of pre-saved node positions {node_id: (x, y)}
        save_positions : bool, optional
            Whether to save positions after dragging (default=True)

        Returns
        -------
        None
            Displays an interactive plotly figure

        Examples
        --------
        >>> model = Model('path/to/model.raw')
        >>> # Basic draw
        >>> model.network.draw_one_line(('bus', 201), distance=3)
        >>>
        >>> # Dark theme
        >>> model.network.draw_one_line(('bus', 201), theme='dark')
        >>>
        >>> # Load saved positions
        >>> saved_pos = model.network.load_node_positions()
        >>> model.network.draw_one_line(('bus', 201), load_positions=saved_pos)
        """

        # Color themes
        themes = {
            'light': {
                'bg_color': 'white',
                'text_color': 'black',
                'edge_color': '#888',
                'grid_color': '#eee',
                'node_colors': {
                    'default': '#808080',  # Medium gray for non-bus nodes
                    'node_line': '#404040'  # Darker gray for node borders
                }
            },
            'dark': {
                'bg_color': '#1a1a1a',
                'text_color': 'white',
                'edge_color': '#666',
                'grid_color': '#333',
                'node_colors': {
                    'default': '#808080',  # Medium gray for non-bus nodes
                    'node_line': '#a0a0a0'  # Lighter gray for node borders in dark mode
                }
            }
        }

        # Voltage level colors - from low to high voltage
        voltage_colors = [
            (0, '#add8e6'),  # Light blue for low voltage
            (69, '#6495ed'),  # Corn flower blue for sub-transmission
            (115, '#0000ff'),  # Blue for transmission
            (230, '#000080'),  # Navy for high transmission
            (500, '#800080'),  # Purple for extra high voltage
            (765, '#4b0082'),  # Indigo for ultra high voltage
        ]

        def get_voltage_color(kv):
            """Get color based on voltage level"""
            if not kv:
                return themes[theme]['node_colors']['default']
            for i, (volt, color) in enumerate(voltage_colors):
                if kv < volt:
                    if i == 0:
                        return voltage_colors[0][1]
                    # Interpolate between colors
                    prev_volt, prev_color = voltage_colors[i - 1]
                    return color
            return voltage_colors[-1][1]  # Return highest voltage color if above all levels

        # Save/load positions functionality
        def get_positions_file():
            """Get path to positions cache file"""
            cache_dir = Path.home() / '.cache' / 'psse_model_util'
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir / 'node_positions.json'

        def save_node_positions(positions):
            """Save node positions to file"""
            if not save_positions:
                return
            pos_file = get_positions_file()
            # Convert positions to serializable format
            serializable_pos = {str(k): (float(v[0]), float(v[1]))
                                for k, v in positions.items()}
            with open(pos_file, 'w') as f:
                json.dump(serializable_pos, f)

        def load_saved_positions():
            """Load saved positions from file"""
            pos_file = get_positions_file()
            if pos_file.exists():
                with open(pos_file) as f:
                    return json.load(f)
            return {}

        # Ensure graph exists
        if not self._graph or self._graph.number_of_nodes() == 0:
            self.graph(regenerate=True)

        # Get subgraph of nodes within distance
        nodes_in_range = {node_id}
        current_nodes = {node_id}

        for _ in range(distance):
            next_nodes = set()
            for node in current_nodes:
                try:
                    next_nodes.update(self._graph.neighbors(node))
                except networkx.exception.NetworkXException:
                    warnings.warn(f'Unable to add node {node} to one-line diagram.')
            nodes_in_range.update(next_nodes)
            current_nodes = next_nodes

        subgraph = self._graph.subgraph(nodes_in_range)

        # Use provided positions or load saved ones or generate new layout
        if load_positions:
            pos = {node: load_positions[str(node)]
                   for node in subgraph.nodes()
                   if str(node) in load_positions}
            # Generate positions for any missing nodes
            missing_nodes = set(subgraph.nodes()) - set(pos.keys())
            if missing_nodes:
                temp_pos = nx.spring_layout(subgraph.subgraph(missing_nodes))
                pos.update(temp_pos)
        else:
            pos = nx.spring_layout(subgraph)

        # Prepare node traces by type
        node_traces = defaultdict(lambda: {"x": [], "y": [], "text": [],
                                           "hovertext": [], "ids": [], "color": []})

        # Get central node properties for title
        center_props = subgraph.nodes[node_id]
        title = f"One-line Diagram: {node_id}"
        if 'name' in center_props:
            title = f"One-line Diagram: {center_props['name']} {node_id}"

        theme_colors = themes[theme]

        for node in subgraph.nodes():
            x, y = pos[node]
            node_type = node[0] if isinstance(node, tuple) else str(node)

            # Get node properties for hover text
            props = subgraph.nodes[node]
            hover_text = "<br>".join([f"{k}: {v}" for k, v in props.items()])

            if 'name' in props:
                display_text = f"{props['name']}\n({str(node)})"
            else:
                display_text = str(node)

            # Determine node color
            if node_type == 'bus' and 'baskv' in props:
                node_color = get_voltage_color(float(props['baskv']))
            else:
                node_color = theme_colors['node_colors']['default']

            node_traces[node_type]["x"].append(x)
            node_traces[node_type]["y"].append(y)
            node_traces[node_type]["text"].append(str(display_text))
            node_traces[node_type]["hovertext"].append(hover_text)
            node_traces[node_type]["ids"].append(str(node))
            node_traces[node_type]["color"].append(node_color)

        # Node styling
        node_style = {
            "bus": dict(
                symbol="circle-dot",
                size=20,
                line=dict(color=theme_colors['node_colors']['node_line'], width=2)
            ),
            "generator": dict(
                symbol="star",
                size=20,
                line=dict(color=theme_colors['node_colors']['node_line'], width=2)
            ),
            "load": dict(
                symbol="triangle-down",
                size=20,
                line=dict(color=theme_colors['node_colors']['node_line'], width=2)
            ),
            "transformer": dict(
                symbol="square-x",
                size=20,
                line=dict(color=theme_colors['node_colors']['node_line'], width=2)
            ),
            "fixshunt": dict(
                symbol="diamond",
                size=15,
                line=dict(color=theme_colors['node_colors']['node_line'], width=2)
            )
        }

        default_style = dict(
            symbol="circle",
            size=15,
            line=dict(color=theme_colors['node_colors']['node_line'], width=1)
        )

        traces = []

        for node_type, nodes in node_traces.items():
            style = node_style.get(node_type, default_style)
            style['color'] = nodes["color"]  # Use calculated colors

            # Special handling for transformers
            if node_type == 'transformer':
                hovertemplate = "%{hovertext}<extra></extra>"  # Force hover text display
            else:
                hovertemplate = None

            trace = go.Scatter(
                x=nodes["x"],
                y=nodes["y"],
                mode='markers+text',
                text=nodes["text"],
                ids=nodes["ids"],
                textposition="top center",
                hovertext=nodes["hovertext"],
                hoverinfo="text",
                hovertemplate=hovertemplate,  # Add hover template for transformers
                marker=style,
                name=node_type,
                customdata=nodes["ids"],
            )
            traces.append(trace)

        # Create edge traces
        edge_x = []
        edge_y = []
        edge_text = []

        for edge in subgraph.edges(data=True):
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            edge_props = "<br>".join([f"{k}: {v}" for k, v in edge[2].items()])
            edge_text.extend([edge_props, edge_props, None])  # We add None for the line break

        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            mode='lines',
            line=dict(width=1.5, color=theme_colors['edge_color']),
            hoverinfo='text',
            hovertext=edge_text,
            name='connections'
        )

        traces.append(edge_trace)

        # Add voltage color key before creating the figure:
        voltage_key_text = [f"{int(volt)} kV" for volt, _ in voltage_colors]
        # Add "< " to first and "> " to last value
        voltage_key_text[0] = f"< {voltage_key_text[0]}"
        voltage_key_text[-1] = f"> {voltage_key_text[-1]}"

        voltage_key = go.Scatter(
            x=[-1.2] * len(voltage_colors),  # Place on far left
            y=np.linspace(-0.2, 0.5, len(voltage_colors)),
            mode='markers+text',
            text=voltage_key_text,
            textposition="middle right",
            marker=dict(
                size=20,
                color=[color for _, color in voltage_colors],
                symbol='square',
                line=dict(color=theme_colors['text_color'], width=1)
            ),
            name="Bus Voltage",
            hoverinfo='none',
            legendgroup='voltage',
            legendgrouptitle_text='Bus Voltage Levels',  # Add group title
            showlegend=False
        )

        traces.append(voltage_key)

        # Create figure with theme-aware layout
        fig = go.Figure(
            data=traces,
            layout=go.Layout(
                title=dict(
                    text=title,
                    x=0.5,
                    y=0.95,
                    xanchor='center',
                    yanchor='top',
                    font=dict(size=16, color=theme_colors['text_color'])
                ),
                showlegend=True,
                legend=dict(
                    x=0.02,  # Position legend on left side
                    y=1,  # Position at top
                    xanchor='left',
                    yanchor='top',
                    bgcolor='rgba(255,255,255,0.8)' if theme == 'light' else 'rgba(0,0,0,0.8)',
                    bordercolor=theme_colors['text_color'],
                    borderwidth=1,
                    title=dict(
                        text='Network Components',  # Add legend title
                        side='top'
                    )
                ),
                hovermode='closest',
                margin=dict(b=20, l=120, r=50, t=40),  # Increased left margin for legend
                xaxis=dict(
                    showgrid=False,
                    zeroline=False,
                    showticklabels=False,
                    gridcolor=theme_colors['grid_color'],
                    range=[-1.3, 1.3],  # Adjust range to show voltage key
                ),
                yaxis=dict(
                    showgrid=False,
                    zeroline=False,
                    showticklabels=False,
                    gridcolor=theme_colors['grid_color']
                ),
                plot_bgcolor=theme_colors['bg_color'],
                paper_bgcolor=theme_colors['bg_color'],
                dragmode='select',  # 'pan'
                modebar=dict(
                    orientation='v',
                    bgcolor='rgba(0,0,0,0)',
                    color=theme_colors['text_color'],
                    activecolor=theme_colors['edge_color']
                ),
                annotations=[
                    dict(
                        text="",  # Bus Voltage Levels
                        x=-1.2,
                        y=1.05,
                        xref="x",
                        yref="y",
                        showarrow=False,
                        font=dict(color=theme_colors['text_color']),
                        xanchor='center'
                    )
                ],
                newshape=dict(line_color='cyan'),
                font=dict(color=theme_colors['text_color'])
            )
        )

        # Save final positions
        if save_positions:
            save_node_positions(pos)

        # Show with config
        # Show figure with corrected config
        fig.show(config={
            'editable': True,
            'displaylogo': False,
            'modeBarButtonsToAdd': [
                'select',
                'pan2d',
                'drawopenpath',
                'select2d',
                'eraseshape',
                'dragmode'  # Add drag mode button
            ],
            'modeBarButtonsToRemove': [
                'lasso2d',
                'zoomIn2d',
                'zoomOut2d',
                'autoScale2d'
            ],
            'scrollZoom': True,
            'displayModeBar': True,
            'toImageButtonOptions': {
                'format': 'svg',
                'filename': f'one_line_{node_id}'
            }
        })

    def load_node_positions(self) -> dict:
        """
        Load previously saved node positions from cache.

        Returns
        -------
        dict
            Dictionary of node positions {node_id: (x, y)}
        """
        cache_file = Path.home() / '.cache' / 'psse_model_util' / 'node_positions.json'
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return {}


class Harmonics(AbstractSection):
    """
    Represents the 'harmonics' section of the PSSE v35 RAWX (JSON) file.
    RAW-sourced .rawx files do not contain harmonics data, so this section
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
    RAW-sourced .rawx files do not contain timeseries data, so this section
    has minimal functionality.
    """

    def __init__(self, section: Dict[str, Any]):
        """
        Initialize the TimeSeries class with data from the 'timeseries' section.

        :param section: Dictionary containing the 'timeseries' section data
        """
        super().__init__(section)


class Model:
    """Comprehensive representation of a PSS/E power system model from RAW/RAWX files.

    The Model class serves as the primary interface for loading, processing, and analyzing
    PSS/E v33-35 power system models. It provides structured access to network topology,
    equipment data, and analysis capabilities.

    Attributes:
        name (str): Identifier for the model, derived from input file or user-specified
        raw_file_path (Path): Source RAW/RAWX file location
        json_data (dict): Structured representation of model data
        general (General): Model metadata and version information
        network (Network): Power system component data and topology
        harmonics (Harmonics): Harmonic analysis data if present
        timeseries (TimeSeries): Time-dependent data if present
        version (float): PSS/E version number of the model

    Args:
        file_path_or_json (Union[str, dict, Path]): Input source - either file path or
            preloaded data
        name (str, optional): Custom identifier for the model
        force_recalculate (bool, optional): Force reprocessing even if cache exists

    Raises:
        FileNotFoundError: If specified input file does not exist
        JSONDecodeError: If JSON data is invalid
        ValueError: If input format is unrecognized

    Example:
        >>> # Load from RAW file
        >>> from model import Model
        >>> fp = r"path/to/Model_1.raw"
        >>> model = Model(fp, name="Summer_Peak")
        >>>
        >>> # Filter to specific areas
        >>> filtered = model.filter_by_area({101: 'AREA1', 102: 'AREA2'})
        >>>
        >>> # Access network data
        >>> buses = model.network.bus
        >>> lines = model.network.acline
        >>>
        >>> # Analyze network topology
        >>> graph = model.network.graph()
        >>> path = nx.shortest_path(graph, ('bus', 201), ('bus', 205))
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
        logger.info('Model __init__ starting.')

        # Initialize basic attributes
        self.name: str = name  # If not name, self._read_json will set a name.
        self.raw_file_path: Path = None  # site_data_dir / f"rawx_{dtdt.now().strftime('%Y_%m_%d_%H_%M_%S')}.model"
        self.json_data = {}

        # Load the RAW or RAWX data
        logger.info('Model __init__ loading model from disk...')
        self._read_json(file_path_or_json, force_recalculate=force_recalculate)

        # Set up the pickle path for caching
        self._pickle_path = None
        self.pickle_path  # This calls the property setter to initialize the path

        # Check if we can load from a cached pickle file
        if not force_recalculate and self.pickle_path and self.pickle_path.exists():
            self.read_pickle()
            logger.info(f'Model __init__ ({self.pickle_path}) finished: '
                        f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')
            return

        # Set up the pickle path for caching
        self._csv_folder = None
        self.csv_folder  # This calls the property setter to initialize the path

        logger.info(f'Model __init__ elapsed time: '
                    f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')
        logger.info('Model __init__ building pd.DataFrames...')

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
                except Exception:
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
        logger.info('Model __init__ caching to disk...')
        self.to_pickle()

        logger.info(f'Model __init__ elapsed time: '
                    f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')
        logger.info(f'Model __init__ ({self.raw_file_path}) finished: '
                    f'{((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

    def _prepare_json_data(self, data: dict) -> dict:
        """
        Prepare dictionary data for JSON serialization.

        Args:
            data: Dictionary containing model data

        Returns:
            Dictionary with all values converted to JSON-serializable format
        """
        serializable_data = {}
        for key, value in data.items():
            if isinstance(value, dict):
                serializable_data[key] = {}
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, dict):
                        # Handle nested dictionary structure
                        if 'fields' in subvalue and 'data' in subvalue:
                            serializable_data[key][subkey] = {
                                'fields': subvalue['fields'],
                                'data': [
                                    [str(item) if item is not None else None for item in row]
                                    if isinstance(row, list) else str(row)
                                    for row in subvalue['data']
                                ]
                            }
                    else:
                        serializable_data[key][subkey] = subvalue
            else:
                serializable_data[key] = value
        return serializable_data

    def to_json(self, file_path: Path = None) -> str:
        """
        Convert the model to a JSON string or save to a file.

        Args:
            file_path: Optional path to save JSON file

        Returns:
            JSON string representation of the model
        """
        serializable_data = self._prepare_json_data(self.json_data)
        json_str = json.dumps(serializable_data, cls=ModelEncoder)

        if file_path:
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(json_str)

        return json_str

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
            # Attempt to parse the string as JSON using custom decoder
            try:
                self.json_data = json.loads(file_path_or_json, cls=ModelDecoder)
            except TypeError as e:
                warnings.warn(str(e))
                self.json_data = json.loads(file_path_or_json)
            self.raw_file_path = None
        elif isinstance(file_path_or_json, dict):
            # Input is already a dictionary
            self.json_data = file_path_or_json
            self.raw_file_path = None
        elif Path(file_path_or_json).suffix.lower() == '.model':
            self.raw_file_path = Path(file_path_or_json).with_suffix('.raw')
            if not self.raw_file_path.exists():
                self.raw_file_path = self.raw_file_path.with_suffix('.raw')

            # Only set name if not explicitly provided in __init__
            if not self.name:
                self.name = self.raw_file_path.stem

            self.read_pickle()
        else:
            # Assume input is a file path
            self.raw_file_path = Path(file_path_or_json)

            # Check if we can use cached data
            if not force_recalculate and self.pickle_path.exists():
                # Load model from cached pickle file instead of .raw or .rawx file.
                self.read_pickle()
                return self.json_data

            # Set the name attribute based on the file name
            if not self.name:
                self.name = self.raw_file_path.stem

            if self.raw_file_path.suffix == ".rawx":
                # Load and clean the JSON data from the file
                self.json_data = load_and_clean_json(self.raw_file_path)
            else:
                self.json_data = raw_file_to_rawx_dict(self.raw_file_path)
        return self.json_data

    @copy_doc(Network.filter_by_area)
    def filter_by_area(self,
                       areas: dict | list[str] = INCLUDE_AREAS,
                       inplace: bool = False,
                       graph_effect: str = 'clear') -> 'Model':
        # This method delegates to Network.filter_by_area.
        # The inherited docstring describes expected behavior.
        model = self if inplace else self.copy(deep=True)
        model.network.filter_by_area(
            areas=areas,
            inplace=True,
            graph_effect=graph_effect
        )
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

    def network_dfs(self) -> Dict[str, pd.DataFrame]:
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
            if not self.pickle_path:
                logger.warning("Unable to set Model.csv_folder, because pickle_path is None.")
                self._csv_folder = None
                return self._csv_folder
            self._csv_folder = site_data_dir / f"{self.pickle_path.stem}"
            self._csv_folder.parent.mkdir(parents=True, exist_ok=True)
        if self._csv_folder and not isinstance(self._csv_folder, Path):
            self._csv_folder = Path(self._csv_folder)
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
        logger.info(f'Exporting model ({self.pickle_path}) ...')

        # Create the folder to store CSV files
        csv_folder = self.csv_folder
        csv_folder.mkdir(parents=True, exist_ok=True)

        # Export general information
        csv_path = csv_folder / 'general.csv'
        logger.info(f'Exporting {str(csv_path)}...')
        general_df = pd.DataFrame([self.version], columns=['version'])
        general_df.to_csv(csv_path)
        logger.info(f'Elapsed export time: {((perf_counter_ns() - start_time) / 1e9):.9f} seconds.')

        # Export each DataFrame from the network section.
        # Include the index only when it holds named fields (MultiIndex or named
        # single index).  A plain RangeIndex has index.names == [None] and
        # should be excluded to avoid a spurious unnamed column in the CSV.
        for section, df in self.network_dfs().items():
            csv_path = csv_folder / f'network_{section}.csv'
            logger.info(f'Exporting {str(csv_path)}...')
            include_index = any(name is not None for name in df.index.names)
            df.to_csv(csv_path, index=include_index)
            logger.info(f'Elapsed export time: {((perf_counter_ns() - start_time) / 1e9):.9f} seconds...')
        logger.info(f'Finished exporting to CSV files: {csv_path.parent}')

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
        >>> from model import Model
        >>> fp = r"path/to/Model_1.raw"
        >>> model = Model(fp)
        >>> print(model.pickle_path)
        path/to/cache/Model_1.model
        """
        if not hasattr(self, '_pickle_path'):
            self._pickle_path = None
        if self._pickle_path is None:
            if hasattr(self, 'raw_file_path') and self.raw_file_path:
                self._pickle_path = site_cache_dir / f"{self.raw_file_path.stem}.model"
            elif hasattr(self, 'name') and self.name:
                self._pickle_path = site_cache_dir / f'{self.name}.model'
            else:
                logger.warning("Unable to determine pickle path. Neither raw_file_path nor name is set.")
                return None
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
         >>> from model import Model
        >>> fp = r"path/to/Model_1.raw"
        >>> model = Model(fp)
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
        logger.info(f'Saved: {self.pickle_path}')
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
        except Exception as e:
            if resilient:
                warnings.warn(f'Could not load file {str(self.pickle_path)}. {str(e)}')
            else:
                raise

        # Save current name before loading attributes
        original_name = self.name

        # Load attributes from pickled object
        attr_names = [attr for attr in dir(obj) if not attr.startswith('__')]
        for attr_name in attr_names:
            try:
                setattr(self, attr_name, getattr(obj, attr_name))
            except Exception as e:
                warnings.warn(f'Unable to load attribute "{attr_name}" from cache. {str(e)}')

        # Restore original name if one was provided
        if original_name:
            self.name = original_name

        logger.info(f'Data loaded from cache: "{self.pickle_path}".')
        if obj:
            return FpPickleType(self.pickle_path, obj)
        else:
            return FpPickleType(None, None)


if __name__ == '__main__':
    export_format = 'None'  # 'csv' or 'None'

    logger.info('Starting psse_model_util/model.py...')
    start = perf_counter_ns()

    from psse_model_util.common.dirs import clear_site_cache

    clear_site_cache()

    fp = Path(__file__).parent.parent / r'tests\data\sample_34.raw'
    # fp = Path(__file__).parent.parent / r'tests\data\Model_1.raw'

    pickle_path = site_cache_dir / fp.with_suffix('.model').name
    if not pickle_path.exists():
        model = Model(file_path_or_json=fp, force_recalculate=True)
        if 'sample' in model.name:
            # Example native areas
            NATIVE_AREAS = {101: 'CENTRAL', 206: 'EAST', 301: 'CENTRAL_DC'}

            # Example neighboring areas
            NEIGHBOR_AREAS = {401: 'EAST_COGEN1', 3011: 'WEST', 402: 'EAST_COGEN2'}

            # Combined dictionary of native and neighboring areas, used for filtering models
            INCLUDE_AREAS = NEIGHBOR_AREAS.copy() | NATIVE_AREAS.copy()
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

    try:
        native_model.network.draw_one_line(node_id=('bus', 201), distance=2)
        logger.info(f"Native Network graph: {native_graph.number_of_nodes()} nodes, "
                    f"{native_graph.number_of_edges()} edges.")
    except Exception as e:
        warnings.warn(str(e))

    if export_format == 'csv':
        csv_folder = native_model.csv_folder
        logger.info(f'CSV: {csv_folder}')
        native_model.to_csv()

    logger.info(f'Finished psse_model_util/rawx/model.py: '
                f'{((perf_counter_ns() - start) / 1e9):.9f} seconds')
    print(f'Log file: {get_log_file_path(logger)}')
