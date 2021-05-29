from __future__ import annotations

import re
import random
import itertools
import math
from collections import defaultdict
from typing import TYPE_CHECKING

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_dying
from src.cats import Win_Stealer

if TYPE_CHECKING:
    from src.users import User

MATCHMAKERS = UserSet()
ACTED = UserSet()
LOVERS: UserDict[User, User] = UserDict()

def _set_lovers(target1, target2):
    if target1 in LOVERS:
        LOVERS[target1].add(target2)
    else:
        LOVERS[target1] = UserSet({target2})

    if target2 in LOVERS:
        LOVERS[target2].add(target1)
    else:
        LOVERS[target2] = UserSet({target1})

    target1.send(messages["matchmaker_target_notify"].format(target2))
    target2.send(messages["matchmaker_target_notify"].format(target1))

def get_lovers():
    lovers = []
    pl = get_players()
    for lover in LOVERS:
        done = None
        for i, lset in enumerate(lovers):
            if lover in pl and lover in lset:
                if done is not None: # plot twist! two clusters turn out to be linked!
                    done.update(lset)
                    for lvr in LOVERS[lover]:
                        if lvr in pl:
                            done.add(lvr)

                    lset.clear()
                    continue

                for lvr in LOVERS[lover]:
                    if lvr in pl:
                        lset.add(lvr)
                done = lset

        if done is None and lover in pl:
            lovers.append(set())
            lovers[-1].add(lover)
            for lvr in LOVERS[lover]:
                if lvr in pl:
                    lovers[-1].add(lvr)

    while set() in lovers:
        lovers.remove(set())

    return lovers

@command("match", chan=False, pm=True, playing=True, phases=("night",), roles=("matchmaker",))
def choose(var, wrapper, message):
    """Select two players to fall in love. You may select yourself as one of the lovers."""
    if wrapper.source in MATCHMAKERS:
        wrapper.send(messages["already_matched"])
        return

    pieces = re.split(" +", message)
    if len(pieces) < 2:
        return
    target1 = get_target(var, wrapper, pieces[0], allow_self=True)
    target2 = get_target(var, wrapper, pieces[1], allow_self=True)
    if not target1 or not target2:
        return

    if target1 is target2:
        wrapper.send(messages["choose_different_people"])
        return

    MATCHMAKERS.add(wrapper.source)
    ACTED.add(wrapper.source)

    _set_lovers(target1, target2)

    wrapper.send(messages["matchmaker_success"].format(target1, target2))

    debuglog("{0} (matchmaker) MATCH: {1} ({2}) WITH {3} ({4})".format(wrapper.source, target1, get_main_role(target1), target2, get_main_role(target2)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    ACTED.clear()
    pl = get_players()
    for mm in get_all_players(("matchmaker",)):
        if mm not in MATCHMAKERS:
            lovers = random.sample(pl, 2)
            MATCHMAKERS.add(mm)
            _set_lovers(*lovers)
            mm.send(messages["random_matchmaker"])

@event_listener("send_role")
def on_send_role(evt, var):
    ps = get_players()
    for mm in get_all_players(("matchmaker",)):
        if mm in MATCHMAKERS and not var.ALWAYS_PM_ROLE:
            continue
        pl = ps[:]
        random.shuffle(pl)
        mm.send(messages["matchmaker_notify"])
        if var.NIGHT_COUNT > 0:
            mm.send(messages["players_list"].format(pl))

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    MATCHMAKERS.discard(player)
    ACTED.discard(player)
    if death_triggers and player in LOVERS:
        lovers = set(LOVERS[player])
        for lover in lovers:
            if lover not in get_players():
                continue # already died somehow
            to_send = "lover_suicide_no_reveal"
            if var.ROLE_REVEAL in ("on", "team"):
                to_send = "lover_suicide"
            channels.Main.send(messages[to_send].format(lover, get_reveal_role(lover)))
            debuglog("{0} ({1}) LOVE SUICIDE: {2} ({3})".format(lover, get_main_role(lover), player, evt.params.main_role))
            add_dying(var, lover, killer_role=evt.params.killer_role, reason="lover_suicide")

@event_listener("game_end_messages")
def on_game_end_messages(evt, var):
    done = {}
    lovers = []
    for lover1, lset in LOVERS.items():
        for lover2 in lset:
            # check if already said the pairing
            if (lover1 in done and lover2 in done[lover1]) or (lover2 in done and lover1 in done[lover2]):
                continue
            lovers.append(messages["lover_pair_endgame"].format(lover1, lover2))
            if lover1 in done:
                done[lover1].append(lover2)
            else:
                done[lover1] = [lover2]

    if lovers:
        evt.data["messages"].append(messages["lovers_endgame"].format(lovers))

@event_listener("team_win")
def on_team_win(evt, var, player, main_role, allroles, winner):
    if winner == "lovers" and player in get_lovers()[0]:
        evt.data["team_win"] = True

@event_listener("player_win")
def on_player_win(evt, var, player, main_role, all_roles, winner, team_win, survived):
    if player in LOVERS:
        evt.data["special"].append("lover")
    pl = get_players()
    if player in LOVERS and survived and LOVERS[player].intersection(pl):
        for lover in LOVERS[player]:
            if lover not in pl:
                # cannot win with dead lover (lover idled out)
                continue
            if team_win or lover in evt.params.team_wins:
                # lovers only win this way if one of them got a team win
                evt.data["individual_win"] = True
                break

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    mms = (get_all_players(("matchmaker",)) - MATCHMAKERS) | ACTED
    evt.data["acted"].extend(ACTED)
    evt.data["nightroles"].extend(mms)

@event_listener("get_team_affiliation")
def on_get_team_affiliation(evt, var, target1, target2):
    if target1 in LOVERS and target2 in LOVERS:
        for lset in get_lovers():
            if target1 in lset and target2 in lset:
                evt.data["same"] = True
                break

@event_listener("myrole")
def on_myrole(evt, var, user):
    # Remind lovers of each other
    if user in get_players() and user in LOVERS:
        evt.data["messages"].append(messages["matched_info"].format(LOVERS[user]))

@event_listener("revealroles")
def on_revealroles(evt, var):
    # print out lovers
    pl = get_players()
    done = {}
    lovers = []
    for lover1, lset in LOVERS.items():
        if lover1 not in pl:
            continue
        for lover2 in lset:
            # check if already said the pairing
            if (lover1 in done and lover2 in done[lover1]) or (lover2 in done and lover1 in done[lover2]):
                continue
            if lover2 not in pl:
                continue
            lovers.append("{0}/{1}".format(lover1, lover2))
            if lover1 in done:
                done[lover1].append(lover2)
            else:
                done[lover1] = [lover2]
    if lovers:
        evt.data["output"].append(messages["lovers_revealroles"].format(lovers))

@event_listener("reset")
def on_reset(evt, var):
    MATCHMAKERS.clear()
    ACTED.clear()
    LOVERS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["matchmaker"] = {"Village", "Safe"}
    elif kind == "special_keys":
        evt.data["matchmaker"] = {"lover"}
