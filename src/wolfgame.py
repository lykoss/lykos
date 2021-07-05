# Copyright (c) 2011, Jimmy Cao All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.  Redistributions in binary
# form must reproduce the above copyright notice, this list of conditions and
# the following disclaimer in the documentation and/or other materials provided
# with the distribution.  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS
# AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING,
# BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER
# OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import annotations

import itertools
import json
import os
import platform
import random
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request

from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import FrozenSet, Set, Optional, Callable

from src import db, config, locks, dispatcher, channels, users, hooks, handler, trans
from src.users import User

from src.debug import handle_error
from src.events import Event, EventListener, event_listener
from src.transport.irc import get_ircd
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.decorators import command, hook, COMMANDS
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState
from src.gamemodes import GAME_MODES
from src.messages import messages, LocalMode
from src.warnings import *
from src.context import IRCContext
from src.status import try_protection, add_dying, is_dying, kill_players, get_absent, is_silent
from src.votes import chk_decision
from src.trans import chk_win, chk_nightdone, reset, stop_game
from src.cats import (
    Wolf, Wolfchat, Wolfteam, Killer, Village, Neutral, Hidden, Wolf_Objective, Village_Objective,
    role_order
    )

from src.functions import (
    get_players, get_all_players, get_participants,
    get_main_role, get_all_roles, get_reveal_role,
    get_target, change_role, match_role, match_mode
   )

# Game Logic Begins:

var.LAST_STATS = None  # type: ignore
var.LAST_ADMINS = None  # type: ignore
var.LAST_TIME = None  # type: ignore
var.LAST_GOAT = UserDict() # type: ignore # actually UserDict[users.User, datetime]

var.ADMIN_PINGING = False  # type: ignore
var.DCED_LOSERS = UserSet()  # type: ignore
var.ADMIN_TO_PING = None  # type: ignore
var.AFTER_FLASTGAME = None  # type: ignore
var.PINGING_IFS = False  # type: ignore
var.PHASE = "none"  # type: ignore

var.ROLES = UserDict() # type: ignore # actually UserDict[str, UserSet]
var.ORIGINAL_ROLES = UserDict() # type: ignore # actually UserDict[str, UserSet]
var.MAIN_ROLES = UserDict() # type: ignore # actually UserDict[users.User, str]
var.ORIGINAL_MAIN_ROLES = UserDict() # type: ignore # actually UserDict[users.User, str]
var.FINAL_ROLES = UserDict() # type: ignore # actually UserDict[users.User, str]
var.ALL_PLAYERS = UserList() # type: ignore
var.FORCE_ROLES = DefaultUserDict(UserSet) # type: ignore
var.ORIGINAL_ACCS = UserDict() # type: ignore # actually UserDict[users.User, str]

var.IDLE_WARNED = UserSet() # type: ignore
var.IDLE_WARNED_PM = UserSet() # type: ignore
var.NIGHT_IDLE_EXEMPT = UserSet() # type: ignore

var.DEAD = UserSet() # type: ignore

var.DEADCHAT_PLAYERS = UserSet() # type: ignore

var.SPECTATING_WOLFCHAT = UserSet() # type: ignore
var.SPECTATING_DEADCHAT = UserSet() # type: ignore

var.ORIGINAL_SETTINGS = {} # type: ignore
var.GAMEMODE_VOTES = UserDict() # type: ignore

var.LAST_SAID_TIME = UserDict() # type: ignore

var.GAME_START_TIME = datetime.now()  # type: ignore # for idle checker only
var.CAN_START_TIME = 0 # type: ignore

var.DISCONNECTED = UserDict() # type: ignore # actually UserDict[User, Tuple[datetime, str]]

var.RESTARTING = False # type: ignore

def connect_callback():
    db.init_vars()
    SIGUSR1 = getattr(signal, "SIGUSR1", None)
    SIGUSR2 = getattr(signal, "SIGUSR2", None)

    def sighandler(signum, frame):
        wrapper = dispatcher.MessageDispatcher(users.FakeUser.from_nick("<console>"), channels.Main)
        if signum == signal.SIGINT:
            # Exit immediately if Ctrl-C is pressed twice
            signal.signal(signal.SIGINT, signal.SIG_DFL)

        if signum in (signal.SIGINT, signal.SIGTERM):
            forced_exit.func(wrapper, "")
        elif signum == SIGUSR1:
            restart_program.func(wrapper, "")
        elif signum == SIGUSR2:
            plog("Scheduling aftergame restart")
            aftergame.func(wrapper, "frestart")

    signal.signal(signal.SIGINT, sighandler)
    signal.signal(signal.SIGTERM, sighandler)

    if SIGUSR1:
        signal.signal(SIGUSR1, sighandler)

    if SIGUSR2:
        signal.signal(SIGUSR2, sighandler)

    def who_end(event, request):
        if request is channels.Main:
            # Devoice all on connect
            mode = hooks.Features["PREFIX"]["+"]
            pending = []
            for user in channels.Main.modes.get(mode, ()):
                pending.append(("-" + mode, user))
            accumulator.send(pending)
            next(accumulator, None)

            # Expire tempbans
            expire_tempbans()

            players = db.get_pre_restart_state()
            if players:
                channels.Main.send(*players, first="PING! ")
                channels.Main.send(messages["game_restart_cancel"])

            var.CURRENT_GAMEMODE = GAME_MODES["default"][0]()
            reset(channels.Main.game_state)

            who_end_listener.remove("who_end")

    def end_listmode(event, chan, mode):
        if chan is channels.Main and mode == get_ircd().quiet_mode:
            pending = []
            for quiet in chan.modes.get(mode, ()):
                if re.search(r"^{0}.+\!\*@\*$".format(get_ircd().quiet_prefix), quiet):
                    pending.append(("-" + mode, quiet))
            accumulator.send(pending)
            next(accumulator, None)

            end_listmode_listener.remove("end_listmode")

    def mode_change(event, actor, target):
        if target is channels.Main: # we may or may not be opped; assume we are
            accumulator.send([])
            next(accumulator, None)

            mode_change_listener.remove("mode_change")

    who_end_listener = EventListener(who_end)
    who_end_listener.install("who_end")
    end_listmode_listener = EventListener(end_listmode)
    end_listmode_listener.install("end_listmode")
    mode_change_listener = EventListener(mode_change)
    mode_change_listener.install("mode_change")

    def accumulate_cmodes(count):
        modes = []
        for i in range(count):
            item = yield
            modes.extend(item)
            yield i

        if modes:
            channels.Main.mode(*modes)

    accumulator = accumulate_cmodes(3)
    accumulator.send(None)

@command("sync", flag="m", pm=True)
def fsync(wrapper: MessageDispatcher, message: str):
    """Makes the bot apply the currently appropriate channel modes."""
    sync_modes()

@event_listener("sync_modes")
def on_sync_modes(evt):
    sync_modes()

def sync_modes():
    game_state = channels.Main.game_state
    if game_state:
        voices = [None]
        mode = hooks.Features["PREFIX"]["+"]
        pl = get_players(game_state)

        for user in channels.Main.users:
            if config.Main.get("gameplay.nightchat") and game_state.PHASE == "night":
                if mode in user.channels[channels.Main]:
                    voices.append(("-" + mode, user))
            elif user in pl and mode not in user.channels[channels.Main]:
                voices.append(("+" + mode, user))
            elif user not in pl and mode in user.channels[channels.Main]:
                voices.append(("-" + mode, user))

        if game_state.in_game:
            voices[0] = "+m"
        else:
            voices[0] = "-m"

        channels.Main.mode(*voices)

@command("refreshdb", flag="m", pm=True)
def refreshdb(wrapper: MessageDispatcher, message: str):
    """Updates our tracking vars to the current db state."""
    db.expire_stasis()
    db.init_vars()
    expire_tempbans()
    wrapper.reply("Done.")

@command("fdie", flag="F", pm=True)
def forced_exit(wrapper: MessageDispatcher, message: str):
    """Forces the bot to close."""

    var = wrapper.game_state

    args = message.split()

    # Force in debug mode by default
    force = config.Main.get("debug.enabled")

    if args and args[0] == "-dirty":
        # use as a last resort
        os.abort()
    elif args and args[0] == "-force":
        force = True
        message = " ".join(args[1:])

    if var.PHASE in var.GAME_PHASES:
        if var.PHASE == "join" or force or wrapper.source.nick == "<console>":
            stop_game(var, log=False)
        else:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(what="stop", cmd="fdie"))
            return

    reset_modes_timers(var)
    reset(var)

    msg = "{0} quit from {1}"

    if message.strip():
        msg += " ({2})"

    hooks.quit(wrapper, msg.format("Scheduled" if forced_exit.aftergame else "Forced",
               wrapper.source, message.strip()))

def _restart_program(mode=None):
    plog("RESTARTING")

    python = sys.executable

    # FIXME: should maintain the same --config option
    if mode is not None:
        print(mode)
        assert mode in ("debug",)
        os.execl(python, python, sys.argv[0], "--{0}".format(mode))
    else:
        import src
        args = []
        if config.Main.get("debug.enabled"):
            args.append("--debug")
        os.execl(python, python, sys.argv[0], *args)


@command("frestart", flag="D", pm=True)
def restart_program(wrapper: MessageDispatcher, message: str):
    """Restarts the bot."""

    var = wrapper.game_state

    args = message.split()

    # Force in debug mode by default
    force = config.Main.get("debug.enabled")

    if args and args[0] == "-force":
        force = True
        message = " ".join(args[1:])

    if var.PHASE in var.GAME_PHASES:
        if var.PHASE == "join" or force:
            stop_game(var, log=False)
        else:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(what="restart", cmd="frestart"))
            return

    reset_modes_timers(var)
    db.set_pre_restart_state(p.nick for p in get_players(var))
    reset(var)

    msg = "{0} restart from {1}".format(
        "Scheduled" if restart_program.aftergame else "Forced", wrapper.source)

    message = message.strip()
    mode = None

    if message:
        args = message.split()
        first_arg = args[0].lower()

        if first_arg.endswith("mode") and first_arg != "mode":
            mode = first_arg.replace("mode", "")

            valid_modes = ("normal", "verbose", "debug")

            if mode not in valid_modes:
                wrapper.pm(messages["invalid_restart_mode"].format(mode, valid_modes))
                return

            msg += " in {0} mode".format(mode)
            message = " ".join(args[1:])

    if message:
        msg += " ({0})".format(message.strip())

    hooks.quit(wrapper, msg.format(wrapper.source, message.strip()))

    def restart_buffer(evt, user, reason):
        # restart the bot once our quit message goes though to ensure entire IRC queue is sent
        if user is users.Bot:
            _restart_program(mode)

    EventListener(restart_buffer).install("server_quit")

    # This is checked in the on_error handler. Some IRCds, such as InspIRCd, don't send the bot
    # its own QUIT message, so we need to use ERROR. Ideally, we shouldn't even need the above
    # handler now, but I'm keeping it for now just in case.
    var.RESTARTING = True

@command("ping", pm=True)
def pinger(wrapper: MessageDispatcher, message: str):
    """Check if you or the bot is still connected."""
    wrapper.reply(messages["ping"].format(nick=wrapper.source, bot_nick=users.Bot))

@command("notice", pm=True)
def mark_prefer_notice(wrapper: MessageDispatcher, message: str):
    """Makes the bot NOTICE you for every interaction."""

    if wrapper.private and message:
        # Ignore if called in PM with parameters, likely a message to wolfchat
        # and not an intentional invocation of this command
        return

    temp = wrapper.source.lower()

    account = temp.account

    if account is None:
        wrapper.pm(messages["not_logged_in"])
        return

    notice = wrapper.source.prefers_notice()
    # FIXME: Should not use var here
    action, toggle = (var.PREFER_NOTICE_ACCS.discard, "off") if notice else (var.PREFER_NOTICE_ACCS.add, "on")

    action(account)
    db.toggle_notice(account)
    wrapper.pm(messages["notice_" + toggle])

@command("swap", pm=True, phases=("join", "day", "night"))
def replace(wrapper: MessageDispatcher, message: str):
    """Swap out a player logged in to your account."""
    if wrapper.source not in channels.Main.users:
        wrapper.pm(messages["invalid_channel"].format(channels.Main))
        return

    var = wrapper.game_state

    if wrapper.source in get_players(var):
        wrapper.pm(messages["you_already_playing"])
        return

    if wrapper.source.account is None:
        wrapper.pm(messages["not_logged_in"])
        return

    pl = get_participants(var)
    target = None

    for user in var.ALL_PLAYERS:
        if users.equals(user.account, wrapper.source.account):
            if user is wrapper.source or user not in pl:
                continue
            elif target is None:
                target = user
            else:
                wrapper.pm(messages["swap_notice"])
                return

    if target is None:
        wrapper.pm(messages["account_not_playing"])
        return
    elif target is not wrapper.source:
        target.swap(wrapper.source)
        if var.PHASE in var.GAME_PHASES:
            return_to_village(var, wrapper.source, show_message=False)

        cmodes = []

        if not var.DEVOICE_DURING_NIGHT or var.PHASE != "night":
            cmodes += [("-v", target), ("+v", wrapper.source)]

        toggle_modes = config.Main.get("transports[0].channels.main.auto_mode_toggle", ())
        for mode in set(toggle_modes) & wrapper.source.channels[channels.Main]: # user.channels is a set of current modes
            cmodes.append(("-" + mode, wrapper.source))
            channels.Main.old_modes[wrapper.source].add(mode)

        for mode in channels.Main.old_modes[target]:
            cmodes.append(("+" + mode, target))

        channels.Main.mode(*cmodes)

        channels.Main.send(messages["player_swap"].format(wrapper.source, target))
        if var.PHASE in var.GAME_PHASES:
            myrole.func(wrapper, "")

@command("pingif", pm=True)
def altpinger(wrapper: MessageDispatcher, message: str):
    """Pings you when the number of players reaches your preference. Usage: "pingif <players>". https://werewolf.chat/Pingif"""

    if wrapper.source.account is None:
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
    with locks.join_timer:
        var.PINGING_IFS = True
        to_ping = []
        pl = get_players(var)

        chk_acc = set()

        # Add accounts/hosts to the list of possible players to ping
        for num in var.PING_IF_NUMS_ACCS:
            if num <= len(pl):
                for acc in var.PING_IF_NUMS_ACCS[num]:
                    if db.has_unacknowledged_warnings(acc):
                        continue
                    chk_acc.add(users.lower(acc))

        # Don't ping alt connections of users that have already joined
        for player in pl:
            var.PINGED_ALREADY_ACCS.add(users.lower(player.account))

        # Remove players who have already been pinged from the list of possible players to ping
        chk_acc -= var.PINGED_ALREADY_ACCS

        # If there is nobody to ping, do nothing
        if not chk_acc:
            var.PINGING_IFS = False
            return

        def get_altpingers(event, chan, user):
            if (event.params.away or user.stasis_count() or not var.PINGING_IFS or
                chan is not channels.Main or user is users.Bot or user in pl):
                return

            temp = user.lower()
            if temp.account in chk_acc:
                to_ping.append(temp)
                var.PINGED_ALREADY_ACCS.add(temp.account)
                return

        def ping_altpingers(event, request):
            if request is channels.Main:
                var.PINGING_IFS = False
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

def join_deadchat(var, *all_users):
    if not var.ENABLE_DEADCHAT or var.PHASE not in var.GAME_PHASES:
        return

    to_join = []
    pl = get_participants(var)

    for user in all_users:
        if user.stasis_count() or user in pl or user in var.DEADCHAT_PLAYERS or user not in channels.Main.users:
            continue
        to_join.append(user)

    if not to_join:
        return

    msg = messages["player_joined_deadchat"].format(to_join)
    
    people = var.DEADCHAT_PLAYERS.union(to_join)

    for user in var.DEADCHAT_PLAYERS:
        user.queue_message(msg)
    for user in var.SPECTATING_DEADCHAT:
        user.queue_message("[deadchat] " + msg)
    for user in to_join:
        user.queue_message(messages["joined_deadchat"])
        user.queue_message(messages["players_list"].format(list(people)))

    var.DEADCHAT_PLAYERS.update(to_join)
    var.SPECTATING_DEADCHAT.difference_update(to_join)

    user.send_messages() # send all messages at once

def leave_deadchat(var, user, *, force=None):
    if not var.ENABLE_DEADCHAT or var.PHASE not in var.GAME_PHASES or user not in var.DEADCHAT_PLAYERS:
        return

    var.DEADCHAT_PLAYERS.remove(user)
    if force is None:
        user.send(messages["leave_deadchat"])
        msg = messages["player_left_deadchat"].format(user)
    else:
        user.send(messages["force_leave_deadchat"].format(force))
        msg = messages["player_force_leave_deadchat"].format(user, force)

    if var.DEADCHAT_PLAYERS or var.SPECTATING_DEADCHAT:
        for user in var.DEADCHAT_PLAYERS:
            user.queue_message(msg)
        for user in var.SPECTATING_DEADCHAT:
            user.queue_message("[deadchat] " + msg)

        user.send_messages()

@command("deadchat", pm=True)
def deadchat_pref(wrapper: MessageDispatcher, message: str):
    """Toggles auto joining deadchat on death."""

    var = wrapper.game_state

    if not var.ENABLE_DEADCHAT:
        return

    temp = wrapper.source.lower()

    if wrapper.source.account is None:
        wrapper.pm(messages["not_logged_in"])
        return

    if temp.account in var.DEADCHAT_PREFS_ACCS:
        wrapper.pm(messages["chat_on_death"])
        var.DEADCHAT_PREFS_ACCS.remove(temp.account)
    else:
        wrapper.pm(messages["no_chat_on_death"])
        var.DEADCHAT_PREFS_ACCS.add(temp.account)

    db.toggle_deadchat(temp.account)

@command("join", pm=True, allow_alt=False)
def join(wrapper: MessageDispatcher, message: str):
    """Either starts a new game of Werewolf or joins an existing game that has not started yet."""
    # keep this and the event in fjoin() in sync
    var = wrapper.game_state
    evt = Event("join", {
        "join_player": join_player,
        "join_deadchat": join_deadchat,
        "vote_gamemode": vote_gamemode
        })
    if not evt.dispatch(var, wrapper, message, forced=False): # FIXME: Remove var from this
        return
    if var.PHASE in ("none", "join"):
        if wrapper.private:
            return

        def _cb():
            if message:
                evt.data["vote_gamemode"](var, wrapper, message.lower().split()[0], doreply=False)
        evt.data["join_player"](var, wrapper, callback=_cb) # FIXME: remove var

    else: # join deadchat
        if wrapper.private and wrapper.source is not wrapper.target:
            evt.data["join_deadchat"](var, wrapper.source)

def join_player(var, wrapper: MessageDispatcher, # FIXME: remove var
                who: Optional[User] = None,
                forced: bool = False,
                *,
                callback: Optional[Callable] = None) -> None:
    """Join a player to the game.

    :param var: Deprecated
    :param wrapper: Player being joined
    :param who: User who executed the join or fjoin command
    :param forced: True if this was a forced join
    :param callback: A callback that is fired upon a successful join.
    """
    if who is None:
        who = wrapper.source

    if wrapper.target is not channels.Main:
        return

    var = wrapper.game_state

    if not wrapper.source.is_fake and wrapper.source.account is None:
        if forced:
            who.send(messages["account_not_logged_in"].format(wrapper.source), notice=True)
        else:
            wrapper.source.send(messages["not_logged_in"], notice=True)
        return

    if _join_player(var, wrapper, who, forced) and callback: # FIXME: remove var
        callback() # FIXME: join_player should be async and return bool; caller can await it for result

def _join_player(var, wrapper: MessageDispatcher, who=None, forced=False): # FIXME: remove var
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
    if var.PHASE == "none":
        if not wrapper.source.is_fake:
            toggle_modes = config.Main.get("transports[0].channels.main.auto_mode_toggle", ())
            for mode in set(toggle_modes) & wrapper.source.channels[channels.Main]:
                cmodes.append(("-" + mode, wrapper.source))
                channels.Main.old_modes[wrapper.source].add(mode)
        var.ROLES["person"].add(wrapper.source)
        var.MAIN_ROLES[wrapper.source] = "person"
        var.ALL_PLAYERS.append(wrapper.source)
        var.PHASE = "join"
        from src import pregame
        with pregame.WAIT_LOCK:
            pregame.WAIT_TOKENS = var.WAIT_TB_INIT
            pregame.WAIT_LAST   = time.time()
        var.GAME_ID = time.time()
        var.PINGED_ALREADY_ACCS = set()
        var.PINGED_ALREADY = set()
        if wrapper.source.account:
            var.ORIGINAL_ACCS[wrapper.source] = wrapper.source.account
        var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.MINIMUM_WAIT)
        wrapper.send(messages["new_game"].format(wrapper.source))

        # Set join timer
        if var.JOIN_TIME_LIMIT > 0:
            t = threading.Timer(var.JOIN_TIME_LIMIT, kill_join, [var, wrapper])
            trans.TIMERS["join"] = (t, time.time(), var.JOIN_TIME_LIMIT)
            t.daemon = True
            t.start()

    elif wrapper.source in pl:
        key = "you_already_playing" if who is wrapper.source else "other_already_playing"
        who.send(messages[key], notice=True)
        return True # returning True lets them use !j mode to vote for a gamemode while already joined
    elif len(pl) >= var.MAX_PLAYERS:
        who.send(messages["too_many_players"], notice=True)
        return False
    elif var.PHASE != "join":
        who.send(messages["game_already_running"], notice=True)
        return False
    else:
        if not config.Main.get("debug.enabled"):
            for player in pl:
                if users.equals(player.account, temp.account):
                    if who is wrapper.source:
                        who.send(messages["account_already_joined_self"].format(player), notice=True)
                    else:
                        who.send(messages["account_already_joined_other"].format(who), notice=True)
                    return

        var.ALL_PLAYERS.append(wrapper.source)
        if not wrapper.source.is_fake or not config.Main.get("debug.enabled"):
            toggle_modes = config.Main.get("transports[0].channels.main.auto_mode_toggle", ())
            for mode in set(toggle_modes) & wrapper.source.channels[channels.Main]:
                cmodes.append(("-" + mode, wrapper.source))
                channels.Main.old_modes[wrapper.source].add(mode)
            wrapper.send(messages["player_joined"].format(wrapper.source, len(pl) + 1))

        var.ROLES["person"].add(wrapper.source)
        var.MAIN_ROLES[wrapper.source] = "person"
        # ORIGINAL_ACCS is only cleared on reset(), so can be used to determine if a player has previously joined
        # The logic in this if statement should only run once per account
        if not wrapper.source.is_fake and wrapper.source.account not in var.ORIGINAL_ACCS.values():
            if wrapper.source.account:
                var.ORIGINAL_ACCS[wrapper.source] = wrapper.source.account
            now = datetime.now()

            # add var.EXTRA_WAIT_JOIN to wait time
            if now > var.CAN_START_TIME:
                var.CAN_START_TIME = now + timedelta(seconds=var.EXTRA_WAIT_JOIN)
            else:
                var.CAN_START_TIME += timedelta(seconds=var.EXTRA_WAIT_JOIN)

            # make sure there's at least var.WAIT_AFTER_JOIN seconds of wait time left, if not add them
            if now + timedelta(seconds=var.WAIT_AFTER_JOIN) > var.CAN_START_TIME:
                var.CAN_START_TIME = now + timedelta(seconds=var.WAIT_AFTER_JOIN)

        var.LAST_STATS = None # reset
        var.LAST_GSTATS = None
        var.LAST_PSTATS = None
        var.LAST_RSTATS = None
        var.LAST_TIME = None

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
def kill_join(var: GameState, wrapper: MessageDispatcher): # FIXME: Remove var
    pl = [x.nick for x in get_players(var)]
    pl.sort(key=lambda x: x.lower())
    reset_modes_timers(var)
    reset(var)
    wrapper.send(*pl, first="PING! ")
    wrapper.send(messages["game_idle_cancel"])
    # use this opportunity to expire pending stasis
    db.expire_stasis()
    db.init_vars()
    expire_tempbans()
    if var.AFTER_FLASTGAME is not None:
        var.AFTER_FLASTGAME()
        var.AFTER_FLASTGAME = None

@command("fjoin", flag="A")
def fjoin(wrapper: MessageDispatcher, message: str):
    """Force someone to join a game.

    :param wrapper: Dispatcher
    :param message: Command text. If empty, we join ourselves
    """
    # keep this and the event in def join() in sync
    var = wrapper.game_state
    evt = Event("join", {
        "join_player": join_player,
        "join_deadchat": join_deadchat,
        "vote_gamemode": vote_gamemode
        })

    if not evt.dispatch(var, wrapper, message, forced=True):
        return
    success = False
    if not message.strip():
        evt.data["join_player"](var, wrapper, forced=True)
        return

    parts = re.split(" +", message)
    to_join = []
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
                evt.data["join_player"](var, type(wrapper)(tojoin, wrapper.target), forced=True, who=wrapper.source)
                success = True
        # Allow joining single number fake users in debug mode
        elif users.predicate(tojoin) and debug_mode:
            user = users.add(wrapper.client, nick=tojoin)
            evt.data["join_player"](var, type(wrapper)(user, wrapper.target), forced=True, who=wrapper.source)
            success = True
        # Allow joining ranges of numbers as fake users in debug mode
        elif "-" in tojoin and debug_mode:
            first, hyphen, last = tojoin.partition("-")
            if first.isdigit() and last.isdigit():
                if int(last)+1 - int(first) > var.MAX_PLAYERS - len(get_players(var)):
                    wrapper.send(messages["too_many_players_to_join"].format(wrapper.source))
                    break
                success = True
                for i in range(int(first), int(last)+1):
                    user = users.add(wrapper.client, nick=str(i))
                    evt.data["join_player"](var, type(wrapper)(user, wrapper.target), forced=True, who=wrapper.source)
    if success:
        wrapper.send(messages["fjoin_success"].format(wrapper.source, len(get_players(var))))

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
        if var.PHASE in var.GAME_PHASES:
            dead_target = users.complete_match(person, var.DEADCHAT_PLAYERS)
        if target:
            target = target.get()
            if wrapper.target is not channels.Main:
                wrapper.pm(messages["fquit_fail"])
                return

            msg = [messages["fquit_success"].format(wrapper.source, target)]
            if get_main_role(var, target) != "person" and var.ROLE_REVEAL in ("on", "team"):
                msg.append(messages["fquit_goodbye"].format(get_reveal_role(var, target)))
            if var.PHASE == "join":
                player_count = len(get_players(var)) - 1
                to_say = "new_player_count"
                if not player_count:
                    to_say = "no_players_remaining"
                msg.append(messages[to_say].format(player_count))

            wrapper.send(*msg)

            if var.PHASE != "join":
                var.DCED_LOSERS.add(target)

            add_dying(var, target, "bot", "fquit", death_triggers=False)
            kill_players(var)

        elif dead_target:
            dead_target = dead_target.get()
            leave_deadchat(var, dead_target, force=wrapper.source)
            if wrapper.source not in var.DEADCHAT_PLAYERS:
                wrapper.pm(messages["admin_fleave_deadchat"].format(dead_target))

        else:
            wrapper.send(messages["not_playing"].format(person))
            return

@event_listener("chan_kick")
def kicked_modes(evt, chan, actor, target, reason): # FIXME: This uses var
    if target is users.Bot and chan is channels.Main:
        chan.join()
    channels.Main.old_modes.pop(target, None)

@event_listener("chan_part")
def parted_modes(evt, chan, user, reason): # FIXME: This uses var
    if user is users.Bot and chan is channels.Main:
        chan.join()
    channels.Main.old_modes.pop(user, None)

@command("stats", pm=True, phases=("join", "day", "night"))
def stats(wrapper: MessageDispatcher, message: str):
    """Displays the player statistics."""
    var = wrapper.game_state
    pl = get_players(var)

    if wrapper.public and (wrapper.source in pl or var.PHASE == "join"):
        # only do this rate-limiting stuff if the person is in game
        if var.LAST_STATS and var.LAST_STATS + timedelta(seconds=var.STATS_RATE_LIMIT) > datetime.now():
            wrapper.pm(messages["command_ratelimited"])
            return

        var.LAST_STATS = datetime.now()

    if wrapper.private and "src.roles.helper.wolves" in sys.modules:
        from src.roles.helper.wolves import get_wolflist
        msg = messages["players_list_count"].format(
            len(pl), get_wolflist(var, wrapper.source, shuffle=False, remove_player=False))
    else:
        msg = messages["players_list_count"].format(len(pl), pl)

    wrapper.reply(msg)

    if var.PHASE == "join" or var.STATS_TYPE == "disabled":
        return

    entries = []
    first_count = 0

    start_roles = set(var.ORIGINAL_MAIN_ROLES.values())
    for roleset, amount in var.CURRENT_GAMEMODE.ACTIVE_ROLE_SETS.items():
        if amount == 0:
            continue
        for role, count in var.CURRENT_GAMEMODE.ROLE_SETS[roleset].items():
            if count == 0:
                continue
            start_roles.add(role)

    # Uses events in order to enable roles to modify logic
    # The events are fired off as part of transition_day and del_player, and are not calculated here
    if var.STATS_TYPE == "default":
        # Collapse var.ROLE_STATS into a Dict[str, Tuple[int, int]]
        role_stats = {}
        for stat_set in var.ROLE_STATS:
            for r, a in stat_set:
                if r not in role_stats:
                    role_stats[r] = (a, a)
                else:
                    mn, mx = role_stats[r]
                    role_stats[r] = (min(mn, a), max(mx, a))
        # remove any 0/0 entries if they weren't starting roles, otherwise we may have bad grammar in !stats
        role_stats = {r: v for r, v in role_stats.items() if r in start_roles or v != (0, 0)}
        order = [r for r in role_order() if r in role_stats]
        if var.DEFAULT_ROLE in order:
            order.remove(var.DEFAULT_ROLE)
            order.append(var.DEFAULT_ROLE)
        first = role_stats[order[0]]
        if first[0] == first[1] == 1:
            first_count = 1

        for role in order:
            if role in var.CURRENT_GAMEMODE.SECONDARY_ROLES:
                continue
            count = role_stats.get(role, (0, 0))
            if count[0] == count[1]:
                if count[0] == 0:
                    if role not in start_roles:
                        continue
                    entries.append(messages["stats_reply_entry_none"].format(role))
                else:
                    entries.append(messages["stats_reply_entry_single"].format(role, count[0]))
            else:
                entries.append(messages["stats_reply_entry_range"].format(role, count[0], count[1]))

    # Show everything as-is, with no hidden information
    elif var.STATS_TYPE == "accurate":
        l1 = [k for k in var.ROLES.keys() if var.ROLES[k]]
        l2 = [k for k in var.ORIGINAL_ROLES.keys() if var.ORIGINAL_ROLES[k]]
        rs = set(l1+l2)
        rs = [role for role in role_order() if role in rs]

        # picky ordering: villager always last
        if var.DEFAULT_ROLE in rs:
            rs.remove(var.DEFAULT_ROLE)
        rs.append(var.DEFAULT_ROLE)

        for role in rs:
            count = len(var.ROLES[role])
            # only show actual roles
            if role in var.CURRENT_GAMEMODE.SECONDARY_ROLES:
                continue

            if role == rs[0]:
                if count == 1:
                    first_count = 1

            if count == 0:
                if role not in start_roles:
                    continue
                entries.append(messages["stats_reply_entry_none"].format(role))
            else:
                entries.append(messages["stats_reply_entry_single"].format(role, count))

    # Only show team affiliation, this may be different than what mystics
    # and wolf mystics are told since neutrals are split off. Determination
    # of what numbers are shown is the same as summing up counts in "accurate"
    # as accurate, this contains no hidden information
    elif var.STATS_TYPE == "team":
        wolfteam = 0
        villagers = 0
        neutral = 0

        for role, players in var.ROLES.items():
            if role in var.CURRENT_GAMEMODE.SECONDARY_ROLES:
                continue
            if role in Wolfteam:
                wolfteam += len(players)
            elif role in Neutral:
                neutral += len(players)
            else:
                villagers += len(players)

        if wolfteam == 1:
            first_count = 1

        if wolfteam == 0:
            entries.append(messages["stats_reply_entry_none"].format("wolfteam player"))
        else:
            entries.append(messages["stats_reply_entry_single"].format("wolfteam player", wolfteam))

        if villagers == 0:
            entries.append(messages["stats_reply_entry_none"].format("village member"))
        else:
            entries.append(messages["stats_reply_entry_single"].format("village member", villagers))

        if neutral == 0:
            entries.append(messages["stats_reply_entry_none"].format("neutral player"))
        else:
            entries.append(messages["stats_reply_entry_single"].format("neutral player", neutral))

    wrapper.reply(messages["stats_reply"].format(var.PHASE, first_count, entries))

@event_listener("del_player")
def on_del_player(evt: Event, var, player: User, all_roles: Set[str], death_triggers: bool):
    # update var.ROLE_STATS
    # Event priorities:
    # 1 = Expanding the possible set (e.g. traitor would add themselves if nickrole is villager)
    # 3 = Removing from the possible set (e.g. can't be traitor if was a night kill and only wolves could kill at night),
    # 5 = Setting known_role to True if the role is actually known for sure publically (e.g. revealing totem)
    # 2 and 4 are not used by included roles, but may be useful expansion points for custom roles to modify stats
    event = Event("update_stats", {"possible": {evt.params.main_role, evt.params.reveal_role}, "known_role": False},
            killer_role=evt.params.killer_role,
            reason=evt.params.reason)
    event.dispatch(var, player, evt.params.main_role, evt.params.reveal_role, all_roles)
    # Given the set of possible roles this nick could be (or its actual role if known_role is True),
    # figure out the set of roles that need deducting from their counts in var.ROLE_STATS
    if event.data["known_role"]:
        # we somehow know the exact role that died (for example, we know traitor died even though they revealed as villager)
        # as a result, deduct only them
        possible = {evt.params.main_role}
    else:
        possible = set(event.data["possible"])
    newstats = set()
    # For every possible role this person is, try to deduct 1 from that role's count in our stat sets
    # if a stat set doesn't contain the role, then that would lead to an impossible condition and therefore
    # that set is not added to newstats to indicate that set is no longer possible
    for p in possible:
        for rs in var.ROLE_STATS:
            d = Counter(dict(rs))
            if p in d and d[p] >= 1:
                d[p] -= 1
                newstats.add(frozenset(d.items()))
    var.ROLE_STATS = newstats

    if var.PHASE == "join":
        if player in var.GAMEMODE_VOTES:
            del var.GAMEMODE_VOTES[player]

        for role in var.FORCE_ROLES:
            var.FORCE_ROLES[role].discard(player)

        # Died during the joining process as a person
        var.ALL_PLAYERS.remove(player)
    if var.PHASE in var.GAME_PHASES:
        # remove the player from variables if they're in there
        var.DISCONNECTED.pop(player, None)

# FIXME: get rid of the priority once we move state transitions into the main event loop instead of having it here
@event_listener("kill_players", priority=10)
def on_kill_players(evt: Event, var: GameState, players: Set[User]):
    cmode = []
    deadchat = []
    game_ending = False

    for player in players:
        if not player.is_fake:
            if var.PHASE != "night" or not var.DEVOICE_DURING_NIGHT:
                cmode.append(("-v", player.nick))
            if var.in_game and var.QUIET_DEAD_PLAYERS:
                # Died during the game, so quiet!
                ircd = get_ircd()
                if ircd.supports_quiet():
                    cmode.append((f"+{ircd.quiet_mode}", f"{ircd.quiet_prefix}{player.nick}!*@*"))
            if var.PHASE == "join":
                for mode in channels.Main.old_modes[player]:
                    cmode.append(("+" + mode, player.nick))
                del channels.Main.old_modes[player]
            lplayer = player.lower()
            if lplayer.account not in var.DEADCHAT_PREFS_ACCS:
                deadchat.append(player)

    # attempt to devoice all dead players
    if cmode:
        channels.Main.mode(*cmode)

    if not evt.params.end_game:
        join_deadchat(var, *deadchat)
        return

    # see if we need to end the game or transition phases
    # FIXME: make state transitions part of the overall event loop
    game_ending = chk_win(var)

    if not game_ending:
        # if game isn't about to end, join people to deadchat
        join_deadchat(var, *deadchat)

        if var.PHASE == "day" and var.GAMEPHASE == "day":
            # PHASE is day but GAMEPHASE is night during transition_day; ensure we only induce lynch during actual daytime
            chk_decision(var)
        elif var.PHASE == "night" and var.GAMEPHASE == "night":
            # PHASE is night but GAMEPHASE is day during transition_night; ensure we only try to end night during actual nighttime
            chk_nightdone(var)
    else:
        # HACK: notify kill_players that game is ending so it can pass it to its caller
        evt.prevent_default = True

@handle_error
def reaper(cli, gameid):
    # check to see if idlers need to be killed.
    last_day_id = var.DAY_COUNT
    num_night_iters = 0
    short = False

    while gameid == var.GAME_ID:
        skip = False
        time.sleep(1 if short else 10)
        short = False
        with locks.reaper:
            # Terminate reaper when game ends
            if var.PHASE not in var.GAME_PHASES:
                return
            if var.PHASE != var.GAMEPHASE:
                # in a phase transition, so don't run the reaper here or else things may break
                # flag to re-run sooner than usual though
                short = True
                continue
            elif var.DEVOICE_DURING_NIGHT:
                if var.PHASE == "night":
                    # don't count nighttime towards idling
                    # this doesn't do an exact count, but is good enough
                    num_night_iters += 1
                    skip = True
                elif var.PHASE == "day" and var.DAY_COUNT != last_day_id:
                    last_day_id = var.DAY_COUNT
                    num_night_iters += 1
                    for user in var.LAST_SAID_TIME:
                        var.LAST_SAID_TIME[user] += timedelta(seconds=10 * num_night_iters)
                    num_night_iters = 0

            if not skip and (var.WARN_IDLE_TIME or var.PM_WARN_IDLE_TIME or var.KILL_IDLE_TIME):  # only if enabled
                to_warn    = set() # type: Set[users.User]
                to_warn_pm = set() # type: Set[users.User]
                to_kill    = set() # type: Set[users.User]
                for user in get_players(var):
                    if user.is_fake:
                        continue
                    lst = var.LAST_SAID_TIME.get(user, var.GAME_START_TIME)
                    tdiff = datetime.now() - lst
                    if var.WARN_IDLE_TIME and (tdiff > timedelta(seconds=var.WARN_IDLE_TIME) and
                                            user not in var.IDLE_WARNED):
                        to_warn.add(user)
                        var.IDLE_WARNED.add(user)
                        var.LAST_SAID_TIME[user] = (datetime.now() - timedelta(seconds=var.WARN_IDLE_TIME))  # Give them a chance
                    elif var.PM_WARN_IDLE_TIME and (tdiff > timedelta(seconds=var.PM_WARN_IDLE_TIME) and
                                            user not in var.IDLE_WARNED_PM):
                        to_warn_pm.add(user)
                        var.IDLE_WARNED_PM.add(user)
                        var.LAST_SAID_TIME[user] = (datetime.now() - timedelta(seconds=var.PM_WARN_IDLE_TIME))
                    elif var.KILL_IDLE_TIME and (tdiff > timedelta(seconds=var.KILL_IDLE_TIME) and
                                            (not var.WARN_IDLE_TIME or user in var.IDLE_WARNED) and
                                            (not var.PM_WARN_IDLE_TIME or user in var.IDLE_WARNED_PM)):
                        to_kill.add(user)
                    elif (tdiff < timedelta(seconds=var.WARN_IDLE_TIME) and
                                            (user in var.IDLE_WARNED or user in var.IDLE_WARNED_PM)):
                        var.IDLE_WARNED.discard(user)  # player saved themselves from death
                        var.IDLE_WARNED_PM.discard(user)
                for user in to_kill:
                    if var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["idle_death"].format(user, get_reveal_role(var, user)))
                    else:
                        channels.Main.send(messages["idle_death_no_reveal"].format(user))
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(user)
                    if var.IDLE_PENALTY:
                        trans.NIGHT_IDLED.discard(user) # don't double-dip if they idled out night as well
                        add_warning(user, var.IDLE_PENALTY, users.Bot, messages["idle_warning"], expires=var.IDLE_EXPIRY)
                    add_dying(var, user, "bot", "idle", death_triggers=False)
                pl = get_players(var)
                x = [a for a in to_warn if a in pl]
                if x:
                    channels.Main.send(messages["channel_idle_warning"].format(x))
                msg_targets = [p for p in to_warn_pm if p in pl]
                for p in msg_targets:
                    p.queue_message(messages["player_idle_warning"].format(channels.Main))
                if msg_targets:
                    p.send_messages()
            for dcedplayer, (timeofdc, what) in list(var.DISCONNECTED.items()):
                mainrole = get_main_role(var, dcedplayer)
                revealrole = get_reveal_role(var, dcedplayer)
                if what == "quit" and (datetime.now() - timeofdc) > timedelta(seconds=var.QUIT_GRACE_TIME):
                    if mainrole != "person" and var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["quit_death"].format(dcedplayer, revealrole))
                    else: # FIXME: Merge those two
                        channels.Main.send(messages["quit_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.PART_PENALTY:
                        trans.NIGHT_IDLED.discard(dcedplayer) # don't double-dip if they idled out night as well
                        add_warning(dcedplayer, var.PART_PENALTY, users.Bot, messages["quit_warning"], expires=var.PART_EXPIRY)
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "quit", death_triggers=False)
                elif what == "part" and (datetime.now() - timeofdc) > timedelta(seconds=var.PART_GRACE_TIME):
                    if mainrole != "person" and var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["part_death"].format(dcedplayer, revealrole))
                    else: # FIXME: Merge those two
                        channels.Main.send(messages["part_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.PART_PENALTY:
                        trans.NIGHT_IDLED.discard(dcedplayer) # don't double-dip if they idled out night as well
                        add_warning(dcedplayer, var.PART_PENALTY, users.Bot, messages["part_warning"], expires=var.PART_EXPIRY)
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "part", death_triggers=False)
                elif what == "account" and (datetime.now() - timeofdc) > timedelta(seconds=var.ACC_GRACE_TIME):
                    if mainrole != "person" and var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["account_death"].format(dcedplayer, revealrole))
                    else:
                        channels.Main.send(messages["account_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.ACC_PENALTY:
                        trans.NIGHT_IDLED.discard(dcedplayer) # don't double-dip if they idled out night as well
                        add_warning(dcedplayer, var.ACC_PENALTY, users.Bot, messages["acc_warning"], expires=var.ACC_EXPIRY)
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "account", death_triggers=False)
            kill_players(var)

@command("")  # update last said
def update_last_said(wrapper: MessageDispatcher, message: str):
    if wrapper.target is not channels.Main:
        return

    var = wrapper.game_state

    if var.PHASE not in ("join", "none"):
        var.LAST_SAID_TIME[wrapper.source] = datetime.now()

@event_listener("chan_join", priority=1)
def on_join(evt, chan, user): # FIXME: This uses var
    if user is users.Bot:
        plog("Joined {0}".format(chan))
    if chan is not channels.Main:
        return
    user.update_account_data("<chan_join>", lambda new_user: return_to_village(var, new_user, show_message=True))

@command("goat")
def goat(wrapper: MessageDispatcher, message: str):
    """Use a goat to interact with anyone in the channel during the day."""

    var = wrapper.game_state

    if wrapper.source in var.LAST_GOAT and var.LAST_GOAT[wrapper.source] + timedelta(seconds=var.GOAT_RATE_LIMIT) > datetime.now():
        wrapper.pm(messages["command_ratelimited"])
        return
    target = re.split(" +", message)[0]
    if not target:
        wrapper.pm(messages["not_enough_parameters"])
        return
    victim = users.complete_match(users.lower(target), wrapper.target.users)
    if not victim:
        wrapper.pm(messages["goat_target_not_in_channel"].format(target))
        return

    var.LAST_GOAT[wrapper.source] = datetime.now()
    wrapper.send(messages["goat_success"].format(wrapper.source, victim.get()))

@command("fgoat", flag="j")
def fgoat(wrapper: MessageDispatcher, message: str):
    """Forces a goat to interact with anyone or anything, without limitations."""

    nick = message.split(' ')[0].strip()
    victim = users.complete_match(users.lower(nick), wrapper.target.users)
    if victim:
        togoat = victim.get()
    else:
        togoat = message

    wrapper.send(messages["goat_success"].format(wrapper.source, togoat))

@handle_error
def return_to_village(var, target, *, show_message, new_user=None):
    with locks.reaper:
        if channels.Main not in target.channels:
            # managed to leave the channel in between the time return_to_village was scheduled and called
            return

        if target.account not in var.ORIGINAL_ACCS.values():
            return

        if target in var.DISCONNECTED:
            del var.DISCONNECTED[target]
            if new_user is None:
                new_user = target

            var.LAST_SAID_TIME[target] = datetime.now()
            var.DCED_LOSERS.discard(target)

            if new_user is not target:
                # different users, perform a swap. This will clean up disconnected users.
                target.swap(new_user)

            if show_message:
                if not var.DEVOICE_DURING_NIGHT or var.PHASE != "night":
                    channels.Main.mode(("+v", new_user))
                if target.nick == new_user.nick:
                    channels.Main.send(messages["player_return"].format(new_user))
                else:
                    channels.Main.send(messages["player_return_nickchange"].format(new_user, target))
        else:
            # this particular user doesn't exist in var.DISCONNECTED, but that doesn't
            # mean that they aren't dced. They may have rejoined as a different nick,
            # for example, and we want to mark them as back without requiring them to do
            # a !swap.
            userlist = users.get(account=target.account, allow_multiple=True, allow_ghosts=True)
            userlist = [u for u in userlist if u in var.DISCONNECTED]
            if len(userlist) == 1:
                return_to_village(var, userlist[0], show_message=show_message, new_user=target)

@event_listener("account_change")
def account_change(evt, user, old_account): # FIXME: This uses var
    if user not in channels.Main.users:
        return # We only care about game-related changes in this function

    pl = get_participants(var)
    if user in pl and user.account not in var.ORIGINAL_ACCS.values() and user not in var.DISCONNECTED:
        leave(var, "account", user) # this also notifies the user to change their account back
        if var.PHASE != "join":
            channels.Main.mode(["-v", user.nick])
    elif (user not in pl or user in var.DISCONNECTED) and user.account in var.ORIGINAL_ACCS.values():
        # if they were gone, maybe mark them as back
        return_to_village(var, user, show_message=True)

@event_listener("nick_change")
def nick_change(evt, user, old_nick): # FIXME: This function needs some way to have var
    if user not in channels.Main.users:
        return

    pl = get_participants(var)
    if user.account in var.ORIGINAL_ACCS.values() and user not in pl:
        for other in pl:
            if users.equals(user.account, other.account):
                if re.search(var.GUEST_NICK_PATTERN, other.nick):
                    # The user joined to the game is using a Guest nick, which is usually due to a connection issue.
                    # Automatically swap in this user for that old one.
                    replace(var, MessageDispatcher(user, users.Bot), "")
                return

@event_listener("chan_part")
def left_channel(evt, chan, user, reason): # FIXME: This uses var
    leave(var, "part", user, chan)

@event_listener("chan_kick") # FIXME: This uses var
def channel_kicked(evt, chan, actor, user, reason):
    leave(var, "kick", user, chan)

@event_listener("server_quit")
def quit_server(evt, user, reason): # FIXME: This uses var
    leave(var, "quit", user, reason)

def leave(var, what, user, why=None):
    if what in ("part", "kick") and why is not channels.Main:
        return
    if why and why == var.CHANGING_HOST_QUIT_MESSAGE:
        return
    if var.PHASE == "none":
        return

    ps = get_players(var)
    # Only mark living players as disconnected, unless they were kicked
    if (user in ps or what == "kick") and var.PHASE in var.GAME_PHASES:
        var.DCED_LOSERS.add(user)

    # leaving the game channel means you leave deadchat
    if user in var.DEADCHAT_PLAYERS:
        leave_deadchat(var, user)

    if user not in ps or user in var.DISCONNECTED:
        return

    # If we got that far, the player was in the game. This variable tracks whether or not we want to kill them off.
    killplayer = True

    population = ""

    if var.PHASE == "join":
        lpl = len(ps) - 1
        if lpl < var.MIN_PLAYERS:
            with locks.join_timer:
                from src.pregame import START_VOTES
                START_VOTES.clear()

        if lpl <= 0:
            population = " " + messages["no_players_remaining"]
        else:
            population = " " + messages["new_player_count"].format(lpl)

    reveal = ""
    if get_main_role(var, user) == "person" or var.ROLE_REVEAL not in ("on", "team"):
        reveal = "_no_reveal"

    grace_times = {"part": var.PART_GRACE_TIME, "quit": var.QUIT_GRACE_TIME, "account": var.ACC_GRACE_TIME, "leave": 0}

    reason = what
    if reason == "kick":
        reason = "leave"

    if reason in grace_times and (grace_times[reason] <= 0 or var.PHASE == "join"):
        # possible message keys (for easy grep):
        # "quit_death", "quit_death_no_reveal", "leave_death", "leave_death_no_reveal", "account_death", "account_death_no_reveal"
        msg = messages["{0}_death{1}".format(reason, reveal)]
    elif what != "kick": # There's time for the player to rejoin the game
        if reason != "quit":
            # message keys: "part_grace_time_notice", "account_grace_time_notice"
            # No message is sent for quit because the user won't be online to receive it...
            user.send(messages["{0}_grace_time_notice".format(reason)].format(grace_times[reason], chan=channels.Main))
        msg = messages["player_missing"]
        population = ""
        killplayer = False

    channels.Main.send(msg.format(user, get_reveal_role(var, user)) + population)
    var.SPECTATING_WOLFCHAT.discard(user)
    var.SPECTATING_DEADCHAT.discard(user)
    leave_deadchat(var, user)

    if killplayer:
        add_dying(var, user, "bot", what, death_triggers=False)
        kill_players(var)
    else:
        var.DISCONNECTED[user] = (datetime.now(), what)

@command("leave", pm=True, phases=("join", "day", "night"))
def leave_game(wrapper: MessageDispatcher, message: str):
    """Quits the game."""
    var = wrapper.game_state
    if wrapper.target is channels.Main:
        if wrapper.source not in get_players(var):
            return
        if var.PHASE == "join":
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
        if var.PHASE in var.GAME_PHASES and wrapper.source not in get_players(var) and wrapper.source in var.DEADCHAT_PLAYERS:
            leave_deadchat(var, wrapper.source)
        return
    else:
        return

    if get_main_role(var, wrapper.source) != "person" and var.ROLE_REVEAL in ("on", "team"):
        role = get_reveal_role(var, wrapper.source)
        channels.Main.send(messages["quit_reveal"].format(wrapper.source, role) + population)
    else:
        channels.Main.send(messages["quit_no_reveal"].format(wrapper.source) + population)
    if var.PHASE != "join":
        var.DCED_LOSERS.add(wrapper.source)
        if var.LEAVE_PENALTY:
            trans.NIGHT_IDLED.discard(wrapper.source) # don't double-dip if they idled out night as well
            add_warning(wrapper.source, var.LEAVE_PENALTY, users.Bot, messages["leave_warning"], expires=var.LEAVE_EXPIRY)

    add_dying(var, wrapper.source, "bot", "quit", death_triggers=False)
    kill_players(var)

@hook("featurelist")  # For multiple targets with PRIVMSG
def getfeatures(cli, nick, *rest):
    for r in rest:
        if r.startswith("TARGMAX="):
            x = r[r.index("PRIVMSG:"):]
            if "," in x:
                l = x[x.index(":")+1:x.index(",")]
            else:
                l = x[x.index(":")+1:]
            l = l.strip()
            if not l or not l.isdigit():
                continue
            else:
                var.MAX_PRIVMSG_TARGETS = int(l)
                continue
        if r.startswith("PREFIX="):
            prefs = r[7:]
            chp = []
            nlp = []
            finder = True
            for char in prefs:
                if char == "(":
                    continue
                if char == ")":
                    finder = False
                    continue
                if finder:
                    chp.append(char)
                else:
                    nlp.append(char)
            allp = zip(chp, nlp)
            var.MODES_PREFIXES = {}
            for combo in allp:
                var.MODES_PREFIXES[combo[1]] = combo[0] # For some reason this needs to be backwards

        if r.startswith("CHANMODES="):
            chans = r[10:].split(",")
            var.LISTMODES, var.MODES_ALLSET, var.MODES_ONLYSET, var.MODES_NOSET = chans
        if r.startswith("MODES="):
            try:
                var.MODELIMIT = int(r[6:])
            except ValueError:
                pass
        if r.startswith("STATUSMSG="):
            var.STATUSMSG_PREFIXES = list(r.split("=")[1])
        if r.startswith("CASEMAPPING="):
            var.CASEMAPPING = r.split("=")[1]

            if var.CASEMAPPING not in ("rfc1459", "strict-rfc1459", "ascii"):
                # This is very unlikely to happen, but just in case.
                errlog("Unsupported case mapping: {0!r}; falling back to rfc1459.".format(var.CASEMAPPING))
                var.CASEMAPPING = "rfc1459"

@command("", chan=False, pm=True)
def relay(wrapper: MessageDispatcher, message: str):
    """Wolfchat and Deadchat"""
    var = wrapper.game_state
    if message.startswith("\u0001PING"):
        wrapper.pm(message, notice=True)
        return
    if message == "\u0001VERSION\u0001":
        try:
            ans = subprocess.check_output(["git", "log", "-n", "1", "--pretty=format:%h"])
            reply = "\u0001VERSION lykos {0}, Python {1} -- https://github.com/lykoss/lykos\u0001".format(str(ans.decode()), platform.python_version())
        except (OSError, subprocess.CalledProcessError):
            reply = "\u0001VERSION lykos, Python {0} -- https://github.com/lykoss/lykos\u0001".format(platform.python_version())
        wrapper.pm(reply, notice=True)
        return
    if message == "\u0001TIME\u0001":
        wrapper.pm("\u0001TIME {0}\u0001".format(time.strftime('%a, %d %b %Y %T %z', time.localtime())), notice=True)
    if var.PHASE not in var.GAME_PHASES:
        return

    pl = get_players(var)

    if wrapper.source in pl and wrapper.source in var.IDLE_WARNED_PM:
        wrapper.pm(messages["privmsg_idle_warning"].format(channels.Main))

    if message.startswith(var.CMD_CHAR):
        return

    if "src.roles.helper.wolves" in sys.modules:
        from src.roles.helper.wolves import get_talking_roles
        badguys = get_players(var, get_talking_roles(var))
    else:
        badguys = get_players(var, Wolfchat)
    wolves = get_players(var, Wolf)

    if wrapper.source not in pl and var.ENABLE_DEADCHAT and wrapper.source in var.DEADCHAT_PLAYERS:
        to_msg = var.DEADCHAT_PLAYERS - {wrapper.source}
        if to_msg or var.SPECTATING_DEADCHAT:
            if message.startswith("\u0001ACTION"):
                message = message[8:-1]
                for user in to_msg:
                    user.queue_message(messages["relay_action"].format(wrapper.source, message))
                for user in var.SPECTATING_DEADCHAT:
                    user.queue_message(messages["relay_action_deadchat"].format(wrapper.source, message))
            else:
                for user in to_msg:
                    user.queue_message(messages["relay_message"].format(wrapper.source, message))
                for user in var.SPECTATING_DEADCHAT:
                    user.queue_message(messages["relay_message_deadchat"].format(wrapper.source, message))

            user.send_messages()

    elif wrapper.source in badguys and len(badguys) > 1:
        # handle wolfchat toggles
        if not var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wolves.extend(var.ROLES["traitor"])
        if var.PHASE == "night" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
            return
        elif var.PHASE == "day" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            return
        elif wrapper.source not in wolves and var.RESTRICT_WOLFCHAT & var.RW_WOLVES_ONLY_CHAT:
            return
        elif wrapper.source not in wolves and var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
            return

        badguys.remove(wrapper.source)
        if message.startswith("\u0001ACTION"):
            message = message[7:-1]
            for player in badguys:
                player.queue_message(messages["relay_action"].format(wrapper.source, message))
            for player in var.SPECTATING_WOLFCHAT:
                player.queue_message(messages["relay_action_wolfchat"].format(wrapper.source, message))
        else:
            for player in badguys:
                player.queue_message(messages["relay_message"].format(wrapper.source, message))
            for player in var.SPECTATING_WOLFCHAT:
                player.queue_message(messages["relay_message_wolfchat"].format(wrapper.source, message))
        if badguys or var.SPECTATING_WOLFCHAT:
            player.send_messages()

def cgamemode(var, arg):
    from src.gamemodes import GAME_MODES
    if var.ORIGINAL_SETTINGS:  # needs reset
        reset_settings()

    modeargs = arg.split("=", 1)

    modeargs = [a.strip() for a in modeargs]
    if modeargs[0] in GAME_MODES.keys():
        from src.gamemodes import InvalidModeException
        md = modeargs.pop(0)
        try:
            gm = GAME_MODES[md][0](*modeargs)
            gm.startup()
            for attr in dir(gm):
                val = getattr(gm, attr)
                if (hasattr(var, attr) and not callable(val)
                                        and not attr.startswith("_")):
                    var.ORIGINAL_SETTINGS[attr] = getattr(var, attr)
                    setattr(var, attr, val)
            var.CURRENT_GAMEMODE = gm
            return True
        except InvalidModeException as e:
            channels.Main.send("Invalid mode: "+str(e))
            return False
    else:
        channels.Main.send(messages["game_mode_not_found"].format(modeargs[0]))

@hook("error")
def on_error(cli, pfx, msg):
    if var.RESTARTING or msg.lower().endswith("(excess flood)"):
        import src
        if src.lagcheck > 0:
            src.lagcheck = max(1, src.lagcheck - 1)
        _restart_program()
    elif msg.lower().startswith("closing link:"):
        raise SystemExit

@command("ftemplate", flag="F", pm=True)
def ftemplate(wrapper: MessageDispatcher, message: str):
    params = re.split(" +", message)
    var = wrapper.game_state

    if params[0] == "":
        # display a list of all templates
        tpls = db.get_templates()
        if not tpls:
            wrapper.reply(messages["no_templates"])
        else:
            tpls = ["{0} (+{1})".format(name, "".join(sorted(flags))) for name, flags in tpls]
            wrapper.reply(*tpls, sep=", ")
    elif len(params) == 1:
        wrapper.reply(messages["not_enough_parameters"])
    else:
        name = params[0].upper()
        flags = params[1]
        tid, cur_flags = db.get_template(name)
        cur_flags = set(cur_flags)

        if flags[0] != "+" and flags[0] != "-":
            # flags is a template name
            tpl_name = flags.upper()
            tpl_id, tpl_flags = db.get_template(tpl_name)
            if tpl_id is None:
                wrapper.reply(messages["template_not_found"].format(tpl_name))
                return
            tpl_flags = "".join(sorted(tpl_flags))
            db.update_template(name, tpl_flags)
            wrapper.reply(messages["template_set"].format(name, tpl_flags))
        else:
            adding = True
            for flag in flags:
                if flag == "+":
                    adding = True
                    continue
                elif flag == "-":
                    adding = False
                    continue
                elif flag == "*":
                    if adding:
                        cur_flags = cur_flags | (var.ALL_FLAGS - {"F"})
                    else:
                        cur_flags = set()
                    continue
                elif flag not in var.ALL_FLAGS:
                    wrapper.reply(messages["invalid_flag"].format(flag, "".join(sorted(var.ALL_FLAGS))))
                    return
                elif adding:
                    cur_flags.add(flag)
                else:
                    cur_flags.discard(flag)
            if cur_flags:
                tpl_flags = "".join(sorted(cur_flags))
                db.update_template(name, tpl_flags)
                wrapper.reply(messages["template_set"].format(name, tpl_flags))
            elif tid is None:
                wrapper.reply(messages["template_not_found"].format(name))
            else:
                db.delete_template(name)
                wrapper.reply(messages["template_deleted"].format(name))

        # re-init var.FLAGS_ACCS since it may have changed
        db.init_vars()

@command("fflags", flag="F", pm=True)
def fflags(wrapper: MessageDispatcher, message: str):
    params = re.split(" +", message)
    params = [p for p in params if p]

    var = wrapper.game_state

    _fa = messages.raw("_commands", "warn opt account")
    _fh = messages.raw("_commands", "warn opt help")
    if not params or params[0] in _fh:
        wrapper.reply(messages["fflags_usage"])
        return

    account = False
    if params[0] in _fa:
        params.pop(0)
        account = True

    if not params:
        wrapper.reply(messages["fflags_usage"])
        return

    nick = params.pop(0)
    flags = None
    if params:
        flags = params.pop(0)

    if nick == "*":
        # display a list of all access
        parts = []
        for acc, flags in var.FLAGS_ACCS.items():
            if not flags:
                continue
            parts.append("{0} (+{1})".format(acc, "".join(sorted(flags))))
        if not parts:
            wrapper.reply(messages["no_access"])
        else:
            wrapper.reply(*parts, sep=", ")
        return

    if account:
        acc = nick
    else:
        m = users.complete_match(nick)
        if m:
            acc = m.get().account
        else:
            acc = nick

    # var.FLAGS_ACC stores lowercased accounts, ensure acc is lowercased as well
    from src.context import lower
    lacc = lower(acc)

    if not flags:
        # display access for the given user
        if not var.FLAGS_ACCS[lacc]:
            wrapper.reply(messages["no_access_account"].format(acc))
        else:
            wrapper.reply(messages["access_account"].format(acc, "".join(sorted(var.FLAGS_ACCS[lacc]))))
        return

    cur_flags = set(var.FLAGS_ACCS[lacc])
    if flags[0] != "+" and flags[0] != "-":
        # flags is a template name
        tpl_name = flags.upper()
        tpl_id, tpl_flags = db.get_template(tpl_name)
        if tpl_id is None:
            wrapper.reply(messages["template_not_found"].format(tpl_name))
            return
        tpl_flags = "".join(sorted(tpl_flags))
        db.set_access(acc, tid=tpl_id)
        wrapper.reply(messages["access_set_account"].format(acc, tpl_flags))
    else:
        adding = True
        for flag in flags:
            if flag == "+":
                adding = True
                continue
            elif flag == "-":
                adding = False
                continue
            elif flag == "*":
                if adding:
                    cur_flags = cur_flags | (var.ALL_FLAGS - {"F"})
                else:
                    cur_flags = set()
                continue
            elif flag not in var.ALL_FLAGS:
                wrapper.reply(messages["invalid_flag"].format(flag, "".join(sorted(var.ALL_FLAGS))))
                return
            elif adding:
                cur_flags.add(flag)
            else:
                cur_flags.discard(flag)
        if cur_flags:
            flags = "".join(sorted(cur_flags))
            db.set_access(acc, flags=flags)
            wrapper.reply(messages["access_set_account"].format(acc, flags))
        else:
            db.set_access(acc, flags=None)
            wrapper.reply(messages["access_deleted_account"].format(acc))

        # re-init var.FLAGS_ACCS since it may have changed
        db.init_vars()

@command("rules", pm=True)
def show_rules(wrapper: MessageDispatcher, message: str):
    """Displays the rules."""

    var = wrapper.game_state

    if hasattr(var, "RULES"):
        rules = var.RULES
        wrapper.reply(messages["channel_rules"].format(channels.Main, rules))
    else:
        wrapper.reply(messages["no_channel_rules"].format(channels.Main))

@command("help", pm=True)
def get_help(wrapper: MessageDispatcher, message: str):
    """Gets help."""
    commands = set()
    for name, functions in COMMANDS.items():
        if not name:
            continue
        for fn in functions:
            if not fn.flag and not fn.owner_only and name not in fn.aliases:
                commands.add(name)
                break
    admin_commands = set()
    if wrapper.source.is_admin():
        for name, functions in COMMANDS.items():
            for fn in functions:
                if fn.flag and name not in fn.aliases:
                    admin_commands.add(name)
    wrapper.pm(messages["commands_list"].format(sorted(commands)))
    if admin_commands:
        wrapper.pm(messages["admin_commands_list"].format(sorted(admin_commands)))
    wrapper.pm(messages["commands_further_help"])

def get_wiki_page(URI):
    try:
        response = urllib.request.urlopen(URI, timeout=2).read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, socket.timeout):
        return False, messages["wiki_request_timed_out"]
    if not response:
        return False, messages["wiki_open_failure"]
    parsed = json.loads(response)
    if not parsed:
        return False, messages["wiki_open_failure"]
    return True, parsed

@command("wiki", pm=True)
def wiki(wrapper: MessageDispatcher, message: str):
    """Prints information from the wiki."""

    # no arguments, just print a link to the wiki
    if not message:
        wrapper.reply("https://werewolf.chat")
        return
    rest = message.replace(" ", "_").lower()

    # Get suggestions, for autocompletion
    URI = "https://werewolf.chat/w/api.php?action=opensearch&format=json&search={0}".format(rest)
    success, suggestionjson = get_wiki_page(URI)
    if not success:
        wrapper.pm(suggestionjson)
        return

    # Parse suggested pages, take the first result
    try:
        suggestion = suggestionjson[1][0].replace(" ", "_")
    except IndexError:
        wrapper.pm(messages["wiki_no_info"])
        return

    # Fetch a page from the api, in json format
    URI = "https://werewolf.chat/w/api.php?action=query&prop=extracts&exintro=true&explaintext=true&titles={0}&redirects&format=json".format(suggestion)
    success, pagejson = get_wiki_page(URI)
    if not success:
        wrapper.pm(pagejson)
        return

    try:
        p = pagejson["query"]["pages"].popitem()[1]
        suggestion = p["title"]
        page = p["extract"]
    except (KeyError, IndexError):
        wrapper.pm(messages["wiki_no_info"])
        return

    try:
        fragment = pagejson["query"]["redirects"][0]["tofragment"]
        suggestion += "#{0}".format(fragment)
    except (KeyError, IndexError):
        pass

    # We only want the first paragraph
    if page.find("\n") >= 0:
        page = page[:page.find("\n")]

    wikilink = "https://werewolf.chat/{0}".format(suggestion.replace(" ", "_"))
    wrapper.reply(wikilink)
    if "#" not in wikilink:
        wrapper.pm(page)

@hook("invite")
def on_invite(cli, raw_nick, something, chan):
    if chan == var.CHANNEL:
        cli.join(chan)
        return # No questions
    user = users.get(raw_nick, allow_none=True)
    if user and user.is_admin():
        cli.join(chan) # Allows the bot to be present in any channel

@command("admins", pm=True)
def show_admins(wrapper: MessageDispatcher, message: str):
    """Pings the admins that are available."""

    admins = []

    var = wrapper.game_state

    if wrapper.public and var.LAST_ADMINS and var.LAST_ADMINS + timedelta(seconds=var.ADMINS_RATE_LIMIT) > datetime.now():
        wrapper.pm(messages["command_ratelimited"])
        return

    if wrapper.public:
        var.LAST_ADMINS = datetime.now()

    if var.ADMIN_PINGING:
        return

    var.ADMIN_PINGING = True

    def admin_whoreply(event, chan, user):
        if not var.ADMIN_PINGING or chan is not channels.Main:
            return

        if user.is_admin() and user is not users.Bot and not event.params.away:
            admins.append(user)

    def admin_endwho(event, target):
        if not var.ADMIN_PINGING or target is not channels.Main:
            return

        who_result.remove("who_result")
        who_end.remove("who_end")
        admins.sort(key=lambda x: x.nick)
        wrapper.reply(messages["available_admins"].format(admins))
        var.ADMIN_PINGING = False


    who_result = EventListener(admin_whoreply)
    who_result.install("who_result")
    who_end = EventListener(admin_endwho)
    who_end.install("who_end")

    channels.Main.who()

@command("coin", pm=True)
def coin(wrapper: MessageDispatcher, message: str):
    """It's a bad idea to base any decisions on this command."""

    wrapper.send(messages["coin_toss"].format(wrapper.source))
    rnd = random.random()
    # 59/29/12 split, 59+29=88
    if rnd < 0.59:
        coin = messages.get("coin_land", 0)
    elif rnd < 0.88:
        coin = messages.get("coin_land", 1)
    else:
        coin = messages.get("coin_land", 2)
    wrapper.send(coin.format())

@command("pony", pm=True)
def pony(wrapper: MessageDispatcher, message: str):
    """Toss a magical pony into the air and see what happens!"""

    wrapper.send(messages["pony_toss"].format(wrapper.source))
    # 59/29/7/5 split
    rnd = random.random()
    if rnd < 0.59:
        pony = messages.get("pony_land", 0)
    elif rnd < 0.88:
        pony = messages.get("pony_land", 1)
    elif rnd < 0.95:
        pony = messages.get("pony_land", 2)
    else:
        pony = messages.get("pony_land", 3)
    wrapper.send(pony.format(nick=wrapper.source))

@command("cat", pm=True)
def cat(wrapper: MessageDispatcher, message: str):
    """Toss a cat into the air and see what happens!"""
    wrapper.send(messages["cat_toss"].format(wrapper.source), messages["cat_land"].format(), sep="\n")

@command("time", pm=True, phases=("join", "day", "night"))
def timeleft(wrapper: MessageDispatcher, message: str):
    """Returns the time left until the next day/night transition."""

    var = wrapper.game_state

    if (wrapper.public and var.LAST_TIME and
            var.LAST_TIME + timedelta(seconds=var.TIME_RATE_LIMIT) > datetime.now()):
        wrapper.pm(messages["command_ratelimited"].format())
        return

    if wrapper.public:
        var.LAST_TIME = datetime.now()

    if var.PHASE == "join":
        dur = int((var.CAN_START_TIME - datetime.now()).total_seconds())
        msg = None
        if dur > 0:
            msg = messages["start_timer"].format(dur)

        if msg is not None:
            wrapper.reply(msg)

    if var.PHASE in trans.TIMERS or f"{var.PHASE}_limit" in trans.TIMERS:
        if var.PHASE == "day":
            what = "sunset" # FIXME: hardcoded english
            name = "day_limit"
        elif var.PHASE == "night":
            what = "sunrise"
            name = "night_limit"
        elif var.PHASE == "join":
            what = "the game is canceled if it's not started"
            name = "join"

        remaining = int((trans.TIMERS[name][1] + trans.TIMERS[name][2]) - time.time())
        msg = "There is \u0002{0[0]:0>2}:{0[1]:0>2}\u0002 remaining until {1}.".format(divmod(remaining, 60), what)
    else:
        msg = messages["timers_disabled"].format(var.PHASE.capitalize())

    wrapper.reply(msg)

@command("roles", pm=True)
def list_roles(wrapper: MessageDispatcher, message: str):
    """Display which roles are in play for a specific gamemode."""
    from src.gamemodes import GAME_MODES

    var = wrapper.game_state

    lpl = len(var.ALL_PLAYERS)
    specific = 0

    pieces = re.split(" +", message.strip())
    gamemode = var.CURRENT_GAMEMODE

    if (not pieces[0] or pieces[0].isdigit()) and not hasattr(gamemode, "ROLE_GUIDE"):
        minp = max(GAME_MODES[gamemode.name][1], var.MIN_PLAYERS)
        msg = " ".join((messages["roles_players"].format(lpl), messages["roles_disabled"].format(gamemode.name, minp)))
        wrapper.reply(msg, prefix_nick=True)
        return

    msg = []

    if not pieces[0] and lpl:
        msg.append(messages["roles_players"].format(lpl))
        if var.PHASE in var.GAME_PHASES:
            msg.append(messages["roles_gamemode"].format(gamemode.name))
            pieces[0] = str(lpl)

    if pieces[0] and not pieces[0].isdigit():
        valid = GAME_MODES.keys() - var.DISABLED_GAMEMODES - {"roles"}
        mode = pieces.pop(0)

        matches = match_mode(mode, scope=valid, remove_spaces=True)
        if len(matches) == 0:
            wrapper.reply(messages["invalid_mode"].format(mode), prefix_nick=True)
            return
        elif len(matches) > 1:
            wrapper.reply(messages["ambiguous_mode"].format([m.local for m in matches]), prefix_nick=True)
            return

        mode = matches.get().key

        gamemode = GAME_MODES[mode][0]()

        try:
            gamemode.ROLE_GUIDE
        except AttributeError:
            minp = max(GAME_MODES[mode][1], var.MIN_PLAYERS)
            wrapper.reply(messages["roles_disabled"].format(gamemode.name, minp), prefix_nick=True)
            return

    strip = lambda x: re.sub(r"\(.*\)", "", x)
    rolecnt = Counter()
    roles = list((x, map(strip, y)) for x, y in gamemode.ROLE_GUIDE.items())
    roles.sort(key=lambda x: x[0])

    if pieces and pieces[0].isdigit():
        specific = int(pieces[0])
        new = []
        for role in itertools.chain.from_iterable([y for x, y in roles if x <= specific]):
            if role.startswith("-"):
                rolecnt[role[1:]] -= 1
                new.remove(role[1:])
            else:
                rolecnt[role] += 1
                append = "({0})".format(rolecnt[role]) if rolecnt[role] > 1 else ""
                new.append(role + append)

        if new and var.MIN_PLAYERS <= specific <= var.MAX_PLAYERS:
            msg.append("[{0}]".format(specific))
            msg.append(", ".join(new))
        else:
            msg.append(messages["roles_undefined"].format(specific))

    else:
        final = []

        roles_dict = {}
        for num, role_num in roles:
            roles_dict[num] = list(role_num)

        roles_dict_final = roles_dict.copy()

        for num, role_num in reversed(list(roles_dict.items())):
            if num < var.MIN_PLAYERS:
                roles_dict_final[var.MIN_PLAYERS] = list(role_num) + list(roles_dict_final[var.MIN_PLAYERS])
                del roles_dict_final[num]

        for num, role_num in roles_dict_final.items():
            snum = "[{0}]".format(num)
            if num <= lpl:
                snum = "\u0002{0}\u0002".format(snum)
            final.append(snum)
            new = []
            for role in role_num:
                if role.startswith("-"):
                    if role[1:] not in role_num:
                        rolecnt[role[1:]] -= 1
                        roles = role[1:].split("/")
                        localized_roles = [messages.raw("_roles", x)[0] for x in roles]
                        new.append("-{0}".format("/".join(localized_roles)))
                else:
                    if f"-{role}" not in role_num:
                        rolecnt[role] += 1
                        append = "({0})".format(rolecnt[role]) if rolecnt[role] > 1 else ""
                        roles = role.split("/")
                        localized_roles = [messages.raw("_roles", x)[0] for x in roles]
                        new.append("/".join(localized_roles) + append)

            final.append(", ".join(new))

        msg.append(" ".join(final))

    if not msg:
        msg.append(messages["roles_undefined"].format(specific or lpl))

    wrapper.send(*msg)

@command("myrole", pm=True, phases=("day", "night"))
def myrole(wrapper: MessageDispatcher, message: str):
    """Remind you of your current role."""

    var = wrapper.game_state

    ps = get_participants(var)
    if wrapper.source not in ps:
        return

    role = get_main_role(var, wrapper.source)
    if role in Hidden:
        role = var.HIDDEN_ROLE

    evt = Event("myrole", {"role": role, "messages": []})
    if not evt.dispatch(var, wrapper.source):
        return
    role = evt.data["role"]

    wrapper.pm(messages["show_role"].format(role))

    for msg in evt.data["messages"]:
        wrapper.pm(msg)

@command("faftergame", flag="D", pm=True)
def aftergame(wrapper: MessageDispatcher, message: str):
    """Schedule a command to be run after the current game."""
    if not message.strip():
        wrapper.pm(messages["incorrect_syntax"])
        return

    var = wrapper.game_state

    args = re.split(" +", message)
    before, prefix, after = args.pop(0).lower().partition(var.CMD_CHAR)
    if not prefix: # the prefix was not in the string
        cmd = before
    elif after and not before: # message was prefixed
        cmd = after
    else: # some weird thing, e.g. "fsay!" or even "fs!ay"; we don't care about that
        return

    if cmd in COMMANDS:
        def do_action():
            for fn in COMMANDS[cmd]:
                fn.aftergame = True
                context = MessageDispatcher(wrapper.source, channels.Main if fn.chan else users.Bot)
                fn.caller(context, " ".join(args))
                fn.aftergame = False
    else:
        wrapper.pm(messages["command_not_found"])
        return

    if var.PHASE == "none":
        do_action()
        return

    channels.Main.send(messages["command_scheduled"].format(" ".join([cmd] + args), wrapper.source))
    var.AFTER_FLASTGAME = do_action

def _command_disabled(wrapper: MessageDispatcher, message: str):
    wrapper.send(messages["command_disabled_admin"])

@command("flastgame", flag="D", pm=True)
def flastgame(wrapper: MessageDispatcher, message: str):
    """Disables starting or joining a game, and optionally schedules a command to run after the current game ends."""
    for cmdcls in (COMMANDS["join"] + COMMANDS["start"]):
        cmdcls.func = _command_disabled

    channels.Main.send(messages["disable_new_games"].format(wrapper.source))
    wrapper.game_state.ADMIN_TO_PING = wrapper.source

    if message.strip():
        aftergame.func(wrapper, message)

@command("whoami", pm=True)
def whoami(wrapper: MessageDispatcher, message: str):
    if wrapper.source.account:
        wrapper.pm(messages["whoami_loggedin"].format(wrapper.source.account))
    else:
        wrapper.pm(messages["whoami_loggedout"])

@command("setdisplay", pm=True)
def setdisplay(wrapper: MessageDispatcher, message: str):
    if not wrapper.source.account:
        wrapper.pm(messages["not_logged_in"])
        return

    db.set_primary_player(wrapper.source.account)
    wrapper.reply(messages["display_name_set"].format(wrapper.source.account))

# Called from !game and !join, used to vote for a game mode
def vote_gamemode(var, wrapper, gamemode, doreply): # FIXME: remove var
    from src.gamemodes import GAME_MODES
    if var.FGAMED:
        if doreply:
            wrapper.pm(messages["admin_forced_game"])
        return

    allowed = GAME_MODES.keys() - {"roles"} - var.DISABLED_GAMEMODES
    matches = match_mode(gamemode, scope=allowed, remove_spaces=True)
    if len(matches) == 0:
        if doreply:
            wrapper.pm(messages["invalid_mode"].format(gamemode))
        return
    elif len(matches) > 1:
        if doreply:
            wrapper.pm(messages["ambiguous_mode"].format([m.local for m in matches]))
        return

    gamemode = matches.get().key
    if var.GAMEMODE_VOTES.get(wrapper.source) == gamemode:
        wrapper.pm(messages["already_voted_game"].format(gamemode))
    else:
        var.GAMEMODE_VOTES[wrapper.source] = gamemode
        wrapper.send(messages["vote_game_mode"].format(wrapper.source, gamemode))

def _get_gamemodes(var):
    from src.gamemodes import GAME_MODES
    gamemodes = []
    order = {}
    for gm, (cls, min, max, chance) in GAME_MODES.items():
        if gm == "roles" or gm in var.DISABLED_GAMEMODES:
            continue
        order[LocalMode(gm).local] = (min, max)

    for gm in sorted(order.keys()):
        min, max = order[gm]
        if min <= len(get_players(var)) <= max:
            gm = messages["bold"].format(gm)
        gamemodes.append(gm)

    return gamemodes

@command("game", playing=True, phases=("join",))
def game(wrapper: MessageDispatcher, message: str):
    """Vote for a game mode to be picked."""
    var = wrapper.game_state
    if message:
        vote_gamemode(var, wrapper, message.lower().split()[0], doreply=True)
    else:
        wrapper.pm(messages["no_mode_specified"].format(_get_gamemodes(var)))

@command("games", pm=True)
def show_modes(wrapper: MessageDispatcher, message: str):
    """Show the available game modes."""
    wrapper.pm(messages["available_modes"].format(_get_gamemodes(wrapper.game_state)))

def game_help(args=""): # FIXME: Needs DI for var
    return messages["available_mode_setters_help"].format(_get_gamemodes(var))
game.__doc__ = game_help

def _call_command(wrapper, command, no_out=False):
    """
    Executes a system command.

    If `no_out` is True, the command's output will not be sent to IRC,
    unless the exit code is non-zero.
    """

    child = subprocess.Popen(command.split(),
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    (out, err) = child.communicate()
    ret = child.returncode

    if not (no_out and ret == 0):
        for line in (out + err).splitlines():
            wrapper.pm(line.decode("utf-8"))

    if ret != 0:
        if ret < 0:
            cause = "signal"
            ret *= -1
        else:
            cause = "status"

        wrapper.pm(messages["process_exited"].format(command, cause, ret))

    return ret, out

def _git_pull(wrapper):
    (ret, _) = _call_command(wrapper, "git fetch")
    if ret != 0:
        return False

    (ret, out) = _call_command(wrapper, "git status -b --porcelain", no_out=True)
    if ret != 0:
        return False

    if not re.search(rb"behind \d+", out.splitlines()[0]):
        # Already up-to-date
        wrapper.pm(messages["already_up_to_date"])
        return False

    (ret, _) = _call_command(wrapper, "git pull --stat --ff-only")
    return ret == 0

@command("fpull", flag="D", pm=True)
def fpull(wrapper: MessageDispatcher, message: str):
    """Pulls from the repository to update the bot."""
    _git_pull(wrapper)

@command("update", flag="D", pm=True)
def update(wrapper: MessageDispatcher, message: str):
    """Pull from the repository and restart the bot to update it."""

    var = wrapper.game_state

    force = (message.strip() == "-force")

    if var.PHASE in var.GAME_PHASES:
        if var.PHASE == "join" or force:
            stop_game(var, log=False)
        else:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(what="restart", cmd="update"))
            return

    if update.aftergame:
        # Display "Scheduled restart" instead of "Forced restart" when called with !faftergame
        restart_program.aftergame = True

    ret = _git_pull(wrapper)
    if ret:
        restart_program.func(wrapper, "Updating bot")

@command("fsend", owner_only=True, pm=True)
def fsend(wrapper: MessageDispatcher, message: str):
    """Send raw IRC commands to the server."""
    wrapper.source.client.send(message)

def _say(wrapper, rest, cmd, action=False):
    rest = rest.split(" ", 1)

    if len(rest) < 2:
        wrapper.pm(messages["fsend_usage"].format(cmd))
        return

    target, message = rest

    if target.startswith(tuple(hooks.Features["CHANTYPES"])):
        targ = channels.get(target, allow_none=True)
    else:
        targ = users.get(target, allow_multiple=True)
        if len(targ) == 1:
            targ = targ[0]
        else:
            targ = None

    if targ is None:
        targ = IRCContext(target, wrapper.source.client)

    if not wrapper.source.is_owner() and targ is not channels.Main:
        wrapper.pm(messages["invalid_fsend_permissions"])
        return

    if action:
        message = "\u0001ACTION {0}\u0001".format(message)

    targ.send(message, privmsg=True)

@command("fsay", flag="s", pm=True)
def fsay(wrapper: MessageDispatcher, message: str):
    """Talk through the bot as a normal message."""
    _say(wrapper, message, "fsay")

@command("fdo", flag="s", pm=True)
def fdo(wrapper: MessageDispatcher, message: str):
    """Act through the bot as an action."""
    _say(wrapper, message, "fdo", action=True)

def can_run_restricted_cmd(user):
    # if allowed in normal games, restrict it so that it can only be used by dead players and
    # non-players (don't allow active vengeful ghosts either).
    # also don't allow in-channel (e.g. make it pm only)

    if config.Main.get("debug.enabled"):
        return True

    pl = get_participants(var)

    if user in pl:
        return False

    if user.account in {player.account for player in pl}:
        return False

    return True

def spectate_chat(wrapper: MessageDispatcher, message: str, *, is_fspectate: bool):
    if not can_run_restricted_cmd(wrapper.source):
        wrapper.pm(messages["fspectate_restricted"])
        return

    var = wrapper.game_state

    params = message.split(" ")
    on = "on"
    if not len(params):
        wrapper.pm(messages["fspectate_help"])
        return
    elif len(params) > 1:
        on = params[1].lower()
    what = params[0].lower()
    allowed = ("wolfchat", "deadchat") if is_fspectate else ("wolfchat",)
    if what not in allowed or on not in ("on", "off"):
        wrapper.pm(messages["fspectate_help" if is_fspectate else "spectate_help"])
        return

    if on == "off":
        if what == "wolfchat":
            var.SPECTATING_WOLFCHAT.discard(wrapper.source)
        else:
            var.SPECTATING_DEADCHAT.discard(wrapper.source)
        wrapper.pm(messages["fspectate_off"].format(what))
    else:
        players = []
        if what == "wolfchat":
            already_spectating = wrapper.source in var.SPECTATING_WOLFCHAT
            var.SPECTATING_WOLFCHAT.add(wrapper.source)
            players = list(get_players(var, Wolfchat))
            if "src.roles.helper.wolves" in sys.modules:
                from src.roles.helper.wolves import is_known_wolf_ally
                players = [p for p in players if is_known_wolf_ally(var, p, p)]
            if not is_fspectate and not already_spectating and var.SPECTATE_NOTICE:
                spectator = wrapper.source.nick if var.SPECTATE_NOTICE_USER else "Someone"
                for player in players:
                    player.queue_message(messages["fspectate_notice"].format(spectator, what))
                if players:
                    player.send_messages()
        elif var.ENABLE_DEADCHAT:
            if wrapper.source in var.DEADCHAT_PLAYERS:
                wrapper.pm(messages["fspectate_in_deadchat"])
                return
            var.SPECTATING_DEADCHAT.add(wrapper.source)
            players = var.DEADCHAT_PLAYERS
        else:
            wrapper.pm(messages["fspectate_deadchat_disabled"])
            return
        wrapper.pm(messages["fspectate_on"].format(what))
        wrapper.pm("People in {0}: {1}".format(what, ", ".join([player.nick for player in players])))

@command("spectate", flag="p", pm=True, phases=("day", "night"))
def spectate(wrapper: MessageDispatcher, message: str):
    """Spectate wolfchat or deadchat."""
    spectate_chat(wrapper, message, is_fspectate=False)

@command("fspectate", flag="F", pm=True, phases=("day", "night"))
def fspectate(wrapper: MessageDispatcher, message: str):
    """Spectate wolfchat or deadchat."""
    spectate_chat(wrapper, message, is_fspectate=True)

@command("revealroles", flag="a", pm=True, phases=("day", "night"))
def revealroles(wrapper: MessageDispatcher, message: str):
    """Reveal role information."""

    if not can_run_restricted_cmd(wrapper.source):
        wrapper.pm(messages["temp_invalid_perms"])
        return

    var = wrapper.game_state

    output = []
    for role in role_order():
        if var.ROLES.get(role):
            # make a copy since this list is modified
            users = list(var.ROLES[role])
            out = []
            # go through each nickname, adding extra info if necessary
            for user in users:
                evt = Event("revealroles_role", {"special_case": []})
                evt.dispatch(var, user, role)
                special_case = evt.data["special_case"]

                if not evt.prevent_default and user not in var.ORIGINAL_ROLES[role] and role not in var.CURRENT_GAMEMODE.SECONDARY_ROLES:
                    for old_role in role_order(): # order doesn't matter here, but oh well
                        if user in var.ORIGINAL_ROLES[old_role] and user not in var.ROLES[old_role]:
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

@command("fgame", flag="g", phases=("join",))
def fgame(wrapper: MessageDispatcher, message: str):
    """Force a certain game mode to be picked. Disable voting for game modes upon use."""
    from src.gamemodes import GAME_MODES
    var = wrapper.game_state

    if message:
        gamemode = message.strip().lower()
        parts = gamemode.replace("=", " ", 1).split(None, 1)
        if len(parts) > 1:
            gamemode, modeargs = parts
        else:
            gamemode = parts[0]
            modeargs = None

        _fr = messages.raw("_commands", "fgame opt reset")
        if gamemode in _fr:
            reset_settings()
            channels.Main.send(messages["fgame_success"].format(wrapper.source))
            var.FGAMED = False
            return

        allowed = GAME_MODES.keys() - var.DISABLED_GAMEMODES
        gamemode = gamemode.split()[0]
        match = match_mode(gamemode, scope=allowed, remove_spaces=True)
        if len(match) == 0:
            wrapper.pm(messages["invalid_mode"].format(gamemode))
            return
        elif len(match) > 1:
            wrapper.pm(messages["ambiguous_mode"].format([m.local for m in match]))
            return
        parts[0] = match.get().key

        if cgamemode(var, "=".join(parts)):
            channels.Main.send(messages["fgame_success"].format(wrapper.source))
            var.FGAMED = True
    else:
        wrapper.pm(fgame.__doc__())

def fgame_help(args=""):
    args = args.strip()
    from src.gamemodes import GAME_MODES

    if not args:
        return messages["available_mode_setters"].format(GAME_MODES.keys() - var.DISABLED_GAMEMODES)
    elif args in GAME_MODES.keys() and args not in var.DISABLED_GAMEMODES:
        return GAME_MODES[args][0].__doc__ or messages["setter_no_doc"].format(args)
    else:
        return messages["setter_not_found"].format(args)


fgame.__doc__ = fgame_help

# eval/exec/freceive are owner-only but also marked with "d" flag
# to disable them outside of debug mode
@command("eval", owner_only=True, flag="d", pm=True)
def pyeval(wrapper: MessageDispatcher, message: str):
    """Evaluate a Python expression."""
    try:
        wrapper.send(str(eval(message))[:500])
    except Exception as e:
        wrapper.send("{e.__class__.__name__}: {e}".format(e=e))

@command("exec", owner_only=True, flag="d", pm=True)
def py(wrapper: MessageDispatcher, message: str):
    """Execute arbitrary Python code."""
    try:
        exec(message)
    except Exception as e:
        wrapper.send("{e.__class__.__name__}: {e}".format(e=e))

@command("freceive", owner_only=True, flag="d", pm=True)
def freceive(wrapper: MessageDispatcher, message: str):
    from oyoyo.parse import parse_raw_irc_command
    try:
        line = message.encode("utf-8")
        prefix, cmd, args = parse_raw_irc_command(line)
        prefix = prefix.decode("utf-8")
        args = [arg.decode("utf-8") for arg in args if isinstance(arg, bytes)]
        if cmd in ("privmsg", "notice"):
            is_notice = cmd == "notice"
            handler.on_privmsg(wrapper.client, prefix, *args, notice=is_notice)
        else:
            handler.unhandled(wrapper.client, prefix, cmd, *args)
    except Exception as e:
        wrapper.send("{e.__class__.__name__}: {e}".format(e=e))

def _force_command(wrapper: MessageDispatcher, name: str, players, message):
    for user in players:
        handler.parse_and_dispatch(wrapper, name, message, force=user)
    wrapper.send(messages["operation_successful"])

@command("force", flag="d")
def force(wrapper: MessageDispatcher, message: str):
    """Force a certain player to use a specific command."""
    msg = re.split(" +", message)
    if len(msg) < 2:
        wrapper.send(messages["incorrect_syntax"])
        return

    target = msg.pop(0).strip()
    match = users.complete_match(target, get_participants(wrapper.game_state))
    if target == "*":
        players = get_players(wrapper.game_state)
    elif not match:
        wrapper.send(messages["invalid_target"])
        return
    else:
        players = [match.get()]

    _force_command(wrapper, msg.pop(0), players, " ".join(msg))

@command("rforce", flag="d")
def rforce(wrapper: MessageDispatcher, message: str):
    """Force all players of a given role to perform a certain action."""
    msg = re.split(" +", message)
    if len(msg) < 2:
        wrapper.send(messages["incorrect_syntax"])
        return

    var = wrapper.game_state

    target = msg.pop(0).strip().lower()
    possible = match_role(target, allow_special=False, remove_spaces=True)
    if target == "*":
        players = get_players(var)
    elif possible:
        players = get_all_players(var, (possible.get().key,))
    elif len(possible) > 1:
        wrapper.send(messages["ambiguous_role"].format([r.singular for r in possible]))
        return
    else:
        wrapper.send(messages["no_such_role"].format(message))
        return

    _force_command(wrapper, msg.pop(0), players, " ".join(msg))

@command("frole", flag="d", phases=("join",))
def frole(wrapper: MessageDispatcher, message: str):
    """Force a player into a certain role."""
    var = wrapper.game_state
    pl = get_players(var)

    parts = message.lower().split(",")
    for part in parts:
        try:
            (name, role) = part.split(":", 1)
        except ValueError:
            wrapper.send(messages["frole_incorrect"].format(part))
            return
        umatch = users.complete_match(name.strip(), pl)
        rmatch = match_role(role.strip(), allow_special=False)
        role = None
        if rmatch:
            role = rmatch.get().key
        if not umatch or not rmatch or role == var.DEFAULT_ROLE:
            wrapper.send(messages["frole_incorrect"].format(part))
            return
        var.FORCE_ROLES[role].add(umatch.get())

    wrapper.send(messages["operation_successful"])

@command("ftotem", flag="d", phases=("night",))
def ftotem(wrapper: MessageDispatcher, message: str):
    """Force a shaman to have a particular totem."""
    msg = re.split(" +", message)
    if len(msg) < 2:
        wrapper.send(messages["incorrect_syntax"])
        return

    var = wrapper.game_state

    target = msg.pop(0).strip()
    match = users.complete_match(target, get_players(var))
    if not match:
        wrapper.send(messages["invalid_target"])
        return

    from src.roles.helper.shamans import change_totem
    try:
        change_totem(var, match.get(), " ".join(msg))
    except ValueError as e:
        wrapper.send(str(e))
        return

    wrapper.send(messages["operation_successful"])
