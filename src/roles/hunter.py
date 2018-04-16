import re
import random
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_target, get_main_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

KILLS = UserDict() # type: Dict[users.User, users.User]
HUNTERS = UserSet()
PASSED = UserSet()

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hunter",))
def hunter_kill(var, wrapper, message):
    """Kill someone once per game."""
    if wrapper.source in HUNTERS and wrapper.source not in KILLS:
        wrapper.pm(messages["hunter_already_killed"])
        return
    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
    if not target:
        return

    orig = target
    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    evt.dispatch(var, "kill", wrapper.source, target, frozenset({"detrimental"}))
    if evt.prevent_default:
        return

    target = evt.data["target"]

    KILLS[wrapper.source] = target
    HUNTERS.add(wrapper.source)
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["player_kill"].format(orig))

    debuglog("{0} (hunter) KILL: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

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

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    HUNTERS.discard(user)
    PASSED.discard(user)
    KILLS.pop(user, None)
    for h, v in list(KILLS.items()):
        if v is user:
            HUNTERS.discard(h)
            h.send(messages["hunter_discard"])
            del KILLS[h]

@event_listener("night_acted")
def on_acted(evt, var, user, actor):
    if user in KILLS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("hunter",)))

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    for k, d in list(KILLS.items()):
        evt.data["victims"].append(d)
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d].append(k)
        # important, otherwise our del_player listener lets hunter kill again
        del KILLS[k]

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    KILLS.pop(actor, None)
    KILLS.pop(target, None)
    HUNTERS.discard(actor)
    HUNTERS.discard(target)
    PASSED.discard(actor)
    PASSED.discard(target)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(KILLS) + len(PASSED)
    hunter_users = get_all_players(("hunter",))
    evt.data["nightroles"].extend([p for p in hunter_users if p not in HUNTERS or p in KILLS])

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = get_players()
    for hunter in get_all_players(("hunter",)):
        if hunter in HUNTERS:
            continue # already killed
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(hunter)
        to_send = "hunter_notify"
        if hunter.prefers_simple():
            to_send = "hunter_simple"
        hunter.send(messages[to_send], "Players: " + ", ".join(p.nick for p in pl), sep="\n")

@event_listener("succubus_visit")
def on_succubus_visit(evt, var, succubus, target):
    if target in KILLS and KILLS[target] in get_all_players(("succubus",)):
        target.send(messages["no_kill_succubus"].format(KILLS[target]))
        del KILLS[target]
        HUNTERS.discard(target)

@event_listener("begin_day")
def on_begin_day(evt, var):
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
        hunters = (var.ROLES["hunter"] - HUNTERS) | set(KILLS.keys())
        evt.data["hunter"] = len(hunters)

# vim: set sw=4 expandtab:
