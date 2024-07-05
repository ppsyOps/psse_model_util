"""
Parser for PSSE .raw and .seq files.
Supported PSSE versions: 33, 34 and 35.
"""
import re
import io
import warnings
import csv
import os

from psse_model_util import dataformat34
from psse_model_util import dataformat35

from pathlib import Path

# DTYPE_HEADERKEYS = DTYPE_RAW_DATA['HEADER']
# HEADERKEYS = list(dataformat34.DTYPE_RAW_DATA['HEADER'].keys())


def read_case_raw(filename: str | Path) -> dict:
    """Reads a raw file.

    Args:
        filename (str): path of the file

    Returns:
        dict: Mapping of the RAW components
    """
    dataformat = dataformat34
    case = {key: [] for key in dataformat.RAW_DATA.keys()}
    headerkeys = list(dataformat.DTYPE_RAW_DATA['HEADER'].keys())
    key = None

    with io.open(str(filename), encoding="latin-1") as f:
        for line in f:
            # Get type of data
            type_data = get_type_of_data(line)
            if type_data == "END":
                break  # End of file

            if type_data == "COMMENT":
                continue  # Skip comment

            if type_data == "HEADER":
                parts = get_parts(line.split("/")[0], headerkeys,
                                  dataformat.DTYPE_RAW_DATA['HEADER'])
                case["HEADER"] = parts
                # Get PSS/e version number: find the pattern "PSS(R)E-" followed by a float number
                match = re.search(r"PSS\(R\)E-(\d+\.\d+)", line)
                try:
                    _version = float(match.group(1)) if match else 0.0
                except:
                    try:
                        _version = case["HEADER"]['REV']
                    except KeyError:
                        _version = 0

                if int(_version) in [33, 34]:
                    dataformat = dataformat34
                elif int(_version) in [35]:
                    dataformat = dataformat35
                case = {key: [] for key in dataformat.RAW_DATA.keys()}
                headerkeys = list(dataformat.DTYPE_RAW_DATA['HEADER'].keys())
                case["VERSION"] = _version
                parts = get_parts(line.split("/")[0], headerkeys,
                                  dataformat.DTYPE_RAW_DATA['HEADER'])
                case["HEADER"] = parts
                continue

            if type_data == "SKIP":
                continue

            if type_data:  # Header of block data
                key = type_data
                continue

            # Populate dict if is in data block
            if key:
                if key not in dataformat.MULTILINECOMPONENTS:
                    # Get parts and pad with None missing info
                    parts = get_parts(line, dataformat.RAW_DATA[key], dataformat.DTYPE_RAW_DATA[key])

                    # Add to the case
                    case[key].append(parts)

                elif key == "TRANSFORMER":
                    components = []
                    for j, sublist in enumerate(dataformat.RAW_DATA[key]):
                        if not line:
                            continue
                        parts = get_parts(line, sublist, dataformat.DTYPE_RAW_DATA[key][j])
                        components.append(parts)
                        if j < 3:
                            line = next(f)
                        elif j == 3:
                            line = next(f) if components[0]["K"] != 0 else ""
                    # Append to case
                    case[key].append(components)
                else:
                    components = []
                    for j, sublist in enumerate(dataformat.RAW_DATA[key]):
                        parts = get_parts(line, sublist, dataformat.DTYPE_RAW_DATA[key][j])
                        components.append(parts)
                        if j < len(dataformat.RAW_DATA[key]) - 1:
                            line = next(f)
                    # Append to case
                    case[key].append(components)
    return case


def get_type_of_data(line):
    match_end = re.search(r"^Q", line)
    if match_end:
        return "END"

    # header pattern for any PSS/e case version 33 through 36.
    match_header = re.search(r"@!\s*IC,", line)
    if match_header:  #  line.startswith('@!IC,')
        return "HEADER"

    match_comment = re.search(r"^@!", line)
    if match_comment:
        return "COMMENT"

    match_data_type = re.search(r"(?<=BEGIN\s).*(?=\sDATA)", line)
    if match_data_type:
        return match_data_type.group()

    # esto es para el ultimo conjunto de elementos
    # para evitar leer el final del campo
    if "0" in line[0]:
        return "SKIP"

    return None


def get_parts(line, col_names, dtype):
    """Generates the data structure for a line in the RAW or SEQ.

    Args:
        line (str): line of data from the file
        col_names (list): list of fields of the element being read
        dtype (dict): data type of the element's field

    Returns:
        dict: mapping of fields -> value in its corresponding format
    """
    # Use csv reader to handle commas within quotes correctly
    f = io.StringIO(line)
    reader = csv.reader(f, skipinitialspace=True, quotechar="'")
    dtype = {k: (v[0] if isinstance(v, tuple) else v) for k, v in dtype.items()}

    for parts in reader:
        # Extend parts list with None values if it's shorter than data
        parts.extend([None] * (len(col_names) - len(parts)))
        component = {key: try_parse(dtype[key], part, line) for key, part in zip(col_names, parts)}
        return component


def try_parse(dtype, data, line=None):
    """Attempts to convert a piece of data to its corresponding data type.

    Args:
        dtype (fun): conversion function
        data (str): text with the value to convert

    Returns:
        any: converted data
    """
    try:
        if data and dtype == str:
            return dtype(data.replace("'", ""))
        return dtype(data)
    except TypeError:
        return None
    except ValueError as e:
        # TODO: put next 2 lines of code back in and address any raised warnings.
        #       msg = f'"parser.try_parse() failed for dtype: {dtype}, data: {data}, ValueError: {e}'
        #       warnings.warn(msg)
        return data


def read_case_seq(filename, psse_version: int | float = 34):
    """Reads a SEQ file.

    Args:
        filename (str): path of the SEQ file

    Returns:
        dict: mapping of SEQ data components
    """
    psse_version = int(psse_version)
    match psse_version:
        case 33:
            dataformat = dataformat34
        case 34:
            dataformat = dataformat34
        case 35:
            dataformat = dataformat35

    case = {key: [] for key in dataformat.SEQ_DATA.keys()}
    headerkeys = list(dataformat.DTYPE_RAW_DATA['HEADER'].keys())
    key = None

    with io.open(filename, encoding="latin-1") as f:

        for line in f:
            # Get type of data
            type_data = get_type_of_data(line)
            if type_data == "END":
                break  # End of file

            if type_data == "COMMENT":
                continue  # Skip comment

            if type_data == "HEADER":
                # parts = get_parts(line.split("/")[0], headerkeys, dataformat.DTYPE_RAW_DATA['HEADER'])
                # case["HEADER"] = parts
                continue

            if type_data == "SKIP":
                continue

            if type_data:  # Header of block data
                key = type_data
                continue

            if key:
                if key == "ZERO SEQ. TRANSFORMER":
                    is_three_winding = line.split(",")[2].strip() != "0"
                    if is_three_winding:
                        parts = get_parts(line, dataformat.SEQ_DATA[key][1], dataformat.DTYPE_SEQ_DATA[key][1])
                    else:
                        parts = get_parts(line, dataformat.SEQ_DATA[key][0], dataformat.DTYPE_SEQ_DATA[key][0])
                else:
                    parts = get_parts(line, dataformat.SEQ_DATA[key], dataformat.DTYPE_SEQ_DATA[key])

                case[key].append(parts)

    return case


if __name__ == "__main__":
    from pathlib import Path
    fp = Path(__file__).absolute().parent.parent / 'tests/data/sample.raw'
    result = read_case_raw(fp)
    print(result)
