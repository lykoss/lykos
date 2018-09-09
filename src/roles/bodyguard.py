import re
import random
import itertools
import math
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_target, get_main_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Wolf

GUARDED = UserDict() # type: Dict[User, User]
PASSED = UserSet() # type: Set[User]

@command("guard", "protect", "save", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("bodyguard",))
def guard(var, wrapper, message):
    """Guard a player, preventing them from being killed that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="cannot_guard_self")
    if not target:
        return

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    if not evt.dispatch(var, wrapper.source, target):
        return

    target = evt.data["target"]
    GUARDED[wrapper.source] = target

    wrapper.pm(messages["protecting_target"].format(target))
    target.send(messages["target_protected"])

    debuglog("{0} (bodyguard) GUARD: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("pass", chan=False, pm=True, playing=True, phases=("night",), roles=("bodyguard",))
def pass_cmd(var, wrapper, message):
    """Decline to use your special power for that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return
    PASSED.add(wrapper.source)
    wrapper.pm(messages["guardian_no_protect"])
    debuglog("{0} (bodyguard) PASS".format(wrapper.source))

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    if var.PHASE == "night" and player in GUARDED:
        GUARDED[player].send(messages["protector_disappeared"])
    for k,v in list(GUARDED.items()):
        if player.nick in (k, v):
            del GUARDED[k]
    PASSED.discard(player)

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if target_role == "bodyguard":
        if target in GUARDED:
            guarded = GUARDED.pop(target)
            guarded.send(messages["protector disappeared"])
    if actor_role == "bodyguard":
        if actor in GUARDED:
            guarded = GUARDED.pop(actor)
            guarded.send(messages["protector disappeared"])

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(GUARDED) + len(PASSED)
    evt.data["nightroles"].extend(get_players(("bodyguard",)))

@event_listener("fallen_angel_guard_break")
def on_fagb(evt, var, user, killer):
    for g in get_all_players(("bodyguard",)):
        if GUARDED.get(g) is user:
            if g in evt.data["protected"]:
                del evt.data["protected"][g]
            evt.data["bywolves"].add(g)
            if g not in evt.data["victims"]:
                evt.data["onlybywolves"].add(g)
            evt.data["victims"].append(g)
            evt.data["killers"][g].append(killer)
            if g is not user:
                g.send(messages["fallen_angel_success"].format(user))

@event_listener("transition_day_resolve", priority=2)
def on_transition_day_resolve(evt, var, victim):
    if evt.data["protected"].get(victim) == "bodyguard":
        for bodyguard in get_all_players(("bodyguard",)):
            if GUARDED.get(bodyguard) is victim:
                evt.data["dead"].append(bodyguard)
                evt.data["message"][victim].append(messages["bodyguard_protection"].format(bodyguard))
                evt.data["novictmsg"] = False
                evt.stop_processing = True
                evt.prevent_default = True
                break

@event_listener("transition_day_resolve_end", priority=3)
def on_transition_day_resolve_end(evt, var, victims):
    for bodyguard in get_all_players(("bodyguard",)):
        if GUARDED.get(bodyguard) in get_players(Wolf) and bodyguard not in evt.data["dead"]:
            r = random.random()
            if r < var.BODYGUARD_DIES_CHANCE:
                evt.data["bywolves"].add(bodyguard)
                evt.data["onlybywolves"].add(bodyguard)
                if var.ROLE_REVEAL == "on":
                    evt.data["message"][bodyguard].append(messages["bodyguard_protected_wolf"].format(bodyguard))
                else: # off and team
                    evt.data["message"][bodyguard].append(messages["bodyguard_protection"].format(bodyguard))
                evt.data["dead"].append(bodyguard)

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    # needs to be here in order to allow bodyguard protections to work during the daytime
    # (right now they don't due to other reasons, but that may change)
    GUARDED.clear()

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    # the messages for angel and guardian angel are different enough to merit individual loops
    ps = get_players()
    for bg in get_all_players(("bodyguard",)):
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(bg)
        chance = math.floor(var.BODYGUARD_DIES_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = messages["bodyguard_death_chance"].format(chance)

        to_send = "bodyguard_notify"
        if bg.prefers_simple():
            to_send = "bodyguard_simple"
        bg.send(messages[to_send].format(warning), messages["players_list"].format(", ".join(p.nick for p in pl), sep="\n"))

@event_listener("assassinate")
def on_assassinate(evt, var, killer, target, prot):
    if prot == "bodyguard":
        var.ACTIVE_PROTECTIONS[target.nick].remove("bodyguard")
        evt.prevent_default = True
        evt.stop_processing = True
        for bg in var.ROLES["bodyguard"]:
            if GUARDED.get(bg.nick) == target.nick:
                channels.Main.send(messages[evt.params.message_prefix + "bodyguard"].format(killer, target, bg))
                # redirect the assassination to the bodyguard
                evt.data["target"] = bg
                break

@event_listener("begin_day")
def on_begin_day(evt, var):
    PASSED.clear()

@event_listener("reset")
def on_reset(evt, var):
    GUARDED.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["bodyguard"] = {"Village", "Safe", "Nocturnal"}

# vim: set sw=4 expandtab:
