import os
from glob import glob

__all__ = [
    os.path.splitext(os.path.basename(py))[0]
    for py in glob(os.path.join(os.path.dirname(__file__), "*.py"))
    if py != __file__
]

