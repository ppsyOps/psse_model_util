"""
test_dirs.py — common.dirs function and constant tests.

Ported from tests/legacy_tests/common/test_dirs.py; updated for the current
API and project layout after refactoring.  `project_dir` and `code_dir` were
removed from dirs.py since the legacy port; those tests are dropped here.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from psse_model_util.common.dirs import (
    APP_NAME,
    clear_cache,
    clear_site_cache,
    clear_user_cache,
    delete_all_items_in_directory,
    site_cache_dir,
    site_config_dir,
    site_data_dir,
    site_log_dir,
    site_temp_dir,
    user_cache_dir,
    user_config_dir,
    user_data_dir,
    user_log_dir,
    user_state_dir,
)

WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only: tests msvcrt-style file locking. On Linux unlinking "
    "an open file removes the directory entry immediately.",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mock_cache_dirs(tmp_path, monkeypatch):
    mock_user_cache = tmp_path / "user_cache"
    mock_site_cache = tmp_path / "site_cache"
    mock_user_cache.mkdir()
    mock_site_cache.mkdir()
    monkeypatch.setattr("psse_model_util.common.dirs.user_cache_dir", mock_user_cache)
    monkeypatch.setattr("psse_model_util.common.dirs.site_cache_dir", mock_site_cache)
    return mock_user_cache, mock_site_cache


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_app_name():
    assert APP_NAME == "psse_model_util"


# ---------------------------------------------------------------------------
# Site directories
# ---------------------------------------------------------------------------

def test_site_directories():
    for d in (site_log_dir, site_data_dir, site_config_dir, site_temp_dir, site_cache_dir):
        assert isinstance(d, Path)
        if d.exists():
            assert d.is_dir()


# ---------------------------------------------------------------------------
# User directories
# ---------------------------------------------------------------------------

def test_user_directories():
    username = (os.getenv("USERNAME") or os.getenv("USER") or "").lower()
    for d in (user_config_dir, user_log_dir, user_data_dir, user_cache_dir, user_state_dir):
        assert isinstance(d, Path)
        if username:
            assert username in str(d).lower()


# ---------------------------------------------------------------------------
# delete_all_items_in_directory
# ---------------------------------------------------------------------------

def test_delete_all_items_in_directory(temp_dir):
    (temp_dir / "file1.txt").touch()
    (temp_dir / "file2.txt").touch()
    sub = temp_dir / "subdir"
    sub.mkdir()
    (sub / "file3.txt").touch()

    delete_all_items_in_directory(str(temp_dir))

    assert len(list(temp_dir.iterdir())) == 0


def test_delete_all_items_in_directory_invalid_path():
    assert delete_all_items_in_directory("non_existent_directory") is None


# ---------------------------------------------------------------------------
# clear_user_cache / clear_site_cache / clear_cache
# ---------------------------------------------------------------------------

def test_clear_user_cache(mock_cache_dirs):
    mock_user_cache, _ = mock_cache_dirs
    (mock_user_cache / "test_file.txt").touch()
    clear_user_cache()
    assert len(list(mock_user_cache.iterdir())) == 0


def test_clear_site_cache(mock_cache_dirs):
    _, mock_site_cache = mock_cache_dirs
    (mock_site_cache / "test_file.txt").touch()
    clear_site_cache()
    assert len(list(mock_site_cache.iterdir())) == 0


def test_clear_cache(mock_cache_dirs):
    mock_user_cache, mock_site_cache = mock_cache_dirs
    (mock_user_cache / "user_file.txt").touch()
    (mock_site_cache / "site_file.txt").touch()
    clear_cache()
    assert len(list(mock_user_cache.iterdir())) == 0
    assert len(list(mock_site_cache.iterdir())) == 0


# ---------------------------------------------------------------------------
# Cache clear with open files (Windows: open files are skipped, not errored)
# ---------------------------------------------------------------------------

@WINDOWS_ONLY
def test_clear_user_cache_with_open_file(mock_cache_dirs):
    mock_user_cache, _ = mock_cache_dirs
    file_path = mock_user_cache / "open_file.txt"
    f = open(file_path, "w")
    f.write("temp data")
    f.flush()
    try:
        clear_user_cache()
        assert file_path.exists()
    finally:
        f.close()
    clear_user_cache()
    assert not file_path.exists()


@WINDOWS_ONLY
def test_clear_site_cache_with_open_file(mock_cache_dirs):
    _, mock_site_cache = mock_cache_dirs
    file_path = mock_site_cache / "open_file.txt"
    f = open(file_path, "w")
    f.write("site cache content")
    f.flush()
    try:
        clear_site_cache()
        assert file_path.exists()
    finally:
        f.close()
    clear_site_cache()
    assert not file_path.exists()


@WINDOWS_ONLY
def test_clear_cache_handles_open_files(mock_cache_dirs):
    mock_user_cache, mock_site_cache = mock_cache_dirs
    user_file = mock_user_cache / "user_locked.txt"
    site_file = mock_site_cache / "site_locked.txt"
    uf = open(user_file, "w")
    sf = open(site_file, "w")
    uf.write("user temp")
    sf.write("site temp")
    uf.flush()
    sf.flush()
    try:
        clear_cache()
        assert user_file.exists()
        assert site_file.exists()
    finally:
        uf.close()
        sf.close()
    clear_cache()
    assert not user_file.exists()
    assert not site_file.exists()
