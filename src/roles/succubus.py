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
from src.events import Event

ENTRANCED = UserSet() # type: Set[users.User]
VISITED = UserDict() # type: Dict[users.User, users.User]
PASSED = UserSet() # type: Set[users.User]
ALL_SUCC_IDLE = True

@command("visit", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("succubus",))
def hvisit(var, wrapper, message):
    """Entrance a player, converting them to your team."""
    if VISITED.get(wrapper.source):
        wrapper.send(messages["succubus_already_visited"].format(VISITED[wrapper.source]))
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="succubus_not_self")
    if not target:
        return

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    if not evt.dispatch(var, wrapper.source, target):
        return
    target = evt.data["target"]

    VISITED[wrapper.source] = target
    PASSED.discard(wrapper.source)

    if target not in get_all_players(("succubus",)):
        ENTRANCED.add(target)
        wrapper.send(messages["succubus_target_success"].format(target))
    else:
        wrapper.send(messages["harlot_success"].format(target))

    if wrapper.source is not target:
        if target not in get_all_players(("succubus",)):
            target.send(messages["notify_succubus_target"].format(wrapper.source))
        else:
            target.send(messages["harlot_success"].format(wrapper.source))

        revt = Event("succubus_visit", {})
        revt.dispatch(var, wrapper.source, target)

    debuglog("{0} (succubus) VISIT: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("succubus",))
def pass_cmd(var, wrapper, message):
    """Do not entrance someone tonight."""
    if VISITED.get(wrapper.source):
        wrapper.send(messages["succubus_already_visited"].format(VISITED[wrapper.source]))
        return

    PASSED.add(wrapper.source)
    wrapper.send(messages["succubus_pass"])
    debuglog("{0} (succubus) PASS".format(wrapper.source))

@event_listener("harlot_visit")
def on_harlot_visit(evt, var, harlot, victim):
    if victim in get_all_players(("succubus",)):
        harlot.send(messages["notify_succubus_target"].format(victim))
        victim.send(messages["succubus_harlot_success"].format(harlot))
        ENTRANCED.add(harlot)

# entranced logic should run after team wins have already been determined (aka run last)
@event_listener("player_win", priority=6)
def on_player_win(evt, var, user, role, winner, survived):
    if user in ENTRANCED:
        evt.data["special"].append("entranced")
        if winner != "succubi":
            evt.data["won"] = False
        else:
            evt.data["iwon"] = True
    if role == "succubus" and winner == "succubi":
        evt.data["won"] = True

@event_listener("chk_win", priority=2)
def on_chk_win(evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    lsuccubi = len(rolemap.get("succubus", ()))
    lentranced = len([x for x in ENTRANCED if x not in var.DEAD])
    if var.PHASE == "day" and lpl - lsuccubi == lentranced:
        evt.data["winner"] = "succubi"
        evt.data["message"] = messages["succubus_win"].format(plural("succubus", lsuccubi), plural("has", lsuccubi), plural("master's", lsuccubi))
    elif not lsuccubi and lentranced and var.PHASE == "day" and lpl == lentranced:
        evt.data["winner"] = "succubi"
        evt.data["message"] = messages["entranced_win"]

@event_listener("exchange_roles")
def on_exchange_roles(evt, var, actor, target, actor_role, target_role):
    del VISITED[:actor:]
    del VISITED[:target:]
    PASSED.discard(actor)
    PASSED.discard(target)

    if actor in ENTRANCED:
        ENTRANCED.remove(actor)
        actor.send(messages["no_longer_entranced"])
    if target in ENTRANCED:
        ENTRANCED.remove(target)
        target.send(messages["no_longer_entranced"])

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    global ALL_SUCC_IDLE
    if "succubus" not in all_roles:
        return
    if player in VISITED:
        # if it's night, also unentrance the person they visited
        if var.PHASE == "night" and var.GAMEPHASE == "night":
            if VISITED[player] in ENTRANCED:
                ENTRANCED.discard(VISITED[player])
                VISITED[player].send(messages["entranced_revert_win"])
        del VISITED[player]

    # if all succubi idled out (every last one of them), un-entrance people
    # death_triggers is False for an idle-out, so we use that to determine which it is
    if death_triggers:
        ALL_SUCC_IDLE = False
    if ALL_SUCC_IDLE and not get_all_players(("succubus",)):
        while ENTRANCED:
            e = ENTRANCED.pop()
            e.send(messages["entranced_revert_win"])

@event_listener("transition_day_resolve", priority=1)
def on_transition_day_resolve(evt, var, victim):
    if victim in get_all_players(("succubus",)) and VISITED.get(victim) and victim not in evt.data["dead"] and victim in evt.data["onlybywolves"]:
        evt.data["message"][victim].append(messages["target_not_home"])
        evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_day_resolve_end", priority=1)
def on_transition_day_resolve_end(evt, var, victims):
    for victim in victims:
        if victim in evt.data["dead"] and victim in VISITED.values() and victim in evt.data["bywolves"]:
            for succubus in VISITED:
                if VISITED[succubus] is victim and succubus not in evt.data["dead"]:
                    if var.ROLE_REVEAL in ("on", "team"):
                        evt.data["message"][succubus].append(messages["visited_victim"].format(succubus, get_reveal_role(succubus)))
                    else:
                        evt.data["message"][succubus].append(messages["visited_victim_noreveal"].format(succubus))
                    evt.data["bywolves"].add(succubus)
                    evt.data["onlybywolves"].add(succubus)
                    evt.data["dead"].append(succubus)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(VISITED) + len(PASSED)
    evt.data["nightroles"].extend(get_all_players(("succubus",)))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    succubi = get_all_players(("succubus",))
    for succubus in succubi:
        pl = get_players()
        random.shuffle(pl)
        pl.remove(succubus)
        to_send = "succubus_notify"
        if succubus.prefers_simple():
            to_send = "succubus_simple"
        succ = []
        for p in pl:
            if p in succubi:
                succ.append("{0} (succubus)".format(p))
            else:
                succ.append(p.nick)
        succubus.send(messages[to_send], messages["players_list"].format(", ".join(succ)), sep="\n")

@event_listener("begin_day")
def on_begin_day(evt, var):
    VISITED.clear()
    PASSED.clear()

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if evt.data["role"] == "succubus" and user in ENTRANCED:
        ENTRANCED.remove(user)
        user.send(messages["no_longer_entranced"])

@event_listener("reset")
def on_reset(evt, var):
    global ALL_SUCC_IDLE
    ALL_SUCC_IDLE = True
    ENTRANCED.clear()
    VISITED.clear()
    PASSED.clear()

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if ENTRANCED:
        evt.data["output"].append("\u0002entranced players\u0002: {0}".format(", ".join(p.nick for p in ENTRANCED)))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["succubus"] = {"Neutral", "Win Stealer", "Cursed", "Nocturnal"}

# vim: set sw=4 expandtab:
