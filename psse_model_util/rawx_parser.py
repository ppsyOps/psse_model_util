import json
import re
import pandas as pd

from psse_model_util.dataformat35 import SEQ_DATA, DTYPE_SEQ_DATA, DTYPE_RAW_DATA

from pathlib import Path


HEADERKEYS = list(DTYPE_RAW_DATA['HEADER'].keys())


def convert_df_column_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Converts the column types of each column of a dataframe from str to
    datetime, float or int if possible."""
    def convert_column(col):
        """Try to convert a column to datetime, float, or int, otherwise keep as string."""
        for dtype in [pd.to_datetime, float, int]:
            try:
                return col.apply(dtype)
            except (ValueError, TypeError):
                continue
        return col

    for col in df.columns:
        df[col] = convert_column(df[col])

    return df


def load_and_clean_json(file_path):
    """
    Loads and cleans the JSON file before parsing.
    """

    def clean_invalid_json_characters(json_string):
        """
        Cleans the JSON string by escaping invalid control characters.
        """
        # Define the invalid characters range (excluding valid JSON characters like \n, \t, etc.)
        # Remove control characters: 0x00-0x1F and 0x7F, except for newline (0x0A) and tab (0x09)
        json_string = re.sub(r'[\x00-\x09\x0B-\x1F\x7F]', lambda match: f"\\u{ord(match.group()):04x}", json_string)
        return json_string

    with open(file_path, 'r', encoding='utf-8') as file:
        raw_data = file.read()
        clean_data = clean_invalid_json_characters(raw_data)
        data = json.loads(clean_data)
    return data

def read_case_rawx(file_path: str | Path, create_dataframes: bool = True, tables_to_type: str = '') -> dict:
    """
    Parses the given PSS/e v35 Extended RAW Data file, containing case data.

    Explanation
    Load the JSON File:

    The JSON file is loaded into a Python dictionary using json.load().
    Extract General Information:

    The general object is directly extracted from the top level of the JSON.
    Extract Network Information:

    The network object is processed by iterating over each key-value pair.
    For each key (e.g., caseid, general, gauss), the fields and data are extracted.
    If data entries are lists, a list of dictionaries is created by zipping fields with each data entry.
    Otherwise, a single dictionary is created by zipping fields with the data entries.
    Return Parsed Data:

    The parsed data is returned as a dictionary for further use.
    This approach ensures that the JSON structure is dynamically parsed, accommodating varying keys and values within the network object.

    # Example 1 usage
    parsed_data = parse_rawx_file('path_to_json_file.json')

    # Display the parsed data (for demonstration purposes)
    import pprint
    pprint.pprint(parsed_data)

    # Example 2 usage:
    fp = Path(__file__).absolute().parent.parent / 'tests/data/sample_v35.rawx'
    result = parse_rawx_file(fp, tables_to_type='list_dict')
    print('file: ', fp.absolute())
    print('\ngeneral:', result['general'])
    print('\nnetwork:')
    for k, v in result['network'].items():
        if k in ['caseid', 'rating', 'bus']:
            print(f'{k}:')
            if isinstance(v, pd.DataFrame):
                print(v.head())
            else:
                print(v)

    :param tables_to_type: '', 'df', 'list_dict', 'list_list'
    :param file_path: Path to the JSON formatted .rawx file
                      (a PSS/e v35 Extended RAW Data file)
    :return: A dictionary with parsed data
    """
    # Open the .rawx file from disk
    file_path = Path(file_path)
    assert file_path.suffix.lower() == '.rawx'
    # with open(file_path, 'r') as file:
    #     data = json.load(file)
    data = load_and_clean_json(file_path)

    # RAWX files contain 2 main sections, 'general' and 'network'.
    parsed_rawx_file = {}
    parsed_rawx_file['general'] = data.get('general', {})
    # Extract network information
    network_data = data.get('network', {})
    # network_data is a  dict like
    #   {'bus': {'fields': ["ibus", "name", "baskv", "ide",...],
    #            'values': [[], [], ...]},
    #    'branch': {'fields': ["ibus", "jbus", "ckt", "hstate", ...],
    #               'values': [[], [], ...]}
    #   }

    # Read the 'network' section of the raw file, which includes equipment data
    # like bus, branch, transformer, etc.
    parsed_rawx_file['network'] = {}
    for key, value in network_data.items():
        # key: str: equipment type like 'bus'.
        # value: dict[dict], where outer dict keys are 'fields' and 'data'.
        fields = value.get('fields', [])  # list[str]
        data_entries = value.get('data', [])  # list or list[list]: list of lists of row data like [[], [], ...]
        if tables_to_type.lower() in ['df', 'list_dict']:
            # Create a DataFrame for each key in network
            if not data_entries:
                parsed_rawx_file['network'][key] = pd.DataFrame(columns=fields)
            elif isinstance(data_entries[0], list):
                # If the data entries are lists (e.g., for "bus", "load")
                parsed_rawx_file['network'][key] = pd.DataFrame(data_entries, columns=fields)
                if tables_to_type.lower() == 'list_dict':
                    parsed_rawx_file['network'][key] = parsed_rawx_file['network'][key].to_dict(orient='records')
            else:
                # If the data entries are not lists (e.g., for "caseid", "general", "gauss")
                # parsed_rawx_file['network'][key] = pd.DataFrame([data_entries], columns=fields)
                parsed_rawx_file['network'][key] = dict(zip(fields, data_entries))
        else:  # tables_to_type.lower() == 'list_list':
            if not data_entries:
                parsed_rawx_file['network'][key] = None
            elif isinstance(data_entries[0], list):
                # If the data entries are lists (e.g., for "bus", "load")
                parsed_rawx_file['network'][key] = [dict(zip(fields, entry)) for entry in data_entries]
            else:
                # If the data entries are not lists (e.g., for "caseid", "general", "gauss")
                parsed_rawx_file['network'][key] = dict(zip(fields, data_entries))

    return parsed_rawx_file


if __name__ == "__main__":
    from pathlib import Path
    fp = Path(__file__).absolute().parent.parent / 'tests/data/sample_v35.rawx'
    result = read_case_rawx(fp, tables_to_type='list_dict')
    print('file: ', fp.absolute())
    print('\ngeneral:', result['general'])
    print('\nnetwork:')
    for k, v in result['network'].items():
        if k in ['caseid', 'rating', 'bus']:
            print(f'{k}:')
            if isinstance(v, pd.DataFrame):
                print(v.head())
            else:
                print(v)

