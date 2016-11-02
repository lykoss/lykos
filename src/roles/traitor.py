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

@event_listener("get_reveal_role")
def on_get_reveal_role(evt, var, nick):
    # in team reveal, show traitor as wolfteam, otherwise team stats won't sync with how
    # they're revealed upon death. Team stats should show traitor as wolfteam or else
    # the stats are wrong in that they'll report one less wolf than actually exists,
    # which can confuse a lot of people
    if evt.data["role"] == "traitor" and var.HIDDEN_TRAITOR and var.ROLE_REVEAL != "team":
        evt.data["role"] = var.DEFAULT_ROLE

@event_listener("get_final_role")
def on_get_final_role(evt, cli, var, nick, role):
    # if a traitor turns we want to show them as traitor in the end game readout
    # instead of "wolf (was traitor)"
    if role == "traitor" and evt.data["role"] == "wolf":
        evt.data["role"] = "traitor"

@event_listener("update_stats")
def on_update_stats(evt, cli, var, nick, nickrole, nickreveal, nicktpls):
    if nickrole == var.DEFAULT_ROLE and var.HIDDEN_TRAITOR:
        evt.data["possible"].add("traitor")
    # if this is a night death and we know for sure that wolves (and only wolves)
    # killed, then that kill cannot be traitor as long as they're in wolfchat.
    # TODO: need to figure out how to actually piece this together, but will
    # likely require splitting off every other role first.

# vim: set sw=4 expandtab:
