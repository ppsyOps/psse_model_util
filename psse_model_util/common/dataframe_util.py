from typing import Union
import re
from datetime import datetime as dtdt
import arrow

from pathlib import Path

import numpy as np
import pandas as pd
import pytz

# If df[col1] is null get value from df[col1]
def coalesce(df: pd.DataFrame, new_col: str, col1: str, col2: str,
             drop=True) -> pd.DataFrame:
    """
    caolesce says: if data in one column (col1) of a dataframe is missing, then fill
    it with data from another column (col2) and save it to new_col.
    :param df: pd.DataFrame to process
    :param new_col: name of column in df in which to place the result.  Note
                    that you could set new_col to an existing column name, such
                    as col1, which would overwrite that column.
    :param col1: Use data from this column if not None/NaN, else use col2
    :param col2: Use data from this column if col1 contains None/NaN
    :param drop: bool: if True, drop col1 and col2.
                       if True, do not drop any columns.
    :return: pd.DataFrame
    Make column c which takes the value in c1, unless it is null,
    in which case it uses the value in c2.  If `drop`, columns c1 and
    c2 and removed"""
    df[new_col] = df[col1].fillna(df[col2])
    if drop:
        df.drop([col1, col2], axis=1, inplace=True)
    return df


def create_empty_DataFrame(columns, index_col=None):
    """
    Create an empty dataframe and specify the datatype of each column.
    Ex: df = create_empty_DataFrame([('my_date', 'datetime64[ns]'),
                                     ('my_num', int),
                                     ('id', str),
                                     ('primary', bool),
                                     ('side', str),
                                     ('quantity', int),
                                     ('price', float)
                                     ]
                                    )
    :param columns: list of 2-tuples, where each tuple is a pair of column name and data type.
    :return: an empty pandas DataFrame with the specified column names and data types.
    """
    if index_col:
        index_type = next((t for name, t in columns if name == index_col))
        df = pd.DataFrame({name: pd.Series(dtype=t)
                           for name, t in columns if name != index_col},
                          index=pd.Index([], dtype=index_type))
    else:
        df = pd.DataFrame({name: pd.Series(dtype=t)
                           for name, t in columns if name != index_col})
    cols = [name for name, _ in columns]
    if index_col:
        cols.remove(index_col)
    return df[cols]


def make_naive(datetime_value: arrow.Arrow | dtdt,
               as_tz=None):
    """
    Converts an arrow.Arrow or datetime with timezone to a datetime
    that is time zone naive.  If a timezone is part of datetime_value,
    the datetime is converted to as_tz before stripping time zone info.
    :param datetime_value:
    :return: naive datetime.datetime value, i.e., datetime_value stripped of
             tz_info.
    """
    if datetime_value.tzinfo == None:
        return datetime_value
    elif isinstance(datetime_value, arrow.Arrow):
        datetime_value = datetime_value.datetime
    if as_tz:
        return datetime_value.astimezone(as_tz).replace(tzinfo=None)
    else:
        return datetime_value.replace(tzinfo=None)


def make_df_naive(df: pd.DataFrame, as_tz = pytz.UTC):
    """
    Convert all datetime columns in a dataframe from aware to naive.
    :param df: pd.DataFrame to process.
    :param as_tz: a valid datetime.tzinfo object, like pytz.UTC
    :return:
    """
    for col in df.columns:
        if df[col].dtype == 'datetime64[ns]':
            df[col] = df[col].apply(lambda x: make_naive(x, as_tz))
    return df


def df_column_validator(df_column: pd.Series,
                        nullable: bool = None,
                        col_dtype=None,
                        col_min=None,
                        col_max=None,
                        isin: list = [],
                        pattern: str = '',
                        pattern_criteria: str = 'all') -> str:
    """
    Validates data in a specific dataframe column.
    :param df_column: a pd.Series, like df['column_name']
    :param nullable: True if col_name is allowed to contain null values, else
                     False. If null, validation is skipped.
    :param col_dtype: Expected dtype of col_name.  If null, validation is
                      skipped. Optionally, provide a list/tuple of types.
    :param col_min: Min permissible value.  If null, validation is skipped.
    :param col_max: Max permissible value.  If null, validation is skipped.
    :param pattern: str: regex pattern to find in df_column.  If '', validation
                         is skipped.
    :param pattern_criteria: 'all' or 'any'.  If 'all', then pattern must match
                             for every row/item in df_column.  If any, then
                             even a single row match is considered success.
    :return: A str describing failed validatations.  Returns an empty str if
             all validations pass.
    """
    pattern_criteria: str = pattern_criteria.lower()
    if not isinstance(df_column, pd.Series) \
            and not isinstance(df_column, pd.DataFrame):
        df_column = pd.Series(df_column)
    result = ''
    if nullable is False and df_column.isnull().values.any():
        result += 'Cannot contain null values.  '
    if col_dtype and df_column.dtype != col_dtype:
        if isinstance(col_dtype, list) or isinstance(col_dtype, tuple) \
                and df_column.dtype not in col_dtype:
            result += f'Expected dtype to be in {col_dtype}; got {df_column.dtype}.  '
        elif df_column.dtype != col_dtype:
            if 'datetime' in str(col_dtype) and 'datetime' in str(df_column.dtype):
                # df_column is a datetime as expected.
                pass
            else:
                result += f'Expected dtype {col_dtype}; got {df_column.dtype}.  '
    if col_min is not None and df_column.min() < col_min:
        result += f'{df_column.min()} < allowable min, {col_min}.  '
    if col_max is not None and df_column.max() > col_max:
        result += f'{df_column.max()} > allowable max, {col_max}.  '
    if isin and not df_column.isin(isin).all():
        result += 'Contains a value not in: {isin}'
    if pattern:
        series = df_column.astype(str, copy=True)
        if isinstance(pattern, str):
            compiled = re.compile(pattern)
        elif isinstance(pattern, re.Pattern):
            pass
        else:
            raise TypeError(f'pattern must be str or re.Pattern (i.e., a '
                            f'compiled regex pattern).')

        if pattern_criteria == 'all':
            b = series.apply(lambda x: bool(re.search(pattern=compiled,
                                                      string=x))).all()
        elif pattern_criteria == 'any':
            b = series.apply(lambda x: bool(re.search(pattern=compiled,
                                                      string=x))).any()
        else:
            raise ValueError('pattern_criteria must be in ["all", "any"]')
        if not b:
            result += f're.search({pattern}, ["{df_column.name}"]).{pattern_criteria}() not satisfied.'

    return result


def df_to_excel_worksheet(dataframe: pd.DataFrame, sheet_name: str,
                filepath: Union[str, Path] = Path(),
                if_sheet_exists='replace',
                **kwargs):
    """
    Write a dataframe to a specific Excel worksheet without overwriting other
    worksheets.
    :param dataframe: The dataframe to export to Excel.
    :param sheet_name: The name of the Excel worksheet to overwrite.
    :param filepath: The path to the Excel workbook.
    :param if_sheet_exists: If True and sheet_name exists, it will be
               overwritten. If False and sheet_name exists, an exception will
               be raised.
    :param kwargs: additional arguments to pass to pd.DataFrame.to_excel().
    """
    dataframe = make_df_naive(dataframe)
    kwargs.setdefault('index', False)
    kwargs.setdefault('na_rep', '')
    kwargs.setdefault('merge_cells', False)

    # Ensure filepath is a Path object
    filepath = Path(filepath)

    # Check if directory exists, create it if it does not
    if not filepath.parent.exists():
        filepath.parent.mkdir(parents=True, exist_ok=True)

    mode = 'a' if Path(filepath).exists() and Path(filepath).is_file() else 'w'

    if mode.startswith('w'):
        with pd.ExcelWriter(filepath, engine='openpyxl', mode=mode) as writer:
            dataframe.to_excel(writer, sheet_name=sheet_name, **kwargs)
    else:
        # if_sheet_exists is only valid in append mode (mode='a')
        with pd.ExcelWriter(filepath, mode=mode,
                            if_sheet_exists=if_sheet_exists) as writer:
            dataframe.to_excel(writer, sheet_name=sheet_name, **kwargs)

def move_columns_far_left(df: pd.DataFrame, columns_to_move: list | tuple):
    """
    Move a specified subset of columns (columns_to_move) to the far left (the beginning) of the dataframe.

    Verbose version of code:
        # Filter out cols_to_move from the original DataFrame's columns
        remaining_cols = [col for col in df.columns if col not in columns_to_move]
        # Concatenate the moved columns with the remaining columns
        new_order = columns_to_move + remaining_cols
        #  Reindex the DataFrame using this new column order
        return df[new_order]

    :param df: pd.DataFrame for which to modify the column order
    :param columns_to_move: Columns to move to the far left (the beginning) of the dataframe.
    :return: The DataFrame with columns re-ordered.
    """
    return df[columns_to_move + [col for col in df.columns if col not in columns_to_move]]


def move_columns_far_right(df: pd.DataFrame, columns_to_move: list | tuple):
    """
    Move a specified subset of columns (columns_to_move) to the far right (the end) of the dataframe.
    :param df: pd.DataFrame for which to modify the column order
    :param columns_to_move: Columns to move to the far right (the end) of the dataframe.
    :return: The DataFrame with columns re-ordered.
    """
    return df[[col for col in df.columns if col not in columns_to_move] + columns_to_move]


# Function to convert DataFrame columns to numeric (int/float)
def convert_columns_to_numeric(df):
    """
    Automatically convert DataFrame columns from string to numeric (int/float)
    if applicable.

    Parameters:
    df (pd.DataFrame): The input DataFrame with string values.

    Returns:
    pd.DataFrame: The DataFrame with columns converted to numeric types where possible.
                  Non-convertible values are set to NaN.
    """
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

if __name__ == '__main__':

    # --------------------  Multiple Dataframes -------------------------------

    # SQL-like join two dataframes (inner, outer, left, right, cross).
    # Note: use now="cross" for a cartesian join.
    df1 = pd.DataFrame({'A': list(range(10)), 'Ax2': list(range(0, 20, 2))})
    df2 = pd.DataFrame({'A': list(range(10)), 'Ax3': list(range(0, 30, 3))})
    df3 = pd.merge(df1, df2, how='left', left_on=['A'], right_on=['A'])


    # --------------------------  Columns  ------------------------------------

    # Reorder columns.
    df = pd.DataFrame(np.random.rand(10, 4), columns=['A', 'C', 'B', 'D'])
    df = df.reindex(columns=['A', 'B', 'C', 'D'])

    # Drop columns.
    df = pd.DataFrame(np.random.rand(10, 4), columns=['A', 'B', 'C', 'D'])
    df.drop(['C', 'D'], axis=1)
