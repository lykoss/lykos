from src.containers import UserSet
from src.decorators import event_listener
from src.functions import get_main_role, change_role
from src.events import Event

__all__ = ["add_exchange", "try_exchange"]

EXCHANGE = UserSet() # type: Set[users.User]

def add_exchange(var, user):
    EXCHANGE.add(user)

def try_exchange(var, actor, target):
    """Check if an exchange is happening. Return True if the exchange occurs."""
    if actor is target or target not in EXCHANGE:
        return False

    EXCHANGE.remove(target)

    role = get_main_role(actor)
    target_role = get_main_role(target)

    actor_role = change_role(var, actor, role, target_role, inherit_from=target)
    target_role = change_role(var, target, target_role, role, inherit_from=actor)

    if actor_role == target_role: # swap state of two players with the same role
        evt = Event("swap_role_state", {"actor_messages": [], "target_messages": []})
        evt.dispatch(var, actor, target, actor_role)

        actor.send(*evt.data["actor_messages"])
        target.send(*evt.data["target_messages"])

    return True

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    EXCHANGE.discard(player)

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if EXCHANGE:
        evt.data["output"].append("\u0002exchange\u0002: {0}".format(", ".join(p.nick for p in EXCHANGE)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    EXCHANGE.clear()

@event_listener("reset")
def on_reset(evt, var):
    EXCHANGE.clear()
