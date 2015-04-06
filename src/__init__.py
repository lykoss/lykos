import argparse
import datetime
import time

import botconfig
from src import _logger
from src import settings as var

# Todo: Allow game modes to be set via config

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

botconfig.DEBUG_MODE = debug_mode if not botconfig.DISABLE_DEBUG_MODE and not normal else False
botconfig.VERBOSE_MODE = verbose if not normal else False

# Initialize Database

var.init_db()

# Prepare the logger

kwargs = dict(use_utc=botconfig.USE_UTC, ts_format=botconfig.TIMESTAMP_FORMAT,
         bypassers=(("write", set(), {(botconfig, "DEBUG_MODE")}, None, True),
         ("display", set(), {(botconfig, "DEBUG_MODE"), (botconfig, "VERBOSE_MODE")}, None, True)),
         print_ts=True, split=False)

logger = _logger.Logger(logfiles={"debug": "debug.log", "error": "errors.log", "normal": None}, **kwargs)

stream = _logger.NamedLevelsLogger(write=False, levels={"warning": 15, "normal": 10, "debug": 5},
          level=10, logfiles={"normal": None}, **kwargs)

stream.bypassers.update(("level", set(), {(botconfig, "DEBUG_MODE"), (botconfig, "VERBOSE_MODE")}, None, 15))
