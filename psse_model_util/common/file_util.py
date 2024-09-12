from copy import deepcopy
import csv
import glob
import io
from pathlib import Path
import time
import warnings
import pickle

from psse_model_util.common.constants import DOWNLOAD_WAIT_SECONDS, RESILIENT

import pandas as pd


def uneven_lists_to_df(list_of_lists: list, columns: list =[],
                       header_rows: list | int| None=None) -> pd.DataFrame:
    """
    Converts a list of lists with uneven lengths into a pandas DataFrame,
    optionally using specified rows as headers.

    This function handles lists of lists where the inner lists may not all
    have the same length by padding shorter lists with `None` values. It can
    also handle extracting header row(s) from the data to use as column names
    in the resulting DataFrame.

    :param list_of_lists: A list of lists, where each inner list represents a
                row in the DataFrame. Inner lists can have variable lengths.
    :type list_of_lists: list
    :param columns: A list of column names for the DataFrame. If not provided
                or not enough names are provided, default names are generated
                in the format 'Col{i}'.
    :type columns: list, optional
    :param header_rows: An integer or a list of integers specifying the row(s)
                from `list_of_lists` that should be used as the header (column
                names). If `None`, no rows are used as headers, and `columns`
                or default column names are used instead.
    :type header_rows: list | int | None, optional
    :return: A pandas DataFrame created from the input list of lists, with
                columns named according to the `columns` parameter or derived
                from `header_rows`, and with rows padded with `None` values as
                necessary to match the length of the longest row.
    :rtype: pd.DataFrame

    **Example**::

        >>> list_of_lists = [[1, 2, 3], [4, 5], [6]]
        >>> columns = ['A', 'B', 'C']
        >>> df = uneven_lists_to_df(list_of_lists, columns)
        >>> print(df)
           A    B    C
        0  1  2.0  3.0
        1  4  5.0  NaN
        2  6  NaN  NaN
    """
    lol = deepcopy(list_of_lists)
    cols = columns.copy()
    # Read the header row(s) if specified
    if header_rows is None:
        pass
    else:
        if isinstance(header_rows, int):
            header_rows = [header_rows]
        # Read the rows at indices indicated by header_rows into a new variable
        cols = []
        for i in sorted(header_rows, reverse=True):
            cols.extend(lol.pop(i))

    # Determine the length of the longest row
    max_row_length = max(len(row) for row in lol)

    # Add empty/None values to make all rows have the same number of columns
    for row in lol:
        row.extend([None] * (max_row_length - len(row)))

    # If columns are not provided for all columns, add default column names
    if len(cols) < max_row_length:
        cols.extend(f'Col{i}' for i in range(len(cols), max_row_length))

    # Convert the list to a pandas DataFrame
    df = pd.DataFrame(lol, columns=cols)

    return df


def read_uneven_csv_file(file_path, columns=[],
                         header_rows: list | int | None = None,
                         as_dataframe=False):
    """
    Reads a CSV file that may have rows with variable numbers of columns. It
    can return the results either as a pandas DataFrame or as a list of lists,
    with optional custom column headers.

    :param file_path: The path to the CSV file to be read.
    :type file_path: str
    :param columns: A list specifying the names of the columns. If not
                provided, and `header_rows` is not specified, columns will be
                auto-named based on their order. If `header_rows` is specified,
                names from the specified rows will be used.
    :type columns: list, optional
    :param header_rows: Specifies one or more rows from the CSV to be used as
                header(s) for column names. Can be a single integer (for one
                header row) or a list of integers (for multiple header rows).
                If `None`, no row is treated as a header unless `columns` is
                explicitly provided.
    :type header_rows: list | int | None, optional
    :param as_dataframe: Determines the return type. If `True`, returns the
                data as a pandas DataFrame. If `False`, returns the data as a
                list of lists. Default is `False`.
    :type as_dataframe: bool, optional

    :return: Depending on the `as_dataframe` flag, returns either a pandas
                DataFrame or a list of lists containing the CSV data. If
                `as_dataframe` is True and either `columns` is provided or
                header rows are defined, the DataFrame will have column names
                accordingly. Otherwise, it returns a list of lists with raw
                CSV row data.
    :rtype: pandas.DataFrame or list

    **Example**::

        # Read CSV data into a DataFrame with auto-named columns
        df = read_uneven_csv_file('path/to/file.csv', as_dataframe=True)

        # Read CSV, specifying a single header row and returning a list of lists
        data = read_uneven_csv_file('path/to/file.csv', header_rows=0)
    """
    data = []
    assert isinstance(header_rows, int) \
           or isinstance(header_rows, list) \
           or isinstance(header_rows, tuple) \
           or header_rows is None

    with open(file_path, 'r') as file:
        csv_reader = csv.reader(file)

        # Iterate over each row in the CSV filea
        for row in csv_reader:
            data.append(row)

    # If `as_dataframe` is False, return the list of lists
    if not as_dataframe:
        return data

    return uneven_lists_to_df(list_of_lists=data, columns=columns, header_rows=header_rows)


def write_bytesio_to_disk(bytes_io, file_path: Path, overwrite: bool = True):
    """
    Writes the contents of a BytesIO object to a file on disk.

    This function writes the content of a BytesIO object to a specified file
    path. It can optionally overwrite existing files. If the target directory
    does not exist, it is created. If the file exists and `overwrite` is set
    to False, the function emits a warning instead of raising an error.

    :param bytes_io: A BytesIO object whose contents are to be written to disk.
    :type bytes_io: io.BytesIO
    :param file_path: The path (including file name) where the BytesIO content
                should be written. Can be a string or a Path object.
    :type file_path: Path
    :param overwrite: If True (default), an existing file at `file_path` will
                be overwritten. If False, and a file exists at `file_path`, a
                warning is issued.
    :type overwrite: bool, optional

    :raises AssertionError: If `bytes_io` is not an instance of io.BytesIO.
    :raises Exception: General exception catch for file writing process, with
                an error message warning.

    **Example**::

        from io import BytesIO
        from pathlib import Path

        # Create a BytesIO object
        bytes_io = BytesIO(b'Test content')

        # Specify the file path
        file_path = Path('/path/to/output.txt')

        # Write the BytesIO content to the specified file path
        write_bytesio_to_disk(bytes_io, file_path)

    Note that if the specified `file_path` directory does not exist, it will be created. If the file already exists, it will be overwritten by default, unless `overwrite` is set to False, in which case a warning will be issued without writing.
    """
    assert isinstance(bytes_io, io.BytesIO)

    if isinstance(file_path, str):
        file_path = Path(file_path)

    if not file_path.parent.exists():
        # Create the file_path.parent folder if it doesn't exist.
        file_path.parent.mkdir(parents=True, exist_ok=True)
    elif file_path.exists():
        if overwrite:
            # Remove the existing file, so we can write it anew.
            file_path.unlink()
        else:
            # File exists and overwrite=False, so we can't write the file.
            # raise FileExistsError
            warnings.warn('File exists and overwrite=False.  Cannot write file.')

    try:
        # Extract the content of the BytesIO object as bytes.
        bytes_data = bytes_io.getvalue()

        # Open a file for writing and write the bytes data to it.
        with open(file_path, 'wb') as file:
            file.write(bytes_data)

        print(f"BytesIO content has been written to '{file_path}'")
    except Exception as e:
        warnings.warn(f"Error: {e}")


def is_file_locked(filepath):
    """
    Check if the file at 'filepath' is locked or not.
    The approach is to try opening the file in append mode.
    If the file is locked, it should raise an exception.
    """
    try:
        # Attempt to open the file in append mode. If it's locked, this should fail.
        with open(filepath, 'a'):
            pass
        return False  # File is not locked
    except Exception as e:
        return True  # File is likely locked or another error occurred preventing access


def to_pickle(pickle_path: Path | str, data, resilient: bool = RESILIENT) -> bool:
    try:
        with open(pickle_path, 'wb') as file:
            pickle.dump(data, file)
            print(f'Cached object to disk as "{pickle_path}".')
            return True
    except Exception as e:
        if resilient:
            warnings.warn(f'Unable to cache object to disk as "{pickle_path}".  {str(e)}')
            return False
        else:
            raise e


def read_pickle(pickle_path: Path | str = None,
                 mode: str = 'rb', resilient: bool = RESILIENT):
    if not pickle_path.exists():
        if resilient:
            return None
        else:
            raise FileNotFoundError()

    try:
        with open(pickle_path, 'rb') as file:
            obj = pickle.load(file)
        print(f'Data loaded from cache: "{pickle_path}".')
    except Exception as e:
        if resilient:
            warnings.warn(f'Unable to read object from disk "{pickle_path}".  {str(e)}')
        else:
            raise e

    return obj
