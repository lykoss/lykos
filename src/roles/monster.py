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
from src.status import try_misdirection, try_exchange, add_protection
from src.cats import Wolf

@event_listener("team_win")
def on_team_win(evt, var, player, main_role, all_roles, winner):
    if winner == "monsters" and main_role == "monster":
        evt.data["team_win"] = True

@event_listener("chk_win", priority=4)
def on_chk_win(evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    monsters = rolemap.get("monster", ())
    traitors = rolemap.get("traitor", ())
    lm = len(monsters)

    if not lrealwolves and not traitors and monsters:
        evt.data["message"] = messages["monster_win"].format(lm)
        evt.data["winner"] = "monsters"
    elif lwolves >= lpl / 2 and monsters:
        evt.data["message"] = messages["monster_wolf_win"].format(lm)
        evt.data["winner"] = "monsters"

@event_listener("send_role")
def on_send_role(evt, var):
    for monster in get_all_players(var, ("monster",)):
        add_protection(var, monster, protector=None, protector_role="monster", scope=Wolf)
        monster.send(messages["monster_notify"])

@event_listener("remove_protection")
def on_remove_protection(evt, var, target, attacker, attacker_role, protector, protector_role, reason):
    if attacker_role == "fallen angel" and protector_role == "monster":
        evt.data["remove"] = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["monster"] = {"Neutral", "Win Stealer", "Cursed"}
