import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import Event
from src.cats import Wolf, Wolfchat

VISITED = UserDict() # type: Dict[users.User, users.User]
PASSED = UserSet() # type: Set[users.User]

@command("visit", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("harlot",))
def hvisit(var, wrapper, message):
    """Visit a player. You will die if you visit a wolf or a target of the wolves."""

    if VISITED.get(wrapper.source):
        wrapper.pm(messages["harlot_already_visited"].format(VISITED[wrapper.source]))
        return
    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="harlot_not_self")
    if not target:
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    vrole = get_main_role(target)

    VISITED[wrapper.source] = target
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["harlot_success"].format(target))
    if target is not wrapper.source:
        target.send(messages["harlot_success"].format(wrapper.source))
        revt = Event("harlot_visit", {})
        revt.dispatch(var, wrapper.source, target)

    debuglog("{0} (harlot) VISIT: {1} ({2})".format(wrapper.source, target, vrole))

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("harlot",))
def pass_cmd(var, wrapper, message):
    """Do not visit someone tonight."""
    if VISITED.get(wrapper.source):
        wrapper.pm(messages["harlot_already_visited"].format(VISITED[wrapper.source]))
        return
    PASSED.add(wrapper.source)
    wrapper.pm(messages["no_visit"])
    debuglog("{0} (harlot) PASS".format(wrapper.source))

@event_listener("transition_day_resolve", priority=1)
def on_transition_day_resolve(evt, var, victim):
    if victim in var.ROLES["harlot"] and VISITED.get(victim) and victim not in evt.data["dead"] and evt.data["killers"][victim] == ["@wolves"]:
        evt.data["message"][victim].append(messages["target_not_home"])
        evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_day_resolve_end", priority=1)
def on_transition_day_resolve_end(evt, var, victims):
    for victim in victims:
        if victim in evt.data["dead"] and victim in VISITED.values() and "@wolves" in evt.data["killers"][victim]:
            for hlt in VISITED:
                if VISITED[hlt] is victim and hlt not in evt.data["dead"]:
                    if var.ROLE_REVEAL in ("on", "team"):
                        evt.data["message"][hlt].append(messages["visited_victim"].format(hlt, get_reveal_role(hlt)))
                    else:
                        evt.data["message"][hlt].append(messages["visited_victim_noreveal"].format(hlt))
                    evt.data["dead"].append(hlt)

@event_listener("transition_day_resolve_end", priority=3)
def on_transition_day_resolve_end3(evt, var, victims):
    for harlot in get_all_players(("harlot",)):
        if VISITED.get(harlot) in get_players(Wolf) and harlot not in evt.data["dead"]:
            evt.data["message"][harlot].append(messages["harlot_visited_wolf"].format(harlot))
            evt.data["dead"].append(harlot)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(VISITED) + len(PASSED)
    evt.data["nightroles"].extend(get_all_players(("harlot",)))

@event_listener("new_role")
def on_new_role(evt, var, player, old_role):
    if old_role == "harlot" and evt.data["role"] != "harlot":
        PASSED.discard(player)
        if player in VISITED:
            VISITED.pop(player).send(messages["harlot_disappeared"].format(player))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    for harlot in get_all_players(("harlot",)):
        pl = get_players()
        random.shuffle(pl)
        pl.remove(harlot)
        to_send = "harlot_info"
        if harlot.prefers_simple():
            to_send = "harlot_simple"
        harlot.send(messages[to_send], messages["players_list"].format(", ".join(p.nick for p in pl)), sep="\n")

@event_listener("begin_day")
def on_begin_day(evt, var):
    VISITED.clear()
    PASSED.clear()

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    if "harlot" not in all_roles:
        return
    del VISITED[:player:]
    PASSED.discard(player)

@event_listener("reset")
def on_reset(evt, var):
    VISITED.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["harlot"] = {"Village", "Safe", "Nocturnal"}
    elif kind == "lycanthropy_role":
        evt.data["harlot"] = {"prefix": "harlot"}

# vim: set sw=4 expandtab:
