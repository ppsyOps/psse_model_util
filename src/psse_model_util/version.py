"""
version.py — backwards-compat shim. Real version lives in __about__.py.
Do not add logic here; use __about__.__version__ directly.
"""
from psse_model_util.__about__ import __version__

__pkg_name__ = 'psse_model_util'
__ver__ = __version__

if __name__ == '__main__':
    print('__pkg_name__:', __pkg_name__)
    print('__version__:', __version__)
