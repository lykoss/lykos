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
from src.events import Event

JESTERS = UserSet() # type: UserSet[users.User]

@event_listener("chk_decision_lynch")
def on_chk_decision_lynch(evt, var, voters):
    if evt.data["votee"] in get_all_players(("jester",)):
        JESTERS.add(evt.data["votee"])

@event_listener("player_win")
def on_player_win(evt, var, player, role, winner, survived):
    if player in JESTERS:
        evt.data["iwon"] = True

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    for jester in get_all_players(("jester",)):
        if jester.prefers_simple():
            jester.send(messages["jester_simple"])
        else:
            jester.send(messages["jester_notify"])

@event_listener("reset")
def on_reset(evt, var):
    JESTERS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["jester"] = {"Neutral", "Innocent"}
