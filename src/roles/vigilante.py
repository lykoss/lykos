import re
import random
from collections import defaultdict

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

KILLS = UserDict() # type: Dict[users.User, users.User]
PASSED = UserSet() # type: Set[users.User]

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("vigilante",))
def vigilante_kill(var, wrapper, message):
    """Kill someone at night, but you die too if they aren't a wolf or win stealer!"""

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_suicide")

    orig = target
    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    evt.dispatch(var, wrapper.source, target)
    if evt.prevent_default:
        return
    target = evt.data["target"]

    KILLS[wrapper.source] = target
    PASSED.discard(wrapper.source)

    wrapper.send(messages["player_kill"].format(orig))
    debuglog("{0} (vigilante) KILL: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("vigilante",))
def vigilante_retract(var, wrapper, message):
    """Removes a vigilante's kill selection."""
    if wrapper.source not in KILLS and wrapper.source not in PASSED:
        return

    del KILLS[:wrapper.source:]
    PASSED.discard(wrapper.source)

    wrapper.send(messages["retracted_kill"])
    debuglog("{0} (vigilante) RETRACT".format(wrapper.source))

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("vigilante",))
def vigilante_pass(var, wrapper, message):
    """Do not kill anyone tonight as a vigilante."""
    del KILLS[:wrapper.source:]
    PASSED.add(wrapper.source)
    wrapper.send(messages["hunter_pass"])

    debuglog("{0} (vigilante) PASS".format(wrapper.source))

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    PASSED.discard(user)
    del KILLS[:user:]
    for vigilante, target in list(KILLS.items()):
        if target is user:
            vigilante.send(messages["hunter_discard"])
            del KILLS[vigilante]

@event_listener("night_acted")
def on_acted(evt, var, target, spy):
    if target in KILLS:
        evt.data["acted"] = True

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    for vigilante, target in list(KILLS.items()):
        evt.data["victims"].append(target)
        evt.data["onlybywolves"].discard(target)
        evt.data["killers"][target].append(vigilante)
        # important, otherwise our del_player listener lets hunter kill again
        del KILLS[vigilante]

        if get_main_role(target) not in var.WOLF_ROLES | var.WIN_STEALER_ROLES:
            var.DYING.add(vigilante)

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "vigilante":
        del KILLS[:user:]
        PASSED.discard(user)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(KILLS) + len(PASSED)
    evt.data["nightroles"].extend(get_all_players(("vigilante",)))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = get_players()
    for vigilante in get_all_players(("vigilante",)):
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(vigilante)
        to_send = "vigilante_notify"
        if vigilante.prefers_simple():
            to_send = "vigilante_simple"
        vigilante.send(messages[to_send], messages["players_list"].format(", ".join(p.nick for p in pl)), sep="\n")

@event_listener("begin_day")
def on_begin_day(evt, var):
    KILLS.clear()
    PASSED.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        evt.data["vigilante"] = len(var.ROLES["vigilante"])
    elif kind == "role_categories":
        evt.data["vigilante"] = {"village", "safe"}

# vim: set sw=4 expandtab:
