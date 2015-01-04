import argparse
import botconfig
from settings import wolfgame as var

# Todo: Allow game modes to be set via config

# Handle launch parameters

# Argument --debug means start in debug mode
#          --verbose means to print a lot of stuff (when not in debug mode)

parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true')
parser.add_argument('--sabotage', action='store_true')
parser.add_argument('--verbose', action='store_true')

args = parser.parse_args()

debug_mode = args.debug
verbose = args.verbose
sabotage = args.sabotage

# Carry over settings from botconfig into settings/wolfgame.py

for setting, value in botconfig.__dict__.items():
    if not setting.isupper():
        continue # Not a setting
    if setting == "DEBUG_MODE":
        debug_mode = value
    if setting == "VERBOSE_MODE":
        verbose = value
    if setting == "DEFAULT_MODULE":
        sabotage = value
    if not setting in var.__dict__.keys():
        continue # Don't carry over config-only settings

    # If we got that far, it's valid
    setattr(var, setting, value)

botconfig.DEBUG_MODE = debug_mode if not botconfig.DISABLE_DEBUG_MODE else False
botconfig.VERBOSE_MODE = verbose

botconfig.DEFAULT_MODULE = "sabotage" if args.sabotage else "wolfgame"

# Initialize Database

var.init_db()
