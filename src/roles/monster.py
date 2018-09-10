import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, status, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Wolf

@event_listener("player_win")
def on_player_win(evt, var, player, mainrole, winner, survived):
    if winner == "monsters" and mainrole == "monster":
        evt.data["won"] = True

@event_listener("chk_win", priority=4)
def on_chk_win(evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    monsters = rolemap.get("monster", ())
    traitors = rolemap.get("traitor", ())

    if not lwolves and not traitors and monsters:
        s = "s" if len(monsters) > 1 else ""
        evt.data["message"] = messages["monster_win"].format(s, "" if s else "s")
        evt.data["winner"] = "monsters"
    elif lwolves >= lpl / 2 and monsters:
        s = "s" if len(monsters) > 1 else ""
        evt.data["message"] = messages["monster_wolf_win"].format(s)
        evt.data["winner"] = "monsters"

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    for monster in get_all_players(("monster",)):
        status.add_protection(var, monster, protector=None, protector_role="monster", scope=Wolf)
        if monster.prefers_simple():
            monster.send(messages["monster_simple"])
        else:
            monster.send(messages["monster_notify"])

@event_listener("remove_protection")
def on_remove_protection(evt, var, target, attacker, attacker_role, protector, protector_role):
    if attacker_role == "fallen angel" and protector_role == "monster":
        evt.data["remove"] = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["monster"] = {"Neutral", "Win Stealer", "Cursed"}
