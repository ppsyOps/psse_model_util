"""
The purpose of this module is to convert to parse a raw file into a dict similar
to the dict created when reading from a rawx file, then create a compatible model.
"""
import argparse
import re
import io
import json
import csv
import warnings
from io import StringIO
from typing import Tuple, List
from pathlib import Path

import numpy as np
import pandas as pd
import json

from psse_model_util.common.dirs import site_temp_dir

RAW_RAWX_MAP_CSV = Path(__file__).parent / r"dataformat/rawx_raw_map.csv"
_PATTERNS = {'column_names': r'^(?!@!\s*IC|^@!\s*IC\s).*@!(?!.*BEGIN\s+SUBSTATION).*,.+$',
             # Column name lines except for case identification lines.
             'column_names_case_id': r'^@!\s*IC.*',
             # Column names for Case identification (column names and data typically on lines 1-2)
             'sys_wide_general': r'^GENERAL,(\s*[A-Z]+\s*=\s*[^,]+,)*\s*[A-Z]+\s*=\s*[^,]+$',
             # System-wide general info
             'sys_wide_gauss': r'^GAUSS,(\s*[A-Z]+\s*=\s*[^,]+,)*\s*[A-Z]+\s*=\s*[^,]+$',  # System-wide gauss info
             'sys_wide_newton': r'^NEWTON,(\s*[A-Z]+\s*=\s*[^,]+,)*\s*[A-Z]+\s*=\s*[^,]+$',  # System-wide newton info
             'sys_wide_adjust': r'^ADJUST,(\s*[A-Z]+\s*=\s*[^,]+,)*\s*[A-Z]+\s*=\s*[^,]+$',  # System-wide adjust info
             'sys_wide_tysl': r'^TYSL,(\s*[A-Z]+\s*=\s*[^,]+,)*\s*[A-Z]+\s*=\s*[^,]+$',  # System-wide tysl info
             'sys_wide_solver': r'^SOLVER, [A-Z]{1,6},(\s*[A-Z]+\s*=\s*[^,]+,)*\s*[A-Z]+\s*=\s*[^,]+$',
             # System-wide solver info
             'sys_wide_rating': r'^RATING,\s*\d+,\s*".*?",\s*".*?"$',  # System-wide rating data
             # 'section_divider': r'^(?!.*(?:BEGIN\s+SUBSTATION|BEGIN\s+GNE)).*0\s*/\s*END\s+OF\s+.*$',
             'section_divider': r'^.*0\s*/\s*END\s+OF\s+.*$',
             # section divider (except substation section)
             'gne': r'\bBEGIN\s+GNE\s+DATA\b',  # gne special data lines with unique parsing rules
             'gne_special': r'^@! (REAL|INTG|CHAR)\d.*\)\)$',  # gne special data lines with unique parsing rules
             'substation_subsection': r'^@! BEGIN SUBSTATION.*',
             # subsection divider for substation data block and substation node data
             'substation_switching': r'.*BEGIN\s+SUBSTATION\s+SWITCHING\s+DEVICE\s+DATA\s*$',
             # section divider for substation switching data
             'eof': r'Q\s*',  # end of file indicator.
             # data row
             'data': r'^(?:(?:"(?:[^"]|"")*"|[^,\n]*)(?:,(?:"(?:[^"]|"")*"|[^,\n]*))*\n?)*$',
             'empty': r'^\s*$'
             }
# MULTI_ROW_RECORDS = {'TRANSFORMER DATA': 5, 'TWO-TERMINAL DC DATA': 3,
#                      'VSC DC LINE DATA': 2, 'MULTI-TERMINAL DC DATA': 4,
#                      'GNE DATA': 5}
MULTI_ROW_RECORDS = {'TRANSFORMER DATA': 5, 'TWO-TERMINAL DC DATA': 3,
                     'VSC DC LINE DATA': 2, 'MULTI-TERMINAL DC DATA': 4,
                     'GNE DATA': 5}

_section_map_df: pd.DataFrame = pd.DataFrame()
raw_rawx_columns: pd.DataFrame = pd.DataFrame()


def _get_section_map(filepath: Path = RAW_RAWX_MAP_CSV) -> pd.DataFrame:
    """Creates section map from raw_rawx_map.csv

    Reads CSV file containing section mapping data, removes duplicates,
    and performs data cleaning operations. The result is cached globally
    to avoid repeated file operations.

    Args:
        filepath (Path, optional): Path to the CSV file containing raw section
            mapping data. Defaults to RAW_RAWX_MAP_CSV.

    Returns:
        pd.DataFrame: A cleaned DataFrame containing three columns:
            - section_raw: Raw section identifiers
            - subsection_raw: Raw subsection identifiers (may contain NaN)
            - section_rawx: Processed section identifiers

    Note:
        This function uses a global cache (_section_map_df) to store results.
        Subsequent calls will return the cached DataFrame without re-reading
        the file.

        The function performs the following cleaning operations:
        - Removes duplicate rows based on section_raw_34, subsection_raw_34,
          and section_rawx columns
        - Renames columns from *_34 format to standard names
        - Drops rows where both section_raw and subsection_raw are NaN
        - Sets subsection_raw to NaN when it equals section_raw
    """
    global _section_map_df

    if not _section_map_df.empty:
        return _section_map_df

    df = pd.read_csv(filepath)
    df_dropped_dup = df.drop_duplicates(subset=['section_raw_34', 'subsection_raw_34', 'section_rawx'])

    df_dropped_dup = df_dropped_dup.rename(
        columns={'section_raw_34': 'section_raw',
                 'subsection_raw_34': 'subsection_raw'}
    ).reset_index(drop=True)

    _section_map_df = df_dropped_dup[['section_raw', 'subsection_raw', 'section_rawx']]

    _section_map_df = _section_map_df.dropna(subset=_section_map_df.columns[:2], how='any')
    _section_map_df.loc[_section_map_df['subsection_raw'] == _section_map_df['section_raw'], 'subsection_raw'] = np.nan

    return _section_map_df


def raw_file_to_rawx_dict(raw_filepath: str | Path,
                          return_dataframes: bool = False) -> dict:
    """Reads a raw file and converts the content to a rawx json format.

    Args:
        raw_filepath (str | Path): path of the file
        return_dataframes (bool, optional): If True, section data will be
            returned as pandas DataFrames. Otherwise, data will be returned
            as a dictionary with 'fields' and 'data' keys. Defaults to False.

    Returns:
        dict: corresponding the json rawx file format.
    """
    # initial
    global raw_rawx_columns
    section, raw_column_names, rawx_column_names = '', [], []
    key = None
    end_record_line_index = -1
    result: dict = {}  # rawx dict
    result['network'] = {}

    def _get_line_type(line: str) -> str | None:
        line = line.strip()
        # Find which of the regex patterns matches.  If no match found, return None.
        # Iterate through patterns and find matching pattern
        for pattern_name, pattern_regex in _PATTERNS.items():
            if re.match(pattern_regex, line):
                return pattern_name
        # No match found.  Unknown line type.
        return None

    # Read the raw file
    with io.open(str(raw_filepath), encoding="latin-1") as file:
        f = file.readlines()
        assert f[0].startswith('@!IC,'), \
            'Expected 1st line of file to start with "@!IC,"'
        assert '/ PSS(R)E-3' in f[1], \
            'Expected to find case info. and PSSE version number in 2nd line of file.'
        assert f[4].startswith('GENERAL,'), \
            'Expected 1st line of file to start with "GENERAL,"'

        category, section, rawx_section = None, None, None
        record_data, data, finished_sys_wide = [], [], False

        # Case Info (First 2 lines of raw file), which maps to result['general']
        # _____________________________________________________________________
        version = f[1].split('/ PSS(R)E-', 1)[1].strip()
        version = float(version.split(' ', 1)[0])
        print('\n\nVersion: ', version)

        raw_rawx_columns = _get_raw_rawx_columns(filepath=RAW_RAWX_MAP_CSV, version=version)

        result['general'] = {}
        result['general']['version'] = version

        # Network Data, which maps to result['general']
        # _____________________________________________________________________
        result['network']['caseid'] = _read_caseid(f[1])
        rev = int(result['network']['caseid']['data'][2])
        assert int(result['general']['version']) == rev
        print('\ncaseid:', rev)

        # Read system-wide data (data after case info and before bus data).
        syswide_line_num = [i for i, _ in enumerate(f[:6]) if _.startswith('GENERAL,')][0]
        end_syswide_line_num = next((i for i, line in enumerate(f) if line.startswith("0 / END OF")), -1)
        syswide = _read_syswide(f[syswide_line_num: end_syswide_line_num])
        result['network'].update(syswide)

        # Read Network Data (after system-wide data)
        f_list = f[end_syswide_line_num:]  # Convert to list for easier indexing
        line_num = end_syswide_line_num

        while line_num < len(f):
            line = f[line_num]
            line_type = _get_line_type(line)
            print('line_num, line_type, line:', line_num, line_type, line)
            if line_type == 'section_divider':
                # Process previous section.
                if data and rawx_column_names and rawx_section not in ['impcor']:
                    print('\nsection:', section, rawx_section)
                    print('rawx_column_names:', len(rawx_column_names), rawx_column_names)
                    if data:  # Only print if data is not empty
                        print('data[0]:', len(data[0]) if data else 0, data[0] if data else 'No data')
                    if return_dataframes and data:  # Only create DataFrame if there's data
                        result['network'][rawx_section] = pd.DataFrame(data=data, columns=rawx_column_names)
                    elif data:  # Only add if there's data
                        result['network'][rawx_section] = {'fields': rawx_column_names, 'data': data}

                # Prepare for current section data.
                section = line.split(', BEGIN')[-1].strip()
                rawx_section = _raw_to_rawx_section_name(section, None)
                data, record_data = [], []
                line_num_of_record, end_record_line_index = 0, 0

                # Create a mapping of raw to rawx column names
                if rawx_section and not rawx_section.startswith('substation'):  # Skip column mapping for substation section
                    raw_rawx_column_names, raw_column_names = _get_column_names(
                        subsection_raw_value=section,
                        raw_rawx_columns_df=raw_rawx_columns
                    )
                    rawx_column_names = [_[1] for _ in raw_rawx_column_names]
            elif line_type == 'data':
                if rawx_section and rawx_section.startswith('substation'):
                    # Parse substation section
                    substation_data, end_line = _parse_substation_section(f, line_num)
                    result['network']['substation'] = substation_data
                    # Skip to the end of the substation section
                    line_num = end_line
                elif rawx_section == 'impcor':
                    # Parse impedance correction data
                    if not raw_rawx_column_names:  # Only get column names once per section
                        raw_rawx_column_names, _ = _get_column_names(
                            subsection_raw_value='IMPEDANCE CORRECTION DATA',
                            raw_rawx_columns_df=raw_rawx_columns
                        )
                        rawx_column_names = [col[1] for col in raw_rawx_column_names]
                    
                    line_data = split_csv_line(line)
                    if len(line_data) >= 4:  # Ensure we have all required fields
                        # Convert values to appropriate types based on column position
                        row_data = []
                        for i, value in enumerate(line_data[:4]):  # Only process first 4 columns
                            if i == 0:  # itable - integer
                                row_data.append(int(float(value)) if value.strip() else 0)
                            else:  # tap, refact, imfact - float
                                row_data.append(float(value) if value.strip() else 0.0)
                        
                        # Pad with None if we don't have enough values
                        row_data += [None] * (len(rawx_column_names) - len(row_data))
                        data.append(row_data)
                elif section == 'TRANSFORMER DATA':
                    column_names = raw_column_names[line_num_of_record]
                    line_data = split_csv_line(line)
                    line_data += [None] * (len(column_names) - len(line_data))
                    if line_num_of_record == 0:
                        record_data = line_data
                        i, j, k = line_data[:3]
                        # 2-winding tx has 4 lines/record; 3-winding transformer ahs 5 data lines.
                        end_record_line_index = 3 if k == '0' else 4
                    else:
                        record_data += line_data
                        if line_num_of_record == end_record_line_index:
                            # Total number of columns for the record:
                            record_col_count = sum(len(sublist) for sublist in raw_column_names)
                            record_data += [None] * (record_col_count - len(record_data))
                            data += [record_data]
                        if line_num_of_record >= end_record_line_index:
                            line_num_of_record = -1
                    line_num_of_record += 1
                elif section in ['TWO-TERMINAL DC DATA', 'VSC DC LINE DATA', 'GNE DATA']:
                    end_record_line_index = len(raw_column_names) - 1
                    column_names = raw_column_names[line_num_of_record]
                    line_data = split_csv_line(line)
                    line_data += [None] * (len(column_names) - len(line_data))
                    if line_num_of_record == 0:
                        record_data = line_data
                    else:
                        record_data += line_data
                        if line_num_of_record == end_record_line_index:
                            # Total number of columns for the record:
                            record_col_count = sum(len(sublist) for sublist in raw_column_names)
                            record_data += [None] * (record_col_count - len(record_data))
                            data += [record_data]
                        if line_num_of_record >= end_record_line_index:
                            line_num_of_record = -1
                    line_num_of_record += 1
                else:
                    # Parse data in sections with one file line per record.
                    line_data = split_csv_line(line)
                    line_data = line_data + [None] * (len(rawx_column_names) - len(line_data))
                    data += [line_data]
            elif line_type == 'eof':
                # End of file
                break
            line_num += 1

    raw_rawx_columns = pd.DataFrame()
    return result


def _read_caseid(caseid_line: str):
    """Parses the case identification line from a raw file.

    Args:
        caseid_line (str): The second line of the raw file containing case ID information.

    Returns:
        dict: A dictionary containing 'fields' (list of column names) and 'data' (list of parsed values).
    """
    caseid_cols = 'ic', 'sbase', 'rev', 'xfrrat', 'nxfrat', 'basfrq', 'title1', 'title2'
    data = caseid_line.split('/ PSS(R)E-', 1)[0].strip()
    data = [_.strip() for _ in data.split(',')]
    data += [''] * (len(caseid_cols) - len(data))
    # caseid = {k: v for k, v in zip(caseid_cols, data)}
    caseid = {'fields': caseid_cols, 'data': data}
    for key in ('title1', 'title2'):
        if key in caseid and not caseid[key]:
            caseid.pop(key)
    return caseid


def _parse_substation_section(lines, start_line=0):
    """Parse the SUBSTATION section of a PSSE RAW file.

    Args:
        lines: List of strings containing the raw file lines
        start_line: Line number where the SUBSTATION section begins

    Returns:
        tuple: (substation_data, end_line) where:
            - substation_data: Dictionary containing parsed substation data
            - end_line: Line number where the section ends
    """
    substation_data = {
        'substations': [],
        'nodes': [],
        'switching_devices': []
    }
    current_substation = None
    current_node = None
    in_switching_section = False

    i = start_line
    while i < len(lines):
        line = lines[i].strip()

        # Check for end of section
        if line.startswith('0 / END OF SUBSTATION'):
            return substation_data, i

        # Check for switching device section
        if 'BEGIN SUBSTATION SWITCHING DEVICE DATA' in line:
            in_switching_section = True
            i += 1
            # continue

        # Skip empty lines and comments
        if not line or line.startswith('@!') or line.startswith('0 /'):
            i += 1
            # continue

        if in_switching_section:
            # Parse switching device data
            if not line.startswith('Q'):  # Skip end of file marker
                parts = split_csv_line(line)
                if len(parts) >= 8:  # Minimum required fields for switching device
                    device = {
                        'substation': parts[0],
                        'node1': parts[1],
                        'node2': parts[2],
                        'device_type': parts[3],
                        'status': parts[4] if len(parts) > 4 else '',
                        'description': parts[5] if len(parts) > 5 else ''
                    }
                    substation_data['switching_devices'].append(device)
        else:
            # Parse substation and node data
            parts = split_csv_line(line)

            # Check if this is a new substation
            if len(parts) >= 3 and parts[0] and parts[1] == '0':
                current_substation = {
                    'id': parts[0],
                    'name': parts[2],
                    'voltage': parts[3] if len(parts) > 3 else '',
                    'nodes': []
                }
                substation_data['substations'].append(current_substation)
            # Check if this is a node within the current substation
            elif current_substation and len(parts) >= 3 and parts[1] != '0':
                node = {
                    'id': parts[1],
                    'bus_number': parts[2],
                    'voltage': parts[3] if len(parts) > 3 else '',
                    'angle': parts[4] if len(parts) > 4 else '',
                    'base_kv': parts[5] if len(parts) > 5 else ''
                }
                current_substation['nodes'].append(node)
                substation_data['nodes'].append({
                    'substation_id': current_substation['id'],
                    **node
                })

        i += 1

    return substation_data, i


def _read_syswide(lines):
    """Reads and parses system-wide data from a list of lines.

    This function extracts general network information, such as solver settings,
    ratings, and other system-wide parameters.

    Args:
        lines (list): A list of strings, where each string is a line from the raw file
                      containing system-wide data.

    Returns:
        dict: A dictionary where keys are rawx section names (e.g., 'general', 'solver', 'rating')
              and values are dictionaries containing 'fields' and 'data' for each section.
              The 'rating' section data is structured as a list of lists.
    """

    def read_network_general_info_line(line: str):
        # Get the case into line type
        sub_section_name = line.split(',', 1)[0].strip()
        # RATING lines are special
        if sub_section_name == "RATING":
            data = line.split(',')[1:]
            data = [_.strip('" ') for _ in data]
            data = zip(["irate", "name", "desc"], data)
            data = {k: v for k, v in data}
            return 'RATING', data
        # Get a dict of values from the line.
        if sub_section_name == "SOLVER":
            # SOLVER line's first value is the solution method, which has no label.
            # Add a label, so the data parsing code below works.
            line = 'SOLVER, METHOD=' + line.split(',', 1)[1].strip()
        data = dict(pair.split('=') for pair in line.split(', ', 1)[1].split(', '))
        data = {'fields': list(data.keys()), 'data': list(data.values())}
        return sub_section_name, data

    result: dict = {'rating': {'fields': ['irate', 'name', 'desc'],
                               'data': []}}
    capture = False

    # Only need to check the first 30 lines
    for line in lines[:30]:
        line = line.strip()
        if "0 / END OF" in line:
            break
        if line.startswith('GENERAL,'):
            capture = True
        if capture:
            sub_section_name, data = read_network_general_info_line(line)
            if 'fields' in data.keys():
                data['fields'] = [_.lower() for _ in data['fields']]
            if sub_section_name == 'RATING':
                result['rating']['data'] += [list(data.values())]
            else:
                sub_section_name = _raw_to_rawx_section_name(sub_section_name) \
                                   or sub_section_name.lower()
                result[sub_section_name] = data

    return result


def _raw_to_rawx_section_name(section_raw: str,
                              subsection_raw: str | None = None,
                              raw_rawx_map_csv: Path = RAW_RAWX_MAP_CSV):
    """Get the RAWX section name that corresponds to a specific section
    and subsection of a RAW file. subsection_raw can be None.

    Args:
        section_raw (str): section name from RAW file, like 'SUBSTATION'
        subsection_raw (str | None, optional): section name from RAW file,
            like 'SUBSTATION NODE DATA'. Defaults to None.
        raw_rawx_map_csv (Path, optional): Path to the file containing the mapping data.
            Defaults to RAW_RAWX_MAP_CSV.

    Returns:
        str: RAWX section name or None (if not found).
    """
    section_map_df = _get_section_map(raw_rawx_map_csv)

    section_raw = section_raw.upper() if section_raw else None
    subsection_raw = subsection_raw.upper() if subsection_raw else np.nan
    df = section_map_df[(section_map_df['section_raw'] == section_raw) &
                        ((section_map_df['subsection_raw'].isna()) |
                         (section_map_df['subsection_raw'] == subsection_raw))]

    if df.empty:
        return None
    else:
        return df['section_rawx'].iloc[0]


def _get_raw_rawx_columns(filepath: Path | str = RAW_RAWX_MAP_CSV,
                          version=34) -> pd.DataFrame:
    """Loads and preprocesses the raw to rawx column mapping DataFrame.

    This function reads a CSV file containing mappings between raw file column
    names and rawx column names, filters by PSS/E version, renames columns,
    and sorts the data. The result is cached globally for efficiency.

    Args:
        filepath (Path | str, optional): Path to the CSV file containing the
            raw to rawx column mapping data. Defaults to RAW_RAWX_MAP_CSV.
        version (int, optional): The PSS/E version number (e.g., 34, 35) to
            filter the columns. Defaults to 34. Code does not support earlier versions.

    Returns:
        pd.DataFrame: A preprocessed DataFrame containing the raw to rawx column mappings.
    """
    global raw_rawx_columns
    if isinstance(raw_rawx_columns, pd.DataFrame) and not raw_rawx_columns.empty:
        return raw_rawx_columns

    filepath = Path(filepath)
    df = pd.read_csv(filepath)  # Correct way to read the CSV into a DataFrame

    expected_columns = {'field_idx_raw_34', 'section_raw_34', 'subsection_raw_34',
                        'field_raw_34', 'field_idx_raw_35', 'section_raw_35',
                        'subsection_raw_35', 'field_id_rawx', 'section_rawx', 'field_rawx'}
    assert expected_columns.issubset(set(df.columns))

    # Drop columns not applicable to the version specified in the raw file.
    suffix_to_drop = '34' if version >= 35 else '35'
    df.drop(columns=[col for col in df.columns if col.endswith(suffix_to_drop)], inplace=True)

    # Rename columns to drop _34 and _35 suffixes.
    df.rename(columns=lambda col: col.rstrip('_34').rstrip('_35'), inplace=True)
    # Drop rows where 'subsection_raw' or 'field_idx_raw_34' column is null/NaN.
    df.dropna(subset=['subsection_raw', 'field_idx_raw'], inplace=True)
    # Sort columns by subsection then field index, ascending.
    df.sort_values(by=['subsection_raw', 'field_idx_raw'], inplace=True)
    df.reset_index(drop=True, inplace=True)

    raw_rawx_columns = df

    return raw_rawx_columns


def _get_column_names(subsection_raw_value: str,
                      raw_rawx_columns_df: pd.DataFrame) \
        -> Tuple[List, List[str]]:
    """Return an ordered list of tuples (field_raw, field_rawx) for a specific subsection_raw value,
    ordered by field_idx_raw.

    Args:
        subsection_raw_value (str): The value of subsection_raw to filter by.
        raw_rawx_columns_df (pd.DataFrame): The DataFrame to search in.

    Returns:
        Tuple[List, List[str]]: A tuple containing:
            1. List of ordered tuples (field_raw, field_rawx).
            2. List of raw column names. If raw file contains multiple
               rows per record, then List of list of raw column names.
    """
    # Ensure that the DataFrame contains the necessary columns
    if 'subsection_raw' not in raw_rawx_columns_df.columns or \
            'field_idx_raw' not in raw_rawx_columns_df.columns or \
            'field_raw' not in raw_rawx_columns_df.columns or \
            'field_rawx' not in raw_rawx_columns_df.columns:
        raise ValueError("DataFrame must contain 'subsection_raw', 'field_idx_raw', "
                         "'field_raw', and 'field_rawx' columns.")

    # Filter the DataFrame by the given subsection_raw value
    filtered_df = raw_rawx_columns_df[raw_rawx_columns_df['subsection_raw']
                                      == subsection_raw_value]

    # Sort the filtered DataFrame by field_idx_raw
    sorted_df = filtered_df.sort_values(by='field_idx_raw')

    # Create a list of tuples (field_raw, field_rawx)
    raw_rawx_column_names = list(zip(sorted_df['field_raw'], sorted_df['field_rawx']))

    # Create a list of RAW file column names in the expected order.
    raw_column_names = [_[0] for _ in raw_rawx_column_names]

    if subsection_raw_value in MULTI_ROW_RECORDS.keys():
        # Certain sections have multiple rows per record.  For this section,
        # derive the ordered list of RAW columns for reach record.  Return
        # as list[list[str]] named "raw_rawx_column_names".
        raw_column_info = raw_rawx_columns[raw_rawx_columns['subsection_raw'] == subsection_raw_value]
        raw_column_names = []
        row_nums = list(raw_column_info['row_raw'].unique())
        for row_num in row_nums:
            df = raw_column_info[raw_column_info['row_raw'] == row_num]
            raw_column_names += [list(df['field_raw'])]

    return raw_rawx_column_names, raw_column_names


def split_csv_line(line: str, strip_chars: str = '\n\'" ') -> List[str]:
    """
    Parse a line of CSV data. Split it on commas, ignoring commas inside
    quoted string literals (both single and double quotes). Optionally
    strip leading and trailing whitespace from each parsed value.

    Args:
        line (str): A line of CSV data.
        strip_chars (str, optional): Leading and trailing characters to strip from each
            parsed value. Defaults to '\n\'" '.

    Returns:
        List[str]: List of parsed values.
    """
    # Remove trailing carriage return
    line = line.rstrip('\r')
    # Replace double quotes with single quotes to handle quoting consistently
    temp = line.replace('"', "'")
    # Parse the line using csv.reader
    parsed_values = next(csv.reader(StringIO(temp),
                                    skipinitialspace=True,
                                    quotechar="'"))
    # Optionally, strip leading and trailing whitespace
    if strip_chars:
        parsed_values = [value.strip(strip_chars) for value in parsed_values]

    return parsed_values


def save_rawx_dict_to_json(rawx_dict, output_file, compact=False):
    """
    Save the results of raw_file_to_rawx_dict to a JSON file.

    Args:
        rawx_dict (dict): The dictionary returned by raw_file_to_rawx_dict
        output_file (str): The path to the output JSON file
        compact (bool): If True, produces more compact JSON output. Default is True.

    Returns:
        None
    """
    try:
        with open(output_file, 'w') as f:
            if compact:
                json.dump(rawx_dict, f, separators=(',', ':'))
            else:
                json.dump(rawx_dict, f, indent=2)
        print(f"Successfully saved RAWX dictionary to {output_file}")
    except IOError as e:
        print(f"Error writing to file {output_file}: {e}")
    except TypeError as e:
        print(f"Error encoding dictionary to JSON: {e}")


def main(sample_raw34_path: Path | str,
         sample_raw35_path: Path | str,
         save_json: bool = True):
    """
    Main function to convert both PSS/E v34 and v35 RAW files to RAWX

    Args:
        sample_raw34_path (Path | str): Path to the sample v34 RAW file
        sample_raw35_path (Path | str): Path to the sample v35 RAW file
        save_json (bool): If True, saves RAWX dictionary to a JSON file

    Returns:
        None

    Example:
        >>> main("path/to/sample_34.raw", "path/to/sample_35.raw")
    """
    import json
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

    raw34_path, raw35_path = Path(sample_raw34_path), Path(sample_raw35_path)

    if sample_raw34_path:
        result_34 = raw_file_to_rawx_dict(sample_raw34_path)

        print('\n\nresult')
        print(result_34)

        json_temp_file = site_temp_dir / f'{raw34_path.stem}.json'
        json_temp_file.parent.mkdir(parents=True, exist_ok=True)
        if save_json: save_rawx_dict_to_json(rawx_dict=result_34, output_file=json_temp_file, compact=True)

        print(json_temp_file)

    if sample_raw35_path:
        result_35 = raw_file_to_rawx_dict(sample_raw35_path)
        print('\n\nresult')
        print(result_35)

        json_temp_file = site_temp_dir / f'{raw35_path.stem}.json'
        if save_json: save_rawx_dict_to_json(rawx_dict=result_35, output_file=json_temp_file, compact=False)
        print(json_temp_file)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Convert PSS/E v34 or v35 RAW files to RAWX', add_help=True)
    parser.add_argument('-v34', '--raw34_path', type=str, help='Path to the v34 RAW file')
    parser.add_argument('-v35', '--raw35_path', type=str, help='Path to the v35 RAW file')
    parser.add_argument('-s', '--save_json', action='store_true', help='Save RAWX dictionary as a JSON file locally')

    args = parser.parse_args()

    # If raw34_path or raw35_poth not provided, prompt user to enter paths.
    if args.raw34_path == None:
        args.raw34_path = input('Enter the path to the sample v34 RAW file: ').strip()
    if args.raw35_path == None:
        args.raw35_path = input('Enter the path to the sample v35 RAW file: ').strip()

    main(sample_raw34_path=args.raw34_path,
         sample_raw35_path=args.raw35_path,
         save_json=args.save_json)
