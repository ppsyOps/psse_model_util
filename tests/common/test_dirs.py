import pytest
import os
import tempfile
from pathlib import Path

# Import the module to test
from psse_model_util.common.dirs import (
    APP_NAME,
    project_dir,
    code_dir,
    site_log_dir,
    site_data_dir,
    site_config_dir,
    site_temp_dir,
    site_cache_dir,
    user_config_dir,
    user_log_dir,
    user_data_dir,
    user_cache_dir,
    user_state_dir,
    delete_all_items_in_directory,
    clear_user_cache,
    clear_site_cache,
    clear_cache
)

@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield Path(tmpdirname)

def test_app_name():
    """Test if APP_NAME is set correctly."""
    assert APP_NAME == 'psse_model_util'

def test_project_structure():
    """Test if project directory structure is correct."""
    assert project_dir.is_dir()
    assert code_dir.is_dir()
    assert code_dir.name == APP_NAME

def test_site_directories():
    """Test if site directories are set up correctly."""
    site_dirs = [site_log_dir, site_data_dir, site_config_dir, site_temp_dir, site_cache_dir]
    for dir in site_dirs:
        assert dir.parent == project_dir
        if dir.exists():
            assert dir.is_dir()

def test_user_directories():
    """Test if user directories are set up correctly."""
    username = os.environ['USERNAME']
    user_dirs = [user_config_dir, user_log_dir, user_data_dir, user_cache_dir, user_state_dir]
    for dir in user_dirs:
        assert username.lower() in str(dir).lower()

def test_delete_all_items_in_directory(temp_dir):
    """Test delete_all_items_in_directory function."""
    # Create some files and directories
    (temp_dir / 'file1.txt').touch()
    (temp_dir / 'file2.txt').touch()
    (temp_dir / 'subdir').mkdir()
    (temp_dir / 'subdir' / 'file3.txt').touch()

    delete_all_items_in_directory(str(temp_dir))

    assert len(list(temp_dir.iterdir())) == 0

def test_delete_all_items_in_directory_invalid_path():
    """Test delete_all_items_in_directory with invalid path."""
    assert delete_all_items_in_directory('non_existent_directory') is None

@pytest.fixture
def mock_cache_dirs(temp_dir, monkeypatch):
    """Mock cache directories for testing."""
    mock_user_cache = temp_dir / 'user_cache'
    mock_site_cache = temp_dir / 'site_cache'
    mock_user_cache.mkdir()
    mock_site_cache.mkdir()

    monkeypatch.setattr('psse_model_util.common.dirs.user_cache_dir', mock_user_cache)
    monkeypatch.setattr('psse_model_util.common.dirs.site_cache_dir', mock_site_cache)

    return mock_user_cache, mock_site_cache

def test_clear_user_cache(mock_cache_dirs):
    """Test clear_user_cache function."""
    mock_user_cache, _ = mock_cache_dirs
    (mock_user_cache / 'test_file.txt').touch()

    clear_user_cache()

    assert len(list(mock_user_cache.iterdir())) == 0

def test_clear_site_cache(mock_cache_dirs):
    """Test clear_site_cache function."""
    _, mock_site_cache = mock_cache_dirs
    (mock_site_cache / 'test_file.txt').touch()

    clear_site_cache()

    assert len(list(mock_site_cache.iterdir())) == 0

def test_clear_cache(mock_cache_dirs):
    """Test clear_cache function."""
    mock_user_cache, mock_site_cache = mock_cache_dirs
    (mock_user_cache / 'user_file.txt').touch()
    (mock_site_cache / 'site_file.txt').touch()

    clear_cache()

    assert len(list(mock_user_cache.iterdir())) == 0
    assert len(list(mock_site_cache.iterdir())) == 0

def test_clear_user_cache_with_open_file(mock_cache_dirs):
    """Test clear_user_cache fails to delete an open file, then succeeds after closing it."""
    mock_user_cache, _ = mock_cache_dirs
    file_path = mock_user_cache / 'open_file.txt'

    # Create and open the file (keep it open to simulate lock)
    f = open(file_path, 'w')
    f.write("temp data")
    f.flush()

    try:
        clear_user_cache()
        # Windows will silently skip open files, file still exists
        assert file_path.exists()
    finally:
        f.close()  # Close it so deletion is allowed

    # Now try again and ensure it's deleted
    clear_user_cache()
    assert not file_path.exists()

def test_clear_site_cache_with_open_file(mock_cache_dirs):
    """Test clear_site_cache fails on open file, then succeeds after closing it."""
    _, mock_site_cache = mock_cache_dirs
    file_path = mock_site_cache / 'open_file.txt'

    f = open(file_path, 'w')
    f.write("site cache content")
    f.flush()

    try:
        clear_site_cache()
        assert file_path.exists()
    finally:
        f.close()

    clear_site_cache()
    assert not file_path.exists()

def test_clear_cache_handles_open_files(mock_cache_dirs):
    """Test clear_cache gracefully handles open files in both caches."""
    mock_user_cache, mock_site_cache = mock_cache_dirs
    user_file = mock_user_cache / 'user_locked.txt'
    site_file = mock_site_cache / 'site_locked.txt'

    uf = open(user_file, 'w')
    sf = open(site_file, 'w')
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


if __name__ == "__main__":
    pytest.main()
