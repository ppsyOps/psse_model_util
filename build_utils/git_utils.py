import os
from typing import Union
from git import Repo as _Repo  # pip install gitpython
from pathlib import Path


CREATE_GIT_IF_BARE = False


class Repo(_Repo):
    @property
    def sha(self):
        """
        Returns a unique name for this version of the repo as a SHA-1 hash.
        Convenience alias for repo.head.commit.hexsha
        :return: repo.head.commit.hexsha
        """
        return self.head.commit.hexsha

    @property
    def short_sha(self, short=4):
        """
        Get Git's short unique object name, essentially a unique id.
        Use "git rev-parse --short" to get the short "object name to a unique prefix with at least
        length characters. The minimum length is 4, the default is the effective value of the
        core.abbrev configuration variable (see git-config[1])" as per
        https://git-scm.com/docs/git-rev-parse

        :return: Git's abbreviated short unique prefix per https://git-scm.com/docs/git-rev-parse
        """
        return self.git.rev_parse(self.sha, short = short)


def get_repo(repo_path: Union[Path, str],
             create_if_bare:bool = CREATE_GIT_IF_BARE) -> Repo:
    """
    Retrieve a specified git repository.
    :param repo_path:
    :param create_if_bare:
    :param short:
    :return:
    """
    print('repo_path:', repo_path)
    repo = Repo(repo_path)
    if create_if_bare and repo.bare:
        repo = Repo.init(os.path.join(dir, 'bare-repo'), bare = True)
        assert repo.bare
    return repo


def commit(repo, commit_message: str = '') -> Repo:
    repo.git.add(update=True)
    repo.index.commit(commit_message)
    return repo


def push(repo, remote_name='origin'):
    origin = repo.remote(name=remote_name)
    origin.push()
    return repo


def commit_and_push(version,
                repo_path: Path | str,
                commit_message: str = '',
                create_if_bare:bool = CREATE_GIT_IF_BARE,
                remote_name = 'origin'
                ) -> Repo:
    repo = commit(version = version, commit_message = commit_message,
                  repo_path = repo_path, create_if_bare = create_if_bare)
    push(repo, remote_name)
    return repo


def get_hashes(repo_path: Path | str, short:int = 4, create_if_bare = CREATE_GIT_IF_BARE) -> str:
    """
    Get Git's short unique object name, essentially a unique id.
    Use "git rev-parse --short" to get the short "object name to a unique prefix with at least
    length characters. The minimum length is 4, the default is the effective value of the
    core.abbrev configuration variable (see git-config[1])" as per
    https://git-scm.com/docs/git-rev-parse

    :return: Git's abbreviated short unique prefix per https://git-scm.com/docs/git-rev-parse
    """
    repo = get_repo(repo_path=repo_path, create_if_bare = create_if_bare)
    return repo.short_sha, repo.sha


def get_hash(repo_path: Path | str) -> str:
    return get_hashes(repo_path=repo_path)[1]

def get_short_hash(repo_path: Path | str, short:int = 4) -> str:
    return get_hashes(short=short, repo_path=repo_path)[0]


if __name__ == '__main__':
    repo_path = Path(__file__).absolute().parent.parent
    repo = get_repo(repo_path=repo_path)

