import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role
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
def on_bite(evt, var, alpha, target):
    if target.nick not in var.ROLES["harlot"] or target.nick not in VISITED:
        return
    hvisit = VISITED[target.nick]
    if hvisit is not None:
        visited = users._get(hvisit) # FIXME
        if get_main_role(visited) not in var.WOLFCHAT_ROLES and (visited not in evt.params.bywolves or visited in evt.params.protected):
            evt.data["can_bite"] = False

@event_listener("transition_day_resolve", priority=1)
def on_transition_day_resolve(evt, var, victim):
    if victim.nick in var.ROLES["harlot"] and VISITED.get(victim.nick) and victim not in evt.data["dead"] and victim in evt.data["onlybywolves"]:
        if victim not in evt.data["bitten"]:
            evt.data["message"].append(messages["target_not_home"])
            evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_day_resolve_end", priority=1)
def on_transition_day_resolve_end(evt, var, victims):
    for victim in victims + evt.data["bitten"]:
        if victim in evt.data["dead"] and victim.nick in VISITED.values() and (victim in evt.data["bywolves"] or victim in evt.data["bitten"]):
            for hlt in VISITED:
                user = users._get(hlt) # FIXME
                if VISITED[hlt] == victim.nick and user not in evt.data["bitten"] and user not in evt.data["dead"]:
                    if var.ROLE_REVEAL in ("on", "team"):
                        evt.data["message"].append(messages["visited_victim"].format(hlt, get_reveal_role(hlt)))
                    else:
                        evt.data["message"].append(messages["visited_victim_noreveal"].format(hlt))
                    evt.data["bywolves"].add(user)
                    evt.data["onlybywolves"].add(user)
                    evt.data["dead"].append(user)

@event_listener("transition_day_resolve_end", priority=3)
def on_transition_day_resolve_end3(evt, var, victims):
    for harlot in get_all_players(("harlot",)):
        if VISITED.get(harlot.nick) in list_players(var.WOLF_ROLES) and harlot not in evt.data["dead"] and harlot not in evt.data["bitten"]:
            evt.data["message"].append(messages["harlot_visited_wolf"].format(harlot))
            evt.data["bywolves"].add(harlot)
            evt.data["onlybywolves"].add(harlot)
            evt.data["dead"].append(harlot)

@event_listener("night_acted")
def on_night_acted(evt, var, user, actor):
    if VISITED.get(user.nick):
        evt.data["acted"] = True

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(VISITED)
    evt.data["nightroles"].extend(get_all_players(("harlot",)))

@event_listener("exchange_roles")
def on_exchange_roles(evt, var, user, target, user_role, target_role):
    if user_role == "harlot":
        if user.nick in VISITED:
            if VISITED[user.nick] is not None:
                visited = users._get(VISITED[user.nick]) # FIXME
                visited.send(messages["harlot_disappeared"].format(user))
            del VISITED[user.nick]
    if target_role == "harlot":
        if target.nick in VISITED:
            if VISITED[target.nick] is not None:
                visited = users._get(VISITED[target.nick]) # FIXME
                visited.send(messages["harlot_disappeared"].format(target))
            del VISITED[target.nick]

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    for harlot in get_all_players(("harlot",)):
        pl = get_players()
        random.shuffle(pl)
        pl.remove(harlot)
        to_send = "harlot_info"
        if harlot.prefers_simple():
            to_send = "harlot_simple"
        harlot.send(messages[to_send], "Players: " + ", ".join(p.nick for p in pl), sep="\n")

@event_listener("begin_day")
def on_begin_day(evt, var):
    VISITED.clear()

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("harlot",)))

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    if "harlot" not in allroles:
        return
    VISITED.pop(user.nick, None)

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
