from __future__ import annotations

from src import config
from src.containers import UserSet
from src.functions import get_main_role, change_role, get_players
from src.messages import messages
from src.events import Event, event_listener
from src.gamestate import GameState
from src.users import User

__all__ = ["add_exchange", "try_exchange"]

EXCHANGE = UserSet()

def add_exchange(var: GameState, user: User):
    if user not in get_players(var):
        return
    EXCHANGE.add(user)

def try_exchange(var: GameState, actor: User, target: User):
    """Check if an exchange is happening. Return True if the exchange occurs."""
    if actor is target or target not in EXCHANGE:
        return False

    EXCHANGE.remove(target)

    role = get_main_role(var, actor)
    target_role = get_main_role(var, target)

    actor_role, actor_messages = change_role(var, actor, role, target_role, inherit_from=target, send_messages=False)
    target_role, _ = change_role(var, target, target_role, role, inherit_from=actor)
    # defer actor's messages so that things dependent on all roles to be resolved can run after we finish setting
    # the target's role
    actor.send(*actor_messages)

    if actor_role == target_role: # swap state of two players with the same role
        evt = Event("swap_role_state", {"actor_messages": [], "target_messages": []})
        evt.dispatch(var, actor, target, actor_role)

        actor.send(*evt.data["actor_messages"])
        target.send(*evt.data["target_messages"])
        var.extend_phase_limit(config.Main.get("gameplay.totems.exchange.minimum_time"))

    return True

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, allroles: set[str], death_triggers: bool):
    EXCHANGE.discard(player)

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if EXCHANGE:
        evt.data["output"].append(messages["exchange_revealroles"].format(EXCHANGE))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    EXCHANGE.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    EXCHANGE.clear()
