from __future__ import annotations

import itertools
import random
import re
from typing import Optional

from src import channels
from src.containers import UserSet, UserDict
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_reveal_role, get_target
from src.messages import messages
from src.status import add_dying
from src.gamestate import GameState
from src.dispatcher import MessageDispatcher
from src.users import User

MATCHMAKERS = UserSet()
ACTED = UserSet()

# active lover pairings (no dead players), contains forward and reverse mappings
LOVERS: UserDict[User, UserSet] = UserDict()

# all lover pairings (for revealroles/endgame stats), contains forward mappings only
PAIRINGS: UserDict[User, UserSet] = UserDict()

def _set_lovers(target1: User, target2: User):
    # ensure that PAIRINGS maps lower id to higher ids
    if target2 < target1:
        target1, target2 = target2, target1

    if target1 in PAIRINGS:
        PAIRINGS[target1].add(target2)
    else:
        PAIRINGS[target1] = UserSet({target2})

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

def get_all_lovers(var: GameState) -> list[set[User]]:
    """ Get all sets of currently alive lovers.

    This method fully resolves lover chains and returns a list of every polycule.
    Each currently alive lover is guaranteed to be in exactly one of those lists.

    :param var: Game state
    :return: A list containing zero or more sets of lovers.
        Each member of the set is either directly or indirectly matched to every other member of that set.
    """
    lovers = []
    all_lovers = set(LOVERS.keys())
    while all_lovers:
        visited = get_lovers(var, all_lovers.pop(), include_player=True)
        all_lovers -= visited
        lovers.append(visited)

    return lovers

def get_lovers(var: GameState, player: User, *, include_player: bool = False) -> set[User]:
    """ Get all alive players this player is currently in love with.

    :param var: Game state
    :param player: Player to check
    :param include_player: If True, include ``player`` in the result set if they are matched
    :return: If ``player`` is dead or is not matched to anyone else alive, an empty set.
        Otherwise, a set containing every other player that ``player`` is matched to,
        whether directly or indirectly.
        If ``include_player=True``, the set additionally includes ``player``.
    """

    if player not in LOVERS:
        return set()

    visited = {player}
    queue = set(LOVERS[player])
    while queue:
        cur = queue.pop()
        visited.add(cur)
        queue |= LOVERS[cur] - visited

    return visited if include_player else visited - {player}

@command("match", chan=False, pm=True, playing=True, phases=("night",), roles=("matchmaker",))
def choose(wrapper: MessageDispatcher, message: str):
    """Select two players to fall in love. You may select yourself as one of the lovers."""
    if wrapper.source in MATCHMAKERS:
        wrapper.send(messages["already_matched"])
        return

    pieces = re.split(" +", message)
    if len(pieces) < 2:
        return

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
        if var.next_phase == "night":
            mm.send(messages["players_list"].format(pl))

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player, all_roles, death_triggers):
    MATCHMAKERS.discard(player)
    ACTED.discard(player)
    if player in LOVERS:
        lovers = set(LOVERS[player])
        pl = get_players(var)
        if death_triggers:
            for lover in lovers:
                if lover not in pl:
                    continue # already died somehow
                to_send = "lover_suicide_no_reveal"
                if var.role_reveal in ("on", "team"):
                    to_send = "lover_suicide"
                channels.Main.send(messages[to_send].format(lover, get_reveal_role(var, lover)))
                add_dying(var, lover, killer_role=evt.params.killer_role, reason="lover_suicide")

        for lover in lovers:
            LOVERS[lover].discard(player)
            if not LOVERS[lover]:
                del LOVERS[lover]

        del LOVERS[player]

@event_listener("game_end_messages")
def on_game_end_messages(evt: Event, var: GameState):
    lovers = []
    for lover1, lset in PAIRINGS.items():
        for lover2 in lset:
            lovers.append(messages["lover_pair_endgame"].format(lover1, lover2))

    if lovers:
        evt.data["messages"].append(messages["lovers_endgame"].format(lovers))

@event_listener("team_win")
def on_team_win(evt: Event, var: GameState, player, main_role, allroles, winner):
    if winner == "lovers" and player in LOVERS:
        evt.data["team_win"] = True

@event_listener("player_win")
def on_player_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: set[str], winner: str, team_win: bool, survived: bool):
    if player in PAIRINGS or player in itertools.chain.from_iterable(PAIRINGS.values()):
        evt.data["special"].append("lover")
        # grant lover a win if any of the other lovers in their polycule got a team win
        if team_win or get_lovers(var, player) & evt.params.team_wins:
            evt.data["individual_win"] = True

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    mms = (get_all_players(var, ("matchmaker",)) - MATCHMAKERS) | ACTED
    evt.data["acted"].extend(ACTED)
    evt.data["nightroles"].extend(mms)

@event_listener("get_team_affiliation")
def on_get_team_affiliation(evt: Event, var: GameState, target1, target2):
    if target1 in LOVERS and target2 in get_lovers(var, target1):
        evt.data["same"] = True

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user):
    # Remind lovers of each other
    if user in get_players(var) and user in LOVERS:
        evt.data["messages"].append(messages["matched_info"].format(LOVERS[user]))

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    # print out lovers
    pl = get_players(var)
    lovers = []
    for lover1, lset in PAIRINGS.items():
        if lover1 not in pl:
            continue
        for lover2 in lset:
            if lover2 not in pl:
                continue
            lovers.append("{0}/{1}".format(lover1, lover2))
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
