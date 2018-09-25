import re
import random
import itertools
import math
from collections import defaultdict, deque

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.status import try_protection, add_dying

TARGETED = UserDict() # type: Dict[users.User, users.User]
PREV_ACTED = UserSet()

@command("target", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("assassin",))
def target(var, wrapper, message):
    """Pick a player as your target, killing them if you die."""
    if wrapper.source in PREV_ACTED:
        wrapper.send(messages["assassin_already_targeted"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0])
    if not target:
        return

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    if not evt.dispatch(var, wrapper.source, target):
        return
    target = evt.data["target"]

    TARGETED[wrapper.source] = target

    wrapper.send(messages["assassin_target_success"].format(target))

    debuglog("{0} (assassin) TARGET: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["nightroles"].extend(get_all_players(("assassin",)) - PREV_ACTED)
    evt.data["actedcount"] += len(TARGETED) - len(PREV_ACTED)

@event_listener("transition_day", priority=7)
def on_transition_day(evt, var):
    # Select a random target for assassin that isn't already going to die if they didn't target
    pl = get_players()
    for ass in get_all_players(("assassin",)):
        if ass not in TARGETED and ass.nick not in var.SILENCED:
            ps = pl[:]
            ps.remove(ass)
            for victim in set(evt.data["victims"]):
                if victim in ps:
                    ps.remove(victim)
            if len(ps) > 0:
                target = random.choice(ps)
                TARGETED[ass] = target
                ass.send(messages["assassin_random"].format(target))
    PREV_ACTED.update(TARGETED.keys())

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    for ass in get_all_players(("assassin",)):
        if ass in TARGETED:
            continue # someone already targeted

        pl = get_players()
        random.shuffle(pl)
        pl.remove(ass)

        if ass in get_all_players(("village drunk",)): # FIXME: Make into an event when village drunk is split
            TARGETED[ass] = random.choice(pl)
            PREV_ACTED.add(ass)
            message = messages["drunken_assassin_notification"].format(TARGETED[ass])
            if not ass.prefers_simple():
                message += messages["assassin_info"]
            ass.send(message)

        else:
            if ass.prefers_simple():
                ass.send(messages["assassin_simple"])
            else:
                ass.send(messages["assassin_notify"])
            ass.send(messages["players_list"].format(", ".join(p.nick for p in pl)))

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    if player in TARGETED.values():
        for x, y in list(TARGETED.items()):
            if y is player:
                del TARGETED[x]
                PREV_ACTED.discard(x)

    if death_triggers and "assassin" in all_roles and player in TARGETED:
        target = TARGETED[player]
        del TARGETED[player]
        PREV_ACTED.discard(player)
        if target in get_players():
            protected = try_protection(var, target, player, "assassin", "assassin_fail")
            if protected is not None:
                channels.Main.send(*protected)
                return
            if var.ROLE_REVEAL in ("on", "team"):
                role = get_reveal_role(target)
                an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                message = messages["assassin_success"].format(player, target, an, role)
            else:
                message = messages["assassin_success_no_reveal"].format(player, target)
            channels.Main.send(message)
            debuglog("{0} (assassin) ASSASSINATE: {1} ({2})".format(player, target, get_main_role(target)))
            add_dying(var, target, killer_role=evt.params.main_role, reason="assassin")

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in get_all_players(("assassin",)):
        msg = ""
        if user in TARGETED:
            msg = messages["assassin_targeting"].format(TARGETED[user])
        user.send(messages["assassin_role_info"].format(msg))

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "assassin" and user in TARGETED:
        evt.data["special_case"].append("targeting {0}".format(TARGETED[user]))

@event_listener("reset")
def on_reset(evt, var):
    TARGETED.clear()
    PREV_ACTED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["assassin"] = {"Village"}

# vim: set sw=4 expandtab:
