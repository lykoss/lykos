import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

REVEALED_MAYORS = UserSet()

@event_listener("chk_decision_lynch", priority=3)
def on_chk_decision_lynch(evt, var, voters):
    votee = evt.data["votee"]
    if votee in var.ROLES["mayor"] and votee not in REVEALED_MAYORS:
        channels.Main.send(messages["mayor_reveal"].format(votee))
        REVEALED_MAYORS.add(votee)
        evt.data["votee"] = None
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("reset")
def on_reset(evt, var):
    REVEALED_MAYORS.clear()

# vim: set sw=4 expandtab:
