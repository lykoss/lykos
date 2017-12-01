import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.messages import messages
from src.events import Event

TOBECHARMED = {} # type: Dict[users.User, Set[users.User]]
CHARMED = set() # type: Set[users.User]

@command("charm", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("piper",))
def charm(var, wrapper, message):
    """Charm a player, slowly leading to your win!"""
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

    evt1 = Event("targeted_command", {"target": target1.nick, "misdirection": True, "exchange": True})
    evt1.dispatch(wrapper.client, var, "charm", wrapper.source.nick, target1.nick, frozenset({"detrimental"}))
    if evt1.prevent_default:
        return
    target1 = users._get(evt.data["target"]) # FIXME: need to make targeted_command use users

    if target2 is not None:
        evt2 = Event("targeted_command", {"target": target2.nick, "misdirection": True, "exchange": True})
        evt2.dispatch(wrapper.client, var, "charm", wrapper.source.nick, target2.nick, frozenset({"detrimental"}))
        if evt2.prevent_default:
            return
        target2 = users._get(evt.data["target"]) # FIXME

    # Do these checks based on original targets, so piper doesn't know to change due to misdirection/luck totem
    if orig1 is orig2:
        wrapper.pm(messages["must_charm_multiple"])
        return

    if orig1 in CHARMED and orig2 in CHARMED:
        wrapper.pm(messages["targets_already_charmed"].format(orig1, orig2))
        return
    elif orig1 in CHARMED:
        wrapper.pm(messages["target_already_charmed"].format(orig1))
        return
    elif orig2 in CHARMED:
        wrapper.pm(messages["target_already_charmed"].format(orig2))
        return

    TOBECHARMED[wrapper.source] = set(target1, target2)
    TOBECHARMED[wrapper.source].discard(None)

    if orig2:
        debuglog("{0} (piper) CHARM {1} ({2}) && {3} ({4})".format(wrapper.source,
                                                                 target1, get_main_role(target1),
                                                                 target2, get_main_role(target2)))
        wrapper.pm(messages["charm_multiple_success"].format(orig1, ori2))
    else:
        debuglog("{0} (piper) CHARM {1} ({2})".format(wrapper.source, target1, get_main_role(target1)))
        wrapper.pm(messages["charm_success"].format(orig1))

    chk_nightdone(wrapper.client)

@event_listener("chk_win", priority=2)
def on_chk_win(evt, cli, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    lp = len(rolemap.get("piper", ()))
    # lpl doesn't included wounded/sick people or consecrating priests
    # whereas we want to ensure EVERYONE (even wounded people) are charmed for piper win
    if var.PHASE == "day" and lp + len(CHARMED) == len(get_players()):
        evt.data["winner"] = "pipers"
        evt.data["message"] = messages["piper_win"].format("s" if lp > 1 else "", "s" if lp == 1 else "")

@event_listener("player_win")
def on_player_win(evt, var, player, mainrole, winner, survived):
    if winner != "pipers":
        return

    if mainrole == "piper":
        evt.data["won"] = True
    # TODO: add code here (or maybe a sep event?) to let lovers win alongside piper
    # Right now that's still in wolfgame.py, but should be moved here once mm is split

@event_listener("del_player")
def on_del_player(evt, var, player, mainrole, allroles, death_triggers):
    CHARMED.discard(player)
    TOBECHARMED.pop(player, None)

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    tocharm = set(itertools.chain(TOBECHARMED.values()))
    # remove pipers from set; they can never be charmed
    # but might end up in there due to misdirection/luck totems
    tocharm.difference_update(get_all_players(("piper",)))

    # Send out PMs to players who have been charmed
    for target in tocharm:
        charmedlist = list(CHARMED | tocharm - {victim})
        message = messages["charmed"]

        if len(charmedlist) <= 0:
            target.pm(message + messages["no_charmed_players"])
        elif len(charmedlist) == 1:
            target.pm(message + messages["one_charmed_player"].format(charmedlist[0]))
        elif len(charmedlist) == 2:
            target.pm(message + messages["two_charmed_players"].format(charmedlist[0], charmedlist[1]))
        else:
            target.pm(message + messages["many_charmed_players"].format("\u0002, \u0002".join(charmedlist[:-1]), charmedlist[-1]))

    for target in CHARMED:
        tobecharmedlist = list(tocharm)

        if len(tobecharmedlist) == 1:
            message = messages["players_charmed_one"].format(tobecharmedlist[0])
        elif len(tobecharmedlist) == 2:
            message = messages["players_charmed_two"].format(tobecharmedlist[0], tobecharmedlist[1])
        else:
            message = messages["players_charmed_many"].format("\u0002, \u0002".join(tobecharmedlist[:-1]), tobecharmedlist[-1])

        previouscharmed = CHARMED - {target}
        if len(previouscharmed):
            target.pm(message + messages["previously_charmed"].format("\u0002, \u0002".join(previouscharmed)))
        else:
            target.pm(message)

    CHARMED.update(tocharm)
    TOBECHARMED.clear()

@event_listener("night_acted")
def on_night_acted(evt, var, target, actor):
    if target in TOBECHARMED:
        evt.data["acted"] = True

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(TOBECHARMED.keys())
    evt.data["nightroles"].extend(get_all_players(("piper",)))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = set(get_players()) - CHARMED
    for piper in get_all_players(("piper",)):
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(piper)
        to_send = "piper_notify"
        if piper.prefers_simple():
            to_send = "piper_simple"
        piper.send(messages[to_send], "Players: " + ", ".join(pl), sep="\n")

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    # if we're shifting piper around, ensure that the new piper isn't charmed
    if actor_role == "piper":
        CHARMED.discard(target)
    if target_role == "piper":
        CHARMED.discard(actor)

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].extend(get_players(("piper",)))

@event_listener("reset")
def on_reset(evt, var):
    CHARMED.clear()
    TOBECHARMED.clear()

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if CHARMED:
        evt.data["output"].append("\u0002charmed players\u0002: {0}".format(", ".join(CHARMED)))

# vim: set sw=4 expandtab:
