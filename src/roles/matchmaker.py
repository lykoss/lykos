from __future__ import annotations

import re
import random
import itertools
import math
from collections import defaultdict
from typing import TYPE_CHECKING, Set, Optional

from src import channels, users
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_dying
from src.events import Event, event_listener
from src.cats import Win_Stealer

if TYPE_CHECKING:
    from src.gamestate import GameState
    from src.dispatcher import MessageDispatcher
    from src.users import User

MATCHMAKERS = UserSet()
ACTED = UserSet()
LOVERS = UserDict()

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

def get_lovers(var):
    lovers = []
    pl = get_players(var)
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
def choose(wrapper: MessageDispatcher, message: str):
    """Select two players to fall in love. You may select yourself as one of the lovers."""
    if wrapper.source in MATCHMAKERS:
        wrapper.send(messages["already_matched"])
        return

    pieces = re.split(" +", message)
    if len(pieces) < 2:
        return
    var = wrapper.game_state
    target1 = get_target(wrapper, pieces[0], allow_self=True)
    target2 = get_target(wrapper, pieces[1], allow_self=True)
    if not target1 or not target2:
        return

    if target1 is target2:
        wrapper.send(messages["choose_different_people"])
        return

    MATCHMAKERS.add(wrapper.source)
    ACTED.add(wrapper.source)

    _set_lovers(target1, target2)

    wrapper.send(messages["matchmaker_success"].format(target1, target2))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    ACTED.clear()
    pl = get_players(var)
    for mm in get_all_players(var, ("matchmaker",)):
        if mm not in MATCHMAKERS:
            lovers = random.sample(pl, 2)
            MATCHMAKERS.add(mm)
            _set_lovers(*lovers)
            mm.send(messages["random_matchmaker"])

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    ps = get_players(var)
    for mm in get_all_players(var, ("matchmaker",)):
        if mm in MATCHMAKERS and not var.always_pm_role:
            continue
        pl = ps[:]
        random.shuffle(pl)
        mm.send(messages["matchmaker_notify"])
        if var.next_phase != "night":
            mm.send(messages["players_list"].format(pl))

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player, all_roles, death_triggers):
    MATCHMAKERS.discard(player)
    ACTED.discard(player)
    if death_triggers and player in LOVERS:
        lovers = set(LOVERS[player])
        for lover in lovers:
            if lover not in get_players(var):
                continue # already died somehow
            to_send = "lover_suicide_no_reveal"
            if var.role_reveal in ("on", "team"):
                to_send = "lover_suicide"
            channels.Main.send(messages[to_send].format(lover, get_reveal_role(var, lover)))
            add_dying(var, lover, killer_role=evt.params.killer_role, reason="lover_suicide")

@event_listener("game_end_messages")
def on_game_end_messages(evt: Event, var: GameState):
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
def on_team_win(evt: Event, var: GameState, player, main_role, allroles, winner):
    if winner == "lovers" and player in get_lovers(var)[0]:
        evt.data["team_win"] = True

@event_listener("player_win")
def on_player_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: Set[str], winner: str, team_win: bool, survived: bool):
    if player in LOVERS:
        evt.data["special"].append("lover")
    pl = get_players(var)
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
def on_chk_nightdone(evt: Event, var: GameState):
    mms = (get_all_players(var, ("matchmaker",)) - MATCHMAKERS) | ACTED
    evt.data["acted"].extend(ACTED)
    evt.data["nightroles"].extend(mms)

@event_listener("get_team_affiliation")
def on_get_team_affiliation(evt: Event, var: GameState, target1, target2):
    if target1 in LOVERS and target2 in LOVERS:
        for lset in get_lovers(var):
            if target1 in lset and target2 in lset:
                evt.data["same"] = True
                break

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user):
    # Remind lovers of each other
    if user in get_players(var) and user in LOVERS:
        evt.data["messages"].append(messages["matched_info"].format(LOVERS[user]))

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    # print out lovers
    pl = get_players(var)
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
def on_reset(evt: Event, var: GameState):
    MATCHMAKERS.clear()
    ACTED.clear()
    LOVERS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["matchmaker"] = {"Village", "Safe"}
    elif kind == "special_keys":
        evt.data["matchmaker"] = {"lover"}
