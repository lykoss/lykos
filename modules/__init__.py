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
