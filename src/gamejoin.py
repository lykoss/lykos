
from __future__ import annotations

import threading
import time
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, Callable, List, Union, Set

from src.decorators import command
from src.functions import get_players, get_reveal_role
from src.gamestate import PregameState, GameState
from src.warnings import expire_tempbans, decrement_stasis, add_warning
from src.messages import messages
from src.status import add_dying, kill_players
from src.events import Event, EventListener, event_listener
from src.debug import handle_error
from src import db, users, channels, locks, pregame, config, trans, context, reaper, relay

if TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.channels import Channel
    from src.users import User

PINGED_ALREADY: Set[str] = set()
PINGING_PLAYERS: bool = False

@command("join", pm=True, allow_alt=False)
def join(wrapper: MessageDispatcher, message: str):
    """Either starts a new game of Werewolf or joins an existing game that has not started yet."""
    from src.wolfgame import vote_gamemode
    var = wrapper.game_state

    if not var.in_game:
        if wrapper.private:
            return

        def _cb():
            if message:
                vote_gamemode(wrapper, message.lower().split()[0], doreply=False)
        join_player(wrapper, callback=_cb)

    else: # join deadchat
        if wrapper.private and wrapper.source is not wrapper.target:
            relay.join_deadchat(var, wrapper.source)

def join_player(wrapper: MessageDispatcher,
                who: Optional[User] = None,
                forced: bool = False,
                *,
                callback: Optional[Callable] = None) -> None:
    """Join a player to the game.

    :param wrapper: Player being joined
    :param who: User who executed the join or fjoin command
    :param forced: True if this was a forced join
    :param callback: A callback that is fired upon a successful join.
    """
    if who is None:
        who = wrapper.source

    if wrapper.target is not channels.Main:
        return

    if not wrapper.source.is_fake and not wrapper.source.account:
        if forced:
            who.send(messages["account_not_logged_in"].format(wrapper.source), notice=True)
        else:
            wrapper.source.send(messages["not_logged_in"], notice=True)
        return

    if _join_player(wrapper, who, forced) and callback:
        callback() # FIXME: join_player should be async and return bool; caller can await it for result

def _join_player(wrapper: MessageDispatcher, who: Optional[User]=None, forced=False):
    var = wrapper.game_state
    pl = get_players(var)

    stasis = wrapper.source.stasis_count()

    if stasis > 0:
        if forced and stasis == 1:
            decrement_stasis(wrapper.source)
        elif wrapper.source is who:
            who.send(messages["you_stasis"].format(stasis), notice=True)
            return False
        else:
            who.send(messages["other_stasis"].format(wrapper.source, stasis), notice=True)
            return False

    temp = wrapper.source.lower()

    # don't check unacked warnings on fjoin
    if wrapper.source is who and db.has_unacknowledged_warnings(temp.account):
        wrapper.pm(messages["warn_unacked"])
        return False

    cmodes = []
    if not wrapper.source.is_fake:
        cmodes.append(("+v", wrapper.source))
    if var is None:
        channels.Main.game_state = users.Bot.game_state = var = PregameState()
        if not wrapper.source.is_fake:
            toggle_modes = config.Main.get("transports[0].channels.main.auto_mode_toggle", ())
            for mode in set(toggle_modes) & wrapper.source.channels[channels.Main]:
                cmodes.append(("-" + mode, wrapper.source))
                channels.Main.old_modes[wrapper.source].add(mode)
        var.players.append(wrapper.source)
        var.current_phase = "join"
        if wrapper.source.account:
            var.ORIGINAL_ACCS[wrapper.source] = wrapper.source.account
        if config.Main.get("timers.wait.enabled"):
            pregame.CAN_START_TIME = datetime.now() + timedelta(seconds=config.Main.get("timers.wait.initial"))
            with locks.wait:
                pregame.WAIT_TOKENS = config.Main.get("timers.wait.command.tokenbucket.initial")
                pregame.WAIT_LAST   = time.time()
        wrapper.send(messages["new_game"].format(wrapper.source))

        # Set join timer
        if config.Main.get("timers.enabled") and config.Main.get("timers.join.enabled"):
            t = threading.Timer(config.Main.get("timers.join.limit"), kill_join, [var, wrapper])
            trans.TIMERS["join"] = (t, time.time(), config.Main.get("timers.join.limit"))
            t.daemon = True
            t.start()

    elif wrapper.source in pl:
        key = "you_already_playing" if who is wrapper.source else "other_already_playing"
        who.send(messages[key], notice=True)
        return True # returning True lets them use !j mode to vote for a gamemode while already joined
    elif len(pl) >= config.Main.get("gameplay.player_limits.maximum"):
        who.send(messages["too_many_players"], notice=True)
        return False
    elif var.in_game:
        who.send(messages["game_already_running"], notice=True)
        return False
    else:
        if not config.Main.get("debug.enabled"):
            for player in pl:
                if context.equals(player.account, temp.account):
                    if who is wrapper.source:
                        who.send(messages["account_already_joined_self"].format(player), notice=True)
                    else:
                        who.send(messages["account_already_joined_other"].format(who), notice=True)
                    return

        var.players.append(wrapper.source)
        if not wrapper.source.is_fake or not config.Main.get("debug.enabled"):
            toggle_modes = config.Main.get("transports[0].channels.main.auto_mode_toggle", ())
            for mode in set(toggle_modes) & wrapper.source.channels[channels.Main]:
                cmodes.append(("-" + mode, wrapper.source))
                channels.Main.old_modes[wrapper.source].add(mode)
            wrapper.send(messages["player_joined"].format(wrapper.source, len(pl) + 1))

        # ORIGINAL_ACCS is only cleared on reset(), so can be used to determine if a player has previously joined
        # The logic in this if statement should only run once per account
        if not wrapper.source.is_fake and wrapper.source.account not in var.ORIGINAL_ACCS.values():
            if wrapper.source.account:
                var.ORIGINAL_ACCS[wrapper.source] = wrapper.source.account
            now = datetime.now()

            if config.Main.get("timers.wait.enabled"):
                # make sure there's at least wait.join seconds of wait time left, if not add them
                if now + timedelta(seconds=config.Main.get("timers.wait.join")) > pregame.CAN_START_TIME:
                    pregame.CAN_START_TIME = now + timedelta(seconds=config.Main.get("timers.wait.join"))

    with locks.join_timer:
        if "join_pinger" in trans.TIMERS:
            trans.TIMERS["join_pinger"][0].cancel()

        t = threading.Timer(10, join_timer_handler, (var,))
        trans.TIMERS["join_pinger"] = (t, time.time(), 10)
        t.daemon = True
        t.start()

    if not wrapper.source.is_fake or not config.Main.get("debug.enabled"):
        channels.Main.mode(*cmodes)

    return True

@handle_error
def kill_join(var: GameState, wrapper: MessageDispatcher):
    pl = [x.nick for x in get_players(var)]
    pl.sort(key=lambda x: x.lower())
    trans.reset(var)
    wrapper.send(*pl, first="PING! ")
    wrapper.send(messages["game_idle_cancel"])
    # use this opportunity to expire pending stasis
    db.expire_stasis()
    db.init_vars()
    expire_tempbans()
    if trans.ENDGAME_COMMAND is not None:
        trans.ENDGAME_COMMAND()
        trans.ENDGAME_COMMAND = None

@command("fjoin", flag="A")
def fjoin(wrapper: MessageDispatcher, message: str):
    """Force someone to join a game.

    :param wrapper: Dispatcher
    :param message: Command text. If empty, we join ourselves
    """
    var = wrapper.game_state

    success = False
    if not message.strip():
        join_player(wrapper, forced=True)
        return

    parts = re.split(" +", message)
    to_join: List[Union[User, str]] = []
    debug_mode = config.Main.get("debug.enabled")
    if not debug_mode:
        match = users.complete_match(parts[0], wrapper.target.users)
        if match:
            to_join.append(match.get())
    else:
        for s in parts:
            match = users.complete_match(s, wrapper.target.users)
            if match:
                to_join.append(match.get())
            elif debug_mode and re.fullmatch(r"[0-9+](?:-[0-9]+)?", s):
                # in debug mode, allow joining fake nicks
                to_join.append(s)
    for tojoin in to_join:
        if isinstance(tojoin, users.User):
            if tojoin is users.Bot:
                wrapper.pm(messages["not_allowed"])
            else:
                join_player(type(wrapper)(tojoin, wrapper.target), forced=True, who=wrapper.source)
                success = True
        # Allow joining single number fake users in debug mode
        elif users.predicate(tojoin) and debug_mode:
            user = users.add(wrapper.client, nick=tojoin)
            join_player(type(wrapper)(user, wrapper.target), forced=True, who=wrapper.source)
            success = True
        # Allow joining ranges of numbers as fake users in debug mode
        elif "-" in tojoin and debug_mode:
            first, hyphen, last = tojoin.partition("-")
            if first.isdigit() and last.isdigit():
                if int(last)+1 - int(first) > config.Main.get("gameplay.player_limits.maximum") - len(get_players(var)):
                    wrapper.send(messages["too_many_players_to_join"].format(wrapper.source))
                    break
                success = True
                for i in range(int(first), int(last)+1):
                    user = users.add(wrapper.client, nick=str(i))
                    join_player(type(wrapper)(user, wrapper.target), forced=True, who=wrapper.source)
    if success:
        wrapper.send(messages["fjoin_success"].format(wrapper.source, len(get_players(var))))

@command("pingif", pm=True)
def altpinger(wrapper: MessageDispatcher, message: str):
    """Pings you when the number of players reaches your preference. Usage: "pingif <players>". https://werewolf.chat/Pingif"""

    if not wrapper.source.account:
        wrapper.pm(messages["not_logged_in"])
        return

    players = wrapper.source.get_pingif_count()
    args = message.lower().split()

    msg = []

    if not args:
        if players:
            msg.append(messages["get_pingif"].format(players))
        else:
            msg.append(messages["no_pingif"])

    elif any((args[0] in ("off", "never"),
              args[0].isdigit() and int(args[0]) == 0,
              len(args) > 1 and args[1].isdigit() and int(args[1]) == 0)):

        if players:
            msg.append(messages["unset_pingif"].format(players))
            wrapper.source.set_pingif_count(0, players)
        else:
            msg.append(messages["no_pingif"])

    elif args[0].isdigit() or (len(args) > 1 and args[1].isdigit()):
        if args[0].isdigit():
            num = int(args[0])
        else:
            num = int(args[1])
        if num > 999:
            msg.append(messages["pingif_too_large"])
        elif players == num:
            msg.append(messages["pingif_already_set"].format(num))
        elif players:
            msg.append(messages["pingif_change"].format(players, num))
            wrapper.source.set_pingif_count(num, players)
        else:
            msg.append(messages["set_pingif"].format(num))
            wrapper.source.set_pingif_count(num)

    else:
        msg.append(messages["pingif_invalid"])

    wrapper.pm(*msg, sep="\n")

@handle_error
def join_timer_handler(var):
    global PINGING_PLAYERS
    with locks.join_timer:
        PINGING_PLAYERS = True
        to_ping: List[User] = []
        pl = get_players(var)

        chk_acc = set()

        # Add accounts/hosts to the list of possible players to ping
        for num in db.PING_IF_NUMS:
            if num <= len(pl):
                for acc in db.PING_IF_NUMS[num]:
                    if db.has_unacknowledged_warnings(acc):
                        continue
                    chk_acc.add(users.lower(acc))

        # Don't ping alt connections of users that have already joined
        for player in pl:
            PINGED_ALREADY.add(users.lower(player.account))

        # Remove players who have already been pinged from the list of possible players to ping
        chk_acc -= PINGED_ALREADY

        # If there is nobody to ping, do nothing
        if not chk_acc:
            PINGING_PLAYERS = False
            return

        def get_altpingers(event: Event, chan: Channel, user: User):
            if (event.params.away or user.stasis_count() or not PINGING_PLAYERS or
                chan is not channels.Main or user is users.Bot or user in pl):
                return

            temp = user.lower()
            if temp.account in chk_acc:
                to_ping.append(temp)
                PINGED_ALREADY.add(temp.account)
                return

        def ping_altpingers(event, request):
            if request is channels.Main:
                global PINGING_PLAYERS
                PINGING_PLAYERS = False
                if to_ping:
                    to_ping.sort(key=lambda x: x.nick)
                    user_list = [(user.ref or user).nick for user in to_ping]

                    msg_prefix = messages["ping_player"].format(len(pl))
                    channels.Main.send(*user_list, first=msg_prefix)
                    del to_ping[:]

                who_result.remove("who_result")
                who_end.remove("who_end")

        who_result = EventListener(get_altpingers)
        who_result.install("who_result")
        who_end = EventListener(ping_altpingers)
        who_end.install("who_end")

        channels.Main.who()

@command("leave", pm=True, phases=("join", "day", "night"))
def leave_game(wrapper: MessageDispatcher, message: str):
    """Quits the game."""
    var = wrapper.game_state
    if wrapper.target is channels.Main:
        if wrapper.source not in get_players(var):
            return
        if var.current_phase == "join":
            lpl = len(get_players(var)) - 1
            if lpl == 0:
                population = " " + messages["no_players_remaining"]
            else:
                population = " " + messages["new_player_count"].format(lpl)
        else:
            args = re.split(" +", message)
            if args[0] not in messages.raw("_commands", "leave opt force"):
                wrapper.pm(messages["leave_game_ingame_safeguard"])
                return
            population = ""
    elif wrapper.private:
        if var.in_game and wrapper.source not in get_players(var) and wrapper.source in relay.DEADCHAT_PLAYERS:
            relay.leave_deadchat(var, wrapper.source)
        return
    else:
        return

    if var.in_game and var.role_reveal in ("on", "team"):
        role = get_reveal_role(var, wrapper.source)
        channels.Main.send(messages["quit_reveal"].format(wrapper.source, role) + population)
    else:
        channels.Main.send(messages["quit_no_reveal"].format(wrapper.source) + population)
    if var.current_phase != "join":
        reaper.DCED_LOSERS.add(wrapper.source)
        if config.Main.get("reaper.enabled") and config.Main.get("reaper.leave.enabled"):
            reaper.NIGHT_IDLED.discard(wrapper.source) # don't double-dip if they idled out night as well
            add_warning(wrapper.source, config.Main.get("reaper.leave.points"), users.Bot, messages["leave_warning"], expires=config.Main.get("reaper.leave.expiration"))

    add_dying(var, wrapper.source, "bot", "quit", death_triggers=False)
    kill_players(var)

@command("fleave", flag="A", pm=True, phases=("join", "day", "night"))
def fleave(wrapper: MessageDispatcher, message: str):
    """Force someone to leave the game."""

    var = wrapper.game_state

    for person in re.split(" +", message):
        person = person.strip()
        if not person:
            continue

        target = users.complete_match(person, get_players(var))
        dead_target = None
        if var.in_game:
            dead_target = users.complete_match(person, relay.DEADCHAT_PLAYERS)
        if target:
            target = target.get()
            if wrapper.target is not channels.Main:
                wrapper.pm(messages["fquit_fail"])
                return

            msg = [messages["fquit_success"].format(wrapper.source, target)]
            if var.in_game and var.role_reveal in ("on", "team"):
                msg.append(messages["fquit_goodbye"].format(get_reveal_role(var, target)))
            if var.current_phase == "join":
                player_count = len(get_players(var)) - 1
                to_say = "new_player_count"
                if not player_count:
                    to_say = "no_players_remaining"
                msg.append(messages[to_say].format(player_count))

            wrapper.send(*msg)

            if var.current_phase != "join":
                reaper.DCED_LOSERS.add(target)

            add_dying(var, target, "bot", "fquit", death_triggers=False)
            kill_players(var)

        elif dead_target:
            dead_target = dead_target.get()
            relay.leave_deadchat(var, dead_target, force=wrapper.source)
            if wrapper.source not in relay.DEADCHAT_PLAYERS:
                wrapper.pm(messages["admin_fleave_deadchat"].format(dead_target))

        else:
            wrapper.send(messages["not_playing"].format(person))
            return

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    global PINGING_PLAYERS
    PINGED_ALREADY.clear()
    PINGING_PLAYERS = False
