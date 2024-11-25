import appdirs
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

__user_root = Path(appdirs.user_data_dir())
user_config_dir = __user_root / 'config'
user_log_dir = __user_root / 'log'
user_data_dir = __user_root / 'data'
user_cache_dir = __user_root / 'cache'
user_state_dir = __user_root / 'state'


def delete_all_items_in_directory(directory: str):
    """
    Delete all items (files and directories) in the specified directory.

    :param directory: The path to the directory to clear.
    """
    # Define the target directory using pathlib
    target_dir = Path(directory)

    if not target_dir.exists():
        return

    if not target_dir.is_dir():
        raise ValueError(f"The provided path '{directory}' is not a valid directory.")

    # Iterate through each item in the directory
    for item in target_dir.iterdir():
        if item.is_dir():
            # Remove the directory and its contents
            shutil.rmtree(item)
        else:
            # Remove the file
            item.unlink()


def clear_user_cache():
    """Delete all files from the user_cache_dir directory."""
    delete_all_items_in_directory(user_cache_dir)


def clear_site_cache():
    """Delete all files from the site_cache_dir directory."""
    delete_all_items_in_directory(site_cache_dir)


def clear_cache():
    """Delete all files from the user_cache_dir and site_cache_dir directories"""
    clear_user_cache()
    clear_site_cache()


if __name__ == '__main__':
    paths = {'project_dir:': project_dir,
             'code_dir': code_dir,
             'site_log_dir': site_log_dir,
             'site_cache_dir': site_cache_dir,
             'site_config_dir': site_config_dir,
             'site_data_dir': site_data_dir,
             'site_temp_dir': site_temp_dir,
             'user_log_dir': user_log_dir,
             'user_config_dir': user_config_dir,
             'user_state_dir': user_state_dir,
             'user_cache_dir': user_cache_dir,
             'user_data_dir': user_data_dir,
             }

    for name, path in paths.items():
        print(f'dirs.{name}: {path}')