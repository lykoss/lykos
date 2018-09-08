from src.decorators import event_listener
from src.containers import UserSet
from src.functions import get_all_players, get_main_role, change_role
from src.events import Event
from src.cats import Wolf
from src.roles._wolf_helper import get_wolfchat_roles

__all__ = ["add_lycanthropy", "remove_lycanthropy", "add_lycanthropy_scope"]

LYCANTHROPES = UserSet()
SCOPE = set()

def add_lycanthropy(var, target):
    """Effect the target with lycanthropy. Fire the add_lycanthropy event."""
    if target in LYCANTHROPES:
        return

    if Event("add_lycanthropy", {}).dispatch(var, target):
        LYCANTHROPES.add(target)

def remove_lycanthropy(var, target):
    """Remove the lycanthropy effect from the target."""
    LYCANTHROPES.discard(target)

def add_lycanthropy_scope(var, scope):
    """Add a scope for roles that can effect lycanthropy, for stats."""
    SCOPE.update(scope)

@event_listener("reconfigure_stats")
def on_reconfigure_stats(evt, var, roleset, reason):
    if reason != "howl" or not LYCANTHROPES or not SCOPE:
        return

    evt2 = Event("get_role_metadata", {})
    evt2.dispatch("lycanthropy_role")

    roles = {}

    wolfchat = get_wolfchat_roles(var)
    for role, count in roleset.items():
        if role in wolfchat or count == 0 or role not in SCOPE:
            continue
        if role in evt2.data and "role" in evt2.data[role]:
            roles[role] = evt2.data[role]["role"]
        else:
            roles[role] = "wolf"

    if roles and roleset in evt.data["new"]:
        evt.data["new"].remove(roleset)

    for role, new_role in roles.items():
        rs = roleset.copy()
        rs[role] -= 1
        rs[new_role] = rs.get(new_role, 0) + 1
        evt.data["new"].append(rs)

@event_listener("bite")
def on_bite(evt, var, biter, target):
    if target in LYCANTHROPES:
        evt.data["kill"] = True

@event_listener("del_player")
def on_del_player(evt, var, player, mainrole, allroles, death_triggers):
    remove_lycanthropy(var, player)

@event_listener("transition_day_resolve_end", priority=2)
def on_transition_day_resolve_end(evt, var, victims):
    for victim in victims:
        if victim in LYCANTHROPES and victim in evt.data["onlybywolves"]:
            vrole = get_main_role(victim)
            if vrole not in Wolf:
                change_role(var, victim, vrole, "wolf", message="lycan_turn")
                evt.data["howl"] += 1
                evt.data["novictmsg"] = False
                evt.data["dead"].remove(victim)
                evt.data["bywolves"].discard(victim)
                evt.data["onlybywolves"].discard(victim)
                evt.data["killers"][victim].remove("@wolves")
                del evt.data["message"][victim]

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if LYCANTHROPES:
        evt.data["output"].append("\u0002lycanthropes\u0002: {0}".format(", ".join(p.nick for p in LYCANTHROPES)))

@event_listener("transition_night_begin")
def on_begin_day(evt, var):
    LYCANTHROPES.clear()
    SCOPE.clear()

@event_listener("reset")
def on_reset(evt, var):
    LYCANTHROPES.clear()
    SCOPE.clear()

# vim: set sw=4 expandtab:
