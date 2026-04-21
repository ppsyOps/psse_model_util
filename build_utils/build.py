import os
import re
import shutil
import subprocess
from datetime import datetime as dtdt
from pathlib import Path
from dateutil.parser import parse

from pip._internal.operations import freeze

from psse_model_util.build_utils.build_utils import increment_version, \
    version_info_2_version, version_info_2_whl_version
from psse_model_util import version
from psse_model_util.build_utils.build_utils import APP_NAME, app_path, OMIT_REQTS, \
    REQTS_REPLACE
from psse_model_util.build_utils.git_utils import commit, get_repo  # , commit_and_push


def update_requirements(app_path=app_path, omit_reqts=OMIT_REQTS,
                        reqts_replace=None):
    """

    :param app_path: The local path at which the project source code is located.
    :param omit_reqts: tuple: names of libraries/requirements to be omitted
                        intentionally from requirements.txt.
    :param reqts_replace: list of lists like [[old, new], [old, new],...]
    :return: dict[tuple]: {full_requirements_path: full_requirements_tuple,
                        requirements_path: requirements_tuple)
    """
    # 2. Create a new requirements.txt
    app_path = Path(app_path)
    os.chdir(app_path)
    # Create requirements_full.txt
    reqts_full = [_ + '\n' for _ in freeze.freeze()]
    reqts_full_fp = app_path.joinpath('requirements_full.txt')
    with open(reqts_full_fp, 'w') as f:
        f.writelines(reqts_full)
    # Create requirements.txt from requirements_full.txt but omit
    # any packages listed in tsd_python.build_utils.build_config.omit_reqts.
    reqts_fp = app_path.joinpath('requirements.txt')
    # split_string = re.split(r"(==|>=)", string)
    reqts = "".join([_ for _ in reqts_full if re.split(r"(==|>=)", _)[0] not in omit_reqts])
    if reqts_replace:
        for old, new in reqts_replace:
            # We may want to
            reqts = reqts.replace(old, new)

    with open(reqts_fp, 'w') as f:
        f.writelines(reqts)
    # print('Updated requirements:', [x.strip('\n') for x in reqts])
    # Save a copy of requirements.txt with timestamp in name.
    date_str = dtdt.now().isoformat().replace(":", "-")[:19]
    shutil.copy('requirements.txt', f'requirements_{date_str}.txt')

    return {reqts_full_fp: reqts_full, reqts_fp: reqts}


def build(app_name=APP_NAME,
          app_path=app_path,
          omit_reqts=OMIT_REQTS,
          reqts_replace=REQTS_REPLACE,
          version=version,
          auto_update_requirements: bool = True,
          increment: bool = None,
          build_wheel: bool = None,
          commit2git: bool | None = None):
    """
    Script to do the following, in order:
        1. Update the requirements.txt file.
        2. Increment the version number and build_timestamp.
        3. Build a wheel file.
    :param app_name: name of app/project, like toolbox or tsd_python.
    :param app_path: The local path at which the project source code is located.
    :param omit_reqts: tuple: names of libraries/requirements to be omitted
                       intentionally from requirements.txt.
    :param version: python 'version' module for the app/project.
    :param auto_update_requirements: Automatically update requirements.txt.
    :param increment: Increment the project version number automatically
                            to the next sub-version.
    :param build_wheel: Build a wheel file (build and dist folders)
    :return:
    """
    committed = False

    # 0. Confirm user committed changes
    if any([increment, build_wheel]):
        ans = input('Did you commit changes to the LOCAL Git repo [Y/N]?')
        if not ans.strip().lower().startswith('y'):
            print('\nCommit changes before starting a release.')
            exit(0)

    # 1. Create a new requirements.txt
    app_path = Path(app_path)
    os.chdir(app_path)
    if auto_update_requirements is None:
        auto_update_requirements = input('\nAuto-update requirements.txt? [Y/N]: ').strip().lower()[:1] == 'y'

    if auto_update_requirements:
        update_requirements(app_path=app_path, omit_reqts=omit_reqts,
                            reqts_replace=reqts_replace)

    # 2. Increment the version number and set a new build timestamp (both in version.py)
    # print('repo_path:', app_path)
    repo = get_repo(repo_path=app_path, create_if_bare=False)
    old_version_info = version.__version_info__
    new_version_info = old_version_info

    if increment is None:
        increment = input('\nIncrement version number? [Y/N]: ').strip().lower()[:1] == 'y'

    if increment:
        new_version_info, build_timestamp, *_ = increment_version(version_file=version.__file__,
                                                                  app_name=app_name,
                                                                  app_path=app_path)
        new_version = version_info_2_version(new_version_info)
        msg = f'{app_name} version: {new_version_info}'
        ans = input(f'old version: {old_version_info} \n' +
                    f'new version: {new_version_info} \n\nCommit to LOCAL Git repo?')
        if ans.strip().lower().startswith('y'):
            commit(repo=repo, commit_message=msg)
            committed = True
    else:
        build_timestamp = parse(version.__build_timestamp__)

    # 3. build your wheel file
    whl = f'{app_name}-{version_info_2_whl_version(new_version_info)}-py3-none-any.whl'
    whl = app_path.joinpath('dist').joinpath(whl)
    if build_wheel is None:
        build_wheel = input('\nBuild wheel file? [Y/N]: ').strip().lower()[:1] == 'y'

    if build_wheel:
        drv = app_path.drive
        py_fp = app_path / 'venv/Scripts/python.exe'
        setup_fp = app_path.joinpath('setup.py')
        mk_whl = app_path.joinpath(f'{app_name}/build_utils/make_wheel.cmd')
        cmd = f"{str(drv)} \n" \
              f"cd {app_path} \n" \
              f"{py_fp} {setup_fp} sdist bdist_wheel"
        with open(mk_whl, 'w') as f:
            # f.write(f'{venv_fp} \npython {setup_fp} sdist bdist_wheel')
            f.write(cmd)
        print('Building wheel...')
        subprocess.run(mk_whl)
        # whl = f'{app_name}-{version_info_2_whl_version(new_version_info)}-py3-none-any.whl'
        # whl = app_path.joinpath('dist').joinpath(whl)
        print('wheel file: ', whl)
        cnt = 0
        while not whl.exists() and cnt < 3:
            cnt += 1
            whl = input(f'Wheel file ""{str(whl.absolute())} does not exit. \n'
                           f'Enter correct file name. ')
            if not whl.strip() or whl.lower().strip() in ['quit', 'q', 'exit', 'e']:
                break
            whl = Path(whl)

        if not whl.exists() or not whl.is_file():
            raise FileNotFoundError(f'Wheel file does not exist or is not a file: '
                                    f'{str(whl)}')

    # 4. Commit new version to Git?
    if commit2git is None:
        commit2git = input('\nPush changes to Git remote? \n'
                           'Yes to push; No to skip  [y/n]: ').strip().lower()[:1] == 'y'

    if commit2git:
        msg = f'{app_name} version: {new_version_info}'
        commit(repo=repo, commit_message=msg)


if __name__ == '__main__':
    build(app_name=APP_NAME,
          app_path=app_path,
          omit_reqts=OMIT_REQTS,
          reqts_replace=REQTS_REPLACE,
          auto_update_requirements=True,
          increment=False,
          build_wheel=True,
          commit2git=True)
