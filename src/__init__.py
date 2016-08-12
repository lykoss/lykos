import argparse
import datetime
import time

import botconfig
import src.settings as var
from src import logger
from src.logger import stream, stream_handler, debuglog, errlog, plog
from src import db

# Import the user-defined game modes
# These are not required, so failing to import it doesn't matter
# The file then imports our game modes
# Fall back to importing our game modes if theirs fail
# Do the same with roles

try:
    import gamemodes # type: ignore
except ImportError:
    import src.gamemodes

try:
    import roles # type: ignore
    roles.CUSTOM_ROLES_DEFINED
except (ImportError, AttributeError):
    import src.roles

# Handle launch parameters

# Argument --debug means start in debug mode
#          --verbose means to print a lot of stuff (when not in debug mode)
#          --normal means to override the above and use nothing
# Settings can be defined in the config, but launch argumentss override it

debug_mode = False
verbose = False
normal = False

# Carry over settings from botconfig into settings.py

for setting, value in botconfig.__dict__.items():
    if not setting.isupper():
        continue # Not a setting
    if setting == "DEBUG_MODE":
        debug_mode = value
    if setting == "VERBOSE_MODE":
        verbose = value
    if setting == "NORMAL_MODE":
        normal = value
    if not setting in var.__dict__.keys():
        continue # Don't carry over config-only settings

    # If we got that far, it's valid
    setattr(var, setting, value)

parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true')
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--normal', action='store_true')

args = parser.parse_args()

if args.debug: debug_mode = True
if args.verbose: verbose = True
if args.normal: normal = True

botconfig.DEBUG_MODE = debug_mode if not normal else False
botconfig.VERBOSE_MODE = verbose if not normal else False

# vim: set sw=4 expandtab:
