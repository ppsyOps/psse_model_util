from datetime import timedelta
from collections import namedtuple

import pandas as pd
from pathlib import Path

RangeFilterType = namedtuple('RangeFilterType', ['min', 'max'])

# Maximum number of segments allowed in alternate paths when comparing models
# This is used in the compare_graph method of ModelComparison class
ALT_PATH_MAX_PATH_LENGTH = 5

# # Dictionary mapping bus type codes to their descriptions
# BUS_TYPES = {1: 'LOAD', 2: 'GEN', 3: 'SWING', 4: 'SHUTDOWN'}

# Default voltage range filter for buses, used in filtering operations
DEFAULT_KV_FILTER = RangeFilterType(138, 10_000)

# # Default MW range filter for generators, used in filtering operations
GEN_MW_FILTER = RangeFilterType(20, 10_000)

# Number of seconds to wait for a download to complete (used in file_util.wait_for_file())
DOWNLOAD_WAIT_SECONDS = 3

# Dictionary of native PJM areas with their area numbers as keys and names as values
NATIVE_AREAS = {101: 'CENTRAL', 206: 'EAST', 301: 'CENTRAL_DC'}

# Dictionary of neighboring areas to PJM with their area numbers as keys and names as values
NEIGHBOR_AREAS = {401: 'EAST_COGEN1', 3011: 'WEST', 402: 'EAST_COGEN2'}

# Combined dictionary of native and neighboring areas, used for filtering models
INCLUDE_AREAS = NEIGHBOR_AREAS.copy() | NATIVE_AREAS.copy()

# Filters used by compare.ModelComparison.query_network_df_comparison() method.  This filters the
# MModelComparison dataframes to a reduced record set that will be used for creation
# of INCH or IDEV files.
NETWORK_DF_COMPARISON_QUERIES = {
    'bus': f'ibus.isin({list(INCLUDE_AREAS.keys())}) '
           f'and baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
           f'and (presence != "both" or evhi_delta > 0 or nvlo_delta > 0 '
           f'or va_delta > 0 or nvhi_delta > 0 or evlo_delta > 0 '
           f'or ide_delta > 0 or baskv_delta > 0 or name_delta > 0 '
           f'or zone_delta > 0 or vm_delta > 0 or owner_delta > 0 '
           f'or area_delta > 0)',
    'generator': f'pg_model2 > {GEN_MW_FILTER[0]}',
    'load': f'pl_model1 > 10',
    'acline': f'(ibus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
              f'or jbus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
              f'or ibus_baskv_model2 >= {DEFAULT_KV_FILTER[0]} '
              f'or jbus_baskv_model2 >= {DEFAULT_KV_FILTER[0]}) ',
    'transformer': f'ibus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
                   f'or jbus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
                   f'or kbus_baskv_model1 >= {DEFAULT_KV_FILTER[0]} '
                   f'or ibus_baskv_model2 >= {DEFAULT_KV_FILTER[0]} '
                   f'or jbus_baskv_model2 >= {DEFAULT_KV_FILTER[0]} '
                   f'or kbus_baskv_model2 >= {DEFAULT_KV_FILTER[0]}'
    }

# Flag to determine if operations should be resilient (continue on errors) or raise exceptions
RESILIENT = True

# # INCH (Incremental Network Change) related constants
# # Actions that can be performed in INCH files
# INCH_ACTIONS = ('#ADD', '#DELETE', '#MODIFY')
#
# # Keywords used in INCH files to denote actions
# INCH_KEYWORDS = ('Add', 'Modify', 'Mod', 'Delete', 'Del')
#
# # Section headers used in INCH files
# INCH_SECTIONS = ('#DATA_TITLE', '#ADD_BUS', '#DELETE_BUS', '#MODIFY_BUS', '#ADD_GEN', '#DELETE_GEN', '#MODIFY_GEN',
#                  '#ADD_LOAD', '#DELETE_LOAD', '#MODIFY_LOAD', '#ADD_FXSHUNT', '#DELETE_FXSHUNT', '#MODIFY_FXSHUNT',
#                  '#ADD_SWSHUNT', '#DELETE_SWSHUNT', '#MODIFY_SWSHUNT', '#ADD_BRANCH', '#DELETE_BRANCH',
#                  '#MODIFY_BRANCH', '#ADD_TRANSFORMER', '#DELETE_TRANSFORMER', '#MODIFY_TRANSFORMER', '#ADD_AREA',
#                  '#DELETE_AREA', '#MODIFY_AREA', '#ADD_ZONE', '#DELETE_ZONE', '#MODIFY_ZONE', '#END',
#                  )
