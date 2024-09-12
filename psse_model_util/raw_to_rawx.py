"""
The purpose of this module is to convert to parse a raw file into a dict similar
to the dict created when reading from a rawx file, then create a compatible model.
"""
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

SECTION_MAP_CSV = Path(__file__).parent / r"common/raw_rawx_section_map.csv"
RAW_RAWX_MAP_CSV = Path(__file__).parent / r"common/rawx_raw_map.csv"
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

section_map_df: pd.DataFrame = pd.DataFrame()
raw_rawx_columns: pd.DataFrame = pd.DataFrame()


def raw_file_to_rawx_dict(raw_filepath: str | Path,
                          return_dataframes: bool = False) -> dict:
    """Reads a raw file and converts the content to a rawx json format.

    Args:
        raw_filepath (str): path of the file

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

    def _get_line_type(line: str) -> str:
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
        for line_num, line in enumerate(f[end_syswide_line_num:]):
            line_num = line_num + end_syswide_line_num
            line_type = _get_line_type(line)
            if line_type == 'section_divider':
                # Process previous section.
                if data and rawx_column_names and rawx_section not in ['impcor']:
                    # TODO: Parse impedence correction data, impcor, which is excluded in the line above.
                    print('\nsection:', section, rawx_section)
                    print('rawx_column_names:', len(rawx_column_names), rawx_column_names)
                    print('data[0]:', len(data[0]), data[0])
                    if return_dataframes:
                        result['network'][rawx_section] = pd.DataFrame(data=data, columns=rawx_column_names)
                    else:
                        result['network'][rawx_section] = {'fields': rawx_column_names,
                                                           'data': data}

                # Prepare for current section data.
                section = line.split(', BEGIN')[-1].strip()
                rawx_section = _raw_to_rawx_section_name(section, None)
                data, record_data = [], []
                # Some records are multi-ine in RAW files.  Track the current
                # line of a given record.  Since, we are starting anew section,
                # we have not started a record.
                line_num_of_record, end_record_line_index = 0, 0

                # Create a mapping of raw to rawx column names (in the expected RAW file column order)
                raw_rawx_column_names, raw_column_names \
                    = _get_column_names(subsection_raw_value=section, raw_rawx_columns_df=raw_rawx_columns)
                rawx_column_names = [_[1] for _ in raw_rawx_column_names]
            elif line_type == 'data':
                # if rawx_section.startswith('gne') or rawx_section.startswith('substation'):
                if rawx_section.startswith('substation') or rawx_section in ['impcor']:
                    # TODO: Placeholder for Substation and Impedance correction data parsing.
                    warnings.warn(f"SKIPPING '{section}' section.  Parsing of this section is not yet supported.")
                    data = []
                    continue
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

    raw_rawx_columns = pd.DataFrame()
    return result


def _read_caseid(caseid_line: str):
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


def _read_syswide(lines):
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
                              section_map_csv: Path = SECTION_MAP_CSV):
    """Get the RAWX section name that corresponds to a specific section
    and subsection of a RAW file. subsection_raw can be None.
    :param section_raw: section name from RAW file, like 'SUBSTATION'
    :param subsection_raw: section name from RAW file, like 'SUBSTATION NODE DATA'
    :param section_map_csv: optional Path to the file containing the mapping data.
    :return: RAWX section name or None (if not found).
    """

    def read_section_map(filepath: Path = SECTION_MAP_CSV) -> Tuple:
        return pd.read_csv(filepath)

    global section_map_df
    if section_map_csv and section_map_df.empty:
        section_map_df = read_section_map(Path(section_map_csv))

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
    """
    Return an ordered list of tuples (field_raw, field_rawx) for a specific subsection_raw value,
    ordered by field_idx_raw.

    :param subsection_raw_value: The value of subsection_raw to filter by.
    :param raw_rawx_columns_df: The DataFrame to search in.
    :return: Tuple of:
                1) List of ordered tuples (field_raw, field_rawx).
                2) List of raw column names.  If raw file contains multiple
                   rows per record, then List of list of raw column names.
                3) List of rawx column names (same as the 2nd tupe item in item 1)
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

    :param line: A line of CSV data.
    :param strip_chars: Leading and trailing characters to strip from each
                        parsed value.
    :return: List of parsed values.
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


if __name__ == "__main__":
    from pathlib import Path
    from psse_model_util.common.dirs import site_temp_dir

    fp = Path(__file__).absolute().parent.parent / 'tests/data/sample_34.raw'
    fp.parent.mkdir(parents=True, exist_ok=True)
    result = raw_file_to_rawx_dict(fp)
    print('\n\nresult')
    print(result)
    json_temp_file = site_temp_dir / f'{fp.stem}.json'
    json_temp_file.parent.mkdir(parents=True, exist_ok=True)
    save_rawx_dict_to_json(rawx_dict=result, output_file=json_temp_file, compact=True)
    print(json_temp_file)

    fp = Path(__file__).absolute().parent.parent / 'tests/data/sample_v35.raw'
    result = raw_file_to_rawx_dict(fp)
    print('\n\nresult')
    print(result)
    json_temp_file = site_temp_dir / f'{fp.stem}.json'
    save_rawx_dict_to_json(rawx_dict=result, output_file=json_temp_file, compact=False)
    print(json_temp_file)
