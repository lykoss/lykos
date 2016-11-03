import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

REVEALED_MAYORS = set()

@event_listener("rename_player")
def on_rename_player(evt, cli, var, prefix, nick):
    if prefix in REVEALED_MAYORS:
        REVEALED_MAYORS.remove(prefix)
        REVEALED_MAYORS.add(nick)

@event_listener("chk_decision_lynch", priority=3)
def on_chk_decision_lynch(evt, cli, var, voters):
    votee = evt.data["votee"]
    if votee in var.ROLES["mayor"] and votee not in REVEALED_MAYORS:
        cli.msg(botconfig.CHANNEL, messages["mayor_reveal"].format(votee))
        REVEALED_MAYORS.add(votee)
        evt.data["votee"] = None
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("reset")
def on_reset(evt, var):
    REVEALED_MAYORS.clear()

# vim: set sw=4 expandtab:
