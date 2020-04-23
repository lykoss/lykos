from typing import Optional
from collections import Counter
from src.messages import messages
from src.events import Event
from src.cats import Wolfteam, Neutral, Hidden
from src import settings as var

__all__ = [
    "get_players", "get_all_players", "get_participants",
    "get_target", "change_role",
    "get_main_role", "get_all_roles", "get_reveal_role",
    ]

def get_players(roles=None, *, mainroles=None):
    from src.status import is_dying
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
    return [p for p in var.ALL_PLAYERS if p in pl and not is_dying(var, p)]

def get_all_players(roles=None, *, rolemap=None):
    from src.status import is_dying
    if rolemap is None:
        rolemap = var.ROLES
    if roles is None:
        roles = set(rolemap.keys())
    pl = set()
    for role in roles:
        for user in rolemap[role]:
            pl.add(user)

    if rolemap is not var.ROLES:
        return pl

    return {p for p in pl if not is_dying(var, p)}

def get_participants():
    """List all players who are still able to participate in the game."""
    evt = Event("get_participants", {"players": get_players()})
    evt.dispatch(var)
    return evt.data["players"]

def get_target(var, wrapper, message, *, allow_self=False, allow_bot=False, not_self_message=None):
    """Autocomplete a target for an in-game command.

    :param var: Game state
    :param MessageDispatcher wrapper: Message context
    :param str message: Text to complete against
    :param bool allow_self: Whether or not to allow the current player as the target
    :param bool allow_bot: Whether or not to allow the bot as the target
    :param str not_self_message: If allow_self is False, the message key to output if we matched ourselves
    :returns: The matched target, or None if no matches
    :rtype: Optional[User]
    """
    from src import users # FIXME: we should move get_target elsewhere to avoid circular imports
    if not message:
        wrapper.pm(messages["not_enough_parameters"])
        return

    players = get_players()
    if not allow_self and wrapper.source in players:
        players.remove(wrapper.source)

    if allow_bot:
        players.append(users.Bot)

    match = users.complete_match(message, players)
    if not match:
        if not len(match) and users.lower(wrapper.source.nick).startswith(users.lower(message)):
            wrapper.pm(messages[not_self_message or "no_target_self"])
            return
        if not len(match):
            wrapper.pm(messages["not_playing"].format(message))
        else:
            # display some helpful suggestions, including account disambiguation if needed
            nicks = Counter(users.lower(x.nick) for x in match)
            suggestions = []
            for nick, count in nicks.items():
                if count == 1:
                    suggestions.append(nick)
                else:
                    for user in match:
                        luser = user.lower()
                        if luser.nick == nick:
                            suggestions.append("{0}:{1}".format(luser.nick, luser.account))
            suggestions.sort()
            wrapper.pm(messages["not_playing_suggestions"].format(message, suggestions))
        return

    return match.get()

def change_role(var, player, oldrole, newrole, *, inherit_from=None, message="new_role"):
    # in_wolfchat is filled as part of priority 4
    # if you wish to modify evt.data["role"], do so in priority 3 or sooner
    evt = Event("new_role",
            {"role": newrole, "messages": [], "in_wolfchat": False},
            inherit_from=inherit_from)
    evt.dispatch(var, player, oldrole)
    newrole = evt.data["role"]

    var.ROLES[oldrole].remove(player)
    var.ROLES[newrole].add(player)
    # only adjust MAIN_ROLES/FINAL_ROLES if we're changing the player's actual role
    if var.MAIN_ROLES[player] == oldrole:
        var.MAIN_ROLES[player] = newrole
        var.FINAL_ROLES[player] = newrole

    # if giving the player a new role during night, don't warn them for not acting
    var.NIGHT_IDLE_EXEMPT.add(player)

    sayrole = newrole
    if sayrole in Hidden:
        sayrole = var.HIDDEN_ROLE

    if message:
        player.send(messages[message].format(sayrole))
    player.send(*evt.data["messages"])

    return newrole

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
    evt = Event("get_reveal_role", {"role": get_main_role(user)})
    evt.dispatch(var, user)
    role = evt.data["role"]

    if var.ROLE_REVEAL != "team":
        return role

    if role in Wolfteam:
        return "wolfteam player"
    elif role in Neutral:
        return "neutral player"
    else:
        return "village member"

# vim: set sw=4 expandtab:
