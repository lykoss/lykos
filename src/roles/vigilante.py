import re
import random
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.decorators import command, event_listener
from src.messages import messages
from src.events import Event

KILLS = {} # type: Dict[users.User, users.User]
PASSED = set() # type: Set[users.User]

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("vigilante",))
def vigilante_kill(var, wrapper, message):
    """Kill someone at night, but you die too if they aren't a wolf or win stealer!"""

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_suicide")

    orig = target
    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    evt.dispatch(var, "kill", wrapper.source, target, frozenset({"detrimental"}))
    if evt.prevent_default:
        return
    target = evt.data["target"]

    KILLS[wrapper.source] = target
    PASSED.discard(wrapper.source)

    wrapper.send(messages["player_kill"].format(orig))

    debuglog("{0} (vigilante) KILL: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

    chk_nightdone(wrapper.client)

@command("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("vigilante",))
def vigilante_retract(var, wrapper, message):
    """Removes a vigilante's kill selection."""
    if wrapper.source not in KILLS and wrapper.source not in PASSED:
        return

    KILLS.pop(wrapper.source, None)
    PASSED.discard(wrapper.source)
    wrapper.send(messages["retracted_kill"])

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("vigilante",))
def vigilante_pass(var, wrapper, message):
    """Do not kill anyone tonight as a vigilante."""
    KILLS.pop(wrapper.source, None)
    PASSED.add(wrapper.source)
    wrapper.send(messages["hunter_pass"])

    debuglog("{0} (vigilante) PASS".format(wrapper.source))
    chk_nightdone(wrapper.client)

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    PASSED.discard(user)
    KILLS.pop(user, None)
    for vigilante, target in list(KILLS.items()):
        if target is user:
            vigilante.send(messages["hunter_discard"])
            del KILLS[vigilante]

@event_listener("swap_player")
def on_swap(evt, var, old_user, user):
    for vigilante, target in set(KILLS.items()):
        if vigilante is old_user:
            KILLS[user] = KILLS.pop(vigilante)
        if target is old_user:
            KILLS[vigilante] = user

    if old_user in PASSED:
        PASSED.remove(old_user)
        PASSED.add(user)

@event_listener("night_acted")
def on_acted(evt, var, target, spy):
    if target in KILLS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("vigilante",)))

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

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    KILLS.pop(actor, None)
    KILLS.pop(target, None)
    PASSED.discard(actor)
    PASSED.discard(target)

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
        vigilante.send(messages[to_send], "Players: " + ", ".join(p.nick for p in pl), sep="\n")

@event_listener("succubus_visit")
def on_succubus_visit(evt, cli, var, nick, victim):
    for vigilante, target in set(KILLS.items()):
        if vigilante.nick == victim:
            if target in var.ROLES["succubus"]:
                vigilante.send(messages["no_kill_succubus"].format(target))
                del KILLS[vigilante]

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

# vim: set sw=4 expandtab:
