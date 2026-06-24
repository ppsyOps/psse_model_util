"""DEPRECATED backwards-compatibility shim.

Kept only so older imports of ``psse_model_util.version`` keep working. The
canonical version string lives in :mod:`psse_model_util.__about__`; use
``__about__.__version__`` directly. Do not add logic here.
"""
from psse_model_util.__about__ import __version__

__pkg_name__ = 'psse_model_util'
__ver__ = __version__

if __name__ == '__main__':
    print('__pkg_name__:', __pkg_name__)
    print('__version__:', __version__)
