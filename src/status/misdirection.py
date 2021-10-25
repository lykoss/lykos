from __future__ import annotations

import random
from typing import Set, Iterable

from src.events import Event, event_listener
from src.containers import UserSet
from src.gamestate import GameState
from src.functions import get_players
from src.messages import messages
from src.users import User
from src.cats import Category

__all__ = ["add_misdirection", "try_misdirection", "add_misdirection_scope", "in_misdirection_scope"]

AS_ACTOR = UserSet()
AS_TARGET = UserSet()
ACTOR_SCOPE = set()
TARGET_SCOPE = set()

def _get_target(var: GameState, target: User):
    """Internal helper for try_misdirection. Return one target over."""
    pl = get_players(var)
    index = pl.index(target)
    if random.randint(0, 1):
        index -= 2
    if index == len(pl) - 1: # last item
        index = -1
    return pl[index+1]

def add_misdirection(var: GameState, user: User, *, as_actor: bool = False, as_target: bool = False):
    # misdirection as_actor should work on dead players as well; don't do an alive check here
    if as_actor:
        AS_ACTOR.add(user)
    if as_target and user in get_players(var):
        AS_TARGET.add(user)

def try_misdirection(var: GameState, actor: User, target: User):
    """Check if misdirection can apply. Return the target."""
    if actor is not target:
        if actor in AS_ACTOR:
            target = _get_target(var, target)
        if target in AS_TARGET:
            target = _get_target(var, target)
    return target

def add_misdirection_scope(var: GameState, scope: Category | Set[str], *, as_actor: bool = False, as_target: bool = False):
    if as_actor:
        ACTOR_SCOPE.update(scope)
    if as_target:
        TARGET_SCOPE.update(scope)

def in_misdirection_scope(var: GameState, roles: Category | Set[str] | str, *, as_actor: bool = False, as_target: bool = False):
    assert as_actor or as_target, "in_misdirection_scope requires specifying which scope to check"
    if isinstance(roles, str):
        roles = {roles}
    if as_actor and not roles & ACTOR_SCOPE:
        return False
    if as_target and not roles & TARGET_SCOPE:
        return False
    return True

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, allroles: Set[str], death_triggers: bool):
    # don't clear AS_ACTOR here; we want dead players to still be misdirected (e.g. vengeful ghost)
    AS_TARGET.discard(player)

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if AS_ACTOR or AS_TARGET:
        misdirected = AS_ACTOR | AS_TARGET
        out = []
        for user in misdirected:
            as_what = []
            if user in AS_ACTOR:
                as_what.append(messages["misdirection_as_actor"])
            if user in AS_TARGET:
                as_what.append(messages["misdirection_as_target"])
            out.append(messages["misdirection_join"].format(user, as_what))
        evt.data["output"].append(messages["misdirection_revealroles"].format(out))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    AS_ACTOR.clear()
    AS_TARGET.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    AS_ACTOR.clear()
    AS_TARGET.clear()
