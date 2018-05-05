import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
from src.utilities import *
from src import debuglog, errlog, plog, users, channels
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

@event_listener("get_reveal_role")
def on_get_reveal_role(evt, var, user):
    # in team reveal, show traitor as wolfteam, otherwise team stats won't sync with how
    # they're revealed upon death. Team stats should show traitor as wolfteam or else
    # the stats are wrong in that they'll report one less wolf than actually exists,
    # which can confuse a lot of people
    if evt.data["role"] == "traitor" and var.HIDDEN_TRAITOR and var.ROLE_REVEAL != "team":
        evt.data["role"] = var.DEFAULT_ROLE

@event_listener("get_final_role")
def on_get_final_role(evt, var, user, role):
    # if a traitor turns we want to show them as traitor in the end game readout
    # instead of "wolf (was traitor)"
    if role == "traitor" and evt.data["role"] == "wolf":
        evt.data["role"] = "traitor"

@event_listener("update_stats", priority=1)
def on_update_stats1(evt, var, player, mainrole, revealrole, allroles):
    if mainrole == var.DEFAULT_ROLE and var.HIDDEN_TRAITOR:
        evt.data["possible"].add("traitor")

@event_listener("update_stats", priority=3)
def on_update_stats3(evt, var, player, mainrole, revealrole, allroles):
    # if this is a night death and we know for sure that wolves (and only wolves)
    # killed, then that kill cannot be traitor as long as they're in wolfchat.
    # ismain True = night death, False = chain death; chain deaths can be traitors
    # even if only wolves killed, so we short-circuit there as well
    # TODO: luck/misdirection totem can leak info due to our short-circuit below this comment.
    # If traitor dies due to one of these totems, both traitor count and villager count is reduced by
    # 1. If traitor does not die, and no other roles can kill (no death totems), then traitor count is unchanged
    # and villager count is reduced by 1. We should make it so that both counts are reduced when
    # luck/misdirection are potentially in play.
    # FIXME: this doesn't check RESTRICT_WOLFCHAT to see if traitor was removed from wolfchat. If
    # they've been removed, they can be killed like normal so all this logic is meaningless.
    if "traitor" not in evt.data["possible"] or not evt.params.ismain or mainrole == "traitor":
        return
    if var.PHASE == "day" and var.GAMEPHASE == "night":
        mevt = Event("get_role_metadata", {})
        mevt.dispatch(var, "night_kills")
        nonwolf = 0
        total = 0
        for role, num in mevt.data.items():
            if role != "wolf":
                nonwolf += num
            total += num
        if nonwolf == 0:
            evt.data["possible"].discard("traitor")
            return
        # TODO: this doesn't account for everything, for example if there was a hunter kill
        # and a wolf kill, and a wolf + villager died, we know the villager was the wolf kill
        # and therefore cannot be traitor. However, we currently do not have the logic to deduce this

@event_listener("chk_win", priority=1.1)
def on_chk_win(evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    did_something = False
    if lrealwolves == 0:
        for traitor in list(rolemap["traitor"]):
            rolemap["wolf"].add(traitor)
            rolemap["traitor"].remove(traitor)
            rolemap["cursed villager"].discard(traitor)
            mainroles[traitor] = "wolf"
            did_something = True
            if var.PHASE in var.GAME_PHASES:
                var.FINAL_ROLES[traitor.nick] = "wolf" # FIXME
                traitor.send(messages["traitor_turn"])
                debuglog(traitor, "(traitor) TURNING")
    if did_something:
        if var.PHASE in var.GAME_PHASES:
            var.TRAITOR_TURNED = True
            channels.Main.send(messages["traitor_turn_channel"])
        evt.prevent_default = True
        evt.stop_processing = True

# vim: set sw=4 expandtab:
