import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange

JESTERS = UserSet() # type: UserSet[users.User]

@event_listener("lynch")
def on_lynch(evt, var, votee, voters):
    if votee in get_all_players(("jester",)):
        JESTERS.add(votee)

@event_listener("player_win")
def on_player_win(evt, var, player, main_role, all_roles, winner, team_win, survived):
    if player in JESTERS:
        evt.data["individual_win"] = True

@event_listener("send_role")
def on_send_role(evt, var):
    for jester in get_all_players(("jester",)):
        jester.send(messages["jester_notify"])

@event_listener("reset")
def on_reset(evt, var):
    JESTERS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["jester"] = {"Neutral", "Innocent"}
