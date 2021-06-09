# Imports all role definitions
import os.path
import glob
import importlib

path = os.path.dirname(os.path.abspath(__file__))
search = os.path.join(path, "*.py")

for f in glob.iglob(search):
    f = os.path.basename(f)
    n, _ = os.path.splitext(f)
    if f.startswith("_"):
        continue
    importlib.import_module("." + n, package="src.roles")
