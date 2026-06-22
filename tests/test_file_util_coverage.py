"""
test_file_util_coverage.py — characterization tests for file_util.

Targets edge/error branches in psse_model_util.common.file_util that the
existing tests/test_file_util.py does not exercise: str-path coercion,
parent-dir creation, overwrite-unlink, write/load error handling under the
resilient flag, non-resilient raises, and get_available_model_files.

Expected behavior here was derived by running the code (characterization).
"""
from __future__ import annotations

import io
import pickle

import pytest

from psse_model_util.common.file_util import (
    get_available_model_files,
    read_pickle,
    to_pickle,
    write_bytesio_to_disk,
)

# ---------------------------------------------------------------------------
# write_bytesio_to_disk
# ---------------------------------------------------------------------------

def test_write_bytesio_accepts_str_path(tmp_path):
    """A str file_path is coerced to Path and written (line 180)."""
    content = b"string path content"
    file_path = tmp_path / "as_string.bin"
    write_bytesio_to_disk(io.BytesIO(content), str(file_path))
    assert file_path.exists()
    assert file_path.read_bytes() == content


def test_write_bytesio_creates_missing_parent(tmp_path):
    """A missing parent directory is created before writing (line 184)."""
    content = b"nested content"
    file_path = tmp_path / "missing" / "deeper" / "out.bin"
    assert not file_path.parent.exists()
    write_bytesio_to_disk(io.BytesIO(content), file_path)
    assert file_path.exists()
    assert file_path.read_bytes() == content


def test_write_bytesio_overwrites_existing(tmp_path):
    """Existing file with overwrite=True is unlinked then rewritten (line 188)."""
    file_path = tmp_path / "overwrite.bin"
    write_bytesio_to_disk(io.BytesIO(b"first"), file_path)
    assert file_path.read_bytes() == b"first"
    write_bytesio_to_disk(io.BytesIO(b"second"), file_path, overwrite=True)
    assert file_path.read_bytes() == b"second"


def test_write_bytesio_warns_on_write_error(tmp_path, monkeypatch):
    """A write failure is caught and surfaced as a warning (lines 203-204).

    Force the failure cross-platform by injecting a raising ``open`` into the
    module globals (rather than relying on OS-specific illegal filenames).
    """
    import psse_model_util.common.file_util as fu

    def _boom(*args, **kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(fu, "open", _boom, raising=False)
    target = tmp_path / "out.bin"
    with pytest.warns(UserWarning, match="Error:"):
        fu.write_bytesio_to_disk(io.BytesIO(b"data"), target)


# ---------------------------------------------------------------------------
# to_pickle
# ---------------------------------------------------------------------------

def test_to_pickle_non_resilient_raises(tmp_path):
    """With resilient=False a write failure re-raises (line 218)."""
    bad_path = tmp_path / "no_such_dir" / "out.pickle"
    with pytest.raises(Exception):
        to_pickle(bad_path, {"k": "v"}, resilient=False)


# ---------------------------------------------------------------------------
# read_pickle
# ---------------------------------------------------------------------------

def test_read_pickle_corrupt_resilient_returns_none(tmp_path):
    """A corrupt pickle under resilient=True warns and returns None (rather
    than crashing with UnboundLocalError)."""
    bad = tmp_path / "corrupt.pickle"
    bad.write_bytes(b"not a valid pickle stream")
    with pytest.warns(UserWarning, match="Unable to read object"):
        result = read_pickle(bad, resilient=True)
    assert result is None


def test_read_pickle_corrupt_non_resilient_raises(tmp_path):
    """A corrupt pickle under resilient=False re-raises the load error (line 237)."""
    bad = tmp_path / "corrupt2.pickle"
    bad.write_bytes(b"\x80\x04not really a pickle")
    with pytest.raises(Exception) as exc_info:
        read_pickle(bad, resilient=False)
    assert not isinstance(exc_info.value, FileNotFoundError)


def test_read_pickle_roundtrip_returns_obj(tmp_path):
    """Sanity: a valid pickle loads and returns the object (line 239)."""
    data = {"alpha": [1, 2, 3]}
    good = tmp_path / "good.pickle"
    good.write_bytes(pickle.dumps(data))
    assert read_pickle(good) == data


# ---------------------------------------------------------------------------
# get_available_model_files
# ---------------------------------------------------------------------------

def test_get_available_model_files_missing_dir_raises(tmp_path):
    """A non-existent directory raises FileNotFoundError (lines 259-260)."""
    missing = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError):
        get_available_model_files(missing)


def test_get_available_model_files_path_is_file_raises(tmp_path):
    """A path that exists but is not a directory raises FileNotFoundError (line 259)."""
    a_file = tmp_path / "plain.txt"
    a_file.write_text("not a dir", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        get_available_model_files(a_file)


def test_get_available_model_files_lists_and_orders(tmp_path):
    """rawx files are returned before raw files, each sorted (lines 262-264)."""
    (tmp_path / "b.raw").write_text("", encoding="utf-8")
    (tmp_path / "a.raw").write_text("", encoding="utf-8")
    (tmp_path / "z.rawx").write_text("", encoding="utf-8")
    (tmp_path / "m.rawx").write_text("", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("", encoding="utf-8")

    result = get_available_model_files(tmp_path)
    names = [p.name for p in result]
    assert names == ["m.rawx", "z.rawx", "a.raw", "b.raw"]


def test_get_available_model_files_empty_dir(tmp_path):
    """An empty directory returns an empty list (lines 262-264)."""
    assert get_available_model_files(tmp_path) == []
