from __future__ import annotations

from datetime import datetime, timedelta
import typing

from src.functions import match_mode, match_role
from src.messages import messages
from src.decorators import command
from src import channels, users, config, db

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from typing import Optional

LAST_GSTATS: Optional[datetime] = None
LAST_PSTATS: Optional[datetime] = None
LAST_RSTATS: Optional[datetime] = None

@command("gamestats", pm=True)
def game_stats(wrapper: MessageDispatcher, message: str):
    """Get the game stats for a given game size or lists game totals for all game sizes if no game size is given."""
    # NOTE: Need to dynamically translate roles and gamemodes
    if wrapper.public:
        global LAST_GSTATS
        if (LAST_GSTATS and config.Main.get("ratelimits.gamestats", 0) and
            LAST_GSTATS + timedelta(seconds=config.Main.get("ratelimits.gamestats")) > datetime.now()):
            wrapper.pm(messages["command_ratelimited"])
            return

        if wrapper.game_state and wrapper.game_state.in_game and wrapper.target is channels.Main:
            wrapper.pm(messages["stats_wait_for_game_end"])
            return

        LAST_GSTATS = datetime.now()

    gamemode = "*"
    gamesize = None
    msg = message.split()
    # Check for gamemode
    if msg and not msg[0].isdigit():
        gamemode = msg[0]
        if gamemode != "*":
            matches = match_mode(gamemode, remove_spaces=True, allow_extra=True)
            if matches:
                gamemode = matches.get().key
            elif len(matches) == 0:
                wrapper.pm(messages["invalid_mode"].format(msg[0]))
                return
            else:
                wrapper.pm(messages["ambiguous_mode"].format([m.local for m in matches]))
                return
        msg.pop(0)

    if msg and msg[0].isdigit():
        gamesize = int(msg[0])

    # List all games sizes and totals if no size is given
    if not gamesize:
        wrapper.send(db.get_game_totals(gamemode))
    else:
        # Attempt to find game stats for the given game size
        wrapper.send(db.get_game_stats(gamemode, gamesize))

@command("playerstats", pm=True)
def player_stats(wrapper: MessageDispatcher, message: str):
    """Gets the stats for the given player and role or a list of role totals if no role is given."""
    # NOTE: Need to dynamically translate gamemodes
    if wrapper.public:
        global LAST_PSTATS
        if (LAST_PSTATS and config.Main.get("ratelimits.playerstats", 0) and
            LAST_PSTATS + timedelta(seconds=config.Main.get("ratelimits.playerstats")) > datetime.now()):
            wrapper.pm(messages["command_ratelimited"])
            return

        if wrapper.game_state and wrapper.game_state.in_game and wrapper.target is channels.Main:
            wrapper.pm(messages["no_command_in_channel"])
            return

        LAST_PSTATS = datetime.now()

    params = message.split()

    # Check if we have enough parameters
    if params:
        match = users.complete_match(params[0])
        if len(match) == 0:
            user = None
            account = params[0]
        elif not match:
            user = None
            account = None
        else:
            user = match.get()
            account = user.account
    else:
        user = wrapper.source
        account = user.account

    if account is None:
        key = "account_not_logged_in"
        if user is wrapper.source:
            key = "not_logged_in"
        wrapper.pm(messages[key].format(params[0]))
        return

    # List the player's total games for all roles if no role is given
    if len(params) < 2:
        msg, totals = db.get_player_totals(account)
        wrapper.pm(msg)
        wrapper.pm(*totals, sep=", ")
    else:
        role = " ".join(params[1:])
        matches = match_role(role, allow_extra=True)

        if len(matches) == 0:
            wrapper.send(messages["no_such_role"].format(role))
            return
        elif len(matches) > 1:
            wrapper.send(messages["ambiguous_role"].format([m.singular for m in matches]))
            return

        role = matches.get().key
        wrapper.send(db.get_player_stats(account, role))

@command("mystats", pm=True)
def my_stats(wrapper: MessageDispatcher, message: str):
    """Get your own stats."""
    msg = message.split()
    player_stats.func(wrapper, " ".join([wrapper.source.nick] + msg))

@command("rolestats", pm=True)
def role_stats(wrapper: MessageDispatcher, message: str):
    """Gets the stats for a given role in a given gamemode or lists role totals across all games if no role is given."""
    if wrapper.public:
        global LAST_RSTATS
        if (LAST_RSTATS and config.Main.get("ratelimits.rolestats", 0) and
            LAST_RSTATS + timedelta(seconds=config.Main.get("ratelimits.rolestats")) > datetime.now()):
            wrapper.pm(messages["command_ratelimited"])
            return

        
        if wrapper.game_state and wrapper.game_state.in_game and wrapper.target is channels.Main:
            wrapper.pm(messages["stats_wait_for_game_end"])
            return

        LAST_RSTATS = datetime.now()

    params = message.split()
    
    if not params:
        first, totals = db.get_role_totals()
        wrapper.pm(*totals, sep=", ", first=first)
        return

    roles = match_role(message, allow_extra=True)
    if params[-1] == "*" and not roles:
        role = " ".join(params[:-1])
        roles = match_role(role, allow_extra=True)
        if not roles:
            if len(roles) > 0:
                wrapper.pm(messages["ambiguous_role"].format(roles))
            else:
                wrapper.pm(messages["no_such_role"].format(role))
            return

    if roles:
        wrapper.pm(db.get_role_stats(roles.get().key))
        return

    gamemode = params[-1]
    roles = match_role(" ".join(params[:-1]), allow_extra=True)
    matches = match_mode(gamemode, remove_spaces=True, allow_extra=True)
    if matches and roles:
        gamemode = matches.get().key
    else:
        if len(roles) > 0:
            wrapper.pm(messages["ambiguous_role"].format(roles))
        elif len(matches) > 0:
            wrapper.pm(messages["ambiguous_mode"].format([m.local for m in matches]))
        else:
            wrapper.pm(messages["no_such_role"].format(message))
        return

    if len(params) == 1:
        first, totals = db.get_role_totals(gamemode)
        wrapper.pm(*totals, sep=", ", first=first)
        return

    wrapper.pm(db.get_role_stats(roles.get().key, gamemode))
