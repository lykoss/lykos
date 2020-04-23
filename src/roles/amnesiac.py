import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target, change_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.cats import role_order, Win_Stealer

ROLES = UserDict()  # type: Dict[users.User, str]
STATS_FLAG = False # if True, we begin accounting for amnesiac in update_stats

def _get_blacklist(var):
    blacklist = var.CURRENT_GAMEMODE.SECONDARY_ROLES.keys() | Win_Stealer | {"villager", "cultist", "amnesiac"}
    return blacklist

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    global STATS_FLAG
    if var.NIGHT_COUNT == var.AMNESIAC_NIGHTS:
        amnesiacs = get_all_players(("amnesiac",))
        if amnesiacs and not var.HIDDEN_AMNESIAC:
            STATS_FLAG = True

        for amn in amnesiacs:
            role = change_role(var, amn, "amnesiac", ROLES[amn], message="amnesia_clear")
            debuglog("{0} REMEMBER: {1}".format(amn, role))

@event_listener("investigate")
def on_investigate(evt, var, actor, target):
    if evt.data["role"] == "amnesiac":
        evt.data["role"] = ROLES[target]

@event_listener("new_role", priority=1) # Exchange, clone, etc. - assign the amnesiac's final role
def update_amnesiac(evt, var, user, old_role):
    # FIXME: exchange totem messes with var.HIDDEN_AMNESIAC (the new amnesiac is no longer hidden should they die)
    if evt.params.inherit_from is not None and evt.data["role"] == "amnesiac" and old_role != "amnesiac":
        evt.data["role"] = ROLES[evt.params.inherit_from]

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if evt.params.inherit_from is None and evt.data["role"] == "amnesiac":
        roles = set(role_order()) - _get_blacklist(var)
        ROLES[user] = random.choice(list(roles))

@event_listener("role_revealed")
def on_revealing_totem(evt, var, user, role):
    if role not in _get_blacklist(var) and not var.HIDDEN_AMNESIAC and var.ORIGINAL_ROLES["amnesiac"]:
        global STATS_FLAG
        STATS_FLAG = True
    if role == "amnesiac":
        user.send(messages["amnesia_clear"].format(ROLES[user]))
        change_role(var, user, "amnesiac", ROLES[user])

@event_listener("get_reveal_role")
def on_reveal_role(evt, var, user):
    if var.HIDDEN_AMNESIAC and var.ORIGINAL_MAIN_ROLES[user] == "amnesiac":
        evt.data["role"] = "amnesiac"

@event_listener("get_endgame_message")
def on_get_endgame_message(evt, var, player, role, is_mainrole):
    if role == "amnesiac":
        evt.data["message"].append(messages["amnesiac_endgame"].format(ROLES[player]))

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "amnesiac":
        evt.data["special_case"].append(messages["amnesiac_revealroles"].format(ROLES[user]))

@event_listener("update_stats")
def on_update_stats(evt, var, player, mainrole, revealrole, allroles):
    if STATS_FLAG and not _get_blacklist(var) & {mainrole, revealrole}:
        evt.data["possible"].add("amnesiac")

@event_listener("reset")
def on_reset(evt, var):
    global STATS_FLAG
    ROLES.clear()
    STATS_FLAG = False

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["amnesiac"] = {"Hidden", "Team Switcher"}
