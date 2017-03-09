import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
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
    # self-guard ignores luck/misdirection/exchange totem
    evt = Event("targeted_command", {"target": victim, "misdirection": victim != nick, "exchange": victim != nick})
    if not evt.dispatch(cli, var, "guard", nick, victim, frozenset({"beneficial"})):
        return
    victim = evt.data["target"]
    GUARDED[nick] = victim
    LASTGUARDED[nick] = victim
    if victim == nick:
        pm(cli, nick, messages["guardian_guard_self"])
    else:
        pm(cli, nick, messages["protecting_target"].format(GUARDED[nick]))
        pm(cli, victim, messages["target_protected"])
    debuglog("{0} ({1}) GUARD: {2} ({3})".format(nick, role, victim, get_role(victim)))
    chk_nightdone(cli)

@cmd("pass", chan=False, pm=True, playing=True, phases=("night",), roles=("bodyguard", "guardian angel"))
def pass_cmd(cli, nick, chan, rest):
    """Decline to use your special power for that night."""
    if nick in GUARDED:
        pm(cli, nick, messages["already_protecting"])
        return
    PASSED.add(nick)
    pm(cli, nick, messages["guardian_no_protect"])
    debuglog("{0} ({1}) PASS".format(nick, get_role(nick)))
    chk_nightdone(cli)

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
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
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    if var.PHASE == "night" and nick in GUARDED:
        pm(cli, GUARDED[nick], messages["protector_disappeared"])
    for dictvar in (GUARDED, LASTGUARDED):
        for k,v in list(dictvar.items()):
            if nick in (k, v):
                del dictvar[k]
    if nick in PASSED:
        PASSED.discard(nick)

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in GUARDED:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(list_players(("guardian angel", "bodyguard")))

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    if actor_role in ("bodyguard", "guardian angel"):
        if actor in GUARDED:
            pm(cli, GUARDED.pop(actor), messages["protector disappeared"])
        if actor in LASTGUARDED:
            del LASTGUARDED[actor]
    if nick_role in ("bodyguard", "guardian angel"):
        if nick in GUARDED:
            pm(cli, GUARDED.pop(nick), messages["protector disappeared"])
        if nick in LASTGUARDED:
            del LASTGUARDED[nick]

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    evt.data["actedcount"] += len(GUARDED) + len(PASSED)
    evt.data["nightroles"].extend(list_players(("guardian angel", "bodyguard")))

@event_listener("transition_day", priority=4.2)
def on_transition_day(evt, cli, var):
    pl = list_players()
    vs = set(evt.data["victims"])
    for v in pl:
        if v in vs:
            if v in var.DYING:
                continue
            for g in var.ROLES["guardian angel"]:
                if GUARDED.get(g) == v:
                    evt.data["numkills"][v] -= 1
                    if evt.data["numkills"][v] >= 0:
                        evt.data["killers"][v].pop(0)
                    if evt.data["numkills"][v] <= 0 and v not in evt.data["protected"]:
                        evt.data["protected"][v] = "angel"
                    elif evt.data["numkills"][v] <= 0:
                        var.ACTIVE_PROTECTIONS[v].append("angel")
            for g in var.ROLES["bodyguard"]:
                if GUARDED.get(g) == v:
                    evt.data["numkills"][v] -= 1
                    if evt.data["numkills"][v] >= 0:
                        evt.data["killers"][v].pop(0)
                    if evt.data["numkills"][v] <= 0 and v not in evt.data["protected"]:
                        evt.data["protected"][v] = "bodyguard"
                    elif evt.data["numkills"][v] <= 0:
                        var.ACTIVE_PROTECTIONS[v].append("bodyguard")
        else:
            for g in var.ROLES["guardian angel"]:
                if GUARDED.get(g) == v:
                    var.ACTIVE_PROTECTIONS[v].append("angel")
            for g in var.ROLES["bodyguard"]:
                if GUARDED.get(g) == v:
                    var.ACTIVE_PROTECTIONS[v].append("bodyguard")

@event_listener("fallen_angel_guard_break")
def on_fagb(evt, cli, var, victim, killer):
    for g in var.ROLES["guardian angel"]:
        if GUARDED.get(g) == victim:
            if random.random() < var.FALLEN_ANGEL_KILLS_GUARDIAN_ANGEL_CHANCE:
                if g in evt.data["protected"]:
                    del evt.data["protected"][g]
                evt.data["bywolves"].add(g)
                if g not in evt.data["victims"]:
                    evt.data["onlybywolves"].add(g)
                evt.data["victims"].append(g)
                evt.data["killers"][g].append(killer)
            if g != victim:
                pm(cli, g, messages["fallen_angel_success"].format(victim))
    for g in var.ROLES["bodyguard"]:
        if GUARDED.get(g) == victim:
            if g in evt.data["protected"]:
                del evt.data["protected"][g]
            evt.data["bywolves"].add(g)
            if g not in evt.data["victims"]:
                evt.data["onlybywolves"].add(g)
            evt.data["victims"].append(g)
            evt.data["killers"][g].append(killer)
            if g != victim:
                pm(cli, g, messages["fallen_angel_success"].format(victim))

@event_listener("transition_day_resolve", priority=2)
def on_transition_day_resolve(evt, cli, var, victim):
    if evt.data["protected"].get(victim) == "angel":
        evt.data["message"].append(messages["angel_protection"].format(victim))
        evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True
    elif evt.data["protected"].get(victim) == "bodyguard":
        for bodyguard in var.ROLES["bodyguard"]:
            if GUARDED.get(bodyguard) == victim:
                evt.data["dead"].append(bodyguard)
                evt.data["message"].append(messages["bodyguard_protection"].format(bodyguard))
                evt.data["novictmsg"] = False
                evt.stop_processing = True
                evt.prevent_default = True
                break

@event_listener("transition_day_resolve_end")
def on_transition_day_resolve_end(evt, cli, var, victims):
    for bodyguard in var.ROLES["bodyguard"]:
        if GUARDED.get(bodyguard) in list_players(var.WOLF_ROLES) and bodyguard not in evt.data["dead"] and bodyguard not in evt.data["bitten"]:
            r = random.random()
            if r < var.BODYGUARD_DIES_CHANCE:
                evt.data["bywolves"].add(bodyguard)
                evt.data["onlybywolves"].add(bodyguard)
                if var.ROLE_REVEAL == "on":
                    evt.data["message"].append(messages["bodyguard_protected_wolf"].format(bodyguard))
                else: # off and team
                    evt.data["message"].append(messages["bodyguard_protection"].format(bodyguard))
                evt.data["dead"].append(bodyguard)
    for gangel in var.ROLES["guardian angel"]:
        if GUARDED.get(gangel) in list_players(var.WOLF_ROLES) and gangel not in evt.data["dead"] and gangel not in evt.data["bitten"]:
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
def on_transition_night_begin(evt, cli, var):
    # needs to be here in order to allow bodyguard protections to work during the daytime
    # (right now they don't due to other reasons, but that may change)
    GUARDED.clear()

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    # the messages for angel and guardian angel are different enough to merit individual loops
    ps = list_players()
    for bg in var.ROLES["bodyguard"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(bg)
        chance = math.floor(var.BODYGUARD_DIES_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = messages["bodyguard_death_chance"].format(chance)

        if bg in var.PLAYERS and not is_user_simple(bg):
            pm(cli, bg, messages["bodyguard_notify"].format(warning))
        else:
            pm(cli, bg, messages["bodyguard_simple"])  # !simple
        pm(cli, bg, "Players: " + ", ".join(pl))

    for gangel in var.ROLES["guardian angel"]:
        pl = ps[:]
        random.shuffle(pl)
        gself = messages["guardian_self_notification"]
        if not var.GUARDIAN_ANGEL_CAN_GUARD_SELF:
            pl.remove(gangel)
            gself = ""
        if LASTGUARDED.get(gangel) in pl:
            pl.remove(LASTGUARDED[gangel])
        chance = math.floor(var.GUARDIAN_ANGEL_DIES_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = messages["bodyguard_death_chance"].format(chance)

        if gangel in var.PLAYERS and not is_user_simple(gangel):
            pm(cli, gangel, messages["guardian_notify"].format(warning, gself))
        else:
            pm(cli, gangel, messages["guardian_simple"])  # !simple
        pm(cli, gangel, "Players: " + ", ".join(pl))

@event_listener("assassinate")
def on_assassinate(evt, cli, var, nick, target, prot):
    if prot == "angel" and var.GAMEPHASE == "night":
        var.ACTIVE_PROTECTIONS[target].remove("angel")
        evt.prevent_default = True
        evt.stop_processing = True
        cli.msg(botconfig.CHANNEL, messages[evt.params.message_prefix + "angel"].format(nick, target))
    elif prot == "bodyguard":
        var.ACTIVE_PROTECTIONS[target].remove("bodyguard")
        evt.prevent_default = True
        evt.stop_processing = True
        for bg in var.ROLES["bodyguard"]:
            if GUARDED.get(bg) == target:
                cli.msg(botconfig.CHANNEL, messages[evt.params.message_prefix + "bodyguard"].format(nick, target, bg))
                evt.params.del_player(cli, bg, True, end_game=False, killer_role=evt.params.nickrole, deadlist=evt.params.deadlist, original=evt.params.original, ismain=False)
                evt.data["pl"] = evt.params.refresh_pl(evt.data["pl"])
                break

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
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
