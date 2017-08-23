import re
import random
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src import users, debuglog, errlog, plog
from src.functions import get_players, get_target
from src.decorators import command, event_listener
from src.messages import messages
from src.events import Event

KILLS = {} # type: Dict[users.User, users.User]
HUNTERS = set()
PASSED = set()

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hunter",))
def hunter_kill(var, wrapper, message):
    """Kill someone once per game."""
    if wrapper.source in HUNTERS and wrapper.source not in KILLS:
        wrapper.pm(messages["hunter_already_killed"])
        return
    target = get_target(var, wrapper, re.split(" +", message)[0])
    if not target:
        return

    if wrapper.source is target:
        wrapper.pm(messages["no_suicide"])
        return

    orig = target
    evt = Event("targeted_command", {"target": target.nick, "misdirection": True, "exchange": True})
    evt.dispatch(wrapper.client, var, "kill", wrapper.source.nick, target.nick, frozenset({"detrimental"}))
    if evt.prevent_default:
        return

    target = users._get(evt.data["target"]) # FIXME: Need to fix once targeted_command uses the new API

    KILLS[wrapper.source] = target
    HUNTERS.add(wrapper.source)
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["player_kill"].format(orig))

    debuglog("{0} (hunter) KILL: {1} ({2})".format(wrapper.source, target, get_role(target.nick)))
    chk_nightdone(wrapper.client)

@command("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("hunter",))
def hunter_retract(var, wrapper, message):
    """Removes a hunter's kill selection."""
    if wrapper.source not in KILLS and wrapper.source not in PASSED:
        return
    KILLS.pop(wrapper.source, None)
    HUNTERS.discard(wrapper.source)
    PASSED.discard(wrapper.source)
    wrapper.pm(messages["retracted_kill"])

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hunter",))
def hunter_pass(var, wrapper, message):
    """Do not use hunter's once-per-game kill tonight."""
    if wrapper.source in HUNTERS and wrapper.source not in KILLS:
        wrapper.pm(messages["hunter_already_killed"])
        return
    KILLS.pop(wrapper.source, None)
    HUNTERS.discard(wrapper.source)
    PASSED.add(wrapper.source)
    wrapper.pm(messages["hunter_pass"])

    debuglog("{0} (hunter) PASS".format(wrapper.source))
    chk_nightdone(wrapper.client)

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, mainrole, allroles, death_triggers):
    user = users._get(nick) # FIXME
    HUNTERS.discard(user)
    PASSED.discard(user)
    KILLS.pop(user, None)
    for h, v in list(KILLS.items()):
        if v is user:
            HUNTERS.discard(h)
            h.send(messages["hunter_discard"])
            del KILLS[h]

@event_listener("swap_player")
def on_swap(evt, var, old_user, user):
    for a, b in list(KILLS.items()):
        if a is old_user:
            KILLS[user] = KILLS.pop(old_user)
        if b is old_user:
            KILLS[user] = KILLS.pop(old_user)
    if old_user in HUNTERS:
        HUNTERS.discard(old_user)
        HUNTERS.add(user)
    if old_user in PASSED:
        PASSED.discard(old_user)
        PASSED.add(user)

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if users._get(nick) in KILLS: # FIXME
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(var.ROLES["hunter"])

@event_listener("transition_day", priority=2)
def on_transition_day(evt, cli, var):
    for k, d in list(KILLS.items()):
        evt.data["victims"].append(d.nick)
        evt.data["onlybywolves"].discard(d.nick)
        evt.data["killers"][d].append(k.nick)
        # important, otherwise our del_player listener lets hunter kill again
        del KILLS[k]

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    user = users._get(actor) # FIXME
    target = users._get(nick) # FIXME
    KILLS.pop(user, None)
    KILLS.pop(target, None)
    HUNTERS.discard(user)
    HUNTERS.discard(target)
    PASSED.discard(user)
    PASSED.discard(target)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    evt.data["actedcount"] += len(KILLS) + len(PASSED)
    evt.data["nightroles"].extend([p for p in var.ROLES["hunter"] if users._get(p) not in (HUNTERS | KILLS.keys())]) # FIXME

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    ps = get_players()
    for hunter in var.ROLES["hunter"]:
        user = users._get(hunter) # FIXME
        if user in HUNTERS:
            continue # already killed
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(user)
        to_send = "hunter_notify"
        if user.prefers_simple():
            to_send = "hunter_simple"
        user.send(messages[to_send], "Players: " + ", ".join(p.nick for p in pl), sep="\n")

@event_listener("succubus_visit")
def on_succubus_visit(evt, cli, var, nick, victim):
    user = users._get(victim) # FIXME
    if user in KILLS and KILLS[user].nick in var.ROLES["succubus"]: # FIXME
        user.send(messages["no_kill_succubus"].format(KILLS[user]))
        del KILLS[user]
        HUNTERS.discard(user)

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    KILLS.clear()
    PASSED.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    PASSED.clear()
    HUNTERS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        # hunters is the set of all hunters that have not killed in a *previous* night
        # (if they're in both HUNTERS and KILLS, then they killed tonight and should be counted)
        hunters = ({users._get(h) for h in var.ROLES["hunter"]} - HUNTERS) | set(KILLS.keys()) # FIXME
        evt.data["hunter"] = len(hunters)

# vim: set sw=4 expandtab:
