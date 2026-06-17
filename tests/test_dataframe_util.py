"""
test_dataframe_util.py — dataframe_util function tests.

Ported from tests/legacy_tests/common/test_dataframe_util.py; updated for the
current API and project layout after refactoring.
"""
from __future__ import annotations

from datetime import datetime

import arrow
import numpy as np
import pandas as pd
import pytest
import pytz

from psse_model_util.common.dataframe_util import (
    coalesce,
    convert_df_column_dtypes,
    create_empty_DataFrame,
    df_column_validator,
    make_df_naive,
    make_naive,
    move_columns_far_left,
    move_columns_far_right,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df1():
    return pd.DataFrame({
        "str_col":   ["1", "2", "3", "4", "5"],
        "int_col":   ["1", "2", "3", "4", "5"],
        "float_col": ["1.1", "2.2", "3.3", "4.4", "5.5"],
        "date_col":  ["2021-01-01", "2021-01-02", "2021-01-03", "2021-01-04", "2021-01-05"],
        "mixed_col": ["1", "2.2", "3", "4.4", "5"],
        "text_col":  ["a", "b", "c", "d", "e"],
    })


@pytest.fixture
def sample_df2():
    return pd.DataFrame({
        "col1": [0, 1, 2, 3, 4, 5, 6, 7, 8],
        "col2": [0, 2, 4, 6, 8, 10, None, 14, None],
        "col3": [0, 3, 6, 9, 12, 15, 18, None, 0],
    })


@pytest.fixture
def sample_df3():
    return pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9], "D": [10, 11, 12]})


@pytest.fixture
def sample_df4():
    return pd.DataFrame({
        "date_utc": pd.to_datetime(["2023-05-01 12:00:00", "2023-05-02 13:00:00"]).tz_localize("UTC"),
        "date_est": pd.to_datetime(["2023-05-01 08:00:00", "2023-05-02 09:00:00"]).tz_localize("US/Eastern"),
        "number": [1, 2],
        "text": ["a", "b"],
    })


@pytest.fixture
def sample_datetime():
    return datetime(2023, 5, 1, 12, 0, 0, tzinfo=pytz.UTC)


@pytest.fixture
def sample_arrow():
    return arrow.get("2023-05-01T12:00:00+00:00")


# ---------------------------------------------------------------------------
# convert_df_column_dtypes
# ---------------------------------------------------------------------------

def test_convert_all_columns_default(sample_df1):
    result = convert_df_column_dtypes(sample_df1)
    assert result["str_col"].dtype in ["int32", "int64"]
    assert result["int_col"].dtype in ["int32", "int64"]
    assert result["float_col"].dtype in ["float32", "float64"]
    assert pd.api.types.is_datetime64_any_dtype(result["date_col"])
    assert result["mixed_col"].dtype in ["float32", "float64"]
    assert pd.api.types.is_string_dtype(result["text_col"])


def test_convert_specific_columns(sample_df1):
    new_dtypes = {"int_col": [int], "float_col": [float], "date_col": [pd.to_datetime]}
    result = convert_df_column_dtypes(sample_df1, new_dtypes=new_dtypes, convert_all_columns=False)
    assert pd.api.types.is_string_dtype(result["str_col"])
    assert result["int_col"].dtype in ["int32", "int64"]
    assert result["float_col"].dtype in ["float32", "float64"]
    assert pd.api.types.is_datetime64_any_dtype(result["date_col"])
    assert pd.api.types.is_string_dtype(result["mixed_col"])
    assert pd.api.types.is_string_dtype(result["text_col"])


def test_inplace_conversion(sample_df1):
    original_id = id(sample_df1)
    result = convert_df_column_dtypes(sample_df1, inplace=True)
    assert id(result) == original_id
    assert result["int_col"].dtype in ["int32", "int64"]
    assert result["float_col"].dtype in ["float32", "float64"]
    assert pd.api.types.is_datetime64_any_dtype(result["date_col"])


def test_not_inplace_conversion(sample_df1):
    original_id = id(sample_df1)
    result = convert_df_column_dtypes(sample_df1, inplace=False)
    assert id(result) != original_id
    assert result["int_col"].dtype in ["int32", "int64"]
    assert result["float_col"].dtype in ["float32", "float64"]
    assert pd.api.types.is_datetime64_any_dtype(result["date_col"])
    assert pd.api.types.is_string_dtype(sample_df1["int_col"])


def test_custom_conversion_order(sample_df1):
    new_dtypes = {"mixed_col": [int, float]}
    result = convert_df_column_dtypes(sample_df1, new_dtypes=new_dtypes)
    assert result["mixed_col"].dtype in ["float32", "float64"]


def test_failed_conversion():
    df = pd.DataFrame({"unconvertible": ["a", "b", "c", "d", "e"]})
    result = convert_df_column_dtypes(df)
    assert pd.api.types.is_string_dtype(result["unconvertible"])


def test_convert_empty_dataframe():
    result = convert_df_column_dtypes(pd.DataFrame())
    assert result.empty
    assert isinstance(result, pd.DataFrame)


def test_convert_with_nan_values():
    df = pd.DataFrame({"with_nan": ["1", "2", np.nan, "4", "5"]})
    result = convert_df_column_dtypes(df)
    assert result["with_nan"].dtype in ["float32", "float64"]


def test_convert_invalid_input():
    with pytest.raises(AssertionError):
        convert_df_column_dtypes([1, 2, 3])


# ---------------------------------------------------------------------------
# coalesce
# ---------------------------------------------------------------------------

def test_coalesce(sample_df2):
    result = coalesce(sample_df2, "actual", "col2", "col3", drop=False)
    assert list(result["actual"]) == [0., 2, 4, 6, 8, 10, 18, 14, 0]
    assert "col2" in result.columns
    assert "col3" in result.columns


def test_coalesce_with_drop(sample_df2):
    result = coalesce(sample_df2, "actual", "col2", "col3", drop=True)
    assert list(result["actual"]) == [0., 2, 4, 6, 8, 10, 18, 14, 0]
    assert "col2" not in result.columns
    assert "col3" not in result.columns


def test_coalesce_new_column_name(sample_df2):
    result = coalesce(sample_df2, "new_column", "col2", "col3", drop=False)
    assert list(result["new_column"]) == [0., 2, 4, 6, 8, 10, 18, 14, 0]


def test_coalesce_all_null():
    df = pd.DataFrame({"col1": [None, None, None], "col2": [None, None, None]})
    result = coalesce(df, "result", "col1", "col2", drop=False)
    assert result["result"].isna().all()


# ---------------------------------------------------------------------------
# create_empty_DataFrame
# ---------------------------------------------------------------------------

def test_create_empty_DataFrame():
    df = create_empty_DataFrame([
        ("my_date", "datetime64[ns]"),
        ("my_num", int),
        ("id", str),
        ("primary", bool),
        ("side", str),
        ("quantity", int),
        ("price", float),
    ])
    assert pd.api.types.is_datetime64_any_dtype(df["my_date"])
    assert str(df["my_num"].dtype) in ["int32", "int64"]
    assert pd.api.types.is_string_dtype(df["id"])
    assert str(df["primary"].dtype) == "bool"
    assert pd.api.types.is_string_dtype(df["side"])
    assert str(df["quantity"].dtype) in ["int32", "int64"]
    assert str(df["price"].dtype) == "float64"


def test_create_empty_DataFrame_with_invalid_type():
    with pytest.raises(TypeError):
        create_empty_DataFrame([("my_date", "datetime64[ns]"), ("arrow", arrow.Arrow)])


# ---------------------------------------------------------------------------
# make_naive
# ---------------------------------------------------------------------------

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
    est_tz = pytz.timezone("US/Eastern")
    est_dt = datetime(2023, 5, 1, 8, 0, 0, tzinfo=est_tz)
    result = make_naive(est_dt)
    assert result.tzinfo is None
    assert result == datetime(2023, 5, 1, 8, 0, 0)


def test_make_naive_with_as_tz(sample_datetime):
    jst = pytz.timezone("Asia/Tokyo")
    result = make_naive(sample_datetime, as_tz=jst)
    assert result.tzinfo is None
    assert result == datetime(2023, 5, 1, 21, 0, 0)


def test_make_naive_arrow_with_as_tz(sample_arrow):
    jst = pytz.timezone("Asia/Tokyo")
    result = make_naive(sample_arrow, as_tz=jst)
    assert result.tzinfo is None
    assert result == datetime(2023, 5, 1, 21, 0, 0)


# ---------------------------------------------------------------------------
# make_df_naive
# ---------------------------------------------------------------------------

def test_make_df_naive_default(sample_df4):
    result = make_df_naive(sample_df4)
    assert pd.api.types.is_datetime64_any_dtype(result["date_utc"])
    assert pd.api.types.is_datetime64_any_dtype(result["date_est"])
    assert result["date_utc"].dt.tz is None
    assert result["date_est"].dt.tz is None
    assert result["date_utc"].iloc[0] == pd.Timestamp("2023-05-01 12:00:00")
    assert result["date_est"].iloc[0] == pd.Timestamp("2023-05-01 12:00:00")


def test_make_df_naive_with_different_tz(sample_df4):
    jst = pytz.timezone("Asia/Tokyo")
    result = make_df_naive(sample_df4, as_tz=jst)
    assert result["date_utc"].dt.tz is None
    assert result["date_est"].dt.tz is None
    assert result["date_utc"].iloc[0] == pd.Timestamp("2023-05-01 21:00:00")
    assert result["date_est"].iloc[0] == pd.Timestamp("2023-05-01 21:00:00")


def test_make_df_naive_non_datetime_columns(sample_df4):
    result = make_df_naive(sample_df4)
    assert result["number"].dtype == "int64"
    assert pd.api.types.is_string_dtype(result["text"])
    assert result["number"].tolist() == [1, 2]
    assert result["text"].tolist() == ["a", "b"]


def test_make_df_naive_empty_df():
    result = make_df_naive(pd.DataFrame())
    assert result.empty
    assert isinstance(result, pd.DataFrame)


def test_make_df_naive_no_datetime_columns():
    df = pd.DataFrame({"number": [1, 2, 3], "text": ["a", "b", "c"]})
    result = make_df_naive(df)
    assert result.equals(df)


def test_make_df_naive_mixed_aware_naive():
    mixed_df = pd.DataFrame({
        "aware": pd.to_datetime(["2023-05-01 12:00:00", "2023-05-02 13:00:00"]).tz_localize("UTC"),
        "naive": pd.to_datetime(["2023-05-01 12:00:00", "2023-05-02 13:00:00"]),
    })
    result = make_df_naive(mixed_df)
    assert result["aware"].dt.tz is None
    assert result["naive"].dt.tz is None
    assert result["aware"].iloc[0] == pd.Timestamp("2023-05-01 12:00:00")
    assert result["naive"].iloc[0] == pd.Timestamp("2023-05-01 12:00:00")


# ---------------------------------------------------------------------------
# df_column_validator
# ---------------------------------------------------------------------------

def test_multiple_validations():
    series = pd.Series([1, 2, 3, 4, 5])
    result = df_column_validator(series, nullable=False, col_dtype=int, col_min=1, col_max=5, isin=[1, 2, 3, 4, 5])
    assert result == ""


def test_int_vs_int64_dtype():
    result = df_column_validator(pd.Series([1, 2, 3, 4, 5]), col_dtype=int)
    assert result == ""


def test_float_vs_float64_dtype():
    result = df_column_validator(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), col_dtype=float)
    assert result == ""


# ---------------------------------------------------------------------------
# move_columns_far_left
# ---------------------------------------------------------------------------

def test_move_single_column_left(sample_df3):
    assert list(move_columns_far_left(sample_df3, ["C"]).columns) == ["C", "A", "B", "D"]


def test_move_multiple_columns_left(sample_df3):
    assert list(move_columns_far_left(sample_df3, ["C", "A"]).columns) == ["C", "A", "B", "D"]


def test_move_all_columns_left(sample_df3):
    assert list(move_columns_far_left(sample_df3, ["D", "C", "B", "A"]).columns) == ["D", "C", "B", "A"]


def test_move_no_columns_left(sample_df3):
    assert list(move_columns_far_left(sample_df3, []).columns) == ["A", "B", "C", "D"]


def test_move_non_existent_column_left(sample_df3):
    assert list(move_columns_far_left(sample_df3, ["E", "C"]).columns) == ["C", "A", "B", "D"]


def test_input_as_tuple_left(sample_df3):
    assert list(move_columns_far_left(sample_df3, ("C", "A")).columns) == ["C", "A", "B", "D"]


def test_preserve_data_left(sample_df3):
    result = move_columns_far_left(sample_df3, ["C", "A"])
    pd.testing.assert_frame_equal(sample_df3, result[sample_df3.columns])


def test_empty_dataframe_left():
    result = move_columns_far_left(pd.DataFrame(), ["A", "B"])
    assert result.empty
    assert list(result.columns) == []


def test_dataframe_with_columns_but_no_rows_left():
    df = pd.DataFrame(columns=["A", "B", "C"])
    result = move_columns_far_left(df, ["B", "C"])
    assert list(result.columns) == ["B", "C", "A"]
    assert result.empty


def test_move_non_existent_columns_in_non_empty_df_left():
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    assert list(move_columns_far_left(df, ["C", "D", "B"]).columns) == ["B", "A"]


# ---------------------------------------------------------------------------
# move_columns_far_right
# ---------------------------------------------------------------------------

def test_move_single_column_right(sample_df3):
    assert list(move_columns_far_right(sample_df3, ["A"]).columns) == ["B", "C", "D", "A"]


def test_move_multiple_columns_right(sample_df3):
    assert list(move_columns_far_right(sample_df3, ["A", "C"]).columns) == ["B", "D", "A", "C"]


def test_move_all_columns_right(sample_df3):
    assert list(move_columns_far_right(sample_df3, ["A", "B", "C", "D"]).columns) == ["A", "B", "C", "D"]


def test_move_no_columns_right(sample_df3):
    assert list(move_columns_far_right(sample_df3, []).columns) == ["A", "B", "C", "D"]


def test_move_non_existent_column_right(sample_df3):
    assert list(move_columns_far_right(sample_df3, ["E", "C"]).columns) == ["A", "B", "D", "C"]


def test_input_as_tuple_right(sample_df3):
    assert list(move_columns_far_right(sample_df3, ("A", "C")).columns) == ["B", "D", "A", "C"]


def test_preserve_data_right(sample_df3):
    result = move_columns_far_right(sample_df3, ["A", "C"])
    pd.testing.assert_frame_equal(sample_df3, result[sample_df3.columns])


def test_empty_dataframe_right():
    result = move_columns_far_right(pd.DataFrame(), ["A", "B"])
    assert result.empty
    assert list(result.columns) == []


def test_dataframe_with_columns_but_no_rows_right():
    df = pd.DataFrame(columns=["A", "B", "C"])
    result = move_columns_far_right(df, ["A", "B"])
    assert list(result.columns) == ["C", "A", "B"]
    assert result.empty


def test_move_non_existent_columns_in_non_empty_df_right():
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    assert list(move_columns_far_right(df, ["C", "D", "B"]).columns) == ["A", "B"]
