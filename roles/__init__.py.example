# Imports all custom and built-in role definitions
# To implement custom roles, rename this file to __init__.py
import os.path
import glob
import importlib

# get built-in roles
import src.roles

path = os.path.dirname(os.path.abspath(__file__))
search = os.path.join(path, "*.py")

for f in glob.iglob(search):
    f = os.path.basename(f)
    n, _ = os.path.splitext(f)
    if f == "__init__.py":
        continue
    importlib.import_module("." + n, package="roles")

# Important: if this isn't defined, built-in roles will
# be imported. Normally this isn't an issue, but if you
# are attempting to suppress the import of built-in roles
# then that might be an issue for you.
CUSTOM_ROLES_DEFINED = True

# vim: set sw=4 expandtab:
