"""
dirs.py — Application directory management for psse_model_util.

Provides canonical paths for site-level (shared) and user-level (per-user)
data, logs, config, cache, and temp storage using platformdirs.

All paths are packaging-safe: no references to the source tree.
"""

import shutil
from pathlib import Path

import platformdirs

APP_NAME = 'psse_model_util'

# --- User-level dirs (per-user, system-appropriate) ---
__user_root = Path(platformdirs.user_data_dir(APP_NAME))
user_config_dir: Path = __user_root / 'config'
user_log_dir: Path = __user_root / 'log'
user_data_dir: Path = __user_root / 'data'
user_cache_dir: Path = __user_root / 'cache'
user_state_dir: Path = __user_root / 'state'
user_temp_dir: Path = __user_root / 'temp'

# --- Site-level dirs (shared / system-wide) ---
__site_root = Path(platformdirs.site_data_dir(APP_NAME))
site_config_dir: Path = __site_root / 'config'
site_log_dir: Path = __site_root / 'log'
site_data_dir: Path = __site_root / 'data'
site_cache_dir: Path = __site_root / 'cache'
site_temp_dir: Path = __site_root / 'temp'


def delete_all_items_in_directory(directory: str | Path) -> None:
    """
    Delete all items (files and subdirectories) in the specified directory.
    The directory itself is preserved.

    Parameters:
        directory: Path to the directory to clear.

    Raises:
        ValueError: If the path is not a directory.
    """
    target_dir = Path(directory)

    if not target_dir.exists():
        return

    if not target_dir.is_dir():
        raise ValueError(f"The provided path '{directory}' is not a valid directory.")

    for item in target_dir.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception as e:
            print(f"Warning: Could not delete '{item}': {e}")


def clear_user_cache() -> None:
    """Delete all files from the user cache directory."""
    delete_all_items_in_directory(user_cache_dir)


def clear_site_cache() -> None:
    """Delete all files from the site cache directory."""
    delete_all_items_in_directory(site_cache_dir)


def clear_cache() -> None:
    """Delete all files from both user_cache_dir and site_cache_dir."""
    clear_user_cache()
    clear_site_cache()


def get_app_dirs() -> dict[str, Path]:
    """Return a dict of all application directory paths."""
    return {
        "site_config_dir": site_config_dir,
        "site_log_dir": site_log_dir,
        "site_data_dir": site_data_dir,
        "site_cache_dir": site_cache_dir,
        "site_temp_dir": site_temp_dir,
        "user_config_dir": user_config_dir,
        "user_log_dir": user_log_dir,
        "user_data_dir": user_data_dir,
        "user_cache_dir": user_cache_dir,
        "user_state_dir": user_state_dir,
        "user_temp_dir": user_temp_dir,
    }


def copy_doc(from_func):
    """Decorator to copy the docstring from another function or method."""
    def decorator(func):
        func.__doc__ = from_func.__doc__
        return func
    return decorator


if __name__ == '__main__':
    for name, path in get_app_dirs().items():
        print(f'dirs.{name}: {path}')
