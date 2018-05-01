import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

GUARDED = {} # type: Dict[str, str]
LASTGUARDED = {} # type: Dict[str, str]
PASSED = set() # type: Set[str]

@cmd("guard", "protect", "save", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("bodyguard", "guardian angel"))
def guard(cli, nick, chan, rest):
    """Guard a player, preventing them from being killed that night."""
    if nick in GUARDED:
        pm(cli, nick, messages["already_protecting"])
        return
    role = get_role(nick)
    self_in_list = role == "guardian angel" and var.GUARDIAN_ANGEL_CAN_GUARD_SELF
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, self_in_list)
    if not victim:
        return
    if (role == "bodyguard" or not var.GUARDIAN_ANGEL_CAN_GUARD_SELF) and victim == nick:
        pm(cli, nick, messages["cannot_guard_self"])
        return
    if role == "guardian angel" and LASTGUARDED.get(nick) == victim:
        pm(cli, nick, messages["guardian_target_another"].format(victim))
        return

    angel = users._get(nick) # FIXME
    target = users._get(victim) # FIXME

    # self-guard ignores luck/misdirection/exchange totem
    evt = Event("targeted_command", {"target": target, "misdirection": (angel is not target), "exchange": (angel is not target)})
    if not evt.dispatch(var, angel, target):
        return
    victim = evt.data["target"].nick
    GUARDED[nick] = victim
    LASTGUARDED[nick] = victim
    if victim == nick:
        pm(cli, nick, messages["guardian_guard_self"])
    else:
        pm(cli, nick, messages["protecting_target"].format(GUARDED[nick]))
        pm(cli, victim, messages["target_protected"])
    debuglog("{0} ({1}) GUARD: {2} ({3})".format(nick, role, victim, get_role(victim)))

@cmd("pass", chan=False, pm=True, playing=True, phases=("night",), roles=("bodyguard", "guardian angel"))
def pass_cmd(cli, nick, chan, rest):
    """Decline to use your special power for that night."""
    if nick in GUARDED:
        pm(cli, nick, messages["already_protecting"])
        return
    PASSED.add(nick)
    pm(cli, nick, messages["guardian_no_protect"])
    debuglog("{0} ({1}) PASS".format(nick, get_role(nick)))

@event_listener("rename_player")
def on_rename(evt, var, prefix, nick):
    for dictvar in (GUARDED, LASTGUARDED):
        kvp = {}
        for a,b in dictvar.items():
            if a == prefix:
                if b == prefix:
                    kvp[nick] = nick
                else:
                    kvp[nick] = b
            elif b == prefix:
                kvp[a] = nick
        dictvar.update(kvp)
        if prefix in dictvar:
            del dictvar[prefix]
    if prefix in PASSED:
        PASSED.discard(prefix)
        PASSED.add(nick)

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    if var.PHASE == "night" and user.nick in GUARDED:
        pm(user.client, GUARDED[user.nick], messages["protector_disappeared"])
    for dictvar in (GUARDED, LASTGUARDED):
        for k,v in list(dictvar.items()):
            if user.nick in (k, v):
                del dictvar[k]
    PASSED.discard(user.nick)

@event_listener("night_acted")
def on_acted(evt, var, user, actor):
    if user.nick in GUARDED:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["villagers"].update(get_players(("guardian angel", "bodyguard")))

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if actor_role in ("bodyguard", "guardian angel"):
        if actor.nick in GUARDED:
            guarded = users._get(GUARDED.pop(actor.nick)) # FIXME
            guarded.send(messages["protector disappeared"])
        if actor.nick in LASTGUARDED:
            del LASTGUARDED[actor.nick]
    if target_role in ("bodyguard", "guardian angel"):
        if target.nick in GUARDED:
            guarded = users._get(GUARDED.pop(target.nick)) # FIXME
            guarded.send(messages["protector disappeared"])
        if target.nick in LASTGUARDED:
            del LASTGUARDED[target.nick]

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(GUARDED) + len(PASSED)
    evt.data["nightroles"].extend(get_players(("guardian angel", "bodyguard")))

@event_listener("transition_day", priority=4.2)
def on_transition_day(evt, var):
    pl = get_players()
    vs = set(evt.data["victims"])
    for v in pl:
        if v in vs:
            if v in var.DYING:
                continue
            for g in get_all_players(("guardian angel",)):
                if GUARDED.get(g.nick) == v.nick:
                    evt.data["numkills"][v] -= 1
                    if evt.data["numkills"][v] >= 0:
                        evt.data["killers"][v].pop(0)
                    if evt.data["numkills"][v] <= 0 and v not in evt.data["protected"]:
                        evt.data["protected"][v] = "angel"
                    elif evt.data["numkills"][v] <= 0:
                        var.ACTIVE_PROTECTIONS[v.nick].append("angel")
            for g in get_all_players(("bodyguard",)):
                if GUARDED.get(g.nick) == v.nick:
                    evt.data["numkills"][v] -= 1
                    if evt.data["numkills"][v] >= 0:
                        evt.data["killers"][v].pop(0)
                    if evt.data["numkills"][v] <= 0 and v not in evt.data["protected"]:
                        evt.data["protected"][v] = "bodyguard"
                    elif evt.data["numkills"][v] <= 0:
                        var.ACTIVE_PROTECTIONS[v.nick].append("bodyguard")
        else:
            for g in var.ROLES["guardian angel"]:
                if GUARDED.get(g.nick) == v.nick:
                    var.ACTIVE_PROTECTIONS[v.nick].append("angel")
            for g in var.ROLES["bodyguard"]:
                if GUARDED.get(g.nick) == v.nick:
                    var.ACTIVE_PROTECTIONS[v.nick].append("bodyguard")

@event_listener("fallen_angel_guard_break")
def on_fagb(evt, var, user, killer):
    for g in get_all_players(("guardian angel",)):
        if GUARDED.get(g.nick) == user.nick:
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
    for g in get_all_players(("bodyguard",)):
        if GUARDED.get(g.nick) == user.nick:
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
        evt.data["message"].append(messages["angel_protection"].format(victim))
        evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True
    elif evt.data["protected"].get(victim) == "bodyguard":
        for bodyguard in get_all_players(("bodyguard",)):
            if GUARDED.get(bodyguard.nick) == victim.nick:
                evt.data["dead"].append(bodyguard)
                evt.data["message"].append(messages["bodyguard_protection"].format(bodyguard))
                evt.data["novictmsg"] = False
                evt.stop_processing = True
                evt.prevent_default = True
                break

@event_listener("transition_day_resolve_end")
def on_transition_day_resolve_end(evt, var, victims):
    for bodyguard in get_all_players(("bodyguard",)):
        if GUARDED.get(bodyguard.nick) in list_players(var.WOLF_ROLES) and bodyguard not in evt.data["dead"] and bodyguard not in evt.data["bitten"]:
            r = random.random()
            if r < var.BODYGUARD_DIES_CHANCE:
                evt.data["bywolves"].add(bodyguard)
                evt.data["onlybywolves"].add(bodyguard)
                if var.ROLE_REVEAL == "on":
                    evt.data["message"].append(messages["bodyguard_protected_wolf"].format(bodyguard))
                else: # off and team
                    evt.data["message"].append(messages["bodyguard_protection"].format(bodyguard))
                evt.data["dead"].append(bodyguard)
    for gangel in get_all_players(("guardian angel",)):
        if GUARDED.get(gangel.nick) in list_players(var.WOLF_ROLES) and gangel not in evt.data["dead"] and gangel not in evt.data["bitten"]:
            r = random.random()
            if r < var.GUARDIAN_ANGEL_DIES_CHANCE:
                evt.data["bywolves"].add(gangel)
                evt.data["onlybywolves"].add(gangel)
                if var.ROLE_REVEAL == "on":
                    evt.data["message"].append(messages["guardian_angel_protected_wolf"].format(gangel))
                else: # off and team
                    evt.data["message"].append(messages["guardian_angel_protected_wolf_no_reveal"].format(gangel))
                evt.data["dead"].append(gangel)

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
        bg.send(messages[to_send].format(warning), "Players: " + ", ".join(p.nick for p in pl), sep="\n")

    for gangel in get_all_players(("guardian angel",)):
        pl = ps[:]
        random.shuffle(pl)
        gself = messages["guardian_self_notification"]
        if not var.GUARDIAN_ANGEL_CAN_GUARD_SELF:
            pl.remove(gangel)
            gself = ""
        if gangel.nick in LASTGUARDED:
            user = users._get(LASTGUARDED[gangel.nick]) # FIXME
            if user in pl:
                pl.remove(user)
        chance = math.floor(var.GUARDIAN_ANGEL_DIES_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = messages["bodyguard_death_chance"].format(chance)

        to_send = "guardian_notify"
        if gangel.prefers_simple():
            to_send = "guardian_simple"
        gangel.send(messages[to_send].format(warning, gself), "Players: " + ", ".join(p.nick for p in pl), sep="\n")

@event_listener("assassinate")
def on_assassinate(evt, var, killer, target, prot):
    if prot == "angel" and var.GAMEPHASE == "night":
        var.ACTIVE_PROTECTIONS[target.nick].remove("angel")
        evt.prevent_default = True
        evt.stop_processing = True
        channels.Main.send(messages[evt.params.message_prefix + "angel"].format(killer, target))
    elif prot == "bodyguard":
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
    # clear out LASTGUARDED for people that didn't guard last night
    for g in list(LASTGUARDED.keys()):
        if g not in GUARDED:
            del LASTGUARDED[g]

@event_listener("reset")
def on_reset(evt, var):
    GUARDED.clear()
    LASTGUARDED.clear()
    PASSED.clear()

# vim: set sw=4 expandtab:
