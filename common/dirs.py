import platformdirs
import shutil
from pathlib import Path

APP_NAME = 'psse_model_util'

project_dir = Path(__file__).parent.parent.parent
code_dir = project_dir / APP_NAME

__site_root = project_dir  # Path(f'C:/Personal/Projects/{APP_NAME}')
site_log_dir = __site_root / 'log'
site_data_dir: Path = __site_root / 'data'
site_config_dir = __site_root / 'config'
site_temp_dir = __site_root / 'Temp'
site_cache_dir = __site_root / 'cache'

__user_root = Path(platformdirs.user_data_dir(APP_NAME))
user_config_dir = __user_root / 'config'
user_log_dir = __user_root / 'log'
user_data_dir = __user_root / 'data'
user_cache_dir = __user_root / 'cache'
user_state_dir = __user_root / 'state'


def delete_all_items_in_directory(directory: str):
    """
    Delete all items (files and directories) in the specified directory.

    Parameters:
        directory (str): The path to the directory to clear.

    Raises:
        ValueError: If the path is not a directory.
    """
    # Define the target directory using pathlib
    target_dir = Path(directory)

    if not target_dir.exists():
        return

    if not target_dir.is_dir():
        raise ValueError(f"The provided path '{directory}' is not a valid directory.")

    # Iterate through each item in the directory
    for item in target_dir.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception as e:
            print(f"Warning: Could not delete '{item}': {e}")


def clear_user_cache():
    """
    Delete all files from the user cache directory.

    The user cache is located at a system-appropriate location based on the
    current user profile, typically something like:
        - Windows: C:\\Users\\<username>\\AppData\\Local\\psse_model_util\\cache
        - Linux/macOS: ~/.local/share/psse_model_util/cache

    This directory is used for storing user-specific temporary or cache files
    that should persist across sessions but are safe to delete.
    """
    delete_all_items_in_directory(user_cache_dir)


def clear_site_cache():
    """
    Delete all files from the site cache directory.

    The site cache is located in the main project directory and shared across
    all users running this utility from a common installation base. It is used
    for storing shared temporary files (e.g., model parsing artifacts or logs)
    that can be safely cleared to reset application state.
    """
    delete_all_items_in_directory(site_cache_dir)


def clear_cache():
    """Delete all files from the user_cache_dir and site_cache_dir directories"""
    clear_user_cache()
    clear_site_cache()


def get_app_dirs():
    """
    Returns application directories
    """
    return {
        "project_dir": project_dir,
        "code_dir": code_dir,
        "site_log_dir": site_log_dir,
        "site_cache_dir": site_cache_dir,
        "site_config_dir": site_config_dir,
        "site_data_dir": site_data_dir,
        "site_temp_dir": site_temp_dir,
        "user_log_dir": user_log_dir,
        "user_config_dir": user_config_dir,
        "user_state_dir": user_state_dir,
        "user_cache_dir": user_cache_dir,
        "user_data_dir": user_data_dir,
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
