import argparse
import botconfig
from settings import wolfgame as var

# Todo: Allow game modes to be set via config

# Carry over settings from botconfig into settings/wolfgame.py

for setting, value in botconfig.__dict__.items():
    if not setting.isupper():
        continue # Not a setting
    if not setting in var.__dict__.keys():
        continue # Don't carry over config-only settings

    # If we got that far, it's valid
    setattr(var, setting, value)

# Handle launch parameters

# Argument --debug means start in debug mode
#          --verbose means to print a lot of stuff (when not in debug mode)

parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true')
parser.add_argument('--sabotage', action='store_true')
parser.add_argument('--verbose', action='store_true')

args = parser.parse_args()
botconfig.DEBUG_MODE = args.debug if not botconfig.DISABLE_DEBUG_MODE else False
botconfig.VERBOSE_MODE = args.verbose

botconfig.DEFAULT_MODULE = "sabotage" if args.sabotage else "wolfgame"

# Initialize Database

var.init_db()
