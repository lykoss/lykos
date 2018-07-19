import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src.functions import get_players, get_all_players, get_target, get_main_role
from src import channels, users, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

TOBECHARMED = UserDict() # type: Dict[users.User, Set[users.User]]
CHARMED = UserSet() # type: Set[users.User]
PASSED = UserSet() # type: Set[users.User]

@command("charm", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("piper",))
def charm(var, wrapper, message):
    """Charm a player or two, slowly leading to your win!"""
    pieces = re.split(" +", message)
    target1 = pieces[0]
    if len(pieces) > 1:
        if len(pieces) > 2 and pieces[1].lower() == "and":
            target2 = pieces[2]
        else:
            target2 = pieces[1]
    else:
        target2 = None

    target1 = get_target(var, wrapper, target1)
    if not target1:
        return

    if target2 is not None:
        target2 = get_target(var, wrapper, target2)
        if not target2:
            return

    orig1 = target1
    orig2 = target2

    evt1 = Event("targeted_command", {"target": target1, "misdirection": True, "exchange": True})
    evt1.dispatch(var, wrapper.source, target1)
    if evt1.prevent_default:
        return
    target1 = evt1.data["target"]

    if target2 is not None:
        evt2 = Event("targeted_command", {"target": target2, "misdirection": True, "exchange": True})
        evt2.dispatch(var, wrapper.source, target2)
        if evt2.prevent_default:
            return
        target2 = evt2.data["target"]

    # Do these checks based on original targets, so piper doesn't know to change due to misdirection/luck totem
    if orig1 is orig2:
        wrapper.send(messages["must_charm_multiple"])
        return

    if orig1 in CHARMED and orig2 in CHARMED:
        wrapper.send(messages["targets_already_charmed"].format(orig1, orig2))
        return
    elif orig1 in CHARMED:
        wrapper.send(messages["target_already_charmed"].format(orig1))
        return
    elif orig2 in CHARMED:
        wrapper.send(messages["target_already_charmed"].format(orig2))
        return

    if wrapper.source in TOBECHARMED:
        TOBECHARMED[wrapper.source].clear()
    else:
        TOBECHARMED[wrapper.source] = UserSet()

    TOBECHARMED[wrapper.source].update({target1, target2} - {None})
    PASSED.discard(wrapper.source)

    if orig2:
        debuglog("{0} (piper) CHARM {1} ({2}) && {3} ({4})".format(wrapper.source,
                                                                 target1, get_main_role(target1),
                                                                 target2, get_main_role(target2)))
        wrapper.send(messages["charm_multiple_success"].format(orig1, orig2))
    else:
        debuglog("{0} (piper) CHARM {1} ({2})".format(wrapper.source, target1, get_main_role(target1)))
        wrapper.send(messages["charm_success"].format(orig1))

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("piper",))
def pass_cmd(var, wrapper, message):
    """Do not charm anyone tonight."""
    del TOBECHARMED[:wrapper.source:]
    PASSED.add(wrapper.source)

    wrapper.send(messages["piper_pass"])
    debuglog("{0} (piper) PASS".format(wrapper.source))

@command("retract", "r", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("piper",))
def retract(var, wrapper, message):
    """Remove your decision to charm people."""
    if wrapper.source in TOBECHARMED or wrapper.source in PASSED:
        del TOBECHARMED[:wrapper.source:]
        PASSED.discard(wrapper.source)

        wrapper.send(messages["piper_retract"])
        debuglog("{0} (piper) RETRACT".format(wrapper.source))

@event_listener("chk_win", priority=2)
def on_chk_win(evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    # lpl doesn't included wounded/sick people or consecrating priests
    # whereas we want to ensure EVERYONE (even wounded people) are charmed for piper win
    pipers = rolemap.get("piper", set())
    lp = len(pipers)
    if lp == 0: # no alive pipers, short-circuit this check
        return

    uncharmed = set(get_players(mainroles=mainroles)) - CHARMED - pipers

    if var.PHASE == "day" and len(uncharmed) == 0:
        evt.data["winner"] = "pipers"
        evt.data["message"] = messages["piper_win"].format("s" if lp > 1 else "", "s" if lp == 1 else "")

@event_listener("player_win")
def on_player_win(evt, var, player, mainrole, winner, survived):
    if winner != "pipers":
        return

    if mainrole == "piper":
        evt.data["won"] = True

@event_listener("del_player")
def on_del_player(evt, var, player, mainrole, allroles, death_triggers):
    CHARMED.discard(player)
    del TOBECHARMED[:player:]

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    tocharm = set(itertools.chain.from_iterable(TOBECHARMED.values()))
    # remove pipers from set; they can never be charmed
    # but might end up in there due to misdirection/luck totems
    tocharm.difference_update(get_all_players(("piper",)))

    # Send out PMs to players who have been charmed
    for target in tocharm:
        charmedlist = list(CHARMED | tocharm - {target})
        message = messages["charmed"]

        if len(charmedlist) <= 0:
            target.send(message + messages["no_charmed_players"])
        elif len(charmedlist) == 1:
            target.send(message + messages["one_charmed_player"].format(charmedlist[0]))
        elif len(charmedlist) == 2:
            target.send(message + messages["two_charmed_players"].format(charmedlist[0], charmedlist[1]))
        else:
            target.send(message + messages["many_charmed_players"].format("\u0002, \u0002".join(p.nick for p in charmedlist[:-1]), charmedlist[-1]))

    if len(tocharm) > 0:
        for target in CHARMED:
            tobecharmedlist = list(tocharm)

            if len(tobecharmedlist) == 1:
                message = messages["players_charmed_one"].format(tobecharmedlist[0])
            elif len(tobecharmedlist) == 2:
                message = messages["players_charmed_two"].format(tobecharmedlist[0], tobecharmedlist[1])
            else:
                message = messages["players_charmed_many"].format("\u0002, \u0002".join(p.nick for p in tobecharmedlist[:-1]), tobecharmedlist[-1])

            previouscharmed = CHARMED - {target}
            if len(previouscharmed):
                target.send(message + messages["previously_charmed"].format("\u0002, \u0002".join(p.nick for p in previouscharmed)))
            else:
                target.send(message)

    CHARMED.update(tocharm)
    TOBECHARMED.clear()
    PASSED.clear()

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(TOBECHARMED) + len(PASSED)
    evt.data["nightroles"].extend(get_all_players(("piper",)))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = set(get_players()) - CHARMED
    for piper in get_all_players(("piper",)):
        pl = list(ps)
        random.shuffle(pl)
        pl.remove(piper)
        to_send = "piper_notify"
        if piper.prefers_simple():
            to_send = "piper_simple"
        piper.send(messages[to_send], messages["players_list"].format(", ".join(p.nick for p in pl)), sep="\n")

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    # if we're shifting piper around, ensure that the new piper isn't charmed
    if actor_role == "piper":
        CHARMED.discard(target)
        if target_role != "piper":
            del TOBECHARMED[:actor:]
            PASSED.discard(actor)
    if target_role == "piper":
        CHARMED.discard(actor)
        if actor_role != "piper":
            del TOBECHARMED[:target:]
            PASSED.discard(target)

@event_listener("night_acted")
def on_acted(evt, var, target, spy):
    if target in TOBECHARMED:
        evt.data["acted"] = True

@event_listener("reset")
def on_reset(evt, var):
    CHARMED.clear()
    TOBECHARMED.clear()
    PASSED.clear()

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if CHARMED:
        nicks = ", ".join(p.nick for p in CHARMED)
        evt.data["output"].append(messages["piper_revealroles_charmed"].format(nicks))

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    players = TOBECHARMED.get(user)
    if players:
        nicks = ", ".join(p.nick for p in players)
        evt.data["special_case"].append(messages["piper_revealroles_charming"].format(nicks))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["piper"] = {"Neutral", "Win Stealer"}

# vim: set sw=4 expandtab:
