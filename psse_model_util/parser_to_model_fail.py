"""
Parser for PSSE .raw and .seq files.
Supported PSSE versions: 33, 34 and 35.
"""
import re
import io
import warnings
import csv
from pathlib import Path
from collections import namedtuple

from psse_model_util import dataformat34
from psse_model_util import dataformat35
from psse_model_util.common.dataframe_util import convert_columns_to_numeric

import pandas as pd
import networkx as nx


LineMetaType = namedtuple('LineMetaType', ['line_number', 'type', 'content',
                                           'num_col_header_lines'])
BusNode = namedtuple('BusNode', ['SECTION', 'I'])
INode = namedtuple('INode', ['SECTION', 'I', 'ID'])
IJNode = namedtuple('IJNode', ['SECTION', 'I', 'J', 'ID'])
TxNode = namedtuple('TxNode', ['SECTION', 'I', 'J', 'K', 'CKT'])

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
             'section_divider': r'^(?!.*(?:BEGIN\s+SUBSTATION|BEGIN\s+GNE)).*0\s*/\s*END\s+OF\s+.*$',
             # section divider (except substation section)
             'gne': r'\bBEGIN\s+GNE\s+DATA\b',  # gne special data lines with unique parsing rules
             'gne_special': r'^@! (REAL|INTG|CHAR)\d.*\)\)$',  # gne special data lines with unique parsing rules
             'substation_subsection': r'^@! BEGIN SUBSTATION.*',
             # subsection divider for substation data block and substation node data
             'substation_switching': r'.*BEGIN\s+SUBSTATION\s+SWITCHING\s+DEVICE\s+DATA\s*$',
             # section divider for substation switching data
             'eof': r'Q\s*',  # end of file indicator.
             }
BUILT_IN_TYPES = (object, str, float, int, complex, tuple, list, range, dict,
                  set, bytes, bytearray, frozenset, bool, None, type(None))


def clean_str(string: str):
    """
    Strip leading quotes and spaces.  .
    :param string: The input str
    :return: a float, int or stripped str
    """
    name_pattern = r'\s*N\s*A\s*M\s*E\s*'

    if not isinstance(string, str):
        return string
    result = string.strip("""'" \n""")

    if re.findall(name_pattern, string):
        result = 'NAME'

    return result


def typify(string: str):
    """
    Strip leading quotes and spaces.  Attempt to convert to float or int as appropriate.
    :param string: The input str
    :return: a float, int or stripped str
    """
    result = clean_str(string)

    try:
        return int(result)
    except (ValueError, TypeError):
        try:
            return float(result)
        except (ValueError, TypeError):
            return result


def flatten(lst: [list, tuple]) -> list:
    """
    If lst is a list[list], flatten it to a list.
    :param lst: a list or list[list]
    :type lst: list
    :return: flattened list
    :rtype: list
    """
    lst_flat = lst
    lst_flat = sum(lst, []) if lst and isinstance(lst[0], list) else lst_flat
    return lst_flat


def _parse_sys_wide_line(line: str) -> tuple[str, dict]:
    """
    Parse any line from the system-wide section of a PSSE .raw file.
    Examples:
        GENERAL, THRSHZ=0.0001, PQBRAK=0.7, BLOWUP=5.0
        GAUSS, ITMX=100, ACCP=1.6, ACCQ=1.6, ACCM=1.0, TOL=0.0001
        NEWTON, ITMXN=100, ACCN=1.0, TOLN=0.1, VCTOLQ=0.1, VCTOLV=0.00001, DVLIM=0.99, NDVFCT=0.99
        ADJUST, ADJTHR=0.005, ACCTAP=1.0, TAPLIM=0.05, SWVBND=100.0, MXTPSS=99, MXSWIM=10
        TYSL, ITMXTY=20, ACCTY=1.0, TOLTY=0.00001
        SOLVER, FDNS, ACTAPS=1, AREAIN=0, PHSHFT=0, DCTAPS=1, SWSHNT=1, FLATST=0, VARLIM=99, NONDIV=0
        RATING, 1, "CRCUS1", "Circus-Fibrous or threadlike    "
        RATING, 2, "CRSTR2", "Cirrostrarus-Milky, translucent "
        RATING, 3, "CRCUM3", "Cirrocumulus-small, white flakes"
        RATING, 4, "ALTCU4", "Altocumulus-bundles or rollers  "
        RATING, 5, "ALTST5", "Altostratus-dense, gray layer   "
        RATING, 6, "STRTO6", "Stratocumulus-plaices or rollers"
        RATING, 7, "STRTS7", "Stratus-Evenly grey, low layer  "
        RATING, 8, "CMULS8", "Cumulus-Heap with flat basis    "
        RATING, 9, "CMULO9", "Cumulonimbus-thunder, up-rises  "
        RATING,10, "NIBS10", "Nimbostratus-rain,grey, dark    "
        RATING,11, "CPLL11", "capillatus-haired, frayed       "
        RATING,12, "NBUL12", "nebulosus-fog, veil-like        "
    :param line:
    :return: tuple[str, dict]: 2-tuple of (subsection name, dict of k:v pairs)
    """
    # Find the first comma and split into subsection and remaining_str
    subsection, remaining_str = [_.strip() for _ in line.split(',', 1) if _]
    # Rating
    if subsection.upper() == 'RATING':
        parts = [_.strip() for _ in remaining_str.split(',')]
        return subsection, {typify(k): typify(v) for k, v in zip(['SET', 'NAME', 'DESCRIPTION'], parts)}

    # Split remaining_str by commas and process into a dictionary using dict comprehension
    parts = [(_.split('=', 1) + [None])[:2] for _ in remaining_str.split(',')]
    if subsection.upper() == 'SOLVER':
        parts[0] = ['METHOD', parts[0][0]]
    parts = {typify(_[0]): typify(_[1]) for _ in parts}

    return subsection, parts


def _get_line_type(line: str) -> str:
    """
    Determine the type of line in the raw file as per the regex patterns defined in _PATTERNS. If
    none of the patterns match, but it does match the pattern_csv (defined in code below), then type
    of line is 'data'.
    :param line: a line from the raw file
    :type line: str
    :return: a key value from _PATTERNS, which indictates the type of line
    :rtype: str
    """
    line = line.strip()
    # Find which of the regex patterns matches.  If no match found, return None.
    # Iterate through patterns and find matching pattern
    for pattern_name, pattern_regex in _PATTERNS.items():
        if re.match(pattern_regex, line):
            return pattern_name

    # If not match found, check if this line contains csv data.
    pattern_csv = '^(?:(?:"(?:[^"]|"")*"|[^,\n]*)(?:,(?:"(?:[^"]|"")*"|[^,\n]*))*\n?)*$'
    if re.match(pattern_csv, line) is not None:
        # Return 'data' if the line contains csv data
        return 'data'

    return None


def _section_name(string: str):
    """
    Parse the section name from a single line of a raw file.
    For example, return "LOAD" from string="0 / END OF BUS DATA, BEGIN LOAD DATA"
    :param string: a line from a raw file that contains a section header
    :return: the section name
    """
    pattern = r', BEGIN\s*(.*)'
    match = re.search(pattern, string)
    if match:
        # Return the section name, such as 'TRANSFORMER' or 'BUS'.
        return match.group(1).rstrip('DATA').strip()
    else:
        # Pattern is not found; return None.
        return None


def _append_to_graph(network_graph: nx.Graph,
                     record: dict,
                     section: str = None,
                     three_winding_model: str = 'tx as node'):
    # record = {k: v for k, v in zip(col_headers_flat, record_values)}
    if section is not None:
        record['TYPE'] = section
    assert 'TYPE' in record.keys()
    section_name = record['TYPE']

    if section_name in ['GNE', 'SUBSTATION', 'MULTI-TERMINAL DC']:
        # TODO: not implemented.
        warnings.warn('Multi-terminal DC not implemented.')
    if section_name in ['BUS', 'FIXED SHUNT', 'LOAD', 'GENERATOR', 'SWITCHED SHUNT', 'INDUCTION MACHINE']:
        if section_name == 'BUS':
            # BUS section_name has NAME column
            node_id = BusNode(section_name, record['I'])
            record['EXTENDED_NAME'] = f"{record['NAME']} {record['BASKV']}kV"
            network_graph.add_node(node_id, **record)
        elif 'ID' in record.keys():
            # non-BUS sectionS have ID column
            bus_name = network_graph.nodes[('BUS', record['I'])]['NAME']
            record['EXTENDED_NAME'] = f"{bus_name} ({section_name}): {record['ID']}"
            node_id = INode(section_name, record['I'], record['ID'])
            network_graph.add_node(node_id, **record)
            # Create edge from device to bus.
            network_graph.add_edge(node_id, ('BUS', record['I']), **record)
    elif section_name in ['BRANCH', 'SYSTEM SWITCHING', 'MULTI-SECTION LINE', 'FACTS DEVICE']:
        # Create edge from device to bus.
        # node_id = IJNode(section_name, record['I'], record['J'], record['ID'])
        i_bus_name = network_graph.nodes[('BUS', record['I'])]['EXTENDED_NAME']
        j_bus_name = network_graph.nodes[('BUS', record['J'])]['EXTENDED_NAME']
        if section_name == 'BRANCH':
            if 'ID' in record.keys():
                record['EXTENDED_NAME'] = f"{i_bus_name} - {j_bus_name} | {record['ID']}"
            elif 'NAME' in record.keys():
                record['EXTENDED_NAME'] = f"{i_bus_name} - {j_bus_name} | {record['NAME']}"
            else:
                print(f'{record = }')
                raise ValueError('missing ID or NAME')
        else:
            record['EXTENDED_NAME'] = f"{i_bus_name} - {j_bus_name} ({section_name}) | {record['ID']}"

        network_graph.add_edge(('BUS', record['I']), ('BUS', record['J']), **record)
    elif section_name in ['TRANSFORMER']:
        print('record.keys: ', record.keys())
        print('record: ', record)
        try:
            i_bus_name = network_graph.nodes[('BUS', record['I'])]['EXTENDED_NAME']
        except KeyError:
            i_bus_name = f"Bus_{record['I']}_not_found"
        try:
            j_bus_name = network_graph.nodes[('BUS', record['J'])]['EXTENDED_NAME']
        except KeyError:
            j_bus_name = f"Bus_{record['J']}_not_found"
        if record['K'] == 0:
            # 2-winding transformer record.
            record['EXTENDED_NAME'] = f"Tx {i_bus_name} - {j_bus_name} | CKT: {record['CKT']}"

            network_graph.add_edge(('BUS', record['I']), ('BUS', record['J']), **record)
        else:
            # 3-winding transformer record.
            # TODO: Discuss modeling methods below with Afzal.
            try:
                k_bus_name = network_graph.nodes[('BUS', record['K'])]['EXTENDED_NAME']
            except KeyError:
                k_bus_name = f"Bus_{record['K']}_not_found"
            record['EXTENDED_NAME'] = f"Tx {i_bus_name} - {j_bus_name}  - {k_bus_name} | CKT: {record['CKT']}"
            if three_winding_model == 'tx as node':
                # Model tx as a node with 3 branches (star): NAME-I, NAME-J, NAME-K
                # Create node
                node_id = TxNode(section_name, record['I'], record['J'], record['K'], record['CKT'])
                network_graph.add_node(node_id, **record)
                # Create edge from device to bus.
                short_record = {_: record[_] for _ in ['TYPE', 'NAME', 'I', 'J', 'K', 'CKT']}
                network_graph.add_edge(node_id, ('BUS', record['I']), **short_record)
                network_graph.add_edge(node_id, ('BUS', record['J']), **short_record)
                network_graph.add_edge(node_id, ('BUS', record['K']), **short_record)
            else:  # three_winding_model ==  'tx as branches'
                # Model tx as ring bus with branches (delta): I-J, J-K, K-I
                network_graph.add_edge(('BUS', record['I']), ('BUS', record['J']), **record)
                network_graph.add_edge(('BUS', record['I']), ('BUS', record['K']), **record)
                network_graph.add_edge(('BUS', record['J']), ('BUS', record['K']), **record)
    elif section_name in ['VSC DC LINE']:
        try:
            i_bus_name = network_graph.nodes[record['IBUS']]['EXTENDED_NAME']
            j_bus_name = network_graph.nodes[record['JBUS']]['EXTENDED_NAME']
        except KeyError as e:
            msg = (f'Unable to add TWO-TERMINAL DC edge ({record["IBUS"]} - {record["JBUS"]}).  '
                   f'Node {record["IBUS"]} or {record["JBUS"]} not found in model.')
            warnings.warn(msg)
            return
        record['EXTENDED_NAME'] = f"{record['NAME']} (VSC): {i_bus_name}  - {j_bus_name}"
        # Create edge from device to bus.
        i_node = BusNode('BUS', record['IBUS'])
        j_node = BusNode('BUS', record['JBUS'])
        network_graph.add_edge(i_node, j_node, **record)
    elif section_name in ['TWO-TERMINAL DC']:
        try:
            i_bus_name = network_graph.nodes[record['IPR']]['EXTENDED_NAME']
        except KeyError as e:
            msg = (f'Unable to add TWO-TERMINAL DC edge ({record["IPR"]} - {record["IPI"]}).  '
                   f'Node {record["IPR"]} not found in model.')
            warnings.warn(msg)
            return
        try:
            j_bus_name = network_graph.nodes[record['IPI']]['EXTENDED_NAME']
        except KeyError as e:
            msg = (f'Unable to add TWO-TERMINAL DC edge ({record["IPR"]} - {record["IPI"]}).  '
                   f'Node {record["IPI"]} not found in model.')
            warnings.warn(msg)
            return
        record['EXTENDED_NAME'] = f"{record['NAME']} (2-Term DC): {i_bus_name}  - {j_bus_name}"
        # Create edge from device to bus.
        i_node = BusNode('BUS', record['IPR'])
        j_node = BusNode('BUS', record['IPI'])
        network_graph.add_edge(i_node, j_node, **record)

        # Create edge from device to bus.
        network_graph.add_edge(record['IPR'], record['IPI'], **record)
        # Alternatively, include edges for IPR, IPI, IFR
        # and ITR, the rectifier, commutor, winding 1,
        # and winding 2.


def _get_col_headers(lines=list[str],
                     section: str = '',
                     version: [int, float] = 0
                     ) -> tuple[list, list]:  # -> tuple[list[list[str]], list[list[str]]]:
    """
    From a list of lines, find the first set of consecutive column header lines
    in the list of lines.

    Example:
    lines = [
        'col1, col2,col3' , 'col4, col5,col6,col7 '
    ]
    headers = _get_col_headers(lines)
    # headers = [['col1', 'col2', 'col3'],
                 ['col4', 'col5', 'col6', 'col7']
                 ]

    :param lines: list[str]: a list of lines from a PSSE RAW file.
    :return: list[list[str]]: a parsed list of consecutive column headers.
    """
    def rename_duplicates(col_headers):
        """
        handle renaming duplicates in a list of lists (col_headers), where each
        sublist represents column names, you can create a function that checks for
        duplicates and appends suffixes (2, 3, etc.) based on the index of the
        sublist.

        # EXAMPLE usage:
        col_headers = [['NAME', 'MDC', 'RDC'], ['IBUS', 'TYPE', 'MODE'], ['IBUS', 'TYPE', 'DCSET'], ['IBUS', 'TYPE', 'MODE']]
        updated_col_headers = rename_duplicates(col_headers)

        print("Original col_headers:")
        print(col_headers)

        print("\nUpdated col_headers:")
        print(updated_col_headers)

        RESULT:
        Original col_headers:
        [['NAME', 'MDC', 'RDC'], ['IBUS', 'TYPE', 'MODE'],
         ['IBUS', 'TYPE', 'DCSET'], ['IBUS', 'TYPE', 'MODE']]

        Updated col_headers:
        [['NAME', 'MDC', 'RDC'], ['IBUS', 'TYPE', 'MODE'],
         ['IBUS2', 'TYPE2', 'DCSET'], ['IBUS3', 'TYPE3', 'MODE3']]

        :param col_headers:
        :return:
        """
        seen_names = {}  # Dictionary to track seen names and their counts
        updated_col_headers = []  # List to store updated column headers

        for headers in col_headers:
            renamed_headers = []  # List to store renamed headers for current sublist

            for header in headers:
                if header in seen_names:
                    seen_names[header] += 1
                    new_header = f"{header}{seen_names[header]}"
                else:
                    seen_names[header] = 1
                    new_header = header

                renamed_headers.append(new_header)

            updated_col_headers.append(renamed_headers)  # Append the updated sublist to the new list

        return updated_col_headers
    _version = int(version)
    if section and _version in [33, 34, 35]:
        if _version in [33, 34]:
            dataformat = dataformat34
        else:  # elif _version in [35]:
            dataformat = dataformat35
        if isinstance(dataformat.DTYPE_RAW_DATA[section], dict):
            col_names = [list(dataformat.DTYPE_RAW_DATA[section].keys())]
            dtypes = [list(dataformat.DTYPE_RAW_DATA[section].values())]
        elif isinstance(dataformat.DTYPE_RAW_DATA[section], list):
            temp = tuple(dataformat.DTYPE_RAW_DATA[section])
            col_names = [list(inner_dict.keys()) for inner_dict in temp]
            dtypes = [list(inner_dict.values()) for inner_dict in temp]
        else:
            print()
            col_names = [dataformat.DTYPE_RAW_DATA[section]]
            # dtypes = [dtypes] if dtypes else dtypes
    else:
        col_names = []
        dtypes = []
        pattern1 = re.compile(_PATTERNS['column_names'])
        pattern2 = re.compile(_PATTERNS['column_names_case_id'])

        # column_names_case_id
        for line in lines[:5]:
            if not pattern1.match(line) and not pattern2.match(line) :
                return col_names
            line_cols = [clean_str(_) for _ in line[2:].split(',')]
            col_names.append(line_cols)

    col_names = rename_duplicates(col_names)

    # Flatten the list[list[str]] to a list[str]
    # col_headers_flat = sum(result, [])
    result = col_names, dtypes
    return result


def dtypes_to_base_dtypes(dtype_dict: dict) -> dict:
    for k, v in dtype_dict.items():
        if not isinstance(v, BUILT_IN_TYPES):
            dtype_dict[k] = v.__bases__
        else:
            dtype_dict[k] = v
    return dtype_dict

def read_case_raw(filename: str | Path, output_type: str = 'both',
                  three_winding_model: str = 'tx as node'
                  ) -> tuple[dict, nx.Graph]:
    """Reads a raw file.

    Args:
        filename (str): path of the file
        output_type (str): 'df', 'graph', 'both'.  Default: 'both'
        three_winding_model (str): 'tx as node', 'tx as edge'.  Default: 'tx as node'
                    'tx as node': model tx as a node with 3 branches (star): NAME-I, NAME-J, NAME-K
                    'tx as edge': model tx as ring bus with branches (star): I-J, J-K, K-I
    Returns:
        tuple[dict, nx.Graph]
            dict: Mapping of the RAW components
            nx.Graph: Model (NetworkX Graph)
    """
    filename = Path(filename)
    create_df = output_type in ['df', 'both']
    create_graph = output_type in ['graph', 'both']

    case = {}
    network_graph = None
    if create_graph:
        network_graph = nx.Graph()
        network_graph.name = filename.stem

    with io.open(filename, encoding="latin-1") as f:
        # Read all lines from the file
        lines = f.readlines()

    top_lines = [_ for _ in lines[:5] if _.strip()]
    try:
        # Get case info column headers line num, i.
        i, *_ = [(i, _) for i, _ in enumerate(top_lines) if _.startswith('@!')][0]
        # Get the major and minor version number from te PSSE RAW file.
        s = top_lines[i+1].split(r'PSS(R)E-')[1].strip().split(' ', 1)[0]
        _version: float = float(s)
    except ValueError:
        # Settle for the major version number from te PSSE RAW file.
        _version = int(top_lines[i+1].split(',')[2].strip())
    case['VERSION'] = _version
    section, subsection, line_type = 'CASE ID', None, None
    col_headers, col_headers_flat, data_types, data_types_flat = [], [], [], []
    record_line_num, end_record_line_index = 0, 0 # indicates the current record_line_num of end_record_line_index total lines in the record
    record_values, line_values = [], []
    for line_num, line in enumerate(lines):
        line_type = _get_line_type(line)
        match line_type:
            case 'eof':
                return case, network_graph
            case 'gne':
                section = 'GNE'
                records = None
                warnings.warn(f'GNE data not supported.  Skipping.')
            case 'gne_special':
                records = None
                # WIP: Future support for GNE special data:
                # special = line.strip()[2:8].strip(" ,.")
                # case.setdefault('GNE', {})
                # case['GNE'][special] = line.strip()[8:].split(',')
            case 'data':
                if section in ['GNE', 'CASE ID']:
                    # GNE section not supported.
                    continue
                col_headers_flat = flatten(col_headers)
                # col_headers_flat = [clean_str(_) for _ in col_headers_flat]
                data_types_flat = flatten(data_types)
                if section not in case.keys():
                    if data_types_flat:
                        # data_types_flat = data_types_flat
                        dtypes = {k: v for k, v in zip(col_headers_flat, data_types_flat)}
                        base_dtypes = dtypes_to_base_dtypes(dtypes)
                        # Create a dataframe to hold the data for this RAW section.
                        case[section] = pd.DataFrame(columns=col_headers_flat,
                                                     dtype=dtypes)
                    else:
                        # Create a dataframe to hold the data for this RAW section.
                        case[section] = pd.DataFrame(columns=col_headers_flat)

                # Parse values from current line of RAW file.
                line_values = [clean_str(_) for _ in line.split(',')]

                if record_line_num > end_record_line_index:
                    # This line is the start of a new record.  Reset record_line_num.
                    record_line_num = 0

                if record_line_num == 0 or end_record_line_index == 0:
                    # First line of current record.
                    record_values = line_values
                    if section == 'TRANSFORMER':
                        if line_values[2] in [0, '0']:  # i.e., if K==0:
                            # 2-winding transformer ahs 4 data lines.
                            end_record_line_index = 3
                        else:
                            # 3-winding transformer ahs 5 data lines.
                            end_record_line_index = 4
                    elif section in ['TWO-TERMINAL DC', '']:
                        # 3 data lines.
                        end_record_line_index = 2
                else:
                    # Not first line of current record.  Append data to current record values.
                    # if section == 'TRANSFORMER':
                    #     pass
                    record_values += line_values

                if section in ['GNE', 'SUBSTATION', 'MULTI-TERMINAL DC']:
                    warnings.warn(f'{section} data not supported.  Skipping.')
                elif record_line_num == end_record_line_index:
                    if create_df:
                        if len(record_values) < len(col_headers_flat):
                            record_values += [None] * (len(col_headers_flat) - len(record_values))
                        # Add the final record to dataframe, case[section].
                        try:
                            case[section].loc[len(case[section])] = record_values
                        except ValueError as e:
                            print(f'section ({type(section)}): {section}')
                            print(f'col_headers_flat {len(col_headers_flat)}: '
                                  f'{col_headers_flat[:10]}...')
                            print(f'record_values  ({type(record_values)}{len(record_values)}): '
                                  f'{record_values[:6]}...')
                            raise e
                        # Optionally, reset index if needed
                        # if isinstance(case[section], pd.DataFrame):
                        #     case[section].reset_index(drop=True, inplace=True)
                    if create_graph:  # Add node
                        record_values = [typify(_) for _ in record_values]
                        record = {k: v for k, v in zip(col_headers_flat, record_values)}
                        # print(f'\n\nsection: {section}')
                        # print('line_num: ', line_num)
                        # print('line: ', line)
                        # print('col_headers_flat: ', col_headers_flat)
                        # print('record_values: ', record_values)
                        # print('end_record_line_index: ', end_record_line_index)
                        # print('record_line_num: ', record_line_num)
                        # print('line_values: ', line_values)
                        _append_to_graph(network_graph=network_graph,
                                         record=record,
                                         section=section,
                                         three_winding_model=three_winding_model)

                record_line_num += 1
                if _get_line_type(lines[line_num+1]) != 'data':
                    # Convert the dataframe columns to other data types
                    # (instead of all str values).
                    if data_types_flat:
                        try:
                            case[section].astype(dtype=base_dtypes, errors='ignore')
                        except TypeError as e:
                            case[section] = convert_columns_to_numeric(case[section])
                    else:
                        case[section] = convert_columns_to_numeric(case[section])
                    pass
            case 'section_divider' | 'substation_subsection' | 'substation_switching':
                # Get the section name
                section = _section_name(line)
                col_headers, data_types = _get_col_headers(lines=lines[line_num + 1:line_num + 6],
                                                           section=section,
                                                           version=_version)
                col_headers_flat = flatten(col_headers)
                col_headers_flat = [typify(_) for _ in col_headers_flat]
                data_types_flat = flatten(data_types)
                if data_types_flat:
                    dtypes = {k: v for k, v in zip(col_headers_flat, data_types_flat)}
                    base_dtypes = dtypes_to_base_dtypes(dtypes)
                data = None
                case[section] = pd.DataFrame(columns=col_headers_flat)
                record_line_num, end_record_line_index = 0, len(col_headers) - 1
                record_values, line_values = [], []
            case 'column_names':
                # col_headers addressed under 'section_divider' |
                # 'substation_subsection' | 'substation_switching'
                data = None
                pass
            case 'column_names_case_id':
                # Case identification info from the top 2 liens of the RAW file
                record_line_num, end_record_line_indexend_record_line_index = 0, 1
                col_headers, data_types = _get_col_headers(lines=[lines[line_num]],
                                                           section=section,
                                                           version=_version)
                col_headers_flat = flatten(col_headers)
                col_headers_flat = [typify(_) for _ in col_headers_flat]
                data_types_flat = flatten(data_types)
                dtypes = {k: v for k, v in zip(col_headers_flat, data_types_flat)}
                base_dtypes = dtypes_to_base_dtypes(dtypes)
                data, comment = lines[line_num + 1].split('/', 1)
                data = [typify(_) for _ in data.split(',')]  # if data_types, then use data_types instead of thi line.
                # If extra data columns are provided, ignore extra data.
                data = data[:len(col_headers_flat)]
                # If not enough data columns provided, raise exception.
                if len(data) < len(col_headers_flat):
                    raise ValueError(f'len(data) != len(col_headers_flat): '
                                     f'{data} vs. {col_headers_flat}')
                case['CASE ID'] = pd.DataFrame(data=[data], columns=col_headers_flat)
                case['CASE ID'].astype(base_dtypes, errors='ignore')
                records = None
            case str if line_type.startswith("sys_wide"):
                section = 'SYSTEM-WIDE'
                case.setdefault('SYSTEM-WIDE', {})
                subsection, data = _parse_sys_wide_line(line=line)
                subsection = subsection.strip().upper()
                # col_headers = list(data.keys())
                if subsection == 'RATING':
                    case['SYSTEM-WIDE'].setdefault('RATING', {})
                    # if not 'RATING' in case['SYSTEM-WIDE'].keys():
                    #     case['SYSTEM-WIDE']['RATING'] = {}
                    case['SYSTEM-WIDE']['RATING'][data['SET']] = data
                else:
                    case[section][subsection] = data
                records = None

    # Reset the indices for all the dataframes in this case.
    for section in case.keys():
        if isinstance(case[section], pd.DataFrame):

            # Optionally, reset index if needed
            case[section].reset_index(drop=True, inplace=True)

    warnings.warn('End of file indicator, "Q", not found in RAW file.  RAW '
                  'file is not complete.')

    return case, network_graph


if __name__ == "__main__":
    from pathlib import Path

    fp = Path(__file__).absolute().parent.parent / 'tests/data/sample.raw'
    data, network_graph = read_case_raw(fp)
    print(network_graph.name)
    print()

