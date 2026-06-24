"""Parse PSS/E RAW files into a RAWX-compatible dict.

This module reads a PSS/E RAW file (v34/v35) and converts its content into a
nested dictionary that mirrors the structure produced when loading a RAWX
(JSON) file. The resulting dict can then be used to build a compatible model.

The RAW-to-RAWX field and section mapping is data-driven, sourced from
``dataformat/rawx_raw_map.csv`` and filtered to the PSS/E version detected in
the RAW file.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from io import StringIO
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

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
    """Build the RAW-to-RAWX section map from the mapping CSV.

    Reads the section-mapping CSV, drops duplicate rows, and cleans the data.
    The result is cached in the module-level ``_section_map_df`` so subsequent
    calls return the cached DataFrame without re-reading the file.

    Args:
        filepath: Path to the CSV file containing the RAW section mapping data.

    Returns:
        A cleaned DataFrame with three columns:

        - ``section_raw``: RAW section identifiers.
        - ``subsection_raw``: RAW subsection identifiers (may contain NaN).
        - ``section_rawx``: Corresponding RAWX section identifiers.

    Note:
        Cleaning steps applied: duplicate rows are dropped on
        ``section_raw_34``/``subsection_raw_34``/``section_rawx``; the ``*_34``
        columns are renamed to their standard names; rows where both
        ``section_raw`` and ``subsection_raw`` are NaN are dropped; and
        ``subsection_raw`` is set to NaN where it equals ``section_raw``.
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
    """Read a PSS/E RAW file and convert its content to the RAWX dict format.

    Parses the RAW file section by section, mapping RAW field names to their
    RAWX equivalents for the detected PSS/E version, and assembles the result
    into a nested dict keyed under ``'general'`` and ``'network'``.

    Args:
        raw_filepath: Path to the RAW file.
        return_dataframes: If True, each network section is stored as a pandas
            DataFrame. Otherwise sections are stored as dicts with ``'fields'``
            and ``'data'`` keys.

    Returns:
        A dict in the RAWX file format, with top-level ``'general'`` and
        ``'network'`` keys.
    """
    # initial
    global raw_rawx_columns
    section, raw_column_names, rawx_column_names = '', [], []
    end_record_line_index = -1
    result: dict = {}  # rawx dict
    result['network'] = {}

    def _get_line_type(line: str) -> str | None:
        """Return the name of the first ``_PATTERNS`` regex matching ``line``.

        Returns None if no pattern matches (unknown line type).
        """
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

        section, rawx_section = None, None
        record_data, data = [], []

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
                    substation_data, end_line = _parse_substation_section(
                        f,
                        line_num,
                        raw_rawx_columns=raw_rawx_columns
                    )
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
    """Parse the case identification line from a RAW file.

    Args:
        caseid_line: The second line of the RAW file containing case ID
            information.

    Returns:
        A dict with ``'fields'`` (list of column names) and ``'data'`` (list of
        parsed values). The ``title1`` and ``title2`` fields are omitted when
        empty.
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


def _parse_substation_section(lines, start_line=0, raw_rawx_columns=None):
    """Parse the SUBSTATION section of a PSS/E RAW file.

    Reads the substation data block, node data, and switching device data,
    mapping RAW field names to their RAWX equivalents.

    Args:
        lines (list[str]): The RAW file lines.
        start_line (int): Line index where the SUBSTATION section begins.
        raw_rawx_columns (pd.DataFrame | None): RAW-to-RAWX column mappings.

    Returns:
        A ``(substation_data, end_line)`` tuple where ``substation_data`` is a
        dict with ``'substations'``, ``'nodes'``, and ``'switching_devices'``
        lists, and ``end_line`` is the line index where the section ends.
    """
    # Get column name mappings
    substation_columns = {}
    for section in [
        'SUBSTATION DATA BLOCK',
        'SUBSTATION NODE DATA',
        'SUBSTATION SWITCHING DEVICE DATA'
    ]:
        try:
            raw_rawx_pairs, _ = _get_column_names(
                subsection_raw_value=section,
                raw_rawx_columns_df=raw_rawx_columns
            )
            # Convert list of tuples to dict for easier lookup
            substation_columns[section] = {raw: rawx for raw, rawx in raw_rawx_pairs}
        except Exception as e:
            print(f"Warning: Could not load column mappings for {section}: {e}")
            substation_columns[section] = {}

    substation_data = {
        'substations': [],
        'nodes': [],
        'switching_devices': []
    }
    current_substation = None
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
            continue

        # Skip empty lines and comments
        if not line or line.startswith('@!') or line.startswith('0 /'):
            i += 1
            continue

        parts = split_csv_line(line)

        if in_switching_section:
            # Parse switching device data
            if not line.startswith('Q'):  # Skip end of file marker
                if len(parts) >= 4:  # Minimum required fields for switching device
                    # Map fields using the column names from the mapping
                    field_map = substation_columns.get('SUBSTATION SWITCHING DEVICE DATA', {})
                    device = {}

                    # Map fields by position
                    if len(parts) > 0:
                        device[field_map.get('NI', 'inode')] = parts[0]  # from node
                    if len(parts) > 1:
                        device[field_map.get('NJ', 'jnode')] = parts[1]  # to node
                    if len(parts) > 2:
                        device[field_map.get('CKT', 'swlid')] = parts[2]  # device id
                    if len(parts) > 3:
                        device[field_map.get('TYPE', 'type')] = parts[3]  # device type
                    if len(parts) > 4:
                        device[field_map.get('STATUS', 'stat')] = parts[4]  # status
                    if len(parts) > 5:
                        device['description'] = parts[5]  # description

                    substation_data['switching_devices'].append(device)
        else:
            # Parse substation and node data
            if len(parts) >= 3 and parts[0] and parts[1] == '0':
                # This is a substation record
                field_map = substation_columns.get('SUBSTATION DATA BLOCK', {})
                current_substation = {
                    field_map.get('IS', 'isub'): parts[0],  # substation number
                    field_map.get('NAME', 'name'): parts[2],  # substation name
                    'voltage': parts[3] if len(parts) > 3 else '',
                    'nodes': []
                }
                substation_data['substations'].append(current_substation)
            elif current_substation and len(parts) >= 3 and parts[1] != '0':
                # This is a node record
                field_map = substation_columns.get('SUBSTATION NODE DATA', {})
                node = {
                    field_map.get('NI', 'inode'): parts[1],  # node number
                    field_map.get('NAME', 'name'): parts[2],  # node name
                    field_map.get('I', 'ibus'): parts[2],  # bus number
                    'voltage': parts[3] if len(parts) > 3 else '',
                    'angle': parts[4] if len(parts) > 4 else '',
                    'base_kv': parts[5] if len(parts) > 5 else ''
                }
                current_substation['nodes'].append(node)
                substation_data['nodes'].append({
                    'substation_id': current_substation[field_map.get('IS', 'isub')],
                    **node
                })

        i += 1

    return substation_data, i


def _read_syswide(lines):
    """Read and parse system-wide data from a list of RAW file lines.

    Extracts general network information such as GENERAL, SOLVER, and RATING
    settings and other system-wide parameters that appear after the case
    identification lines and before the bus data.

    Args:
        lines (list[str]): RAW file lines containing the system-wide data.

    Returns:
        A dict keyed by RAWX section name (e.g. ``'general'``, ``'solver'``,
        ``'rating'``), each value being a dict with ``'fields'`` and ``'data'``.
        The ``'rating'`` section's ``'data'`` is a list of lists (one per
        RATING line).
    """

    def read_network_general_info_line(line: str):
        """Parse one system-wide line into ``(section_name, data)``.

        RATING and SOLVER lines have special handling; SOLVER's first
        (unlabeled) value is the solution method.
        """
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
    """Map a RAW section/subsection to its RAWX section name.

    Args:
        section_raw: RAW section name, e.g. ``'SUBSTATION'``.
        subsection_raw: RAW subsection name, e.g. ``'SUBSTATION NODE DATA'``.
            May be None.
        raw_rawx_map_csv: Path to the mapping CSV.

    Returns:
        The RAWX section name, or None if no match is found.
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
    """Load and preprocess the RAW-to-RAWX column mapping DataFrame.

    Reads the mapping CSV, filters to the given PSS/E version (dropping the
    columns for the other version), strips the ``_34``/``_35`` suffixes, drops
    rows with missing keys, and sorts by subsection and field index. The result
    is cached in the module-level ``raw_rawx_columns``.

    Args:
        filepath: Path to the RAW-to-RAWX column mapping CSV.
        version: PSS/E version number (e.g. 34 or 35) used to filter the
            columns. Earlier versions are not supported.

    Returns:
        The preprocessed RAW-to-RAWX column mapping DataFrame.
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
    """Return ordered RAW-to-RAWX column name pairs for a RAW subsection.

    The pairs are ordered by ``field_idx_raw``.

    Args:
        subsection_raw_value: The ``subsection_raw`` value to filter by.
        raw_rawx_columns_df: The column-mapping DataFrame to search.

    Returns:
        A 2-tuple of:

        1. A list of ordered ``(field_raw, field_rawx)`` tuples.
        2. A list of RAW column names. For sections with multiple RAW lines
           per record (see ``MULTI_ROW_RECORDS``), this is a list of lists of
           RAW column names (one inner list per record row).

    Raises:
        ValueError: If ``raw_rawx_columns_df`` is missing any of the required
            columns (``subsection_raw``, ``field_idx_raw``, ``field_raw``,
            ``field_rawx``).
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
    r"""Split a CSV line on commas, respecting quoted fields.

    Commas inside quoted string literals (both single and double quotes) are
    not treated as separators. Optionally strips leading and trailing
    characters from each parsed value.

    Args:
        line: A line of CSV data.
        strip_chars: Leading and trailing characters to strip from each parsed
            value. Defaults to ``'\n\'" '``. Pass an empty string to disable
            stripping.

    Returns:
        The list of parsed field values.
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
    """Save a RAWX dict to a JSON file.

    IO and encoding errors are caught and reported via print rather than
    raised.

    Args:
        rawx_dict (dict): The dict returned by :func:`raw_file_to_rawx_dict`.
        output_file (str): Path to the output JSON file.
        compact (bool): If True, write compact JSON (no indentation or
            separator whitespace). Defaults to False.
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
    """Convert sample PSS/E v34 and v35 RAW files to RAWX.

    Parses each provided RAW file with :func:`raw_file_to_rawx_dict`, prints the
    result, and optionally saves it to a JSON file under ``site_temp_dir``.

    Args:
        sample_raw34_path (Path | str): Path to the sample v34 RAW file.
        sample_raw35_path (Path | str): Path to the sample v35 RAW file.
        save_json (bool): If True, save each RAWX dict to a JSON file.

    Examples:
        >>> main("path/to/sample_34.raw", "path/to/sample_35.raw")
    """
    import json
    class ModelDecoder(json.JSONDecoder):
        """JSON decoder that reconstructs pandas DataFrames.

        Deserializes model data produced in the JSON-safe split format,
        rebuilding any object carrying ``index``/``columns``/``data`` keys back
        into a :class:`pandas.DataFrame`.
        """

        def __init__(self, *args, **kwargs):
            super().__init__(object_hook=self.object_hook, *args, **kwargs)

        def object_hook(self, dct):
            """Rebuild a DataFrame from a split-format dict, else pass through."""
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
        if save_json:
            save_rawx_dict_to_json(rawx_dict=result_34, output_file=json_temp_file, compact=True)

        print(json_temp_file)

    if sample_raw35_path:
        result_35 = raw_file_to_rawx_dict(sample_raw35_path)
        print('\n\nresult')
        print(result_35)

        json_temp_file = site_temp_dir / f'{raw35_path.stem}.json'
        if save_json:
            save_rawx_dict_to_json(rawx_dict=result_35, output_file=json_temp_file, compact=False)
        print(json_temp_file)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Convert PSS/E v34 or v35 RAW files to RAWX', add_help=True)
    parser.add_argument('-v34', '--raw34_path', type=str, help='Path to the v34 RAW file')
    parser.add_argument('-v35', '--raw35_path', type=str, help='Path to the v35 RAW file')
    parser.add_argument('-s', '--save_json', action='store_true', help='Save RAWX dictionary as a JSON file locally')

    args = parser.parse_args()

    # If raw34_path or raw35_poth not provided, prompt user to enter paths.
    if args.raw34_path is None:
        args.raw34_path = input('Enter the path to the sample v34 RAW file: ').strip()
    if args.raw35_path is None:
        args.raw35_path = input('Enter the path to the sample v35 RAW file: ').strip()

    main(sample_raw34_path=args.raw34_path,
         sample_raw35_path=args.raw35_path,
         save_json=args.save_json)
