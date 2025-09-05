"""
Tools to help build and deploy code:
- Update build timestamp and version info in version.py.
- Leverages git_utils module to get latest hash.
"""

from datetime import datetime as dtdt
from pathlib import Path
from collections import namedtuple
from typing import Union
from dateutil.parser import parse as dt_parse
from psse_model_util.build_utils.git_utils import get_short_hash

# Constants
APP_NAME: str = 'psse_model_util'

app_path = Path(__file__).absolute()
while APP_NAME.lower() in [part.lower() for part in app_path.parts[:-1]]:
    app_path = app_path.parent

repo_path = Path(app_path)

OMIT_REQTS = (
                "pip",
                "pip-upgrade-tool",  # pip install pip-upgrade-tool
                "pipx",
                "psse_model_util",
                "psse-model-util",
                "pytest",
                "pytz",
                "twine",
                "gitpython",
                "wheel",
)

# 2-tuples of substrings to replace in the requirements.txt file.
REQTS_REPLACE = (
                 ("==", '=='),
)


def tuple2version(tuple_in: Union[tuple, list], fields: list = None) -> namedtuple:
    """
    Creates a namedtuple, 'Version', that contains version information.  Use this instead of
    creating a namedtuple directly, because this function will automatically set the tuple
    to the correct size based on the size of tuple_in.
    :param tuple_in: a regular tuple of values (containing version info) used to create the
                     namedtuple, Version.
    :param fields:  optional list of field names to included in the output namedtuple, Version.
    :return:        a namedtuple, 'Version', which has default field names ['major', 'minor',
                    'micro', 'nano', 'pico', 'sub_5', 'sub_6', ... 'sub_n']
    """
    fields = fields or ['major', 'minor', 'micro', 'nano', 'pico']
    assert len(tuple_in) <= len(fields)
    lst = list(tuple_in)
    # versioning should contain at least major, minor and micro
    lst += [0] * (3 - len(lst))
    if len(lst) > len(fields):
        fields += [f'sub_{i}' for i in range(len(fields), len(lst))]
    Version = namedtuple('Version', fields[:max(3, len(lst))])
    code_str = 'Version(' + ', '.join([f'lst[{i}]' for i in range(len(lst))]) + ')'
    return eval(code_str)


def version_info_2_version(version_info: Union[list, tuple]) -> str:
    """
    read __version_info__ tuple and create a version string, like 2022.2.3
    :param version_info: a namedtuple, like the one created by tuple2version
    :return: a version string to be saved to __version__
    """
    return version_info_2_whl_version(version_info=version_info)
    # if 'final' in list[version_info]:
    #     i = [i for i, x in enumerate(version_info)][0]
    #     return version_info[:i]
    # else:
    #     return '.'.join([str(v) for v in version_info])


def version_info_2_whl_version(version_info: Union[list, tuple]) -> str:
    """
    read __version_info__ tuple and create a version string, like 2022.2.3
    :param version_info: a namedtuple, like the one created by tuple2version
    :return: a version string to be saved to __version__
    """
    assert (len(version_info) >= 3)
    version_info = list(version_info)
    dev_st = {'alpha': 'a', 'beta': 'b', 'rc': 'c', 'final': ''}
    if not len(version_info) > 3:
        version_info = version_info + ['final', 0]
        version_info = version_info[:5]
    version_info = version_info[:3] + ['final', 0]
    version_str = '.'.join([str(v) for v in version_info[:3]])
    return version_str


def version_2_version_info(version: Union[str, tuple, list]) -> tuple:
    """
    Parse out the equivalent of .__version_info__ from .__version__.  This
    function should not be used in toolbox.  Instead, simply call .__version_info__
    However, this is a nice tool that you can use for other packages that contain
    __version__ but not __version_info__.
    :rtype: object
    :param version: a string representing the version of a python package.
    :return: a tuple of values parsed from version
    """
    import re
    result = version
    if type(result) in (int, float, str):
        result = re.split(r'\+|\.', str(version))  # re.split returns a list

    # try to convert each part of the version from str to int.
    result = [int(s) if type(s) == str and s.isnumeric() else s for s in result]

    fields = tuple2version(result)._fields

    return tuple2version(result, fields)


def version_info_from_file(version_file: Union[str, Path, None] = None,
                           app_name=APP_NAME, app_path=app_path) -> tuple:
    """
    Read version.py and extract: __version_info__ and __build_timestamp__
    :param version_file: the path to version.py
    :param app_name: name of app (its sub-folder name).  This argument is
                     only used if version_file is None.
    :return: 4-tuple of __version_info__, __build_timestamp__, file_path,
                        list of lines from version_file
    """
    # read version.py
    if not version_file:
        version_file = Path(app_path) / 'version.py'
    with open(version_file, 'r') as f:
        lines = f.readlines()

    # find the  "__build_timestamp__ = " line from version.py
    build_timestamp = [line for line in lines if line.startswith("__build_timestamp__ = ")][0]
    # parse build_timestamp from the line and convert to a datetime
    build_timestamp = dt_parse(build_timestamp.split('=')[1].strip())

    # find the  "__version_info__ = " line from version.py
    version_info = [line for line in lines if line.startswith("__version_info__ = ")][0]
    # extract text to the right of the "=" sign, which contains the version
    version_info = version_info.split('=')[1].strip()
    # Convert version_info str value to a namedtuple, 'Version'
    if 'tuple2version' in version_info:
        version_info = eval(version_info)
    else:
        version_info = tuple2version(version_info)

    return version_info, build_timestamp, version_file, list(lines)


def refresh_version_info(version_file: Union[str, Path, None] = None,
                         app_name: str = APP_NAME,
                         app_path=app_path,
                         build_timestamp: dtdt = dtdt.utcnow(),
                         increment_by: int = 0,
                         ):
    """
    After a git commit, the short hash changes.  If __version_info__[3] = 'alpha',
    then the short hash in __version_info__[4] needs to be updated.  This
    function updates that value IF needed.
    """
    # read the version_file
    version_file = version_file or Path(app_path) / app_name / 'version.py'
    temp = version_info_from_file(version_file=version_file)
    ver_info_old, old_build_timestamp, version_file, lines = temp

    # if 'alpha' is indicated in version info, find it and the git short hash value
    try:
        alpha_position, old_sha = [(i, x) for i, x in enumerate(list(ver_info_old))
                                   if str(x) == 'alpha'][0]
    except IndexError:
        alpha_position, old_sha = None, None
    # find the current git short hash value.  update version info if needed.
    new_sha = get_short_hash(repo_path=app_path)
    if old_sha == new_sha:
        return ver_info_old, old_build_timestamp, version_file, lines

    # Create ver_info_new
    ver_info_new = ver_info_old = list(ver_info_old)
    if build_timestamp.year == ver_info_new[0] \
            and build_timestamp.month == ver_info_new[1]:
        ver_info_new[0:3] = [build_timestamp.year, build_timestamp.month,
                             int(ver_info_new[2]) + increment_by]
    else:
        ver_info_new[0:3] = [build_timestamp.year, build_timestamp.month, 0]

    if ver_info_old[0:2] != ver_info_new[0:2]:
        # version major and/or minor version changed, so micro resets to 1
        # or to increment by, whichever is larger.
        ver_info_new[2] = max(1, increment_by)
    # If version info includes 'alpha', update the git short sha value.
    if old_sha:
        try:
            ver_info_new[alpha_position + 2] = new_sha
        except IndexError:
            pass
    ver_info_new = tuple2version(ver_info_new)
    ver_new = version_info_2_version(ver_info_new)

    # Update the version_file
    for i, line in enumerate(lines):
        if line.startswith('__version_info__ = '):
            lines[i] = f"__version_info__ = tuple2version({str(tuple(ver_info_new))})\n"
        elif line.startswith('__version__ = '):
            lines[i] = f"__version__ = '{ver_new}'\n"
        elif line.startswith('__build_timestamp__ = '):
            lines[i] = f"__build_timestamp__ = '{build_timestamp.isoformat()}'\n"

    # write to version_file
    with open(version_file, 'w') as f:
        f.writelines(lines)

    # Return version info and build timestamp
    return ver_info_new, build_timestamp, version_file, lines


def increment_version(version_file: Union[str, Path],
                      build_timestamp: dtdt = dtdt.utcnow(),
                      app_name=APP_NAME,
                      app_path=app_path
                      ):
    """
    Update the values of toolbox.version.__version_info__ and .__build_timestamp__
    """
    return refresh_version_info(version_file=version_file,
                                app_name=app_name,
                                app_path=app_path,
                                build_timestamp=build_timestamp,
                                increment_by=1)


if __name__ == '__main__':
    print("tuple2version((1, 2, 3, 'beta', 5)): ",
          tuple2version((1, 2, 3, 'beta', 5)))

    ver_info = version_2_version_info('2022.2.3.alpha.4ae4ff')
    print("version_2_version_info('2022.2.3.alpha.4ae4ff'): ", ver_info)

    ver = version_info_2_version(ver_info)
    print(f"version_info_2_version('{ver_info}'): ", ver)

    ver_info, bld_ts, ver_file, lines = refresh_version_info(app_path=app_path)
    print(f"refresh_version_info(): ", ver_info, bld_ts, ver_file)

    print('Increment version')
    increment_version(version_file=ver_file)
    ver_info, bld_ts, ver_file, lines = refresh_version_info(app_path=app_path)
    print(f"refresh_version_info(): ", ver_info, bld_ts, ver_file)

