import argparse
import botconfig
from settings import wolfgame as var

# Todo: Allow game modes to be set via config

# Handle launch parameters

# Argument --debug means start in debug mode
#          --verbose means to print a lot of stuff (when not in debug mode)
#          --normal means to override the above and use nothing
# Settings can be defined in the config, but launch argumentss override it

debug_mode = False
verbose = False
sabotage = False
normal = False

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
    if setting == "NORMAL_MODE":
        normal = value
    if not setting in var.__dict__.keys():
        continue # Don't carry over config-only settings

    # If we got that far, it's valid
    setattr(var, setting, value)

parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true')
parser.add_argument('--sabotage', action='store_true')
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--normal', action='store_true')

args = parser.parse_args()

if args.debug: debug_mode = True
if args.verbose: verbose = True
if args.sabotage: sabotage = True
if args.normal: normal = True

botconfig.DEBUG_MODE = debug_mode if not botconfig.DISABLE_DEBUG_MODE and not normal else False
botconfig.VERBOSE_MODE = verbose if not normal else False

botconfig.DEFAULT_MODULE = "sabotage" if args.sabotage else "wolfgame"

# Initialize Database

var.init_db()
