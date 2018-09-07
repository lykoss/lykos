"""Core game status are exposed here."""

import os.path
import glob
import importlib

__all__ = []

path = os.path.dirname(os.path.abspath(__file__))
search = os.path.join(path, "*.py")

for f in glob.iglob(search):
    f = os.path.basename(f)
    n, _ = os.path.splitext(f)
    if f.startswith("_"):
        continue
    mod = importlib.import_module("." + n, package="src.status")

    all = mod.__all__
    if set(__all__) & set(all):
        raise TypeError("Error: duplicate names {0}".format(set(__all__) & set(all)))
    __all__.extend(all)

    for name in all:
        globals()[name] = getattr(mod, name)
