from __future__ import annotations

import sys

from src.events import event_listener
from src.decorators import command
from src.containers import UserSet
from src.functions import get_players, get_participants
from src.messages import messages
from src.events import Event
from src.users import User
from src.cats import role_order, Wolf, Wolfchat, Vampire
from src import config, channels, db
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState

DEADCHAT_PLAYERS: UserSet = UserSet()
DEADCHAT_SPECTATE: UserSet = UserSet()
WOLFCHAT_SPECTATE: UserSet = UserSet()
VAMPCHAT_SPECTATE: UserSet = UserSet()

@command("", chan=False, pm=True)
def relay_wolfchat(wrapper: MessageDispatcher, message: str):
    """Relay wolfchat/vampchat messages and commands."""
    var = wrapper.game_state

    if message.startswith(config.Main.get("transports[0].user.command_prefix")):
        return

    if "src.roles.helper.wolves" in sys.modules:
        from src.roles.helper.wolves import get_talking_roles
        wolfchat = get_players(var, get_talking_roles())
    else:
        wolfchat = get_players(var, Wolfchat)
    wolves = get_players(var, Wolf)
    vampires = get_players(var, Vampire)

    if wrapper.source in wolfchat and len(wolfchat) > 1:
        # handle wolfchat toggles
        if not config.Main.get("gameplay.wolfchat.traitor_non_wolf"):
            wolves.extend(get_players(var, ("traitor",)))
        if var.current_phase == "night" and config.Main.get("gameplay.wolfchat.disable_night"):
            return
        elif var.current_phase == "day" and config.Main.get("gameplay.wolfchat.disable_day"):
            return
        elif wrapper.source not in wolves and config.Main.get("gameplay.wolfchat.wolves_only_chat"):
            return
        elif wrapper.source not in wolves and config.Main.get("gameplay.wolfchat.remove_non_wolves"):
            return

        wolfchat.remove(wrapper.source)
        send_to = wolfchat
        spectators = WOLFCHAT_SPECTATE
        spectate_key_suffix = "_wolfchat"
    elif wrapper.source in vampires and len(vampires) > 1:
        # handle vampire chat toggles; they use the same config as wolfchat
        if var.current_phase == "night" and config.Main.get("gameplay.wolfchat.disable_night"):
            return
        elif var.current_phase == "day" and config.Main.get("gameplay.wolfchat.disable_day"):
            return

        vampires.remove(wrapper.source)
        send_to = vampires
        spectators = VAMPCHAT_SPECTATE
        spectate_key_suffix = "_vampchat"
    else:
        # not sending anything
        return

    key = "relay_message"
    if message.startswith("\u0001ACTION") and message[-1] == "\u0001":
        key = "relay_action"
        message = message[8:-1]
    for player in send_to:
        player.queue_message(messages[key].format(wrapper.source, message))
    for player in spectators:
        # full keys used, for grep:
        # relay_message_wolfchat relay_action_wolfchat relay_message_vampchat relay_action_vampchat
        player.queue_message(messages[key + spectate_key_suffix].format(wrapper.source, message))

    User.send_messages()

@command("", chan=False, pm=True)
def relay_deadchat(wrapper: MessageDispatcher, message: str):
    """Relay deadchat messages."""
    if message.startswith(config.Main.get("transports[0].user.command_prefix")):
        return

    if wrapper.source not in get_players(wrapper.game_state) and config.Main.get("gameplay.deadchat") and wrapper.source in DEADCHAT_PLAYERS:
        # relay_message_deadchat and relay_action_deadchat also used here
        key = "relay_message"
        if message.startswith("\u0001ACTION"):
            key = "relay_action"
            message = message[8:-1]
        for user in DEADCHAT_PLAYERS - {wrapper.source}:
            user.queue_message(messages[key].format(wrapper.source, message))
        for user in DEADCHAT_SPECTATE:
            user.queue_message(messages[key + "_deadchat"].format(wrapper.source, message))

        User.send_messages()

def try_restricted_cmd(wrapper: MessageDispatcher, key: str) -> bool:
    # if allowed in normal games, restrict it so that it can only be used by dead players and
    # non-players (don't allow active vengeful ghosts either).
    # also don't allow in-channel (e.g. make it pm only)

    if config.Main.get("debug.enabled"):
        return True

    pl = get_participants(wrapper.game_state)

    if wrapper.source in pl:
        wrapper.pm(messages[key])
        return False

    if wrapper.source.account in {player.account for player in pl}:
        wrapper.pm(messages[key])
        return False

    return True

def spectate_chat(wrapper: MessageDispatcher, message: str, *, is_fspectate: bool):
    if not try_restricted_cmd(wrapper, "spectate_restricted"):
        return

    var = wrapper.game_state

    params = message.split(" ")
    on = "on"
    if not len(params):
        wrapper.pm(messages["fspectate_help" if is_fspectate else "spectate_help"])
        return
    elif len(params) > 1:
        on = params[1].lower()
    what = params[0].lower()
    allowed = ("wolfchat", "vampchat", "deadchat") if is_fspectate else ("wolfchat", "vampchat")
    if what not in allowed or on not in ("on", "off"):
        wrapper.pm(messages["fspectate_help" if is_fspectate else "spectate_help"])
        return

    if on == "off":
        if what == "wolfchat":
            WOLFCHAT_SPECTATE.discard(wrapper.source)
        elif what == "vampchat":
            VAMPCHAT_SPECTATE.discard(wrapper.source)
        else:
            DEADCHAT_SPECTATE.discard(wrapper.source)
        wrapper.pm(messages["spectate_off_{0}".format(what)])
    else:
        if what in ("wolfchat", "vampchat"):
            if what == "wolfchat":
                already_spectating = wrapper.source in WOLFCHAT_SPECTATE
                WOLFCHAT_SPECTATE.add(wrapper.source)
                players = list(get_players(var, Wolfchat))
                if "src.roles.helper.wolves" in sys.modules:
                    from src.roles.helper.wolves import is_known_wolf_ally
                    players = [p for p in players if is_known_wolf_ally(var, p, p)]
            else:
                already_spectating = wrapper.source in VAMPCHAT_SPECTATE
                VAMPCHAT_SPECTATE.add(wrapper.source)
                players = list(get_players(var, Vampire))
                if "src.roles.vampire" in sys.modules:
                    from src.roles.vampire import is_known_vampire_ally
                    players = [p for p in players if is_known_vampire_ally(var, p, p)]

            if not is_fspectate and not already_spectating and config.Main.get("gameplay.spectate.notice"):
                if config.Main.get("gameplay.spectate.include_user"):
                    # keys used: spectate_wolfchat_notice_user spectate_vampchat_notice_user
                    key = "spectate_{0}_notice_user".format(what)
                else:
                    # keys used: spectate_wolfchat_notice spectate_vampchat_notice
                    key = "spectate_{0}_notice".format(what)
                for player in players:
                    player.queue_message(messages[key].format(wrapper.source))
                if players:
                    User.send_messages()
        elif config.Main.get("gameplay.deadchat"):
            if wrapper.source in DEADCHAT_PLAYERS:
                wrapper.pm(messages["spectate_in_deadchat"])
                return
            DEADCHAT_SPECTATE.add(wrapper.source)
            players = DEADCHAT_PLAYERS
        else:
            wrapper.pm(messages["spectate_deadchat_disabled"])
            return
        # keys used: spectate_on_deadchat spectate_on_wolfchat spectate_on_vampchat
        wrapper.pm(messages["spectate_on_{0}".format(what)])
        wrapper.pm(messages["players_list"].format(players))

@command("spectate", flag="p", pm=True, in_game_only=True)
def spectate(wrapper: MessageDispatcher, message: str):
    """Spectate wolfchat, vampire chat, or deadchat."""
    spectate_chat(wrapper, message, is_fspectate=False)

@command("fspectate", flag="F", pm=True, in_game_only=True)
def fspectate(wrapper: MessageDispatcher, message: str):
    """Spectate wolfchat, vampire chat, or deadchat."""
    spectate_chat(wrapper, message, is_fspectate=True)

@command("revealroles", flag="a", pm=True, in_game_only=True)
def revealroles(wrapper: MessageDispatcher, message: str):
    """Reveal role information."""

    if not try_restricted_cmd(wrapper, "temp_invalid_perms"):
        return

    var = wrapper.game_state

    output = []
    for role in role_order():
        if var.roles.get(role):
            # make a copy since this list is modified
            users = list(var.roles[role])
            out = []
            # go through each nickname, adding extra info if necessary
            for user in users:
                evt = Event("revealroles_role", {"special_case": []})
                evt.dispatch(var, user, role)
                special_case: list[str] = evt.data["special_case"]

                if not evt.prevent_default and user not in var.original_roles[role] and role not in var.current_mode.SECONDARY_ROLES:
                    for old_role in role_order(): # order doesn't matter here, but oh well
                        if user in var.original_roles[old_role] and user not in var.roles[old_role]:
                            special_case.append(messages["revealroles_old_role"].format(old_role))
                            break
                if special_case:
                    out.append(messages["revealroles_special"].format(user, special_case))
                else:
                    out.append(user)

            output.append(messages["revealroles_output"].format(role, out))

    evt = Event("revealroles", {"output": output})
    evt.dispatch(var)

    if config.Main.get("debug.enabled"):
        wrapper.send(*output, sep=" | ")
    else:
        wrapper.pm(*output, sep=" | ")

def join_deadchat(var: GameState, *all_users: User):
    if not config.Main.get("gameplay.deadchat") or not var.in_game:
        return

    to_join: list[User] = []
    pl = get_participants(var)

    for user in all_users:
        if user.stasis_count() or user in pl or user in DEADCHAT_PLAYERS or user not in channels.Main.users:
            continue
        to_join.append(user)

    if not to_join:
        return

    msg = messages["player_joined_deadchat"].format(to_join)
    
    people = set(DEADCHAT_PLAYERS).union(to_join) # .union() creates a new UserSet instance, but we don't want that

    for user in DEADCHAT_PLAYERS:
        user.queue_message(msg)
    for user in DEADCHAT_SPECTATE:
        user.queue_message(messages["relay_command_deadchat"].format(msg))
    for user in to_join:
        user.queue_message(messages["joined_deadchat"])
        user.queue_message(messages["players_list"].format(list(people)))

    DEADCHAT_PLAYERS.update(to_join)
    DEADCHAT_SPECTATE.difference_update(to_join)

    User.send_messages() # send all messages at once

def leave_deadchat(var: GameState, user: User, *, force=None):
    if not config.Main.get("gameplay.deadchat") or not var.in_game or user not in DEADCHAT_PLAYERS:
        return

    DEADCHAT_PLAYERS.remove(user)
    if force is None:
        user.send(messages["leave_deadchat"])
        msg = messages["player_left_deadchat"].format(user)
    else:
        user.send(messages["force_leave_deadchat"].format(force))
        msg = messages["player_force_leave_deadchat"].format(user, force)

    if DEADCHAT_PLAYERS or DEADCHAT_SPECTATE:
        for user in DEADCHAT_PLAYERS:
            user.queue_message(msg)
        for user in DEADCHAT_SPECTATE:
            user.queue_message(messages["relay_command_deadchat"].format(msg))

        User.send_messages()

@command("deadchat", pm=True)
def deadchat_pref(wrapper: MessageDispatcher, message: str):
    """Toggles auto joining deadchat on death."""
    if not config.Main.get("gameplay.deadchat"):
        return

    temp = wrapper.source.lower()

    if not wrapper.source.account:
        wrapper.pm(messages["not_logged_in"])
        return

    if temp.account in db.DEADCHAT_PREFS:
        wrapper.pm(messages["chat_on_death"])
        db.DEADCHAT_PREFS.remove(temp.account)
    else:
        wrapper.pm(messages["no_chat_on_death"])
        db.DEADCHAT_PREFS.add(temp.account)

    db.toggle_deadchat(temp.account)

@event_listener("reset")
def on_reset(evt, var):
    DEADCHAT_PLAYERS.clear()
    DEADCHAT_SPECTATE.clear()
    WOLFCHAT_SPECTATE.clear()
