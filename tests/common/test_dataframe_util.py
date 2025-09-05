import pytest
from datetime import datetime
import pytz
from psse_model_util.common.dataframe_util import convert_df_column_dtypes, coalesce
from psse_model_util.common.dataframe_util import create_empty_DataFrame
from psse_model_util.common.dataframe_util import make_df_naive, make_naive
from psse_model_util.common.dataframe_util import make_df_naive
from psse_model_util.common.dataframe_util import move_columns_far_left
from psse_model_util.common.dataframe_util import move_columns_far_right
from psse_model_util.common.dataframe_util import make_naive
from psse_model_util.common.dataframe_util import df_column_validator

import pandas as pd
import numpy as np
import arrow


@pytest.fixture
def sample_df1():
    return pd.DataFrame({
        'str_col': ['1', '2', '3', '4', '5'],
        'int_col': ['1', '2', '3', '4', '5'],
        'float_col': ['1.1', '2.2', '3.3', '4.4', '5.5'],
        'date_col': ['2021-01-01', '2021-01-02', '2021-01-03', '2021-01-04', '2021-01-05'],
        'mixed_col': ['1', '2.2', '3', '4.4', '5'],
        'text_col': ['a', 'b', 'c', 'd', 'e']
    })


def test_convert_all_columns_default(sample_df1):
    result = convert_df_column_dtypes(sample_df1)

    assert result['str_col'].dtype in ['int32', 'int64']
    assert result['int_col'].dtype in ['int32', 'int64']
    assert result['float_col'].dtype in ['float32', 'float64']
    assert result['date_col'].dtype == 'datetime64[ns]'
    assert result['mixed_col'].dtype in ['float32', 'float64']
    assert result['text_col'].dtype == 'object'


def test_convert_specific_columns(sample_df1):
    new_dtypes = {
        'int_col': [int],
        'float_col': [float],
        'date_col': [pd.to_datetime]
    }
    result = convert_df_column_dtypes(sample_df1, new_dtypes=new_dtypes, convert_all_columns=False)

    assert result['str_col'].dtype == 'object'
    assert result['int_col'].dtype in ['int32', 'int64']
    assert result['float_col'].dtype in ['float32', 'float64']
    assert result['date_col'].dtype == 'datetime64[ns]'
    assert result['mixed_col'].dtype == 'object'
    assert result['text_col'].dtype == 'object'


def test_inplace_conversion(sample_df1):
    original_id = id(sample_df1)
    result = convert_df_column_dtypes(sample_df1, inplace=True)

    assert id(result) == original_id
    assert result['int_col'].dtype in ['int32', 'int64']
    assert result['float_col'].dtype in ['float32', 'float64']
    assert result['date_col'].dtype == 'datetime64[ns]'


def test_not_inplace_conversion(sample_df1):
    original_id = id(sample_df1)
    result = convert_df_column_dtypes(sample_df1, inplace=False)

    assert id(result) != original_id
    assert result['int_col'].dtype in ['int32', 'int64']
    assert result['float_col'].dtype in ['float32', 'float64']
    assert result['date_col'].dtype == 'datetime64[ns]'
    assert sample_df1['int_col'].dtype == 'object'  # Original DataFrame should be unchanged


def test_custom_conversion_order(sample_df1):
    new_dtypes = {
        'mixed_col': [int, float]  # Try int first, then float
    }
    result = convert_df_column_dtypes(sample_df1, new_dtypes=new_dtypes)

    assert result['mixed_col'].dtype in ['float32', 'float64']  # Should end up as float


def test_failed_conversion():
    df = pd.DataFrame({
        'unconvertible': ['a', 'b', 'c', 'd', 'e']
    })
    result = convert_df_column_dtypes(df)

    assert result['unconvertible'].dtype == 'object'  # Should remain as object (string)


def test_empty_dataframe():
    df = pd.DataFrame()
    result = convert_df_column_dtypes(df)

    assert result.empty
    assert isinstance(result, pd.DataFrame)


def test_with_nan_values():
    df = pd.DataFrame({
        'with_nan': ['1', '2', np.nan, '4', '5']
    })
    result = convert_df_column_dtypes(df)

    assert result['with_nan'].dtype in ['float32', 'float64']  # Should convert to float due to NaN


def test_invalid_input():
    with pytest.raises(AssertionError):
        convert_df_column_dtypes([1, 2, 3])  # Not a DataFrame



@pytest.fixture
def sample_df2():
    return pd.DataFrame({
        'col1': [0, 1, 2, 3, 4, 5, 6, 7, 8],
        'col2': [0, 2, 4, 6, 8, 10, None, 14, None],
        'col3': [0, 3, 6, 9, 12, 15, 18, None, 0]
    })


def test_coalesce(sample_df2):
    result_df = coalesce(sample_df2, 'actual', 'col2', 'col3', drop=False)
    expected = [0., 2, 4, 6, 8, 10, 18, 14, 0]

    assert 'actual' in result_df.columns
    assert all(result_df['actual'] == expected)
    assert 'col2' in result_df.columns  # Because drop=False
    assert 'col3' in result_df.columns  # Because drop=False


def test_coalesce_with_drop(sample_df2):
    result_df = coalesce(sample_df2, 'actual', 'col2', 'col3', drop=True)
    expected = [0., 2, 4, 6, 8, 10, 18, 14, 0]

    assert 'actual' in result_df.columns
    assert all(result_df['actual'] == expected)
    assert 'col2' not in result_df.columns  # Because drop=True
    assert 'col3' not in result_df.columns  # Because drop=True


def test_coalesce_new_column_name(sample_df2):
    result_df = coalesce(sample_df2, 'new_column', 'col2', 'col3', drop=False)
    expected = [0., 2, 4, 6, 8, 10, 18, 14, 0]

    assert 'new_column' in result_df.columns
    assert all(result_df['new_column'] == expected)


def test_coalesce_all_null():
    df = pd.DataFrame({
        'col1': [None, None, None],
        'col2': [None, None, None]
    })
    result_df = coalesce(df, 'result', 'col1', 'col2', drop=False)

    assert 'result' in result_df.columns
    assert all(result_df['result'].isna())


def test_create_empty_DataFrame():
    df = create_empty_DataFrame([
        ('my_date', 'datetime64[ns]'),
        ('my_num', int),
        ('id', str),
        ('primary', bool),
        ('side', str),
        ('quantity', int),
        ('price', float)
    ])

    assert str(df['my_date'].dtype) == 'datetime64[ns]'
    assert str(df['my_num'].dtype) in ['int32', 'int64']  # Account for different systems
    assert str(df['id'].dtype) == 'object'
    assert str(df['primary'].dtype) == 'bool'
    assert str(df['side'].dtype) == 'object'
    assert str(df['quantity'].dtype) in ['int32', 'int64']  # Account for different systems
    assert str(df['price'].dtype) == 'float64'

def test_create_empty_DataFrame_with_invalid_type():
    with pytest.raises(TypeError):
        # Cannot create df column of type arrow.Arrow.  Should have
        # used type 'object' instead.
        create_empty_DataFrame([
            ('my_date', 'datetime64[ns]'),
            ('arrow', arrow.Arrow)
        ])


@pytest.fixture
def sample_datetime():
    return datetime(2023, 5, 1, 12, 0, 0, tzinfo=pytz.UTC)

@pytest.fixture
def sample_arrow():
    return arrow.get('2023-05-01T12:00:00+00:00')

def test_make_naive_with_timezone_aware_datetime(sample_datetime):
    result = make_naive(sample_datetime)
    assert result.tzinfo is None
    assert result == datetime(2023, 5, 1, 12, 0, 0)

def test_make_naive_with_timezone_naive_datetime():
    naive_dt = datetime(2023, 5, 1, 12, 0, 0)
    result = make_naive(naive_dt)
    assert result == naive_dt
    assert result.tzinfo is None

def test_make_naive_with_arrow(sample_arrow):
    result = make_naive(sample_arrow)
    assert isinstance(result, datetime)
    assert result.tzinfo is None
    assert result == datetime(2023, 5, 1, 12, 0, 0)

def test_make_naive_with_different_timezone():
    est_tz = pytz.timezone('US/Eastern')
    est_dt = datetime(2023, 5, 1, 8, 0, 0, tzinfo=est_tz)
    result = make_naive(est_dt)
    assert result.tzinfo is None
    assert result == datetime(2023, 5, 1, 8, 0, 0)

def test_make_naive_with_as_tz(sample_datetime):
    jst = pytz.timezone('Asia/Tokyo')
    result = make_naive(sample_datetime, as_tz=jst)
    assert result.tzinfo is None
    assert result == datetime(2023, 5, 1, 21, 0, 0)  # UTC+9

def test_make_naive_arrow_with_as_tz(sample_arrow):
    jst = pytz.timezone('Asia/Tokyo')
    result = make_naive(sample_arrow, as_tz=jst)
    assert result.tzinfo is None
    assert result == datetime(2023, 5, 1, 21, 0, 0)  # UTC+9


@pytest.fixture
def sample_df4():
    return pd.DataFrame({
        'date_utc': pd.to_datetime(['2023-05-01 12:00:00', '2023-05-02 13:00:00']).tz_localize('UTC'),
        'date_est': pd.to_datetime(['2023-05-01 08:00:00', '2023-05-02 09:00:00']).tz_localize('US/Eastern'),
        'number': [1, 2],
        'text': ['a', 'b']
    })


def test_make_df_naive_default(sample_df4):
    result = make_df_naive(sample_df4)

    assert result['date_utc'].dtype == 'datetime64[ns]'
    assert result['date_est'].dtype == 'datetime64[ns]'
    assert result['date_utc'].dt.tz is None
    assert result['date_est'].dt.tz is None
    assert result['date_utc'].iloc[0] == pd.Timestamp('2023-05-01 12:00:00')
    assert result['date_est'].iloc[0] == pd.Timestamp('2023-05-01 12:00:00')  # Converted to UTC then made naive


def test_make_df_naive_with_different_tz(sample_df4):
    jst = pytz.timezone('Asia/Tokyo')
    result = make_df_naive(sample_df4, as_tz=jst)

    assert result['date_utc'].dtype == 'datetime64[ns]'
    assert result['date_est'].dtype == 'datetime64[ns]'
    assert result['date_utc'].dt.tz is None
    assert result['date_est'].dt.tz is None
    assert result['date_utc'].iloc[0] == pd.Timestamp('2023-05-01 21:00:00')  # UTC+9
    assert result['date_est'].iloc[0] == pd.Timestamp('2023-05-01 21:00:00')  # EST converted to JST then made naive


def test_make_df_naive_non_datetime_columns(sample_df4):
    result = make_df_naive(sample_df4)

    assert result['number'].dtype == 'int64'
    assert result['text'].dtype == 'object'
    assert result['number'].tolist() == [1, 2]
    assert result['text'].tolist() == ['a', 'b']


def test_make_df_naive_empty_df():
    empty_df = pd.DataFrame()
    result = make_df_naive(empty_df)

    assert result.empty
    assert isinstance(result, pd.DataFrame)


def test_make_df_naive_no_datetime_columns():
    df = pd.DataFrame({
        'number': [1, 2, 3],
        'text': ['a', 'b', 'c']
    })
    result = make_df_naive(df)

    assert result.equals(df)  # Should be unchanged


def test_make_df_naive_mixed_aware_naive():
    mixed_df = pd.DataFrame({
        'aware': pd.to_datetime(['2023-05-01 12:00:00', '2023-05-02 13:00:00']).tz_localize('UTC'),
        'naive': pd.to_datetime(['2023-05-01 12:00:00', '2023-05-02 13:00:00'])
    })
    result = make_df_naive(mixed_df)

    assert result['aware'].dt.tz is None
    assert result['naive'].dt.tz is None
    assert result['aware'].iloc[0] == pd.Timestamp('2023-05-01 12:00:00')
    assert result['naive'].iloc[0] == pd.Timestamp('2023-05-01 12:00:00')


@pytest.fixture
def sample_series():
    return pd.Series([1, 2, 3, 4, 5], name='test_column')


def test_multiple_validations():
    series = pd.Series([1, 2, 3, 4, 5])
    result = df_column_validator(series, nullable=False, col_dtype=int, col_min=1, col_max=5, isin=[1, 2, 3, 4, 5])
    assert result == ''

def test_int_vs_int64_dtype():
    series = pd.Series([1, 2, 3, 4, 5])
    result = df_column_validator(series, col_dtype=int)
    assert result == ''

def test_float_vs_float64_dtype():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = df_column_validator(series, col_dtype=float)
    assert result == ''


@pytest.fixture
def sample_df3():
    return pd.DataFrame({
        'A': [1, 2, 3],
        'B': [4, 5, 6],
        'C': [7, 8, 9],
        'D': [10, 11, 12]
    })

def test_move_single_column_left(sample_df3):
    result = move_columns_far_left(sample_df3, ['C'])
    assert list(result.columns) == ['C', 'A', 'B', 'D']

def test_move_multiple_columns_left(sample_df3):
    result = move_columns_far_left(sample_df3, ['C', 'A'])
    assert list(result.columns) == ['C', 'A', 'B', 'D']

def test_move_all_columns_left(sample_df3):
    result = move_columns_far_left(sample_df3, ['D', 'C', 'B', 'A'])
    assert list(result.columns) == ['D', 'C', 'B', 'A']

def test_move_no_columns_left(sample_df3):
    result = move_columns_far_left(sample_df3, [])
    assert list(result.columns) == ['A', 'B', 'C', 'D']

def test_move_non_existent_column_left(sample_df3):
    result = move_columns_far_left(sample_df3, ['E', 'C'])
    assert list(result.columns) == ['C', 'A', 'B', 'D']

def test_move_duplicate_columns_left():
    df = pd.DataFrame({'A': [1, 2], 'B': [3, 4], 'A': [5, 6]})  # Creates df with columns ['A', 'B']
    result = move_columns_far_left(df, ['B', 'A'])
    assert list(result.columns) == ['B', 'A']

def test_input_as_tuple_left(sample_df3):
    result = move_columns_far_left(sample_df3, ('C', 'A'))
    assert list(result.columns) == ['C', 'A', 'B', 'D']

def test_preserve_data_left(sample_df3):
    result = move_columns_far_left(sample_df3, ['C', 'A'])
    pd.testing.assert_frame_equal(sample_df3, result[sample_df3.columns])

def test_empty_dataframe_left():
    df = pd.DataFrame()
    result = move_columns_far_left(df, ['A', 'B'])
    assert result.empty
    assert list(result.columns) == []

def test_dataframe_with_columns_but_no_rows_left():
    df = pd.DataFrame(columns=['A', 'B', 'C'])
    result = move_columns_far_left(df, ['B', 'C'])
    assert list(result.columns) == ['B', 'C', 'A']
    assert result.empty  # No rows

def test_move_non_existent_columns_in_non_empty_df_left():
    df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})
    result = move_columns_far_left(df, ['C', 'D', 'B'])
    assert list(result.columns) == ['B', 'A']




def test_move_single_column_right(sample_df3):
    result = move_columns_far_right(sample_df3, ['A'])
    assert list(result.columns) == ['B', 'C', 'D', 'A']

def test_move_multiple_columns_right(sample_df3):
    result = move_columns_far_right(sample_df3, ['A', 'C'])
    assert list(result.columns) == ['B', 'D', 'A', 'C']

def test_move_all_columns_right(sample_df3):
    result = move_columns_far_right(sample_df3, ['A', 'B', 'C', 'D'])
    assert list(result.columns) == ['A', 'B', 'C', 'D']

def test_move_no_columns_right(sample_df3):
    result = move_columns_far_right(sample_df3, [])
    assert list(result.columns) == ['A', 'B', 'C', 'D']

def test_move_non_existent_column_right(sample_df3):
    result = move_columns_far_right(sample_df3, ['E', 'C'])
    assert list(result.columns) == ['A', 'B', 'D', 'C']

def test_move_duplicate_columns_right():
    df = pd.DataFrame({'A': [1, 2], 'B': [3, 4], 'A': [5, 6]})  # Creates df with columns ['A', 'B']
    result = move_columns_far_right(df, ['A', 'B'])
    assert list(result.columns) == ['A', 'B']

def test_input_as_tuple_right(sample_df3):
    result = move_columns_far_right(sample_df3, ('A', 'C'))
    assert list(result.columns) == ['B', 'D', 'A', 'C']

def test_preserve_data_right(sample_df3):
    result = move_columns_far_right(sample_df3, ['A', 'C'])
    pd.testing.assert_frame_equal(sample_df3, result[sample_df3.columns])

def test_empty_dataframe_right():
    df = pd.DataFrame()
    result = move_columns_far_right(df, ['A', 'B'])
    assert result.empty
    assert list(result.columns) == []

def test_dataframe_with_columns_but_no_rows_right():
    df = pd.DataFrame(columns=['A', 'B', 'C'])
    result = move_columns_far_right(df, ['A', 'B'])
    assert list(result.columns) == ['C', 'A', 'B']
    assert result.empty  # No rows

def test_move_non_existent_columns_in_non_empty_df_right():
    df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})
    result = move_columns_far_right(df, ['C', 'D', 'B'])
    assert list(result.columns) == ['A', 'B']


if __name__ == "__main__":
    pytest.main()