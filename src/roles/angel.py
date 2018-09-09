import re
import random
import itertools
import math
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src import users, channels, status, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_target, get_main_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Wolf

GUARDED = UserDict() # type: Dict[User, User]
LASTGUARDED = UserDict() # type: Dict[User, User]
PASSED = UserSet() # type: Set[User]

@command("guard", "protect", "save", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("guardian angel",))
def guard(var, wrapper, message):
    """Guard a player, preventing them from being killed that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], allow_self=var.GUARDIAN_ANGEL_CAN_GUARD_SELF, not_self_message="cannot_guard_self")
    if not target:
        return

    if LASTGUARDED.get(wrapper.source) is target:
        wrapper.pm(messages["guardian_target_another"].format(target))
        return

    target_other = wrapper.source is not target

    evt = Event("targeted_command", {"target": target, "misdirection": target_other, "exchange": target_other})
    if not evt.dispatch(var, wrapper.source, target):
        return

    target = evt.data["target"]
    status.add_protection(var, target, wrapper.source, "guardian angel")
    GUARDED[wrapper.source] = target
    LASTGUARDED[wrapper.source] = target

    if wrapper.source is target:
        wrapper.pm(messages["guardian_guard_self"])
    else:
        wrapper.pm(messages["protecting_target"].format(target))
        target.send(messages["target_protected"])

    debuglog("{0} (guardian angel) GUARD: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("pass", chan=False, pm=True, playing=True, phases=("night",), roles=("guardian angel",))
def pass_cmd(var, wrapper, message):
    """Decline to use your special power for that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return

    PASSED.add(wrapper.source)
    wrapper.pm(messages["guardian_no_protect"])
    debuglog("{0} (guardian angel) PASS".format(wrapper.source))

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    if var.PHASE == "night" and player in GUARDED:
        GUARDED[player].send(messages["protector_disappeared"])
    for dictvar in (GUARDED, LASTGUARDED):
        for k,v in list(dictvar.items()):
            if player in (k, v):
                del dictvar[k]
    PASSED.discard(player)

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if actor_role == "guardian angel":
        if actor in GUARDED:
            guarded = GUARDED.pop(actor)
            guarded.send(messages["protector disappeared"])
        if actor in LASTGUARDED:
            del LASTGUARDED[actor]
    if target_role == "guardian angel":
        if target in GUARDED:
            guarded = GUARDED.pop(target)
            guarded.send(messages["protector disappeared"])
        if target in LASTGUARDED:
            del LASTGUARDED[target]

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(GUARDED) + len(PASSED)
    evt.data["nightroles"].extend(get_players(("guardian angel",)))

# FIXME: All of this needs changing because it's incorrect
# Also let's kill the "protected" key

@event_listener("fallen_angel_guard_break")
def on_fagb(evt, var, user, killer):
    for g in get_all_players(("guardian angel",)):
        if GUARDED.get(g) is user:
            if random.random() < var.FALLEN_ANGEL_KILLS_GUARDIAN_ANGEL_CHANCE:
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
    if evt.data["protected"].get(victim) == "angel":
        evt.data["message"][victim].append(messages["angel_protection"].format(victim))
        evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_day_resolve_end", priority=3)
def on_transition_day_resolve_end(evt, var, victims):
    for gangel in get_all_players(("guardian angel",)):
        if GUARDED.get(gangel) in get_players(Wolf) and gangel not in evt.data["dead"]:
            r = random.random()
            if r < var.GUARDIAN_ANGEL_DIES_CHANCE:
                evt.data["bywolves"].add(gangel)
                evt.data["onlybywolves"].add(gangel)
                if var.ROLE_REVEAL == "on":
                    evt.data["message"][gangel].append(messages["guardian_angel_protected_wolf"].format(gangel))
                else: # off and team
                    evt.data["message"][gangel].append(messages["guardian_angel_protected_wolf_no_reveal"].format(gangel))
                evt.data["dead"].append(gangel)

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    # needs to be here in order to allow protections to work during the daytime
    # (right now they don't due to other reasons, but that may change)
    GUARDED.clear()

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = get_players()
    for gangel in get_all_players(("guardian angel",)):
        pl = ps[:]
        random.shuffle(pl)
        gself = messages["guardian_self_notification"]
        if not var.GUARDIAN_ANGEL_CAN_GUARD_SELF:
            pl.remove(gangel)
            gself = ""
        if gangel in LASTGUARDED:
            if LASTGUARDED[gangel] in pl:
                pl.remove(LASTGUARDED[gangel])
        chance = math.floor(var.GUARDIAN_ANGEL_DIES_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = messages["bodyguard_death_chance"].format(chance)

        to_send = "guardian_notify"
        if gangel.prefers_simple():
            to_send = "guardian_simple"
        gangel.send(messages[to_send].format(warning, gself), messages["players_list"].format(", ".join(p.nick for p in pl)), sep="\n")

@event_listener("assassinate")
def on_assassinate(evt, var, killer, target, prot):
    if prot == "angel" and var.GAMEPHASE == "night":
        var.ACTIVE_PROTECTIONS[target.nick].remove("angel")
        evt.prevent_default = True
        evt.stop_processing = True
        channels.Main.send(messages[evt.params.message_prefix + "angel"].format(killer, target))

@event_listener("begin_day")
def on_begin_day(evt, var):
    PASSED.clear()
    # clear out LASTGUARDED for people that didn't guard last night
    for g in list(LASTGUARDED.keys()):
        if g not in GUARDED:
            del LASTGUARDED[g]

@event_listener("reset")
def on_reset(evt, var):
    GUARDED.clear()
    LASTGUARDED.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["guardian angel"] = {"Village", "Safe", "Nocturnal"}
    elif kind == "lycanthropy_role":
        evt.data["guardian angel"] = {"role": "fallen angel", "prefix": "fallen_angel", "secondary_roles": {"assassin"}}

# vim: set sw=4 expandtab:
