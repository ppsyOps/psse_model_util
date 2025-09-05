import pytest
import pandas as pd
import io
import pickle
from pathlib import Path
import csv
import time
import msvcrt
import os

from psse_model_util.common.file_util import (
    uneven_lists_to_df,
    read_uneven_csv_file,
    write_bytesio_to_disk,
    to_pickle,
    read_pickle
)
# from psse_model_util.common.file_lock_checker import check_file_lock

from psse_model_util.common.dirs import site_temp_dir


@pytest.fixture(scope="session")
def temp_dir(tmp_path_factory):
    test_dir = tmp_path_factory.mktemp("test_data")
    return test_dir


@pytest.fixture
def sample_list_of_lists():
    return [[1, 2, 3], [4, 5], [6]]


@pytest.fixture
def sample_csv_content():
    return "a,b,c\n1,2,3\n4,5\n6\n"


@pytest.fixture
def sample_csv_file(temp_dir):
    file_path = temp_dir / "sample.csv"
    file_path.absolute().parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", newline="") as f:
        f.write("a,b,c\n1,2,3\n4,5\n6\n")
    return file_path


def test_uneven_lists_to_df(sample_list_of_lists):
    df = uneven_lists_to_df(sample_list_of_lists, columns=['A', 'B', 'C'])
    expected_df = pd.DataFrame({
        'A': [1, 4, 6],
        'B': [2, 5, None],
        'C': [3, None, None]
    })
    pd.testing.assert_frame_equal(df, expected_df)


def test_uneven_lists_to_df_with_header_rows(sample_list_of_lists):
    sample_list_of_lists.insert(0, ['X', 'Y', 'Z'])
    df = uneven_lists_to_df(sample_list_of_lists, header_rows=0)
    expected_df = pd.DataFrame({
        'X': [1, 4, 6],
        'Y': [2, 5, None],
        'Z': [3, None, None]
    })
    pd.testing.assert_frame_equal(df, expected_df)


def test_read_uneven_csv_file(sample_csv_file):
    df = read_uneven_csv_file(sample_csv_file, as_dataframe=True)
    expected_df = pd.DataFrame({
        'a': ['1', '4', '6'],
        'b': ['2', '5', None],
        'c': ['3', None, None]
    })
    pd.testing.assert_frame_equal(df, expected_df)

def test_read_uneven_csv_file_no_header(sample_csv_file):
    df = read_uneven_csv_file(sample_csv_file, as_dataframe=True, header_rows=None)
    expected_df = pd.DataFrame({
        'Col0': ['a', '1', '4', '6'],
        'Col1': ['b', '2', '5', None],
        'Col2': ['c', '3', None, None]
    })
    pd.testing.assert_frame_equal(df, expected_df)

def test_read_uneven_csv_file_as_list(sample_csv_file):
    data = read_uneven_csv_file(sample_csv_file, as_dataframe=False)
    expected_data = [['a', 'b', 'c'], ['1', '2', '3'], ['4', '5'], ['6']]
    assert data == expected_data


def test_write_bytesio_to_disk(temp_dir):
    content = b"Test content"
    bytes_io = io.BytesIO(content)
    file_path = temp_dir / "test_file.txt"

    write_bytesio_to_disk(bytes_io, file_path)

    assert file_path.exists()
    with open(file_path, "rb") as f:
        assert f.read() == content


def test_write_bytesio_to_disk_no_overwrite(temp_dir):
    content = b"Test content"
    bytes_io = io.BytesIO(content)
    file_path = temp_dir / "test_file.txt"

    # Write the file first time
    write_bytesio_to_disk(bytes_io, file_path)

    # Try to write again without overwrite
    with pytest.warns(UserWarning):
        write_bytesio_to_disk(bytes_io, file_path, overwrite=False)


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
    pickle_path = temp_dir / "test.pickle"

    with open(pickle_path, "wb") as f:
        pickle.dump(data, f)

    loaded_data = read_pickle(pickle_path)
    assert loaded_data == data


def test_read_pickle_non_existent(temp_dir):
    non_existent_path = temp_dir / "non_existent.pickle"

    assert read_pickle(non_existent_path, resilient=True) is None

    with pytest.raises(FileNotFoundError):
        read_pickle(non_existent_path, resilient=False)


if __name__ == "__main__":
    pytest.main()