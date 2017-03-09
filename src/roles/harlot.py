import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

VISITED = {}

@cmd("visit", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("harlot",))
def hvisit(cli, nick, chan, rest):
    """Visit a player. You will die if you visit a wolf or a target of the wolves."""

    if VISITED.get(nick):
        pm(cli, nick, messages["harlot_already_visited"].format(VISITED[nick]))
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, True)
    if not victim:
        return

    if nick == victim:
        pm(cli, nick, messages["harlot_not_self"])
        return

    evt = Event("targeted_command", {"target": victim, "misdirection": True, "exchange": True})
    evt.dispatch(cli, var, "visit", nick, victim, frozenset({"immediate"}))
    if evt.prevent_default:
        return
    victim = evt.data["target"]
    vrole = get_role(victim)

    VISITED[nick] = victim
    pm(cli, nick, messages["harlot_success"].format(victim))
    if nick != victim:
        pm(cli, victim, messages["harlot_success"].format(nick))
        revt = Event("harlot_visit", {})
        revt.dispatch(cli, var, nick, victim)

    debuglog("{0} ({1}) VISIT: {2} ({3})".format(nick, get_role(nick), victim, vrole))
    chk_nightdone(cli)

@cmd("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("harlot",))
def pass_cmd(cli, nick, chan, rest):
    """Do not visit someone tonight."""
    if VISITED.get(nick):
        pm(cli, nick, messages["harlot_already_visited"].format(VISITED[nick]))
        return
    VISITED[nick] = None
    pm(cli, nick, messages["no_visit"])
    debuglog("{0} ({1}) PASS".format(nick, get_role(nick)))
    chk_nightdone(cli)

@event_listener("bite")
def on_bite(evt, cli, var, alpha, target):
    if target not in var.ROLES["harlot"]:
        return
    hvisit = VISITED.get(target)
    if hvisit and get_role(hvisit) not in var.WOLFCHAT_ROLES and (hvisit not in evt.param.bywolves or hvisit in evt.param.protected):
        evt.data["can_bite"] = False

@event_listener("transition_day_resolve", priority=1)
def on_transition_day_resolve(evt, cli, var, victim):
    if victim in var.ROLES["harlot"] and VISITED.get(victim) and victim not in evt.data["dead"] and victim in evt.data["onlybywolves"]:
        if victim not in evt.data["bitten"]:
            evt.data["message"].append(messages["target_not_home"])
            evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_day_resolve_end", priority=1)
def on_transition_day_resolve_end(evt, cli, var, victims):
    for victim in victims + evt.data["bitten"]:
        if victim in evt.data["dead"] and victim in VISITED.values() and (victim in evt.data["bywolves"] or victim in evt.data["bitten"]):
            for hlt in VISITED:
                if VISITED[hlt] == victim and hlt not in evt.data["bitten"] and hlt not in evt.data["dead"]:
                    if var.ROLE_REVEAL in ("on", "team"):
                        evt.data["message"].append(messages["visited_victim"].format(hlt, get_reveal_role(hlt)))
                    else:
                        evt.data["message"].append(messages["visited_victim_noreveal"].format(hlt))
                    evt.data["bywolves"].add(hlt)
                    evt.data["onlybywolves"].add(hlt)
                    evt.data["dead"].append(hlt)

@event_listener("transition_day_resolve_end", priority=3)
def on_transition_day_resolve_end3(evt, cli, var, victims):
    for harlot in var.ROLES["harlot"]:
        if VISITED.get(harlot) in list_players(var.WOLF_ROLES) and harlot not in evt.data["dead"] and harlot not in evt.data["bitten"]:
            evt.data["message"].append(messages["harlot_visited_wolf"].format(harlot))
            evt.data["bywolves"].add(harlot)
            evt.data["onlybywolves"].add(harlot)
            evt.data["dead"].append(harlot)

@event_listener("night_acted")
def on_night_acted(evt, cli, var, nick, sender):
    if VISITED.get(nick):
        evt.data["acted"] = True

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    evt.data["actedcount"] += len(VISITED)
    evt.data["nightroles"].extend(var.ROLES["harlot"])

@event_listener("exchange_roles")
def on_exchange_roles(evt, cli, var, actor, nick, actor_role, nick_role):
    if actor_role == "harlot":
        if actor in VISITED:
            if VISITED[actor] is not None:
                pm(cli, VISITED[actor], messages["harlot_disappeared"].format(actor))
            del VISITED[actor]
    if nick_role == "harlot":
        if nick in VISITED:
            if VISITED[nick] is not None:
                pm(cli, VISITED[nick], messages["harlot_disappeared"].format(nick))
            del VISITED[nick]

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    for harlot in var.ROLES["harlot"]:
        pl = list_players()
        random.shuffle(pl)
        pl.remove(harlot)
        if harlot in var.PLAYERS and not is_user_simple(harlot):
            pm(cli, harlot, messages["harlot_info"])
        else:
            pm(cli, harlot, messages["harlot_simple"])
        pm(cli, harlot, "Players: " + ", ".join(pl))

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    VISITED.clear()

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(var.ROLES["harlot"])

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    if nickrole != "harlot":
        return
    if nick in VISITED:
        del VISITED[nick]

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    kvp = {}
    for a,b in VISITED.items():
        s = nick if a == prefix else a
        t = nick if b == prefix else b
        kvp[s] = t
    VISITED.update(kvp)
    if prefix in VISITED:
        del VISITED[prefix]

@event_listener("reset")
def on_reset(evt, var):
    VISITED.clear()

# vim: set sw=4 expandtab:
