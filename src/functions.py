from src.messages import messages
from src.events import Event
from src import settings as var
from src import users

__all__ = [
    "get_players", "get_all_players", "get_participants",
    "get_target",
    "get_main_role", "get_all_roles", "get_reveal_role",
    "is_known_wolf_ally",
    ]

def get_players(roles=None, *, mainroles=None):
    if mainroles is None:
        mainroles = var.MAIN_ROLES
    if roles is None:
        roles = set(mainroles.values())
    pl = set()
    for user, role in mainroles.items():
        if role in roles:
            pl.add(user)

    if mainroles is not var.MAIN_ROLES:
        # we weren't given an actual player list (possibly),
        # so the elements of pl are not necessarily in var.ALL_PLAYERS
        return list(pl)
    return [p for p in var.ALL_PLAYERS if p in pl]

def get_all_players(roles=None, *, rolemap=None):
    if rolemap is None:
        rolemap = var.ROLES
    if roles is None:
        roles = set(rolemap.keys())
    pl = set()
    for role in roles:
        for user in rolemap[role]:
            pl.add(user)

    return pl

def get_participants():
    """List all players who are still able to participate in the game."""
    evt = Event("get_participants", {"players": get_players()})
    evt.dispatch(var)
    return evt.data["players"]

def get_target(var, wrapper, message, *, allow_self=False, allow_bot=False, not_self_message=None):
    if not message:
        wrapper.pm(messages["not_enough_parameters"])
        return

    players = get_players()
    if not allow_self and wrapper.source in players:
        players.remove(wrapper.source)

    if allow_bot:
        players.append(users.Bot)

    match, count = users.complete_match(message, players)
    if match is None:
        if not count and users.lower(wrapper.source.nick).startswith(users.lower(message)):
            wrapper.pm(messages[not_self_message or "no_target_self"])
            return
        wrapper.pm(messages["not_playing"].format(message))
        return

    return match

def get_main_role(user):
    role = var.MAIN_ROLES.get(user)
    if role is not None:
        return role
    # not found in player list, see if they're a special participant
    if user in get_participants():
        evt = Event("get_participant_role", {"role": None})
        evt.dispatch(var, user)
        role = evt.data["role"]
    if role is None:
        raise ValueError("User {0} isn't playing and has no defined participant role".format(user))
    return role

def get_all_roles(user):
    return {role for role, users in var.ROLES.items() if user in users}

def get_reveal_role(user):
    # FIXME: when amnesiac and clone are split, move this into an event
    if var.HIDDEN_AMNESIAC and user in var.ORIGINAL_ROLES["amnesiac"]:
        role = "amnesiac"
    elif var.HIDDEN_CLONE and user in var.ORIGINAL_ROLES["clone"]:
        role = "clone"
    else:
        role = get_main_role(user)

    evt = Event("get_reveal_role", {"role": role})
    evt.dispatch(var, user)
    role = evt.data["role"]

    if var.ROLE_REVEAL != "team":
        return role

    if role in var.WOLFTEAM_ROLES:
        return "wolfteam player"
    elif role in var.TRUE_NEUTRAL_ROLES:
        return "neutral player"
    else:
        return "village member"

def is_known_wolf_ally(actor, target):
    actor_role = get_main_role(actor)
    target_role = get_main_role(target)

    wolves = var.WOLFCHAT_ROLES
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wolves = var.WOLF_ROLES
        else:
            wolves = var.WOLF_ROLES | {"traitor"}

    return actor_role in wolves and target_role in wolves

# vim: set sw=4 expandtab:
