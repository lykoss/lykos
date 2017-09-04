import re
import random
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src.functions import get_players
from src import debuglog, errlog, plog, users
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event
from src.roles import wolf

wolf.CAN_KILL.remove("wolf cub")
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

# wolf fires on priority 2, so we can add our extra messages now (at default priority 5)
@event_listener("exchange_roles")
def on_exchange(evt, var, user, target, user_role, target_role):
    if not ANGRY_WOLVES:
        return

    wcroles = var.WOLFCHAT_ROLES
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wcroles = var.WOLF_ROLES
        else:
            wcroles = var.WOLF_ROLES | {"traitor"}

    if target_role in wcroles and user_role not in wcroles and wolf.wolf_can_kill(var, target):
        evt.data["user_messages"].append(messages["angry_wolves"])
    elif user_role in wcroles and target_role not in wcroles and wolf.wolf_can_kill(var, user):
        evt.data["target_messages"].append(messages["angry_wolves"])

@event_listener("transition_night_end", priority=3)
def on_transition_night_end(evt, var):
    if not ANGRY_WOLVES:
        return

    wolves = get_players(wolf.CAN_KILL)
    if not wolves or not wolf.wolf_can_kill(var, wolves[0]):
        return

    for wofl in wolves:
        wofl.queue_message(messages["angry_wolves"])

    wofl.send_messages()

@event_listener("chk_win", priority=1)
def on_chk_win(evt, cli, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    did_something = False
    if lrealwolves == 0:
        for wc in list(rolemap["wolf cub"]):
            rolemap["wolf"].add(wc)
            rolemap["wolf cub"].remove(wc)
            wcu = users._get(wc) # FIXME
            if mainroles[wcu] == "wolf cub":
                mainroles[wcu] = "wolf"
            did_something = True
            if var.PHASE in var.GAME_PHASES:
                # don't set cub's FINAL_ROLE to wolf, since we want them listed in endgame
                # stats as cub still.
                wcu.send(messages["cub_grow_up"])
                debuglog(wc, "(wolf cub) GROW UP")
    if did_something:
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("reconfigure_stats")
def on_reconfigure_stats(evt, cli, var, stats):
    if "wolf cub" not in stats or stats["wolf cub"] == 0:
        return
    for role in var.WOLF_ROLES - {"wolf cub"}:
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

# vim: set sw=4 expandtab:
