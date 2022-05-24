from __future__ import annotations

from typing import Optional, Iterable, Callable
from collections import Counter
import functools
import typing

from src.messages import messages, LocalRole, LocalMode, LocalTotem
from src.gamestate import PregameState, GameState
from src.events import Event
from src.cats import Wolfteam, Neutral, Hidden, All
from src.match import Match, match_all

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.users import User

__all__ = [
    "get_players", "get_all_players", "get_participants",
    "get_target", "change_role",
    "get_main_role", "get_all_roles", "get_reveal_role",
    "match_role", "match_mode", "match_totem"
    ]

def get_players(var: Optional[GameState | PregameState], roles=None, *, mainroles=None) -> list[User]:
    from src.status import is_dying
    if var is None:
        return []
    if isinstance(var, PregameState):
        if roles is not None:
            return []
        return list(var.players)

    if mainroles is None:
        mainroles = var.main_roles
    if roles is None:
        roles = set(mainroles.values())
    pl = set()
    for user, role in mainroles.items():
        if role in roles:
            pl.add(user)

    if mainroles is not var.main_roles:
        # we weren't given an actual player list (possibly),
        # so the elements of pl are not necessarily in var.players
        return list(pl)
    return [p for p in var.players if p in pl and not is_dying(var, p)]

def get_all_players(var: Optional[GameState | PregameState], roles=None, *, rolemap=None) -> set[User]:
    from src.status import is_dying
    if var is None:
        return set()
    if isinstance(var, PregameState):
        if roles is not None:
            return set()
        return set(var.players)

    if rolemap is None:
        rolemap = var.roles
    if roles is None:
        roles = set(rolemap.keys())
    pl = set()
    for role in roles:
        for user in rolemap[role]:
            pl.add(user)

    if rolemap is not var.roles:
        return pl

    return {p for p in pl if not is_dying(var, p)}

def get_participants(var: Optional[GameState | PregameState]) -> list[User]:
    """List all players who are still able to participate in the game."""
    evt = Event("get_participants", {"players": get_players(var)})
    evt.dispatch(var)
    return evt.data["players"]

def get_target(wrapper: MessageDispatcher, message: str, *, allow_self: bool = False, allow_bot: bool = False, not_self_message: str = "no_target_self") -> Optional[User]:
    """Autocomplete a target for an in-game command.

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

    players = get_players(wrapper.game_state)
    if not allow_self and wrapper.source in players:
        players.remove(wrapper.source)

    if allow_bot:
        players.append(users.Bot)

    match = users.complete_match(message, players)
    if not match:
        if not len(match) and users.lower(wrapper.source.nick).startswith(users.lower(message)):
            wrapper.pm(messages[not_self_message])
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

def change_role(var: GameState,
                player: User,
                old_role: str,
                new_role: str,
                *,
                inherit_from=None,
                message="new_role",
                send_messages=True) -> tuple[str, list[str | Callable[[], str]]]:
    """ Change the player's main role, updating relevant game state.

    :param var: Game state
    :param player: Player whose role is being changed
    :param old_role: Player's old main role
    :param new_role: Player's new main role
    :param inherit_from: Another player whose role state to inherit from (e.g. in role swaps)
    :param message: Message alerting the player that they have a new role
    :param send_messages: if False, messages are not immediately sent to the player
        and must be sent by the caller
    :return: A tuple containing the player's new role (which may be different from the new_role
        parameter due to events) and a list of messages that were sent to the player (or should
        be sent to the player if send_messages is False).
    """
    # in_wolfchat is filled as part of priority 4
    # if you wish to modify evt.data["role"], do so in priority 3 or sooner
    evt = Event("new_role",
                {"role": new_role, "messages": [], "in_wolfchat": False},
                inherit_from=inherit_from)
    evt.dispatch(var, player, old_role)
    new_role = evt.data["role"]

    var.roles[old_role].remove(player)
    var.roles[new_role].add(player)
    # only adjust main_roles/final_roles if we're changing the player's actual role
    if var.main_roles[player] == old_role:
        var.main_roles[player] = new_role
        var.final_roles[player] = new_role

    # if giving the player a new role during night, don't warn them for not acting
    from src.trans import NIGHT_IDLE_EXEMPT
    NIGHT_IDLE_EXEMPT.add(player)

    say_role = new_role
    if say_role in Hidden:
        say_role = var.hidden_role

    if message:
        evt.data["messages"].insert(0, messages[message].format(say_role))
    if send_messages:
        player.send(*evt.data["messages"])

    return new_role, evt.data["messages"]

def get_main_role(var: GameState, user):
    role = var.main_roles.get(user)
    if role is not None:
        return role
    # not found in player list, see if they're a special participant
    if user in get_participants(var):
        evt = Event("get_participant_role", {"role": None})
        evt.dispatch(var, user)
        role = evt.data["role"]
    if role is None:
        raise ValueError("User {0} isn't playing and has no defined participant role".format(user))
    return role

def get_all_roles(var: GameState, user: User) -> set[str]:
    return {role for role, users in var.roles.items() if user in users}

def get_reveal_role(var: GameState, user) -> str:
    evt = Event("get_reveal_role", {"role": get_main_role(var, user)})
    evt.dispatch(var, user)
    role = evt.data["role"]

    if var.role_reveal != "team":
        return role

    if role in Wolfteam:
        return "wolfteam player"
    elif role in Neutral:
        return "neutral player"
    else:
        return "village member"

def match_role(role: str, remove_spaces: bool = False, allow_extra: bool = False, allow_special: bool = True, scope: Optional[Iterable[str]] = None) -> Match[LocalRole]:
    """ Match a partial role or alias name into the internal role key.

    :param role: Partial role to match on
    :param remove_spaces: Whether or not to remove all spaces before matching.
        This is meant for contexts where we truly cannot allow spaces somewhere; otherwise we should
        prefer that the user matches including spaces where possible for friendlier-looking commands.
    :param allow_extra: Whether to allow keys that are defined in the translation file but do not exist in the bot.
        Typically these are roles that were previously removed.
    :param allow_special: Whether to allow special keys (lover, vg activated, etc.).
        If scope is set, this parameter is ignored.
    :param scope: Limit matched roles to these explicitly passed-in roles (iterable of internal role names).
    :return: Match object with all matches (see src.match.match_all)
    """
    if remove_spaces:
        role = role.replace(" ", "")

    role_map = messages.get_role_mapping(reverse=True, remove_spaces=remove_spaces)

    special_keys: set[str] = set()
    if scope is None and allow_special:
        evt = Event("get_role_metadata", {})
        evt.dispatch(None, "special_keys")
        special_keys = functools.reduce(lambda x, y: x | y, evt.data.values(), special_keys)

    matches = match_all(role, role_map.keys())

    # strip matches that don't refer to actual roles or special keys (i.e. refer to team names)
    filtered_matches: set[LocalRole] = set()
    if scope is not None:
        allowed = set(scope)
    elif allow_extra:
        allowed = set(role_map.values()) | special_keys
    else:
        allowed = All.roles | special_keys

    for match in matches:
        if role_map[match] in allowed:
            filtered_matches.add(LocalRole(role_map[match], match))

    return Match(filtered_matches)

def match_mode(mode: str, remove_spaces: bool = False, allow_extra: bool = False, scope: Optional[Iterable[str]] = None) -> Match[LocalMode]:
    """ Match a partial game mode into the internal game mode key.

    :param mode: Partial game mode to match on
    :param remove_spaces: Whether or not to remove all spaces before matching.
        This is meant for contexts where we truly cannot allow spaces somewhere; otherwise we should
        prefer that the user matches including spaces where possible for friendlier-looking commands.
    :param allow_extra: Whether to allow keys that are defined in the translation file but do not exist in the bot.
        Typically these are game modes that were previously removed.
    :param scope: Limit matched modes to these explicitly passed-in modes (iterable of internal mode names).
    :return: Match object with all matches (see src.match.match_all)
    """
    mode = mode.lower()
    if remove_spaces:
        mode = mode.replace(" ", "")

    mode_map = messages.get_mode_mapping(reverse=True, remove_spaces=remove_spaces)
    matches = match_all(mode, mode_map.keys())

    # strip matches that aren't in scope, and convert to LocalMode objects
    filtered_matches = set()
    if scope is not None:
        allowed = set(scope)
    elif allow_extra:
        allowed = set(mode_map.values())
    else:
        from src.gamemodes import GAME_MODES
        allowed = set(GAME_MODES)

    for match in matches:
        if mode_map[match] in allowed:
            filtered_matches.add(LocalMode(mode_map[match], match))

    return Match(filtered_matches)

def match_totem(totem: str, scope: Optional[Iterable[str]] = None) -> Match[LocalTotem]:
    """ Match a partial totem into the internal totem key.

    :param totem: Partial totem to match on
    :param scope: Limit matched modes to these explicitly passed-in totems (iterable of internal totem names).
    :return: Match object with all matches (see src.match.match_all)
    """
    mode = totem.lower()
    totem_map = messages.get_totem_mapping(reverse=True)
    matches = match_all(totem, totem_map.keys())

    # strip matches that aren't in scope, and convert to LocalMode objects
    filtered_matches = set()
    if scope is not None:
        allowed = set(scope)
    else:
        allowed = set(totem_map.keys())

    for match in matches:
        if totem_map[match] in allowed:
            filtered_matches.add(LocalTotem(totem_map[match], match))

    return Match(filtered_matches)
