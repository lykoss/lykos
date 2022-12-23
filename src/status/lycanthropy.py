from __future__ import annotations

from collections import Counter

from src.containers import UserDict
from src.functions import get_players, get_main_role, change_role
from src.messages import messages
from src.events import Event, event_listener
from src.cats import Wolf, Category
from src.gamestate import GameState
from src.users import User

__all__ = ["add_lycanthropy", "remove_lycanthropy", "add_lycanthropy_scope"]

LYCANTHROPES: UserDict[User, str] = UserDict()
SCOPE = set()

# To handle non-standard lycanthropy behavior, you will need to implement the get_role_metadata event
# with the "lycanthropy_role" key. Depending on how you fill out the metadata, implementing the lycanthrope_role
# event may also be required. For the metadata event, fill in the data dict as follows:
# evt.data[your_role]["role"] should be all possible wolf roles that your_role can turn into when lycanthropy triggers.
#   This can either be a string (indicating one valid role) or an iterable of strings (indicating multiple valid roles).
#   If an iterable of strings, you **must** also implement the lycanthrope_role event.
#   If omitted, it is assumed that the only valid role that your_role can turn into is "wolf".
# evt.data[your_role]["prefix"] should be a message key fragment if set.
#   The message "{prefix}_turn" is sent to the user when lycanthropy triggers for them, and you must also create that
#   message if it does not already exist. If this data key is set, it will override the prefix specified in
#   add_lycanthropy() for the user. By default, the prefix specified in add_lycanthropy() is used.
# evt.data[your_role]["secondary_roles"] should be an iterable of strings for secondary roles to add to the user
#   as part of them turning. By default, no secondary roles are added to the user.

# The lycanthrope_role event is only fired if multiple valid roles are specified in the metadata (as per above).
# This event requires you to fill in the data dict as follows:
# evt.data["role"] must be set to a role name that is one of the possible roles specified from the metadata.
#   By default, if this is not filled in, the bot will error.
#   If a role is given that is not one of the possible roles specified in the metadata, the bot will error.

def add_lycanthropy(var: GameState, target: User, prefix="lycan"):
    """Effect the target with lycanthropy. Fire the add_lycanthropy event."""
    if target in LYCANTHROPES or target not in get_players(var):
        return True

    if Event("add_lycanthropy", {}).dispatch(var, target):
        LYCANTHROPES[target] = prefix
        return True

    return False

def remove_lycanthropy(var: GameState, target: User):
    """Remove the lycanthropy effect from the target."""
    del LYCANTHROPES[:target:]

def add_lycanthropy_scope(var: GameState, scope: Category | set[str]):
    """Add a scope for roles that can effect lycanthropy, for stats."""
    SCOPE.update(scope)

@event_listener("reconfigure_stats")
def on_reconfigure_stats(evt: Event, var: GameState, roleset: Counter, reason: str):
    from src.roles.helper.wolves import get_wolfchat_roles
    if reason != "howl" or not SCOPE:
        return

    evt2 = Event("get_role_metadata", {})
    evt2.dispatch(var, "lycanthropy_role")

    roles = {}

    wolfchat = get_wolfchat_roles()
    for role, count in roleset.items():
        if role in wolfchat or count == 0 or role not in SCOPE:
            continue
        if role in evt2.data and "role" in evt2.data[role]:
            roles[role] = evt2.data[role]["role"]
        else:
            roles[role] = "wolf"

    if roles and roleset in evt.data["new"]:
        evt.data["new"].remove(roleset)

    for role, new_roles in roles.items():
        if isinstance(new_roles, str):
            new_roles = [new_roles]
        for new_role in new_roles:
            rs = roleset.copy()
            rs[role] -= 1
            rs[new_role] = rs.get(new_role, 0) + 1
            evt.data["new"].append(rs)

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    remove_lycanthropy(var, player)

@event_listener("transition_day_resolve_end", priority=2)
def on_transition_day_resolve_end(evt: Event, var: GameState, victims: list[User]):
    evt2 = Event("get_role_metadata", {})
    evt2.dispatch(var, "lycanthropy_role")
    for victim in victims:
        if victim in LYCANTHROPES and evt.data["killers"][victim] == ["@wolves"] and victim in evt.data["dead"]:
            vrole = get_main_role(var, victim)
            if vrole not in Wolf:
                new_role = "wolf"
                prefix = LYCANTHROPES[victim]
                if vrole in evt2.data:
                    if "role" in evt2.data[vrole]:
                        new_role = evt2.data[vrole]["role"]
                        if not isinstance(evt2.data[vrole]["role"], str):
                            evt3 = Event("get_lycanthrope_role", {"role": None})
                            evt3.dispatch(var, victim, vrole, evt2.data[vrole]["role"])
                            assert(evt3.data["role"] in evt2.data[vrole]["role"])
                            new_role = evt3.data["role"]
                    if "prefix" in evt2.data[vrole]:
                        prefix = evt2.data[vrole]["prefix"]
                    for sec_role in evt2.data[vrole].get("secondary_roles", ()):
                        var.roles[sec_role].add(victim)
                        to_send = "{0}_notify".format(sec_role.replace(" ", "_"))
                        victim.send(messages[to_send])
                        # FIXME: Not every role has proper message keys, such as shamans

                change_role(var, victim, vrole, new_role, message=prefix + "_turn")
                evt.data["howl"] += 1
                evt.data["novictmsg"] = False
                evt.data["dead"].remove(victim)
                evt.data["killers"][victim].remove("@wolves")
                del evt.data["message"][victim]

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if LYCANTHROPES:
        evt.data["output"].append(messages["lycanthropy_revealroles"].format(LYCANTHROPES))

@event_listener("transition_night_begin")
def on_begin_day(evt: Event, var: GameState):
    LYCANTHROPES.clear()
    SCOPE.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    LYCANTHROPES.clear()
    SCOPE.clear()
