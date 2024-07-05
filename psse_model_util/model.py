import pickle
import warnings
import typing
from typing import Union, Dict
from pathlib import Path
from collections import namedtuple
from typing import List
from itertools import combinations

from psse_model_util.raw_parser import read_case_raw
from psse_model_util.rawx_parser import read_case_rawx
from psse_model_util.common.classes import (BusId, AreaId, Voltage, Admittance, Resistance, Name,
                                            ActivePower, ZoneId, Rating, OwnerId, OwnerFraction,
                                            Capacitance, Impedance, Inductance, PowerFactor,
                                            Susceptance, ReactivePower, IdStr, IdInt, Status)
from psse_model_util.common import dirs
from psse_model_util.common.dataframe_util import df_to_excel_worksheet
from psse_model_util.constants import RangeFilterType, NATIVE_AREAS, DEFAULT_KV_FILTER, GEN_MW_FILTER, BUS_COL_NAMES, \
    RESILIENT, BUS_TYPES
from psse_model_util import dataformat34

import pandas as pd
import networkx as nx


# Define a type variable
ModelType = typing.TypeVar('ModelType', bound='Model')

FpPickleType = namedtuple('FpPickleType', ['file_path', 'object'])


class Equipment:
    """
    A converter class that initializes itself with attributes based on a provided dictionary.
    """

    def __init__(self, equip_type: str, props_in: dict):
        """
        Initializes a new instance with attributes corresponding to the input
        dictionary's keys and values.

        :param equip_type:
        :param props_in: A dictionary where keys represent attribute names and
                    values represent attribute values.
        """
        self.type: str = equip_type
        self.name: str = ''
        self._orig_props = props_in
        self._extended_name: str = ''

        # (1) Get the name of the section in the .raw file for this equipment
        # and (2) Get a dict of {column name: dtype} for the section.
        self.raw_section, col_dtypes = None, {}
        df_name = equip_type
        if 'header' not in equip_type and not equip_type.endswith('_df'):
            df_name += '_df'
        try:
            self.raw_section = dataformat34.RAW_PROP_SECTION_MAP[df_name]
            col_dtypes = dataformat34.DTYPE_RAW_DATA[self.raw_section]
        except (IndexError, KeyError) as e:
            warnings.warn(f'Could not find {equip_type} in psse_model_util.dataformat34.RAW_PROP_SECTION_MAP')

        # Rename properties to be snake_case.
        props = {key.lower().strip().replace(' ', '_').replace('\n', '').replace('-', '_'): value
                 for key, value in props_in.items()}

        # Try to group props_in into groups like areas, buses, etc based on
        # custom data types.  For these groups, we will add attributes that are
        # dicts like: buses = {'I': 1003, 'J': 1004}.
        grouped_props = (('area_ids', AreaId), ('zone_ids', ZoneId), ('buses', BusId), ('admittance', Admittance),
                         ('mw', ActivePower), ('r', Resistance), ('ratings', Rating), ('owners', OwnerId),
                         ('owner_fractions', OwnerFraction), ('C', Capacitance), ('z', Impedance), ('l', Inductance),
                         ('pf', PowerFactor), ('b', Susceptance), ('var', ReactivePower), ('ids', IdStr),
                         ('ids', IdInt), ('status', Status), ('kv', Voltage)
                         )
        attr_template, subbed_props = dict(), []
        for attr_name, attr_dtype in grouped_props:
            if isinstance(col_dtypes, list):
                col_dtypes = {key: value for d in col_dtypes for key, value in d.items()}
            found_keys = [k for k, v in col_dtypes.items() if v == attr_dtype]
            if found_keys:
                props[attr_name] = {k: v for k, v in props_in.items() if k in found_keys}
                subbed_props += [_.lower() for _ in props[attr_name].keys()]

        # For any props_in not added to grouped attributes above, add them as
        # individual attributes.
        for k, v in props.items():
            dtype = type(v)
            if k not in subbed_props:
                match k:
                    case 'isw':
                        self.slack_bus = props['isw']
                    case _:
                        setattr(self, k, v)

        for new_attr, grouped_attr in (('area_id', 'area_ids'),
                                       ('zone_id', 'zone_ids'),
                                       ('zone_id', 'zone_ids'),
                                       ('bus_id', 'buses'),
                                       ('id', 'ids'),
                                       ):
            if hasattr(self, grouped_attr) and len(getattr(self, grouped_attr)) == 1:
                setattr(self, new_attr, list(getattr(self, grouped_attr).values())[0])

    @property
    def bus_df(self) -> pd.DataFrame:
        """
        Get or create self.buses_df with columns 'BUS' and 'BUS_ID'
        If self._buses_df exists return it.  Else, create it from the dict,
        self._orig_props['buses'].

        :return: A pandas DataFrame with columns 'BUS' and 'BUS_ID', where
                 'BUS' corresponds to the keys of the input dictionary and
                 'BUS_ID' corresponds to the values.

        Example output (pd.DataFrame):
           BUS  BUS_ID
        0   I     123
        1   J     456
        """
        if not hasattr(self, 'buses'):
            return

        if not hasattr(self, '_buses_df') or self._buses_df.empty:
            # Convert the dictionary into a list of tuples, then create a DataFrame
            data = list(self.buses.items())
            self._buses_df = pd.DataFrame(data, columns=['BUS', 'BUS_ID'])

        return self._buses_df

    @property
    def edge_pairs(self) -> tuple[tuple]:
        """
        Find all edge-pairs for this Equipment.
        Equipment may (or may not) have buses and id.  For example, areas do not
        have assigned buses.  For equipment ath has at elast two edges (for
         example (a) at least 2 buses or (b) one bus and one id value), we can
         create pairs of edges to add to our network graph.
        :return: tuple of edge-pairs for this Equipment.
        """
        if not hasattr(self, 'buses'):
            # If equip does not have buses, it does not have edges.
            return

        if not hasattr(self, '_edge_pairs') or not self._edge_pairs:
            edges = []
            if hasattr(self, 'buses'):
                # Get all bus IDs except whatn bus ID is zero, such as in the 3rd
                # winding, K, of a 2-winding transformer.
                edges += [_ for _ in self.buses.values() if _ != 0]
            if len(edges) == 1 and hasattr(self, 'id'):
                edges.append(f'{edges[0]}.{self.id}')
            # Create bus value pairs from bus ID values:
            self._edge_pairs = combinations(edges, 2)

        return self._edge_pairs

    @property
    def extended_name(self):
        raise NotImplementedError
        # if self.name is None:


class Model:
    def __init__(self, file_path: Union[str, Path],
                 force_recalculation: bool = False,
                 pickle_path: Path | str = None):
        """

        :param file_path_or_dataframe_model:
        """
        self.version: float = 0  # 0 indicates unknown PSS/e version number.
        self.force_recalculation = force_recalculation
        self.header: pd.DataFrame = pd.DataFrame()
        self.bus_df: pd.DataFrame = pd.DataFrame()
        self.load_df: pd.DataFrame = pd.DataFrame()
        self.load_df._metadata = {'bus_cols': ['I'], 'ID_col': 'ID'}
        self.fixed_shunt_df: pd.DataFrame = pd.DataFrame()
        self.fixed_shunt_df._metadata = {'bus_cols': ['I'], 'ID_col': 'ID'}
        self.generator_df: pd.DataFrame = pd.DataFrame()
        self.generator_df._metadata = {'bus_cols': ['I'], 'ID_col': 'ID'}
        self.branch_df: pd.DataFrame = pd.DataFrame()
        self.branch_df._metadata = {'bus_cols': ['I', 'J'], 'ID_col': 'ID'}
        self.system_switching_device_df: pd.DataFrame = pd.DataFrame()
        self.system_switching_device_df._metadata = {'bus_cols': ['I', 'J'], 'ID_col': 'CKT'}
        self.transformer_df: pd.DataFrame = pd.DataFrame()
        self.transformer_df._metadata = {'bus_cols': ['I', 'J', 'K']}
        self.area_df: pd.DataFrame = pd.DataFrame()
        self.two_terminal_dc_df: pd.DataFrame = pd.DataFrame()
        self.vsc_dc_line_df: pd.DataFrame = pd.DataFrame()
        self.branch_df._metadata = {'bus_cols': ['I', 'J']}
        self.impedance_correction_df: pd.DataFrame = pd.DataFrame()
        self.impedance_correction_df._metadata = {'bus_cols': ['I']}
        self.multi_terminal_dc_df: pd.DataFrame = pd.DataFrame()
        self.multi_section_line_df: pd.DataFrame = pd.DataFrame()
        self.multi_section_line_df._metadata = {'bus_cols': ['I', 'J'], 'ID_col': 'ID'}
        self.zone_df: pd.DataFrame = pd.DataFrame()
        self.inter_area_transfer_df: pd.DataFrame = pd.DataFrame()
        self.owner_df: pd.DataFrame = pd.DataFrame()
        self.facts_device_df: pd.DataFrame = pd.DataFrame()
        self.facts_device_df._metadata = {'bus_cols': ['I', 'J']}
        self.switched_shunt_df: pd.DataFrame = pd.DataFrame()
        self.switched_shunt_df._metadata = {'bus_cols': ['I']}
        self.induction_machine_df: pd.DataFrame = pd.DataFrame()
        self.induction_machine_df._metadata = {'bus_cols': ['I'], 'ID_col': 'ID'}
        self.sub_station_df: pd.DataFrame = pd.DataFrame()
        self.sub_station_df._metadata = {'bus_cols': ['I'], 'ID_col': 'ID'}
        self._network_graph: nx.Graph = None
        self._filtered: bool = False  # Used in compare.ModelComparison.
        self._orig_dfs: dict[pd.DataFrame] = dict()

        self.file_path = Path(file_path)
        if self.file_path.suffix.lower() == '.model':
            if self.force_recalculation:
                raise ValueError('If file_path is a .model file, cannot set force_recalculation to True.')
            elif pickle_path:
                raise ValueError('If file_path is a .model file, cannot also specify cache_path.')
            else:
                self.pickle_path = self.file_path.with_suffix('.model')
                self._from_pickle()
        elif self.file_path.suffix.lower() in ['.raw', '.rawx']:
            self.pickle_path = pickle_path or dirs.site_cache_dir / f'{self.file_path.stem}.model'
            self.load_raw()

    @property
    def pickle_path(self) -> Path:
        if not self._pickle_path:
            self._pickle_path = self.file_path.with_suffix('.model')
        return self._pickle_path

    @pickle_path.setter
    def pickle_path(self, new_path: Path | str):
        self._pickle_path = Path(new_path)
        if self._pickle_path.is_dir():
            self._pickle_path = self._pickle_path / f'{self.file_path.stem}.model'
        if self._pickle_path.suffix.lower() != '.model':
            self._pickle_path = self._pickle_path.with_suffix('.model')

    @property
    def attr_names(self) -> List[str]:
        return [attr for attr in dir(self) if not attr.startswith('__')]

    # @property
    # def df_names(self) -> List[str]:
    #     return [attr for attr in dir(self)
    #             if not attr.startswith('__')
    #             and isinstance(getattr(self, attr), pd.DataFrame)]

    def _from_pickle(self, mode: str = 'rb', resilient: bool = RESILIENT) -> FpPickleType:
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

    def _to_pickle(self, resilient: bool = RESILIENT) -> bool:
        """
        Cache the parsed model data (dict[dict]) to a pickle file, so it can be
        loaded in future runs without the need to parse the raw file.
        :param resilient: If True, return False if loading pickle fails.
                          If False, raise error if loading pickle fails.
        :return: True is data was read
        """
        self.pickle_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.pickle_path, 'wb') as file:
                pickle.dump(self, file)
                print(f'Cached Model to disk as "{self.pickle_path}".')
                return True
        except Exception as e:
            if resilient:
                warnings.warn(f'Unable to cache Model to disk as "{self.pickle_path}".  {str(e)}')
                return False
            else:
                raise e

    def load_raw(self, append_derived_names: bool = False):
        """
        Loads model data.  If file_path_or_dataframe_model is a dict[pd.DataFrame],
        then we have the model data in memory already.  If not attempt to load
        data from a cached pickle file.  If cached file does not exist (or
        force_recalculation==True), reads the raw file and pickles it to disk.
        :param append_derived_names: bool: if True, then add a 'DERIVED_NAME'
                    column to self.branch_df that includes bus names, bus kV and Ckt.
                    Adding this info makes the load take much, much longer to run.
        :return: None
        """

        # Read raw file to dict[dict], where each sub-dict is a section of the file, such as branches.
        assert self.file_path.suffix.lower() in ['.raw', '.rawx']
        if self.file_path.suffix.lower() == '.rawx':
            # Read extended raw file (.rawx)
            case_data = read_case_rawx(self.file_path, tables_to_type='list_dict')
            data = case_data['network']
            self.version = float(case_data['general']['version'])
            del case_data
        else:
            # Read raw file (.raw)
            data = read_case_raw(str(self.file_path))
            self.version = data['VERSION']
            data.pop('VERSION')
            if self.file_path.suffix.lower() == '.rawx':
                # TODO: Future .rawx file support.  Consider a mapping file (config file) with mapping of .rawx section
                #    and field names to .raw section and field names.  Place that code here and run it, so methods like
                #    filter and compare work for models imported from .rawx files.
                raise NotImplementedError('PSEE .rawx files can be read and parsed. But, the section names and columns names '
                                          'differ from .raw files.  Which means Model methods like "filter" and "compare" '
                                          'will fail with an exception.')

        def generate_dataframe_model(data):
            """Generates a dictionary with each component dataframe inside it.

            Args:
                data (dict): dictionary data model coming from RAW or SEQ

            Returns:
                dict: dictionary with data tables inside
            """

            def _convert_to_dataframe(data):
                """Generates a table for each entry of the elements. The columns are the fields.

                Args:
                    data (list): components of the RAW or SEQ

                Returns:
                    pd.DataFrame: summary table
                """

                # Empty dict for no data
                if not data:
                    return pd.DataFrame()

                # Headers
                if isinstance(data, dict):
                    return pd.DataFrame(list(data.items()), columns=['Item', 'Value'])
                    # return pd.Series(data)

                # Flatten multiline data
                if isinstance(data[0], list):
                    flatten_data = []
                    for element in data:
                        flatten_dict = {k: v for d in element for k, v in d.items()}
                        flatten_data.append(flatten_dict)
                    data = flatten_data

                # Convert to dataframe
                df = pd.DataFrame(data)
                return df

            df_model = {}
            for key, values in data.items():
                if len(values) == 0:
                    continue

                df_model[key] = _convert_to_dataframe(values)
            return df_model

        def dfs_to_properties(model_dict_of_dfs: Dict[str, pd.DataFrame]):
            """
            Convert the parsed .raw file dataframes to properties of self (i.e., Model).
            Convert each key:value pain in a dict[pd.DataFrame] to self.key = value.
            :param model_dict_of_dfs: dict[pd.DataFrame] from
            self._generate_dataframe_model(psse_model_util.parser.read_case_raw.)
            or from cached dict[pd.DataFrame].
            :return: None
            """

            for key, value in model_dict_of_dfs.items():
                key = key.replace(' ', "_").replace('-', "_").lower().strip()
                if "header" not in key.lower() and not key.endswith('_df'):
                    key += '_df'
                if not hasattr(self, key):
                    setattr(self, key, pd.DataFrame())
                attr = getattr(self, key)
                meta = attr._metadata
                setattr(self, key, value)
                if meta:
                    getattr(self, key)._metadata = meta

        # Convert dict[dict] to dict[pd.DataFrame]
        if not self._orig_dfs:
            self._orig_dfs = generate_dataframe_model(data).copy()

        # Make each df in model_dict_of_dfs a named property of the Model object.
        dfs_to_properties(self._orig_dfs)
        if append_derived_names:
            self.append_derived_names()

        self._network_graph = None
        self._filtered: bool = False

        # Create/replace cache on disk (pickle) if appropriate.
        if ~self.bus_df.empty and (self.force_recalculation or not self.pickle_path.exists()):
            # Model is not empty and pickle file does not exist or should
            # be overwritten, so write the model data to a pickle.
            self._to_pickle()

    def reset_model(self):
        """Remove all filters and clear network graph."""
        if not self._orig_dfs:
            raise NameError('Model._orig_dfs not set.')
        self.load_raw(self._orig_dfs)

    def to_excel(self, file_path: Path | str = None):
        file_path = Path(file_path or self.pickle_path.with_suffix('.xlsx'))
        file_path.parent.mkdir(parents=True, exist_ok=True)

        for name in self.attr_names:
            if not isinstance(getattr(self, name), pd.DataFrame):
                continue
            df = getattr(self, name)
            if isinstance(df, dict):
                # Convert dict to pd.DataFrame
                df = pd.DataFrame(list(df.items()), columns=['property', 'value'])

            if isinstance(df, pd.DataFrame):
                print(f'Writing {name} to {file_path}...')
                try:
                    df_to_excel_worksheet(dataframe=df, sheet_name=name, filepath=file_path)
                except Exception as e:
                    if RESILIENT:
                        warnings.warn(f'Unable to write {name} to "{file_path}".  Exception: {str(e)}')
                    else:
                        raise

    @staticmethod
    def filter_equipment(equipment: pd.DataFrame,
                         bus_id_column_names: list[str] = None,
                         keep_bus_ids: list[int] | set[int] = {-1},
                         kv_column_name: str = None,
                         filter_kv_range: RangeFilterType | tuple[int] = None,
                         area_id_column_names: list[str] = None,
                         filter_area_ids: set[int] | list[int] = None,
                         keep_bus_types: dict = BUS_TYPES,
                         bus_type_column_name: str = 'IDE'
                         ) -> pd.DataFrame:
        """

        :param equipment:
        :param bus_id_column_names:
        :param keep_bus_ids: No matter what, keep buses with these bus IDs
                    even if they'd be lost by application of one of the other
                    filters: kv_column_name, keep_kv_range or keep_area_ids.
        :param kv_column_name: Name(s) of the column(s) in equipment that
                    contain bus IDs.
        :param filter_kv_range: filter to kV within
                    RangeFilterType(min kV, max kV)
        :param area_id_column_names:
        :param filter_area_ids: filter to areas in this list.
        :param keep_bus_types: Any buses of this type will not be filtered out
                    by filter_kv_range.  dict of bus types like
                    {1: 'LOAD', 2: 'GEN', 3: 'SWING', 4: 'SHUTDOWN'}
        :return:
        """
        if equipment.empty:
            return equipment
        if keep_bus_ids is not None:
            keep_bus_ids = set(keep_bus_ids)
        if filter_area_ids is not None:
            filter_area_ids = set(filter_area_ids)
        if area_id_column_names is not None:
            area_id_column_names = list(area_id_column_names)

        result: pd.DataFrame = equipment.copy()
        kept_bus_df: pd.DataFrame = pd.DataFrame()
        if bus_id_column_names and keep_bus_ids is not None:
            match len(bus_id_column_names):
                case 3:
                    result = result[result[bus_id_column_names[0]].isin(keep_bus_ids)
                                    | result[bus_id_column_names[1]].isin(keep_bus_ids)
                                    | result[bus_id_column_names[2]].isin(keep_bus_ids)].copy()
                case 2:
                    result = result[result[bus_id_column_names[0]].isin(keep_bus_ids)
                                    | result[bus_id_column_names[1]].isin(keep_bus_ids)].copy()
                case 1:
                    result = result[result[bus_id_column_names[0]].isin(keep_bus_ids)].copy()
            kept_bus_df = result
            if result.empty:
                return result

        if kv_column_name and filter_kv_range:
            assert len(filter_kv_range) == 2
            result = result[(result[kv_column_name] >= filter_kv_range[0])
                            & (result[kv_column_name] <= filter_kv_range[1])].copy()
            if result.empty:
                return result
        if area_id_column_names and filter_area_ids:
            result = result[result[area_id_column_names[0]].isin(filter_area_ids)].copy()
            match len(area_id_column_names):
                case 3:
                    result = result[result[area_id_column_names[0]].isin(filter_area_ids)
                                    | result[area_id_column_names[1]].isin(filter_area_ids)
                                    | result[area_id_column_names[2]].isin(filter_area_ids)].copy()
                case 2:
                    result = result[result[area_id_column_names[0]].isin(filter_area_ids)
                                    | result[area_id_column_names[1]].isin(filter_area_ids)].copy()
                case 1:
                    result = result[result[area_id_column_names[0]].isin(filter_area_ids)].copy()
            if not kept_bus_df.empty:
                # Concatenate the DataFrames
                combined_df = pd.concat([result, kept_bus_df], ignore_index=True)

                # Drop duplicates: assuming no specific column as identifier, using all columns
                combined_df.drop_duplicates(inplace=True)

                # If you have a specific set of columns to check for duplicates, use:
                # combined_df.drop_duplicates(subset=['column1', 'column2'], inplace=True)

                # Assign the result back to self.bus_df
                result = combined_df.copy()

                # Optional: Reset index if you want a clean index
                result.reset_index(drop=True, inplace=True)
        return result

    def filter_model(self, kv_range: RangeFilterType = DEFAULT_KV_FILTER,
                     areas=NATIVE_AREAS,
                     mw_range: RangeFilterType = GEN_MW_FILTER) -> 'Model':
        """

        :param kv_range: (2-tuple) of min and max kV levels to filter
        :param areas: (list) list of areas to filter
        :param mw_range: (2-tuple) of min and max gen / load levels to filter
        :return: self
        """
        if not areas and not any(kv_range):
            return

        # if self.pickle_path.exists():
        #     self.pickle_path.unlink()

        keep_area_ids = list(areas.keys())

        if keep_area_ids:
            # Filter to requested areas.
            self.area_df = self.filter_equipment(equipment=self.area_df,
                                                 area_id_column_names=['I'],
                                                 filter_area_ids=keep_area_ids)

            # Find bus IDs for buses in areas.  (Do not filter by kV yet).
            area_bus_ids = set(self.bus_df[self.bus_df['AREA'].isin(keep_area_ids)]['I'])
        else:
            keep_area_ids = self.area_df['I'].unique().tolist()
            area_bus_ids = set(self.bus_df['I'])

        # Filter to generators in areas with MW range overlapping mw_range.
        self.generator_df = self.generator_df[
            (self.generator_df['I'].isin(area_bus_ids))
            & (self.generator_df['PT'] >= mw_range[0])
            & (self.generator_df['PB'] <= mw_range[1])
            ]
        # Create a df that is a subset of self.bus_df that contains all buses
        # in the already filtered self.generator_df
        gen_bus_df = self.generator_df['I'].unique().tolist()
        gen_bus_df = self.bus_df[self.bus_df['I'].isin(gen_bus_df)].copy()

        # Filtering Load is out of scope per discussion with Afzal.
        # # Filter to load in keep_area_id with MW range overlapping mw_range.
        # self.load_df = self.load_df[
        #     (self.load_df['AREA'].isin(filter_area_ids))
        #     & (self.load_df['PL'] >= mw_range[0])
        #     & (self.load_df['PL'] <= mw_range[1])
        #     ]

        # Filter buses.
        self.bus_df = self.filter_equipment(equipment=self.bus_df,
                                            kv_column_name='BASKV',
                                            filter_kv_range=kv_range,
                                            area_id_column_names=["AREA"],
                                            filter_area_ids=keep_area_ids,
                                            )

        # Append buses that are under min kV range but have a generator from
        # self.generator_df attached.
        combined_df = pd.concat([self.bus_df, gen_bus_df], ignore_index=True)
        del gen_bus_df
        # Drop duplicates: assuming no specific column as identifier, using all columns
        combined_df.drop_duplicates(inplace=True)
        # Assign the result back to self.bus_df
        self.bus_df = combined_df

        # Optional: Reset index if you want a clean index
        self.bus_df.reset_index(drop=True, inplace=True)

        # Unique list of buses:
        keep_bus_ids = list(self.bus_df['I']) + list(self.generator_df['I'])
        # remove duplicates and preserve order.
        keep_bus_ids = list(dict.fromkeys(keep_bus_ids))

        # Filter equipment by bus (buses are already filtered by kv_range and area).
        # Filter tuple: (dataframe_name, dataframe, bus_column_names)
        # kep_bus_ids will also be used in the filter.
        for df_name in self.attr_names:
            df = getattr(self, df_name)
            skip_dfs = ['load', 'generator', 'inter_area_transfer', 'multi_terminal_dc']
            if not isinstance(df, pd.DataFrame) or df_name in skip_dfs:
                # These sections do not fit the standards of the
                # filter_equipment method. So, they must be handled separately.
                continue
            try:
                section_name = dataformat34.RAW_PROP_SECTION_MAP[df_name]
            except KeyError as e:
                warnings.warn(f'No attribute named "{df_name}" found in Model.  Skipping.')
                continue
            dtype_section = dataformat34.DTYPE_RAW_DATA[section_name]
            if isinstance(dtype_section, list):
                dtype_section = {key: value for d in dtype_section for key, value in d.items()}
            df: pd.DataFrame = getattr(self, df_name)
            if isinstance(df._metadata, dict):
                bus_cols = df._metadata['bus_cols']
            else:
                bus_cols = dict()
            df = self.filter_equipment(equipment=df.copy(),
                                       bus_id_column_names=bus_cols,
                                       keep_bus_ids=keep_bus_ids)
            setattr(self, df_name, df)

        # Filter by area.
        self.inter_area_transfer_df = self.filter_equipment(equipment=self.inter_area_transfer_df,
                                                            area_id_column_names=['ARFROM', 'ARTO'],
                                                            filter_area_ids=keep_area_ids)

        # TODO: Determine if and how to filter additional dataframes of data:
        # self.multi_terminal_dc_df = self.multi_terminal_dc_df.copy()

        self._filtered = True

        # Cache the filtered model
        self._to_pickle()

        return self

    @property
    def filtered(self):
        return self._filtered

    def network_graph(self, force_recalculation: bool = None,
                      add_derived_names: bool = False):
        """
        Creates a NetworkX graph from bus_data and branch_data contained in the model_reader.

        Returns:
        -------
        G : NetworkX Graph
            The network model represented as a graph.
        """
        if force_recalculation is None:
            force_recalculation = self.force_recalculation

        if not force_recalculation:
            if self._network_graph:
                return self._network_graph

        # Initialize an empty graph. Use nx.DiGraph() for a directed graph if needed
        # or nx.Graph for an undirected graph.
        print(f'Creating network graph for model: "{self.file_path.stem}"')
        self._network_graph = nx.Graph()

        #              ('equip_type, df)
        edge_specs = (('transformer', self.transformer_df),
                      ('branch', self.branch_df),
                      ('system_switching_device', self.system_switching_device_df),
                      ('vsc_dc_line', self.vsc_dc_line_df),
                      ('multi_section_line', self.multi_section_line_df),
                      ('facts_device', self.facts_device_df),
                      ('load', self.load_df),
                      ('fixed_shunt', self.fixed_shunt_df),
                      ('generator', self.generator_df),
                      ('switched_shunt', self.switched_shunt_df),
                      ('induction_machine', self.induction_machine_df),
                      ('sub_station', self.sub_station_df),
                      )
        # edge_specs = [(attr, getattr(self, attr)) for attr
        #               in self.attr_names if attr not in ['bus_df', 'header']]
        # edge_specs = [_ for _ in edge_specs if isinstance(getattr(self, _[0]), pd.DataFrame)]
        # edge_specs = [(_[0][:-3] if _[0].endswith('_df') else _[0], _[1]) for _
        #               in edge_specs if isinstance(getattr(self, _[0]), pd.DataFrame)]

        # Add nodes
        for _, row in self.bus_df.iterrows():
            # self._network_graph.add_node(row['I'], **row.to_dict())
            kwargs = row.to_dict()
            kwargs.setdefault('type', 'bus')
            # kwargs['equip'] = Equipment(equip_type='bus', props_in=row.to_dict())
            self._network_graph.add_node(row.iloc[0], **row.to_dict())

        # Add edges
        for equip_type, df in edge_specs:
            for _, row in df.iterrows():
                equip = Equipment(equip_type=equip_type, props_in=row.to_dict())
                if equip.edge_pairs:
                    for edge_pair in equip.edge_pairs:
                        kwargs = {'equip': equip, 'type': equip.type, 'name': equip.name}
                        if add_derived_names:
                            nodes = self._network_graph.nodes
                            # Determine the derived_name, which is the concatenation of
                            suffix = ''
                            if hasattr(equip, 'ids'):
                                suffix = ', '.join([_[0].strip() + ': ' + _[1].strip() for _ in equip.ids.items()])

                            derived_name = self.get_extended_name(equip_name=equip.name,
                                                                  bus_nums=equip.buses.values(),
                                                                  suffix=suffix).strip('- ')
                            kwargs.setdefault('derived_name', derived_name)

                            # try:
                            #     # Get derived name from network_graph.nodes
                            #     derived_name = ' - '.join([nodes[bus_num]['NAME'].strip()
                            #                                + ' ' + str(nodes[bus_num]['BASKV'] or '')
                            #                                for bus_num in equip.buses.values()
                            #                                if nodes[bus_num]['NAME']])
                            # except KeyError:
                            #     # Some nodes not found, which is probably because they
                            #     # were filtered out with the Model.filter_model method.
                            #     derived_name = ''
                            # if not derived_name:
                            #     # Look at the original bus_df (before running
                            #     # Model.filter_model) to find bus information.
                            #     bus_df = self._orig_dfs['BUS']
                            #     bus_df = bus_df[bus_df['I'].isin(equip.buses.values())].copy()
                            #     names = [_.strip() for _ in bus_df['NAME'].values]
                            #     kv = [_ for _ in bus_df['BASKV'].values]
                            #     derived_name = ' - '.join([name.strip() + ' ' + str(v) for name, v in zip(names, kv)])
                            # derived_name = equip.name.strip() + ', [' + derived_name + ']'
                            # if hasattr(equip, 'ids'):
                            #     derived_name += ', ' + ': '.join(list(equip.ids.items())[0]).strip()
                            # kwargs.setdefault('derived_name', derived_name)
                        self._network_graph.add_edge(edge_pair[0], edge_pair[1], **kwargs)

        # Save the updated Model object, including networkx graph, to cache.
        self._to_pickle()

        return self._network_graph

    def append_bus_info_to_equip(self, equip_df: pd.DataFrame, inplace=False) -> pd.DataFrame:
        # TODO / WIP: append bus information.  E.g., merge branch_df with bus_df to add bus details to branch_df.
        #   keep this information in memory; do not modify branch_df unless inplace==True.
        raise NotImplementedError

    def get_bus(self, bus_id) -> dict:
        """Get a dict of bus properties from a bus number (bus_id)."""
        return self.bus_df[self.bus_df['I'] == bus_id].to_dict('records')[0]

    def get_bus_name(self, bus_id) -> str:
        """Get a bus name from a bus number (bus_id)."""
        try:
            return list(self.bus_df[self.bus_df['I'] == bus_id].to_dict()['NAME'].values())[0]
        except IndexError:
            return ''

    def get_bus_name_kv(self, bus_id) -> str:
        """Get a bus name from a bus number (bus_id)."""
        bus_df = self.bus_df
        if bus_id not in bus_df['I'].values:
            bus_df = self._orig_dfs['BUS']
            if bus_id not in bus_df['I'].values:
                return ''
        try:
            name = list(bus_df[bus_df['I'] == bus_id].to_dict()['NAME'].values())[0]
        except IndexError:
            return ''
        try:
            kv = list(bus_df[bus_df['I'] == bus_id].to_dict()['BASKV'].values())[0]
        except IndexError:
            kv = ''
        if isinstance(kv, float) and kv == int(kv):
            kv = int(kv)
        return f'{name.strip()} {kv}'

    def get_equip_name(self, bus_ids: list, ckt: str = ''):
        assert len(bus_ids) > 0
        assert isinstance(ckt, str)

        name = ''
        for id in bus_ids:
            if name:
                name += ' - '
                name += self.get_bus_name_kv(bus_id=id)

        ckt = ckt.strip()
        if ckt:
            name += f': {ckt}'

        return name

    def get_extended_name(self, equip_name: str, bus_nums: list[int], suffix: str = ''):
        result = equip_name.strip() + ', [' if equip_name.strip() else '['
        bus_nums = [int(str(_)) for _ in bus_nums]
        for index, bus_num in enumerate(bus_nums):
            result += ' - ' if index > 0 else ''
            result += self.get_bus_name_kv(bus_num).strip()
        result += ']'
        if suffix.strip():
            result += ', ' + suffix.strip()
        return result

    def append_derived_names(self):
        """
        Appends a new column named 'DERIVED_NAME' to each of the
        following pd.DataFrames:
            - self.branch_df

        :return: None
        """
        # Add bus name and kv info to branches.
        self.branch_df['DERIVED_NAME'] = self.branch_df.apply(
            lambda row: self.get_extended_name(equip_name=row['NAME'],
                                               bus_nums=[row['I'], row['J']],
                                               suffix='Ckt: ' + row['CKT']),
            axis=1)


def get_bus_info(model: Model, bus_id: int) -> dict:
    return model.get_bus(bus_id)


if __name__ == '__main__':
    export_to_excel = False
    force_recalculation = True
    # model1_fp = dirs.project_dir / "tests/data/sample.raw"
    # model1_fp = dirs.site_data_dir / "IDC_23S_sum23idctr6p2.raw"
    model1_fp = dirs.site_data_dir / "MMWG_2024SUM_2023Series_Assessment_Final_v35.raw"
    # model1_fp = dirs.site_data_dir / "MMWG_2024SUM_2023Series_Assessment_Final.rawx"

    if force_recalculation:
        ans = input('Are you sure you want to clear cache and force '
                    'recalculation? [y/n]: ').strip().lower()
        if ans != 'y':
            force_recalculation = False

    if "sample.raw" in model1_fp.name:
        native_areas = {2: 'EAST', 4: 'EAST_COGEN1', 6: 'EAST_COGEN2'}
    elif "IDC" in model1_fp.name:
        native_areas = NATIVE_AREAS
    else:
        native_areas = dict()

    # 1. Load a model from a .raw file (or from cache).
    model1: Model = Model(model1_fp, force_recalculation=force_recalculation)
    # 2. Filter the model to specific voltages and areas.
    model1.filter_model(kv_range=DEFAULT_KV_FILTER, areas=native_areas)

    # 3. Append derived names to equipment (using bus name, KV and Ckt)
    model1.append_derived_names()

    # 4. Create a NetworkX Graph for the model.
    model1_graph = model1.network_graph(force_recalculation=force_recalculation,
                                        add_derived_names=False)

    # 5. Export the model info to an Excel spreadsheet.
    if export_to_excel:
        xl_fp = dirs.site_data_dir / f"native_{model1.file_path.stem}.xlsx"
        if force_recalculation or not xl_fp.exists():
            model1.to_excel(file_path=xl_fp)

    # 6. List all attributes of the model
    attributes = [_ for _ in dir(model1) if not _.startswith('_')]
    # Print properties and their values
    for attr in model1.attr_names:
        value = getattr(model1, attr)
        if isinstance(value, pd.DataFrame):
            print(f"{attr}: {value.head(2)}")
        else:
            print(f"{attr}: {value}")
