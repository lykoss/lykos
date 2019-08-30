from src.decorators import event_listener
from src.containers import UserDict
from src.functions import get_players, get_all_players, get_main_role, change_role
from src.messages import messages
from src.events import Event
from src.cats import Wolf
from src import debuglog

__all__ = ["add_lycanthropy", "remove_lycanthropy", "add_lycanthropy_scope"]

LYCANTHROPES = UserDict()
SCOPE = set()

def add_lycanthropy(var, target, prefix="lycan"):
    """Effect the target with lycanthropy. Fire the add_lycanthropy event."""
    if target in LYCANTHROPES or target not in get_players():
        return True

    if Event("add_lycanthropy", {}).dispatch(var, target):
        LYCANTHROPES[target] = prefix
        return True

    return False

def remove_lycanthropy(var, target):
    """Remove the lycanthropy effect from the target."""
    del LYCANTHROPES[:target:]

def add_lycanthropy_scope(var, scope):
    """Add a scope for roles that can effect lycanthropy, for stats."""
    SCOPE.update(scope)

@event_listener("reconfigure_stats")
def on_reconfigure_stats(evt, var, roleset, reason):
    from src.roles.helper.wolves import get_wolfchat_roles
    if reason != "howl" or not SCOPE:
        return

    evt2 = Event("get_role_metadata", {})
    evt2.dispatch(var, "lycanthropy_role")

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

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    remove_lycanthropy(var, player)

@event_listener("transition_day_resolve_end", priority=2)
def on_transition_day_resolve_end(evt, var, victims):
    evt2 = Event("get_role_metadata", {})
    evt2.dispatch(var, "lycanthropy_role")
    for victim in victims:
        if victim in LYCANTHROPES and evt.data["killers"][victim] == ["@wolves"] and victim in evt.data["dead"]:
            vrole = get_main_role(victim)
            if vrole not in Wolf:
                new_role = "wolf"
                prefix = LYCANTHROPES[victim]
                if vrole in evt2.data:
                    if "role" in evt2.data[vrole]:
                        new_role = evt2.data[vrole]["role"]
                    if "prefix" in evt2.data[vrole]:
                        prefix = evt2.data[vrole]["prefix"]
                    for sec_role in evt2.data[vrole].get("secondary_roles", ()):
                        var.ROLES[sec_role].add(victim)
                        to_send = "{0}_{1}".format(sec_role.replace(" ", "_"), "simple" if victim.prefers_simple() else "notify")
                        victim.send(messages[to_send])
                        # FIXME: Not every role has proper message keys, such as shamans

                change_role(var, victim, vrole, new_role, message=prefix + "_turn")
                evt.data["howl"] += 1
                evt.data["novictmsg"] = False
                evt.data["dead"].remove(victim)
                evt.data["killers"][victim].remove("@wolves")
                del evt.data["message"][victim]

                debuglog("{0} ({1}) TURN {2}".format(victim, vrole, new_role))

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
