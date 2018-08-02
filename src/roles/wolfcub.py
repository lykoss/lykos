import re
import random
from collections import defaultdict

from src.utilities import *
from src.functions import get_players
from src import debuglog, errlog, plog, users, channels
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Wolf, Killer

from src.roles._wolf_helper import wolf_can_kill, CAN_KILL

ANGRY_WOLVES = False

@event_listener("wolf_numkills")
def on_wolf_numkills(evt, var):
    if ANGRY_WOLVES:
        evt.data["numkills"] = max(evt.data["numkills"], 2)

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    if death_triggers and "wolf cub" in allroles:
        global ANGRY_WOLVES
        ANGRY_WOLVES = True

@event_listener("new_role")
def on_new_role(evt, var, player, old_role):
    if ANGRY_WOLVES and evt.data["in_wolfchat"] and wolf_can_kill(var, player):
        evt.data["messages"].append(messages["angry_wolves"])

@event_listener("transition_night_end", priority=3)
def on_transition_night_end(evt, var):
    if not ANGRY_WOLVES:
        return

    wolves = get_players(CAN_KILL)
    if not wolves or not wolf_can_kill(var, wolves[0]):
        return

    for wofl in wolves:
        wofl.queue_message(messages["angry_wolves"])

    wofl.send_messages()

@event_listener("chk_win", priority=1)
def on_chk_win(evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    did_something = False
    if lrealwolves == 0:
        for wc in list(rolemap["wolf cub"]):
            rolemap["wolf"].add(wc)
            rolemap["wolf cub"].remove(wc)
            if mainroles[wc] == "wolf cub":
                mainroles[wc] = "wolf"
            did_something = True
            if var.PHASE in var.GAME_PHASES:
                # don't set cub's FINAL_ROLE to wolf, since we want them listed in endgame
                # stats as cub still.
                wc.send(messages["cub_grow_up"])
                debuglog("{0} (wolf cub) GROW UP".format(wc))
    if did_something:
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("reconfigure_stats")
def on_reconfigure_stats(evt, var, stats):
    if "wolf cub" not in stats or stats["wolf cub"] == 0:
        return
    for role in Wolf & Killer:
        if role in stats and stats[role] > 0:
            break
    else:
        stats["wolf"] = stats["wolf cub"]
        stats["wolf cub"] = 0

@event_listener("transition_day_resolve_end")
def on_begin_day(evt, var, victims):
    global ANGRY_WOLVES
    ANGRY_WOLVES = False

@event_listener("reset")
def on_reset(evt, var):
    global ANGRY_WOLVES
    ANGRY_WOLVES = False

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["wolf cub"] = {"Wolf", "Wolfchat", "Wolfteam"}

# vim: set sw=4 expandtab:
