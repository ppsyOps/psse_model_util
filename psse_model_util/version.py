"""
Project versioning info
"""

import re
from typing import Union
from psse_model_util.build_utils.build_utils import tuple2version


__pkg_name__ = 'psse_model_util'
# Example __version_info__ = tuple2version((2021, 2, 9, 'final', 0))
__version_info__ = tuple2version((2025, 1, 0, 'final', 0))
__ver__ = __version_info__
# __build_timestamp__ is in UTC w/ ISO format.
#       Example: __build_timestamp__ = '2022-02-19T06:08:32.729080'
__build_timestamp__ = '2025-01-29T15:38:17.939477'
__version__ = '2025.1.0'

if __name__ == '__main__':
    print('__pkg_name__:', __pkg_name__)
    print('__version_info__:', __version_info__)
    print('__version__:', __version__)  # 2022.2.3.dev0+4ae4ff

