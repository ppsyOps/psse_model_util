"""
test_file_util.py — file_util function tests.

Ported from tests/legacy_tests/common/test_file_util.py; updated for the
current API and project layout after refactoring.
"""
from __future__ import annotations

import io
import pickle
from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.common.file_util import (
    read_pickle,
    read_uneven_csv_file,
    to_pickle,
    uneven_lists_to_df,
    write_bytesio_to_disk,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def temp_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("test_data")


@pytest.fixture
def sample_list_of_lists():
    return [[1, 2, 3], [4, 5], [6]]


@pytest.fixture
def sample_csv_file(temp_dir):
    file_path = temp_dir / "sample.csv"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("a,b,c\n1,2,3\n4,5\n6\n", encoding="utf-8")
    return file_path


# ---------------------------------------------------------------------------
# uneven_lists_to_df
# ---------------------------------------------------------------------------

def test_uneven_lists_to_df(sample_list_of_lists):
    df = uneven_lists_to_df(sample_list_of_lists, columns=["A", "B", "C"])
    expected = pd.DataFrame({"A": [1, 4, 6], "B": [2, 5, None], "C": [3, None, None]})
    pd.testing.assert_frame_equal(df, expected)


def test_uneven_lists_to_df_with_header_rows():
    data = [["X", "Y", "Z"], [1, 2, 3], [4, 5], [6]]
    df = uneven_lists_to_df(data, header_rows=0)
    expected = pd.DataFrame({"X": [1, 4, 6], "Y": [2, 5, None], "Z": [3, None, None]})
    pd.testing.assert_frame_equal(df, expected)


# ---------------------------------------------------------------------------
# read_uneven_csv_file
# ---------------------------------------------------------------------------

def test_read_uneven_csv_file(sample_csv_file):
    df = read_uneven_csv_file(sample_csv_file, as_dataframe=True)
    expected = pd.DataFrame({
        "a": ["1", "4", "6"],
        "b": ["2", "5", None],
        "c": ["3", None, None],
    })
    pd.testing.assert_frame_equal(df, expected)


def test_read_uneven_csv_file_no_header(sample_csv_file):
    df = read_uneven_csv_file(sample_csv_file, as_dataframe=True, header_rows=None)
    expected = pd.DataFrame({
        "Col0": ["a", "1", "4", "6"],
        "Col1": ["b", "2", "5", None],
        "Col2": ["c", "3", None, None],
    })
    pd.testing.assert_frame_equal(df, expected)


def test_read_uneven_csv_file_as_list(sample_csv_file):
    data = read_uneven_csv_file(sample_csv_file, as_dataframe=False)
    assert data == [["a", "b", "c"], ["1", "2", "3"], ["4", "5"], ["6"]]


# ---------------------------------------------------------------------------
# write_bytesio_to_disk
# ---------------------------------------------------------------------------

def test_write_bytesio_to_disk(temp_dir):
    content = b"Test content"
    file_path = temp_dir / "test_file.bin"
    write_bytesio_to_disk(io.BytesIO(content), file_path)
    assert file_path.exists()
    assert file_path.read_bytes() == content


def test_write_bytesio_to_disk_no_overwrite(temp_dir):
    content = b"Test content"
    file_path = temp_dir / "test_no_overwrite.bin"
    write_bytesio_to_disk(io.BytesIO(content), file_path)
    with pytest.warns(UserWarning):
        write_bytesio_to_disk(io.BytesIO(content), file_path, overwrite=False)


# ---------------------------------------------------------------------------
# to_pickle / read_pickle
# ---------------------------------------------------------------------------

def test_to_pickle(temp_dir):
    data = {"test": "data"}
    pickle_path = temp_dir / "test.pickle"
    assert to_pickle(pickle_path, data)
    assert pickle_path.exists()


def test_to_pickle_resilient(temp_dir):
    data = {"test": "data"}
    pickle_path = temp_dir / "non_existent_dir" / "test.pickle"
    assert not to_pickle(pickle_path, data, resilient=True)


def test_read_pickle(temp_dir):
    data = {"test": "data"}
    pickle_path = temp_dir / "read_test.pickle"
    pickle_path.write_bytes(pickle.dumps(data))
    assert read_pickle(pickle_path) == data


def test_read_pickle_non_existent(temp_dir):
    missing = temp_dir / "non_existent.pickle"
    assert read_pickle(missing, resilient=True) is None
    with pytest.raises(FileNotFoundError):
        read_pickle(missing, resilient=False)
