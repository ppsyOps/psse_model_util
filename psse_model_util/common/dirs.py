import appdirs
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

k = Path('//corp.pjm.com/shares/atc')
w = Path('//corp.pjm.com/shares/TransmissionServices')

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
             'k': k,
             'w': w,
             }

    for name, path in paths.items():
        print(f'dirs.{name}: {path}')
