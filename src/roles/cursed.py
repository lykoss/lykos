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

@event_listener("see")
def on_see(evt, cli, var, nick, victim):
    if victim in var.ROLES["cursed villager"]:
        evt.data["role"] = "wolf"

@event_listener("wolflist")
def on_wolflist(evt, cli, var, nick, wolf):
    if nick in var.ROLES["cursed villager"]:
        evt.data["tags"].add("cursed")

# vim: set sw=4 expandtab:
