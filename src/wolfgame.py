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

import copy
import fnmatch
import functools
import itertools
import json
import math
import os
import platform
import random
import re
import signal
import socket
import string
import subprocess
import sys
import threading
import time
import traceback
import urllib.request

from collections import defaultdict, deque, Counter
from datetime import datetime, timedelta
from typing import Set

from oyoyo.parse import parse_nick

import botconfig
import src
import src.settings as var
from src.utilities import *
from src import db, events, dispatcher, channels, users, hooks, logger, debuglog, errlog, plog, cats, handler
from src.users import User

from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.decorators import command, hook, handle_error, event_listener, COMMANDS
from src.dispatcher import MessageDispatcher
from src.messages import messages
from src.warnings import *
from src.context import IRCContext
from src.status import try_protection, add_dying, is_dying, kill_players, get_absent, is_silent
from src.votes import chk_decision
from src.cats import All, Wolf, Wolfchat, Wolfteam, Killer, Neutral, Hidden

from src.functions import (
    get_players, get_all_players, get_participants,
    get_main_role, get_all_roles, get_reveal_role,
    get_target, change_role
   )

# done this way so that events is accessible in !eval (useful for debugging)
Event = events.Event

# Game Logic Begins:

var.LAST_STATS = None
var.LAST_ADMINS = None
var.LAST_GSTATS = None
var.LAST_PSTATS = None
var.LAST_RSTATS = None
var.LAST_TIME = None
var.LAST_GOAT = {}

var.USERS = {}

var.ADMIN_PINGING = False
var.DCED_LOSERS = UserSet() # type: Set[users.User]
var.PLAYERS = {}
var.DCED_PLAYERS = {}
var.ADMIN_TO_PING = None
var.AFTER_FLASTGAME = None
var.PINGING_IFS = False
var.TIMERS = {}
var.PHASE = "none"
var.OLD_MODES = defaultdict(set)

var.ROLES = UserDict() # type: Dict[str, Set[users.User]]
var.ORIGINAL_ROLES = UserDict() # type: Dict[str, Set[users.User]]
var.MAIN_ROLES = UserDict() # type: Dict[users.User, str]
var.ORIGINAL_MAIN_ROLES = UserDict() # type: Dict[users.User, str]
var.ALL_PLAYERS = UserList()
var.FORCE_ROLES = DefaultUserDict(UserSet)

var.DEAD = UserSet()

var.DEADCHAT_PLAYERS = UserSet()

var.SPECTATING_WOLFCHAT = UserSet()
var.SPECTATING_DEADCHAT = UserSet()

var.ORIGINAL_SETTINGS = {}

var.LAST_SAID_TIME = {}

var.GAME_START_TIME = datetime.now()  # for idle checker only
var.CAN_START_TIME = 0
var.STARTED_DAY_PLAYERS = 0

var.DISCONNECTED = {}  # players who are still alive but disconnected

var.RESTARTING = False

if botconfig.DEBUG_MODE and var.DISABLE_DEBUG_MODE_TIMERS:
    var.NIGHT_TIME_LIMIT = 0 # 120
    var.NIGHT_TIME_WARN = 0 # 90
    var.DAY_TIME_LIMIT = 0 # 720
    var.DAY_TIME_WARN = 0 # 600
    var.SHORT_DAY_LIMIT = 0 # 520
    var.SHORT_DAY_WARN = 0 # 400

if botconfig.DEBUG_MODE and var.DISABLE_DEBUG_MODE_REAPER:
    var.KILL_IDLE_TIME = 0 # 300
    var.WARN_IDLE_TIME = 0 # 180
    var.PM_WARN_IDLE_TIME = 0 # 240
    var.JOIN_TIME_LIMIT = 0 # 3600

if botconfig.DEBUG_MODE and var.DISABLE_DEBUG_MODE_STASIS:
    var.LEAVE_PENALTY = 0
    var.IDLE_PENALTY = 0
    var.PART_PENALTY = 0
    var.ACC_PENALTY = 0

if botconfig.DEBUG_MODE and var.DISABLE_DEBUG_MODE_TIME_LORD:
    var.TIME_LORD_DAY_LIMIT = 0 # 60
    var.TIME_LORD_DAY_WARN = 0 # 45
    var.TIME_LORD_NIGHT_LIMIT = 0 # 30
    var.TIME_LORD_NIGHT_WARN = 0 # 20

plog("Loading Werewolf IRC bot")

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
            forced_exit.func(var, wrapper, "")
        elif signum == SIGUSR1:
            restart_program.func(var, wrapper, "")
        elif signum == SIGUSR2:
            plog("Scheduling aftergame restart")
            aftergame.func(var, wrapper, "frestart")

    signal.signal(signal.SIGINT, sighandler)
    signal.signal(signal.SIGTERM, sighandler)

    if SIGUSR1:
        signal.signal(SIGUSR1, sighandler)

    if SIGUSR2:
        signal.signal(SIGUSR2, sighandler)

    def who_end(event, var, request):
        if request is channels.Main:
            if "WHOX" not in hooks.Features:
                if not var.DISABLE_ACCOUNTS:
                    plog("IRCd does not support WHOX, disabling account-related features.")
                var.DISABLE_ACCOUNTS = True
                var.ACCOUNTS_ONLY = False

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

            var.CURRENT_GAMEMODE = var.GAME_MODES["default"][0]()
            reset()

            events.remove_listener("who_end", who_end)

    def end_listmode(event, var, chan, mode):
        if chan is channels.Main and mode == var.QUIET_MODE:
            pending = []
            for quiet in chan.modes.get(mode, ()):
                if re.search(r"^{0}.+\!\*@\*$".format(var.QUIET_PREFIX), quiet):
                    pending.append(("-" + mode, quiet))
            accumulator.send(pending)
            next(accumulator, None)

            events.remove_listener("end_listmode", end_listmode)

    def mode_change(event, var, actor, target):
        if target is channels.Main: # we may or may not be opped; assume we are
            accumulator.send([])
            next(accumulator, None)

            events.remove_listener("mode_change", mode_change)

    events.add_listener("who_end", who_end)
    events.add_listener("end_listmode", end_listmode)
    events.add_listener("mode_change", mode_change)

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

@hook("mode") # XXX Get rid of this when the user/channel refactor is done
def check_for_modes(cli, rnick, chan, modeaction, *target):
    nick = parse_nick(rnick)[0]
    if chan != botconfig.CHANNEL:
        return
    oldpref = ""
    trgt = ""
    keeptrg = False
    target = list(target)
    if target and target != [users.Bot.nick]:
        while modeaction:
            if len(modeaction) > 1:
                prefix = modeaction[0]
                change = modeaction[1]
            else:
                prefix = oldpref
                change = modeaction[0]
            if not keeptrg:
                if target:
                    trgt = target.pop(0)
                else:
                    trgt = "" # Last item, no target
            keeptrg = False
            if not prefix in ("-", "+"):
                change = prefix
                prefix = oldpref
            else:
                oldpref = prefix
            modeaction = modeaction[modeaction.index(change)+1:]
            if change in var.MODES_NOSET:
                keeptrg = True
            if prefix == "-" and change in var.MODES_ONLYSET:
                keeptrg = True
            if change not in var.MODES_PREFIXES.values():
                continue
            if trgt in var.USERS:
                if prefix == "+":
                    var.USERS[trgt]["modes"].add(change)
                    if change in var.USERS[trgt]["moded"]:
                        var.USERS[trgt]["moded"].remove(change)
                elif change in var.USERS[trgt]["modes"]:
                    var.USERS[trgt]["modes"].remove(change)

def reset_settings():
    var.CURRENT_GAMEMODE.teardown()
    var.CURRENT_GAMEMODE = var.GAME_MODES["default"][0]()
    for attr in list(var.ORIGINAL_SETTINGS.keys()):
        setattr(var, attr, var.ORIGINAL_SETTINGS[attr])
    var.ORIGINAL_SETTINGS.clear()

def reset_modes_timers(var):
    # Reset game timers
    with var.WARNING_LOCK: # make sure it isn't being used by the ping join handler
        for x, timr in var.TIMERS.items():
            timr[0].cancel()
        var.TIMERS = {}

    # Reset modes
    cmodes = []
    for plr in get_players():
        if not plr.is_fake:
            cmodes.append(("-v", plr.nick))
    for user, modes in var.OLD_MODES.items():
        for mode in modes:
            cmodes.append(("+" + mode, user))
    var.OLD_MODES.clear()
    if var.QUIET_DEAD_PLAYERS:
        for deadguy in var.DEAD:
            if not deadguy.is_fake:
                cmodes.append(("-{0}".format(var.QUIET_MODE), var.QUIET_PREFIX + deadguy.nick + "!*@*"))
    channels.Main.mode("-m", *cmodes)

def reset():
    var.PHASE = "none" # "join", "day", or "night"
    var.GAME_ID = 0
    var.ALL_PLAYERS.clear()
    var.RESTART_TRIES = 0
    var.DEAD.clear()
    var.JOINED_THIS_GAME = set() # keeps track of who already joined this game at least once (hostmasks)
    var.JOINED_THIS_GAME_ACCS = set() # same, except accounts
    var.PINGED_ALREADY = set()
    var.PINGED_ALREADY_ACCS = set()
    var.FGAMED = False
    var.GAMEMODE_VOTES = {} #list of players who have used !game
    var.ROLE_STATS = frozenset() # type: FrozenSet[FrozenSet[Tuple[str, int]]]

    reset_settings()

    var.LAST_SAID_TIME.clear()
    var.PLAYERS.clear()
    var.DCED_PLAYERS.clear()
    var.DISCONNECTED.clear()
    var.DCED_LOSERS.clear()
    var.SPECTATING_WOLFCHAT.clear()
    var.SPECTATING_DEADCHAT.clear()

    var.ROLES.clear()
    var.ORIGINAL_ROLES.clear()
    var.ROLES["person"] = UserSet()
    var.MAIN_ROLES.clear()
    var.ORIGINAL_MAIN_ROLES.clear()
    var.FORCE_ROLES.clear()

    evt = Event("reset", {})
    evt.dispatch(var)

@command("sync", "fsync", flag="m", pm=True)
def fsync(var, wrapper, message):
    """Makes the bot apply the currently appropriate channel modes."""
    sync_modes(var)

@event_listener("sync_modes")
def on_sync_modes(evt, var):
    sync_modes(var)

def sync_modes(var):
    voices = [None]
    mode = hooks.Features["PREFIX"]["+"]
    pl = get_players()

    for user in channels.Main.users:
        if var.DEVOICE_DURING_NIGHT and var.PHASE == "night":
            if mode in user.channels[channels.Main]:
                voices.append(("-" + mode, user))
        elif user in pl and mode not in user.channels[channels.Main]:
            voices.append(("+" + mode, user))
        elif user not in pl and mode in user.channels[channels.Main]:
            voices.append(("-" + mode, user))

    if var.PHASE in var.GAME_PHASES:
        voices[0] = "+m"
    else:
        voices[0] = "-m"

    channels.Main.mode(*voices)

@command("refreshdb", flag="m", pm=True)
def refreshdb(var, wrapper, message):
    """Updates our tracking vars to the current db state."""
    db.expire_stasis()
    db.init_vars()
    expire_tempbans()
    wrapper.reply("Done.")

@command("fdie", "fbye", flag="F", pm=True)
def forced_exit(var, wrapper, message):
    """Forces the bot to close."""

    args = message.split()

    # Force in debug mode by default
    force = botconfig.DEBUG_MODE

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
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(
                what="stop", cmd="fdie", prefix=botconfig.CMD_CHAR))
            return

    reset_modes_timers(var)
    reset()

    msg = "{0} quit from {1}"

    if message.strip():
        msg += " ({2})"

    hooks.quit(wrapper, msg.format("Scheduled" if forced_exit.aftergame else "Forced",
               wrapper.source, message.strip()))

def _restart_program(mode=None):
    plog("RESTARTING")

    python = sys.executable

    if mode is not None:
        print(mode)
        assert mode in ("normal", "verbose", "debug")
        os.execl(python, python, sys.argv[0], "--{0}".format(mode))
    else:
        os.execl(python, python, *sys.argv)


@command("restart", "frestart", flag="D", pm=True)
def restart_program(var, wrapper, message):
    """Restarts the bot."""

    args = message.split()

    # Force in debug mode by default
    force = botconfig.DEBUG_MODE

    if args and args[0] == "-force":
        force = True
        message = " ".join(args[1:])

    if var.PHASE in var.GAME_PHASES:
        if var.PHASE == "join" or force:
            stop_game(var, log=False)
        else:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(
                what="restart", cmd="frestart", prefix=botconfig.CMD_CHAR))
            return

    reset_modes_timers(var)
    db.set_pre_restart_state(list_players())
    reset()

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
                wrapper.pm(messages["invalid_restart_mode"].format(mode, ", ".join(valid_modes)))
                return

            msg += " in {0} mode".format(mode)
            message = " ".join(args[1:])

    if message:
        msg += " ({0})".format(message.strip())

    hooks.quit(wrapper, msg.format(wrapper.source, message.strip()))

    def restart_buffer(evt, var, user, reason):
        # restart the bot once our quit message goes though to ensure entire IRC queue is sent
        if user is users.Bot:
            _restart_program(mode)

    events.add_listener("server_quit", restart_buffer)

    # This is checked in the on_error handler. Some IRCds, such as InspIRCd, don't send the bot
    # its own QUIT message, so we need to use ERROR. Ideally, we shouldn't even need the above
    # handler now, but I'm keeping it for now just in case.
    var.RESTARTING = True

@command("ping", pm=True)
def pinger(var, wrapper, message):
    """Check if you or the bot is still connected."""
    wrapper.reply(messages["ping"].format(
        nick=wrapper.source, bot_nick=users.Bot,
        cmd_char=botconfig.CMD_CHAR))

@command("simple", pm=True)
def mark_simple_notify(var, wrapper, message):
    """Makes the bot give you simple role instructions, in case you are familiar with the roles."""

    temp = wrapper.source.lower()

    account = temp.account
    userhost = temp.userhost

    if account is None and var.ACCOUNTS_ONLY:
        wrapper.pm(messages["not_logged_in"])
        return

    simple = wrapper.source.prefers_simple()
    simple_set, value = (var.SIMPLE_NOTIFY, userhost) if account is None else (var.SIMPLE_NOTIFY_ACCS, account)
    action, toggle = (simple_set.discard, "off") if simple else (simple_set.add, "on")

    action(value)
    db.toggle_simple(account, userhost)
    wrapper.pm(messages["simple_" + toggle])

@command("notice", pm=True)
def mark_prefer_notice(var, wrapper, message):
    """Makes the bot NOTICE you for every interaction."""

    if wrapper.private and message:
        # Ignore if called in PM with parameters, likely a message to wolfchat
        # and not an intentional invocation of this command
        return

    temp = wrapper.source.lower()

    account = temp.account
    userhost = temp.userhost

    if account is None and var.ACCOUNTS_ONLY:
        wrapper.pm(messages["not_logged_in"])
        return

    notice = wrapper.source.prefers_notice()
    notice_set, value = (var.PREFER_NOTICE, userhost) if account is None else (var.PREFER_NOTICE_ACCS, account)
    action, toggle = (notice_set.discard, "off") if notice else (notice_set.add, "on")

    action(value)
    db.toggle_notice(account, userhost)
    wrapper.pm(messages["notice_" + toggle])

@command("swap", "replace", pm=True, phases=("join", "day", "night"))
def replace(var, wrapper, message):
    """Swap out a player logged in to your account."""
    if wrapper.source not in channels.Main.users:
        wrapper.pm(messages["invalid_channel"].format(channels.Main))
        return

    if wrapper.source in get_players():
        wrapper.pm(messages["already_playing"].format("You"))
        return

    if wrapper.source.account is None:
        wrapper.pm(messages["not_logged_in"])
        return

    rest = message.split()

    if not rest: # bare call
        target = None

        for user in var.ALL_PLAYERS:
            if users.equals(user.account, wrapper.source.account):
                if user is wrapper.source or user not in get_participants():
                    continue
                elif target is None:
                    target = user
                else:
                    wrapper.pm(messages["swap_notice"].format(botconfig.CMD_CHAR))
                    return

        if target is None:
            wrapper.pm(messages["account_not_playing"])
            return

    else:
        pl = get_participants()

        target, _ = users.complete_match(rest[0], pl)

        if target is None:
            wrapper.pm(messages["target_not_playing"])
            return

        if target not in pl:
            wrapper.pm(messages["target_no_longer_playing" if target in var.DEAD else "target_not_playing"])
            return

        if target.account is None:
            wrapper.pm(messages["target_not_logged_in"])
            return

    if users.equals(target.account, wrapper.source.account) and target is not wrapper.source:
        rename_player(var, wrapper.source, target.nick)
        target.swap(wrapper.source)
        if var.PHASE in var.GAME_PHASES:
            return_to_village(var, target, show_message=False)

        if not var.DEVOICE_DURING_NIGHT or var.PHASE != "night":
            channels.Main.mode(("-v", target), ("+v", wrapper.source))

        channels.Main.send(messages["player_swap"].format(wrapper.source, target))
        if var.PHASE in var.GAME_PHASES:
            myrole.func(var, wrapper, "")


@command("pingif", "pingme", "pingat", "pingpref", pm=True)
def altpinger(var, wrapper, message):
    """Pings you when the number of players reaches your preference. Usage: "pingif <players>". https://werewolf.chat/Pingif"""

    if wrapper.source.account is None and var.ACCOUNTS_ONLY:
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
    with var.WARNING_LOCK:
        var.PINGING_IFS = True
        to_ping = []
        pl = list_players()

        checker = set()
        chk_acc = set()

        # Add accounts/hosts to the list of possible players to ping
        if not var.DISABLE_ACCOUNTS:
            for num in var.PING_IF_NUMS_ACCS:
                if num <= len(pl):
                    for acc in var.PING_IF_NUMS_ACCS[num]:
                        if db.has_unacknowledged_warnings(acc, None):
                            continue
                        chk_acc.add(users.lower(acc))

        if not var.ACCOUNTS_ONLY:
            for num in var.PING_IF_NUMS:
                if num <= len(pl):
                    for hostmask in var.PING_IF_NUMS[num]:
                        if db.has_unacknowledged_warnings(None, hostmask):
                            continue
                        checker.add(users.lower(hostmask, casemapping="ascii"))

        # Don't ping alt connections of users that have already joined
        if not var.DISABLE_ACCOUNTS:
            for player in pl:
                user = users._get(player) # FIXME
                var.PINGED_ALREADY_ACCS.add(users.lower(user.account))

        # Remove players who have already been pinged from the list of possible players to ping
        chk_acc -= var.PINGED_ALREADY_ACCS
        checker -= var.PINGED_ALREADY

        # If there is nobody to ping, do nothing
        if not chk_acc and not checker:
            var.PINGING_IFS = False
            return

        def get_altpingers(event, var, chan, user):
            if event.params.away or user.stasis_count() or not var.PINGING_IFS or user is users.Bot or user.nick in pl: # FIXME: Fix this when list_players() returns User instances
                return

            temp = user.lower()
            if temp.account in chk_acc:
                to_ping.append(temp)
                var.PINGED_ALREADY_ACCS.add(temp.account)
                return

            if not var.ACCOUNTS_ONLY:
                if temp.userhost in checker:
                    to_ping.append(temp)
                    var.PINGED_ALREADY.add(temp.userhost)

        def ping_altpingers(event, var, request):
            if request is channels.Main:
                var.PINGING_IFS = False
                if to_ping:
                    to_ping.sort(key=lambda x: x.nick)
                    user_list = [(user.ref or user).nick for user in to_ping]

                    msg_prefix = messages["ping_player"].format(len(pl))
                    channels.Main.send(*user_list, first=msg_prefix)
                    del to_ping[:]

                events.remove_listener("who_result", get_altpingers)
                events.remove_listener("who_end", ping_altpingers)

        events.add_listener("who_result", get_altpingers)
        events.add_listener("who_end", ping_altpingers)

        channels.Main.who()

def join_deadchat(var, *all_users):
    if not var.ENABLE_DEADCHAT or var.PHASE not in var.GAME_PHASES:
        return

    to_join = []
    pl = get_participants()

    for user in all_users:
        if user.stasis_count() or user in pl or user in var.DEADCHAT_PLAYERS:
            continue
        to_join.append(user)

    if not to_join:
        return

    if len(to_join) == 1:
        msg = messages["player_joined_deadchat"].format(to_join[0])
    elif len(to_join) == 2:
        msg = messages["multiple_joined_deadchat"].format(*to_join)
    else:
        msg = messages["multiple_joined_deadchat"].format("\u0002, \u0002".join([user.nick for user in to_join[:-1]]), to_join[-1])

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
def deadchat_pref(var, wrapper, message):
    """Toggles auto joining deadchat on death."""
    if not var.ENABLE_DEADCHAT:
        return

    temp = wrapper.source.lower()

    if wrapper.source.account is None:
        if var.ACCOUNTS_ONLY:
            wrapper.pm(messages["not_logged_in"])
            return

        value = temp.host
        variable = var.DEADCHAT_PREFS

    else:
        value = temp.account
        variable = var.DEADCHAT_PREFS_ACCS

    if value in variable:
        wrapper.pm(messages["chat_on_death"])
        variable.remove(value)
    else:
        wrapper.pm(messages["no_chat_on_death"])
        variable.add(value)

    db.toggle_deadchat(temp.account, temp.host)

@command("join", "j", pm=True)
def join(var, wrapper, message):
    """Either starts a new game of Werewolf or joins an existing game that has not started yet."""
    # keep this and the event in fjoin() in sync
    evt = Event("join", {
        "join_player": join_player,
        "join_deadchat": join_deadchat,
        "vote_gamemode": vote_gamemode
        })
    if not evt.dispatch(var, wrapper, message, forced=False):
        return
    if var.PHASE in ("none", "join"):
        if wrapper.private:
            return
        if var.ACCOUNTS_ONLY:
            if wrapper.source.account is None:
                wrapper.pm(messages["not_logged_in"])
                return
        if evt.data["join_player"](var, wrapper) and message:
            evt.data["vote_gamemode"](var, wrapper, message.lower().split()[0], doreply=False)

    else: # join deadchat
        if wrapper.private and wrapper.source is not wrapper.target:
            evt.data["join_deadchat"](var, wrapper.source)

def join_player(var, wrapper, who=None, forced=False, *, sanity=True):
    if who is None:
        who = wrapper.source

    pl = list_players()
    if wrapper.target is not channels.Main:
        return False

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
    if wrapper.source is who and db.has_unacknowledged_warnings(temp.account, temp.rawnick):
        wrapper.pm(messages["warn_unacked"])
        return False

    cmodes = []
    if not wrapper.source.is_fake:
        cmodes.append(("+v", wrapper.source))
    if var.PHASE == "none":
        if not wrapper.source.is_fake:
            for mode in var.AUTO_TOGGLE_MODES & wrapper.source.channels[channels.Main]:
                cmodes.append(("-" + mode, wrapper.source))
                var.OLD_MODES[wrapper.source].add(mode)
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
        if wrapper.source.userhost:
            var.JOINED_THIS_GAME.add(wrapper.source.userhost)
        if wrapper.source.account:
            var.JOINED_THIS_GAME_ACCS.add(wrapper.source.account)
        var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.MINIMUM_WAIT)
        wrapper.send(messages["new_game"].format(wrapper.source))

        # Set join timer
        if var.JOIN_TIME_LIMIT > 0:
            t = threading.Timer(var.JOIN_TIME_LIMIT, kill_join, [var, wrapper])
            var.TIMERS["join"] = (t, time.time(), var.JOIN_TIME_LIMIT)
            t.daemon = True
            t.start()

    elif wrapper.source.nick in pl: # FIXME: To fix when everything returns Users
        who.send(messages["already_playing"].format("You" if who is wrapper.source else "They"), notice=True)
        # if we're not doing insane stuff, return True so that one can use !join to vote for a game mode
        # even if they are already joined. If we ARE doing insane stuff, return False to indicate that
        # the player was not successfully joined by this call.
        return sanity
    elif len(pl) >= var.MAX_PLAYERS:
        who.send(messages["too_many_players"], notice=True)
        return False
    elif sanity and var.PHASE != "join":
        who.send(messages["game_already_running"], notice=True)
        return False
    else:
        if not botconfig.DEBUG_MODE:
            for nick in pl:
                if users.equals(users._get(nick).account, temp.account): # FIXME
                    msg = messages["account_already_joined"]
                    if who is wrapper.source:
                        who.send(msg.format(who, "your", messages["join_swap_instead"].format(botconfig.CMD_CHAR)), notice=True)
                    else:
                        who.send(msg.format(who, "their", ""), notice=True)
                    return

        var.ALL_PLAYERS.append(wrapper.source)
        if not wrapper.source.is_fake or not botconfig.DEBUG_MODE:
            for mode in var.AUTO_TOGGLE_MODES & wrapper.source.channels[channels.Main]:
                cmodes.append(("-" + mode, wrapper.source))
                var.OLD_MODES[wrapper.source].add(mode)
            wrapper.send(messages["player_joined"].format(wrapper.source, len(pl) + 1))
        if not sanity:
            # Abandon Hope All Ye Who Enter Here
            leave_deadchat(var, wrapper.source)
            var.SPECTATING_DEADCHAT.discard(wrapper.source)
            var.SPECTATING_WOLFCHAT.discard(wrapper.source)
            return True
        var.ROLES["person"].add(wrapper.source)
        var.MAIN_ROLES[wrapper.source] = "person"
        if not wrapper.source.is_fake:
            if wrapper.source.userhost not in var.JOINED_THIS_GAME and wrapper.source.account not in var.JOINED_THIS_GAME_ACCS:
                # make sure this only happens once
                var.JOINED_THIS_GAME.add(wrapper.source.userhost)
                if wrapper.source.account:
                    var.JOINED_THIS_GAME_ACCS.add(wrapper.source.account)
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

    with var.WARNING_LOCK:
        if "join_pinger" in var.TIMERS:
            var.TIMERS["join_pinger"][0].cancel()

        t = threading.Timer(10, join_timer_handler, (var,))
        var.TIMERS["join_pinger"] = (t, time.time(), 10)
        t.daemon = True
        t.start()

    if not wrapper.source.is_fake or not botconfig.DEBUG_MODE:
        channels.Main.mode(*cmodes)

    return True

@handle_error
def kill_join(var, wrapper):
    pl = [x.nick for x in get_players()]
    pl.sort(key=lambda x: x.lower())
    reset_modes_timers(var)
    reset()
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
def fjoin(var, wrapper, message):
    """Forces someone to join a game."""
    # keep this and the event in def join() in sync
    evt = Event("join", {
        "join_player": join_player,
        "join_deadchat": join_deadchat,
        "vote_gamemode": vote_gamemode
        })

    if not evt.dispatch(var, wrapper, message, forced=True):
        return
    noticed = False
    fake = False
    if not message.strip():
        evt.data["join_player"](var, wrapper, forced=True)

    parts = re.split(" +", message)
    possible_users = {u.lower().nick for u in wrapper.target.users}
    to_join = []
    if not botconfig.DEBUG_MODE:
        match = complete_one_match(users.lower(parts[0]), possible_users)
        if match:
            to_join.append(match)
    else:
        for i, s in enumerate(parts):
            match = complete_one_match(users.lower(s), possible_users)
            if match:
                to_join.append(match)
            else:
                to_join.append(s)
    for tojoin in to_join:
        tojoin = tojoin.strip()
        # Allow joining single number fake users in debug mode
        if users.predicate(tojoin) and botconfig.DEBUG_MODE:
            user = users._add(wrapper.client, nick=tojoin) # FIXME
            evt.data["join_player"](var, type(wrapper)(user, wrapper.target), forced=True, who=wrapper.source)
            continue
        # Allow joining ranges of numbers as fake users in debug mode
        if "-" in tojoin and botconfig.DEBUG_MODE:
            first, hyphen, last = tojoin.partition("-")
            if first.isdigit() and last.isdigit():
                if int(last)+1 - int(first) > var.MAX_PLAYERS - len(list_players()):
                    wrapper.send(messages["too_many_players_to_join"].format(wrapper.source.nick))
                    break
                fake = True
                for i in range(int(first), int(last)+1):
                    user = users._add(wrapper.client, nick=str(i)) # FIXME
                    evt.data["join_player"](var, type(wrapper)(user, wrapper.target), forced=True, who=wrapper.source)
                continue
        if not tojoin:
            continue

        maybe_user = None

        for user in wrapper.target.users:
            if users.equals(user.nick, tojoin):
                maybe_user = user
                break
        else:
            if not users.predicate(tojoin) or botconfig.DEBUG_MODE:
                if not noticed: # important
                    wrapper.send("{0}{1}".format(wrapper.source, messages["fjoin_in_chan"]))
                    noticed = True
                continue

        if maybe_user is not None:
            if not botconfig.DEBUG_MODE and var.ACCOUNTS_ONLY:
                if maybe_user.account is None:
                    wrapper.pm(messages["account_not_logged_in"].format(maybe_user))
                    return
        elif botconfig.DEBUG_MODE:
            fake = True

        if maybe_user is not users.Bot:
            if maybe_user is None and users.predicate(tojoin) and botconfig.DEBUG_MODE:
                maybe_user = users._add(wrapper.client, nick=tojoin) # FIXME
            evt.data["join_player"](var, type(wrapper)(maybe_user, wrapper.target), forced=True, who=wrapper.source)
        else:
            wrapper.pm(messages["not_allowed"])
    if fake:
        wrapper.send(messages["fjoin_success"].format(wrapper.source, len(list_players())))

@command("fleave", "fquit", flag="A", pm=True, phases=("join", "day", "night"))
def fleave(var, wrapper, message):
    """Force someone to leave the game."""

    for person in re.split(" +", message):
        person = person.strip()
        if not person:
            continue

        target, _ = users.complete_match(person, get_players())
        dead_target = None
        if var.PHASE in var.GAME_PHASES:
            dead_target, _ = users.complete_match(person, var.DEADCHAT_PLAYERS)
        if target is not None:
            if wrapper.target is not channels.Main:
                wrapper.pm(messages["fquit_fail"])
                return

            msg = [messages["fquit_success"].format(wrapper.source, target)]
            if get_main_role(target) != "person" and var.ROLE_REVEAL in ("on", "team"):
                msg.append(messages["fquit_goodbye"].format(get_reveal_role(target)))
            if var.PHASE == "join":
                player_count = len(list_players()) - 1
                to_say = "new_player_count"
                if not player_count:
                    to_say = "no_players_remaining"
                msg.append(messages[to_say].format(player_count))

            wrapper.send(*msg)

            if var.PHASE != "join":
                if target.nick in var.PLAYERS:
                    var.DCED_PLAYERS[target.nick] = var.PLAYERS.pop(target.nick)

            add_dying(var, target, "bot", "fquit", death_triggers=False)
            kill_players(var)

        elif dead_target is not None:
            leave_deadchat(var, dead_target, force=wrapper.source)
            if wrapper.source not in var.DEADCHAT_PLAYERS:
                wrapper.pm(messages["admin_fleave_deadchat"].format(dead_target))

        else:
            wrapper.send(messages["not_playing"].format(person))
            return

@event_listener("chan_kick")
def kicked_modes(evt, var, chan, actor, target, reason):
    if target is users.Bot and chan is channels.Main:
        chan.join()
    var.OLD_MODES.pop(target, None)

@event_listener("chan_part")
def parted_modes(evt, var, chan, user, reason):
    if user is users.Bot and chan is channels.Main:
        chan.join()
    var.OLD_MODES.pop(user, None)

@command("stats", "players", pm=True, phases=("join", "day", "night"))
def stats(var, wrapper, message):
    """Displays the player statistics."""
    cli, nick, chan, rest = wrapper.client, wrapper.source.name, wrapper.target.name, message # FIXME: @cmd

    pl = list_players()

    if nick != chan and (nick in pl or var.PHASE == "join"):
        # only do this rate-limiting stuff if the person is in game
        if (var.LAST_STATS and
            var.LAST_STATS + timedelta(seconds=var.STATS_RATE_LIMIT) > datetime.now()):
            cli.notice(nick, messages["command_ratelimited"])
            return

        var.LAST_STATS = datetime.now()

    _nick = nick + ": "
    if nick == chan:
        _nick = ""

    badguys = Wolfchat
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            badguys = Wolf
        else:
            badguys = Wolf | {"traitor"}

    role = None
    if nick in pl:
        role = get_role(nick)
    if chan == nick and role in badguys | {"warlock"}:
        ps = pl[:]
        if role in badguys:
            cursed = [x.nick for x in get_all_players(("cursed villager",))] # FIXME
            for i, player in enumerate(ps):
                prole = get_role(player)
                if prole in badguys: # FIXME: Move all this to proper message keys
                    if player in cursed:
                        ps[i] = "\u0002{0}\u0002 (cursed, {1})".format(player, prole)
                elif player in cursed:
                    ps[i] = "{0} (cursed)".format(player)
        elif role == "warlock":
            # warlock not in wolfchat explicitly only sees cursed
            for i, player in enumerate(pl):
                if users._get(player) in get_all_players(("cursed villager",)): # FIXME
                    ps[i] = player + " (cursed)"
        msg = "\u0002{0}\u0002 players: {1}".format(len(pl), ", ".join(ps))
    elif len(pl) > 1:
        msg = "{0}\u0002{1}\u0002 players: {2}".format(_nick,
            len(pl), ", ".join(pl))
    else:
        msg = "{0}\u00021\u0002 player: {1}".format(_nick, pl[0])

    reply(cli, nick, chan, msg)

    if var.PHASE == "join" or var.STATS_TYPE == "disabled":
        return

    message = []

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
        start_roles = set()
        for r, v in var.ORIGINAL_ROLES.items():
            if len(v) == 0:
                continue
            start_roles.add(r)
        order = [r for r in role_order() if r in role_stats]
        if var.DEFAULT_ROLE in order:
            order.remove(var.DEFAULT_ROLE)
            order.append(var.DEFAULT_ROLE)
        first = role_stats[order[0]]
        if first[0] == first[1] == 1:
            vb = "is"
        else:
            vb = "are"

        for role in order:
            if role in var.CURRENT_GAMEMODE.SECONDARY_ROLES:
                continue
            count = role_stats.get(role, (0, 0))
            if count[0] == count[1]:
                if count[0] != 1:
                    if count[0] == 0 and role not in start_roles:
                        continue
                    message.append("\u0002{0}\u0002 {1}".format(count[0] if count[0] else "\u0002no\u0002", plural(role)))
                else:
                    message.append("\u0002{0}\u0002 {1}".format(count[0], role))
            else:
                message.append("\u0002{0}-{1}\u0002 {2}".format(count[0], count[1], plural(role)))

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

        vb = "are"
        for role in rs:
            count = len(var.ROLES[role])
            # only show actual roles
            if role in var.CURRENT_GAMEMODE.SECONDARY_ROLES:
                continue

            if role == rs[0]:
                if count == 1:
                    vb = "is"
                else:
                    vb = "are"

            if count != 1:
                if count == 0 and len(var.ORIGINAL_ROLES[role]) == 0:
                    continue
                message.append("\u0002{0}\u0002 {1}".format(count if count else "\u0002no\u0002", plural(role)))
            else:
                message.append("\u0002{0}\u0002 {1}".format(count, role))

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

        message.append("\u0002{0}\u0002 {1}".format(wolfteam if wolfteam else "\u0002no\u0002", "wolf" if wolfteam == 1 else "wolves"))
        message.append("\u0002{0}\u0002 {1}".format(villagers if villagers else "\u0002no\u0002", "villager" if villagers == 1 else "villagers"))
        message.append("\u0002{0}\u0002 {1}".format(neutral if neutral else "\u0002no\u0002", "neutral player" if neutral == 1 else "neutral players"))
        vb = "is" if wolfteam == 1 else "are"

    stats_mssg =  "{0}It is currently {4}. There {3} {1}, and {2}.".format(_nick,
                                                        ", ".join(message[0:-1]),
                                                        message[-1],
                                                        vb,
                                                        var.PHASE)
    reply(cli, nick, chan, stats_mssg)

@handle_error
def hurry_up(gameid, change):
    if var.PHASE != "day": return
    if gameid:
        if gameid != var.DAY_ID:
            return

    if not change:
        event = Event("daylight_warning", {"message": "daylight_warning"})
        event.dispatch(var)
        channels.Main.send(messages[event.data["message"]])
        return

    var.DAY_ID = 0
    chk_decision(var, timeout=True)

@command("fnight", flag="N")
def fnight(var, wrapper, message):
    """Force the day to end and night to begin."""
    if var.PHASE != "day":
        wrapper.send(messages["not_daytime"], notice=True)
    else:
        hurry_up(0, True)

@command("fday", flag="N")
def fday(var, wrapper, message):
    """Force the night to end and the next day to begin."""
    if var.PHASE != "night":
        wrapper.send(messages["not_nighttime"], notice=True)
    else:
        transition_day()

def stop_game(var, winner="", abort=False, additional_winners=None, log=True):
    if abort:
        channels.Main.send(messages["role_attribution_failed"])
    elif not var.ORIGINAL_ROLES: # game already ended
        return
    if var.DAY_START_TIME:
        now = datetime.now()
        td = now - var.DAY_START_TIME
        var.DAY_TIMEDELTA += td
    if var.NIGHT_START_TIME:
        now = datetime.now()
        td = now - var.NIGHT_START_TIME
        var.NIGHT_TIMEDELTA += td

    daymin, daysec = var.DAY_TIMEDELTA.seconds // 60, var.DAY_TIMEDELTA.seconds % 60
    nitemin, nitesec = var.NIGHT_TIMEDELTA.seconds // 60, var.NIGHT_TIMEDELTA.seconds % 60
    total = var.DAY_TIMEDELTA + var.NIGHT_TIMEDELTA
    tmin, tsec = total.seconds // 60, total.seconds % 60
    gameend_msg = messages["endgame_stats"].format(tmin, tsec,
                                                daymin, daysec,
                                                nitemin, nitesec)

    if not abort:
        channels.Main.send(gameend_msg)

    roles_msg = []

    # squirrel away a copy of our original roleset for stats recording, as the following code
    # modifies var.ORIGINAL_ROLES and var.ORIGINAL_MAIN_ROLES.
    rolecounts = {role: len(players) for role, players in var.ORIGINAL_ROLES.items()}

    # save some typing
    rolemap = var.ORIGINAL_ROLES
    mainroles = var.ORIGINAL_MAIN_ROLES
    orig_main = {} # if get_final_role changes mainroles, we want to stash original main role

    for player, role in mainroles.items():
        evt = Event("get_final_role", {"role": var.FINAL_ROLES.get(player.nick, role)})
        evt.dispatch(var, player, role)
        if role != evt.data["role"]:
            rolemap[role].remove(player)
            rolemap[evt.data["role"]].add(player)
            mainroles[player] = evt.data["role"]
            orig_main[player] = role

    # track if we already printed "was" for a role swap, e.g. The wolves were A (was seer), B (harlot)
    # so that we can make the message a bit more concise
    roleswap_key = "endgame_roleswap_long"

    for role in role_order():
        numrole = len(rolemap[role])
        if numrole == 0:
            continue
        msg = []
        for player in rolemap[role]:
            # check if the player changed roles during game, and if so insert the "was X" message
            player_msg = []
            if mainroles[player] == role and player in orig_main:
                player_msg.append(messages[roleswap_key].format(orig_main[player]))
                roleswap_key = "endgame_roleswap_short"
            evt = Event("get_endgame_message", {"message": player_msg})
            evt.dispatch(var, player, role, is_mainrole=mainroles[player] == role)
            if player_msg:
                msg.append("\u0002{0}\u0002 ({1})".format(player, ", ".join(player_msg)))
            else:
                msg.append("\u0002{0}\u0002".format(player))

        # FIXME: get rid of hardcoded English
        if numrole == 2:
            roles_msg.append("The {1} were {0[0]} and {0[1]}.".format(msg, plural(role)))
        elif numrole == 1:
            roles_msg.append("The {1} was {0[0]}.".format(msg, role))
        else:
            roles_msg.append("The {2} were {0}, and {1}.".format(", ".join(msg[0:-1]), msg[-1], plural(role)))

    message = ""
    count = 0
    if not abort:
        evt = Event("game_end_messages", {"messages": roles_msg})
        evt.dispatch(var)

        channels.Main.send(*roles_msg)

    # map player: all roles of that player (for below)
    allroles = {player: {role for role, players in rolemap.items() if player in players} for player in mainroles}

    # "" indicates everyone died or abnormal game stop
    if winner != "" or log:
        winners = set()
        player_list = []
        if additional_winners is not None:
            winners.update(additional_winners)
        for plr, rol in mainroles.items():
            pentry = {"version": 2,
                      "nick": None,
                      "account": None,
                      "ident": None,
                      "host": None,
                      "role": None,
                      "templates": [],
                      "special": [],
                      "won": False,
                      "iwon": False,
                      "dced": False}
            if plr in var.DCED_LOSERS:
                pentry["dced"] = True
            pentry["account"] = plr.account
            pentry["nick"] = plr.nick
            pentry["ident"] = plr.ident
            pentry["host"] = plr.host

            pentry["mainrole"] = rol
            pentry["allroles"] = allroles[plr]

            won = False
            iwon = False
            survived = get_players()
            if not pentry["dced"]:
                # determine default win status (event can override)
                if rol in Wolfteam or (var.HIDDEN_ROLE == "cultist" and role in Hidden):
                    if winner == "wolves":
                        won = True
                        iwon = plr in survived
                elif rol not in Neutral and winner == "villagers":
                    won = True
                    iwon = plr in survived
                # true neutral roles are handled via the event below

                evt = Event("player_win", {"won": won, "iwon": iwon, "special": pentry["special"]})
                evt.dispatch(var, plr, rol, winner, plr in survived)
                won = evt.data["won"]
                iwon = evt.data["iwon"]
                # ensure that it is a) a list, and b) a copy (so it can't be mutated out from under us later)
                pentry["special"] = list(evt.data["special"])

                # special-case everyone for after the event
                if winner == "everyone":
                    iwon = True

            if pentry["dced"]:
                # You get NOTHING! You LOSE! Good DAY, sir!
                won = False
                iwon = False
            elif not iwon:
                iwon = won and plr in survived  # survived, team won = individual win

            if winner == "":
                pentry["won"] = False
                pentry["iwon"] = False
            else:
                pentry["won"] = won
                pentry["iwon"] = iwon
                if won or iwon:
                    winners.add(plr)

            if not plr.is_fake:
                # don't record fjoined fakes
                player_list.append(pentry)

    if winner == "":
        winners = set()

    if log:
        game_options = {"role reveal": var.ROLE_REVEAL,
                        "stats": var.STATS_TYPE,
                        "abstain": "on" if var.ABSTAIN_ENABLED and not var.LIMIT_ABSTAIN else "restricted" if var.ABSTAIN_ENABLED else "off",
                        "roles": {}}
        for role,pl in var.ORIGINAL_ROLES.items():
            if len(pl) > 0:
                game_options["roles"][role] = len(pl)

        db.add_game(var.CURRENT_GAMEMODE.name,
                    len(survived) + len(var.DEAD),
                    time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(var.GAME_ID)),
                    time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                    winner,
                    player_list,
                    game_options)

        # spit out the list of winners
        winners = sorted(winners, key=lambda u: u.nick)
        channels.Main.send(messages["winners"].format(winners))

    # Message players in deadchat letting them know that the game has ended
    if var.DEADCHAT_PLAYERS:
        for user in var.DEADCHAT_PLAYERS:
            user.queue_message(messages["endgame_deadchat"].format(channels.Main))

        user.send_messages()

    reset_modes_timers(var)
    reset()
    expire_tempbans()

    # This must be after reset()
    if var.AFTER_FLASTGAME is not None:
        var.AFTER_FLASTGAME()
        var.AFTER_FLASTGAME = None
    if var.ADMIN_TO_PING is not None:  # It was an flastgame
        channels.Main.send("PING! {0}".format(var.ADMIN_TO_PING))
        var.ADMIN_TO_PING = None

def chk_win(*, end_game=True, winner=None):
    """ Returns True if someone won """
    lpl = len(get_players())

    if var.PHASE == "join":
        if lpl == 0:
            reset_modes_timers(var)

            reset()

            # This must be after reset()
            if var.AFTER_FLASTGAME is not None:
                var.AFTER_FLASTGAME()
                var.AFTER_FLASTGAME = None
            if var.ADMIN_TO_PING is not None:  # It was an flastgame
                channels.Main.send("PING! {0}".format(var.ADMIN_TO_PING))
                var.ADMIN_TO_PING = None

            return True
        return False
    if var.PHASE not in var.GAME_PHASES:
        return False #some other thread already ended game probably

    return chk_win_conditions(var.ROLES, var.MAIN_ROLES, end_game, winner)

def chk_win_conditions(rolemap, mainroles, end_game=True, winner=None):
    """Internal handler for the chk_win function."""
    with var.GRAVEYARD_LOCK:
        if var.PHASE == "day":
            pl = set(get_players()) - get_absent(var)
            lpl = len(pl)
        else:
            pl = set(get_players(mainroles=mainroles))
            lpl = len(pl)

        if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
            if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
                wcroles = Wolf
            else:
                wcroles = Wolf | {"traitor"}
        else:
            wcroles = Wolfchat

        wolves = set(get_players(wcroles, mainroles=mainroles))
        lwolves = len(wolves & pl)
        lrealwolves = len(get_players(Wolf & Killer, mainroles=mainroles))

        message = ""
        if lpl < 1:
            message = messages["no_win"]
            # still want people like jesters, dullahans, etc. to get wins if they fulfilled their win conds
            winner = "no_team_wins"

        # TODO: flip priority order (so that things like fool run last, and therefore override previous win conds)
        # Priorities:
        # 0 = fool, other roles that end game immediately
        # 1 = things that could short-circuit game ending, such as cub growing up or traitor turning
        #     Such events should also set stop_processing and prevent_default to True to force a re-calcuation
        # 2 = win stealers not dependent on winners, such as succubus
        # Events in priority 3 and 4 should check if a winner was already set and short-circuit if so
        # it is NOT recommended that events in priorities 0 and 2 set stop_processing to True, as doing so
        # will prevent gamemode-specific win conditions from happening
        # 3 = normal roles
        # 4 = win stealers dependent on who won, such as demoniac and monster
        #     (monster's message changes based on who would have otherwise won)
        # 5 = gamemode-specific win conditions
        event = Event("chk_win", {"winner": winner, "message": message, "additional_winners": None})
        if not event.dispatch(var, rolemap, mainroles, lpl, lwolves, lrealwolves):
            return chk_win_conditions(rolemap, mainroles, end_game, winner)
        winner = event.data["winner"]
        message = event.data["message"]

        if winner is None:
            return False

        if end_game:
            debuglog("WIN:", winner)
            channels.Main.send(message)
            stop_game(var, winner, additional_winners=event.data["additional_winners"])
        return True

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
    # The reconfigure_stats event can be used to shift things around (for example, it is used to reflect wolf cub growing up)
    event = Event("reconfigure_stats", {"new": []})
    for p in possible:
        for rs in var.ROLE_STATS:
            d = Counter(dict(rs))
            if p in d and d[p] >= 1:
                d[p] -= 1
                event.data["new"] = [d]
                event.dispatch(var, d, "del_player")
                for v in event.data["new"]:
                    if min(v.values()) >= 0:
                        newstats.add(frozenset(v.items()))
    var.ROLE_STATS = frozenset(newstats)

    if var.PHASE == "join":
        if player.nick in var.GAMEMODE_VOTES:
            del var.GAMEMODE_VOTES[player.nick]

        # Died during the joining process as a person
        var.ALL_PLAYERS.remove(player)
    if var.PHASE in var.GAME_PHASES:
        # remove the player from variables if they're in there
        var.DISCONNECTED.pop(player, None)

# FIXME: get rid of the priority once we move state transitions into the main event loop instead of having it here
@event_listener("kill_players", priority=10)
def on_kill_players(evt: Event, var, players: Set[User]):
    cmode = []
    deadchat = []
    game_ending = False

    for player in players:
        if not player.is_fake:
            if var.PHASE != "night" or not var.DEVOICE_DURING_NIGHT:
                cmode.append(("-v", player.nick))
            if var.PHASE in var.GAME_PHASES and var.QUIET_DEAD_PLAYERS:
                # Died during the game, so quiet!
                cmode.append(("+{0}".format(var.QUIET_MODE), var.QUIET_PREFIX + player.nick + "!*@*"))
            if var.PHASE == "join":
                for mode in var.OLD_MODES[player]:
                    cmode.append(("+" + mode, player.nick))
                del var.OLD_MODES[player]
            lplayer = player.lower()
            if lplayer.account not in var.DEADCHAT_PREFS_ACCS and lplayer.host not in var.DEADCHAT_PREFS:
                deadchat.append(player)

    # attempt to devoice all dead players
    channels.Main.mode(*cmode)

    if not evt.params.end_game:
        join_deadchat(var, *deadchat)
        return

    # see if we need to end the game or transition phases
    # FIXME: make state transitions part of the overall event loop
    game_ending = chk_win()

    if not game_ending:
        # if game isn't about to end, join people to deadchat
        join_deadchat(var, *deadchat)

        if var.PHASE == "day" and var.GAMEPHASE == "day":
            # PHASE is day but GAMEPHASE is night during transition_day; ensure we only induce lynch during actual daytime
            chk_decision(var)
        elif var.PHASE == "night" and var.GAMEPHASE == "night":
            # PHASE is night but GAMEPHASE is day during transition_night; ensure we only try to end night during actual nighttime
            chk_nightdone()
    else:
        # HACK: notify kill_players that game is ending so it can pass it to its caller
        evt.prevent_default = True

@handle_error
def reaper(cli, gameid):
    # check to see if idlers need to be killed.
    var.IDLE_WARNED    = set()
    var.IDLE_WARNED_PM = set()
    chan = botconfig.CHANNEL

    last_day_id = var.DAY_COUNT
    num_night_iters = 0

    while gameid == var.GAME_ID:
        skip = False
        with var.GRAVEYARD_LOCK:
            # Terminate reaper when game ends
            if var.PHASE not in ("day", "night"):
                return
            if var.DEVOICE_DURING_NIGHT:
                if var.PHASE == "night":
                    # don't count nighttime towards idling
                    # this doesn't do an exact count, but is good enough
                    num_night_iters += 1
                    skip = True
                elif var.PHASE == "day" and var.DAY_COUNT != last_day_id:
                    last_day_id = var.DAY_COUNT
                    num_night_iters += 1
                    for nick in var.LAST_SAID_TIME:
                        var.LAST_SAID_TIME[nick] += timedelta(seconds=10*num_night_iters)
                    num_night_iters = 0


            if not skip and (var.WARN_IDLE_TIME or var.PM_WARN_IDLE_TIME or var.KILL_IDLE_TIME):  # only if enabled
                to_warn    = []
                to_warn_pm = []
                to_kill    = []
                for nick in list_players():
                    if is_fake_nick(nick):
                        continue
                    lst = var.LAST_SAID_TIME.get(nick, var.GAME_START_TIME)
                    tdiff = datetime.now() - lst
                    if var.WARN_IDLE_TIME and (tdiff > timedelta(seconds=var.WARN_IDLE_TIME) and
                                            nick not in var.IDLE_WARNED):
                        to_warn.append(nick)
                        var.IDLE_WARNED.add(nick)
                        var.LAST_SAID_TIME[nick] = (datetime.now() -
                            timedelta(seconds=var.WARN_IDLE_TIME))  # Give them a chance
                    elif var.PM_WARN_IDLE_TIME and (tdiff > timedelta(seconds=var.PM_WARN_IDLE_TIME) and
                                            nick not in var.IDLE_WARNED_PM):
                        to_warn_pm.append(nick)
                        var.IDLE_WARNED_PM.add(nick)
                        var.LAST_SAID_TIME[nick] = (datetime.now() -
                            timedelta(seconds=var.PM_WARN_IDLE_TIME))
                    elif var.KILL_IDLE_TIME and (tdiff > timedelta(seconds=var.KILL_IDLE_TIME) and
                                            (not var.WARN_IDLE_TIME or nick in var.IDLE_WARNED) and
                                            (not var.PM_WARN_IDLE_TIME or nick in var.IDLE_WARNED_PM)):
                        to_kill.append(nick)
                    elif (tdiff < timedelta(seconds=var.WARN_IDLE_TIME) and
                                            (nick in var.IDLE_WARNED or nick in var.IDLE_WARNED_PM)):
                        var.IDLE_WARNED.discard(nick)  # player saved themselves from death
                        var.IDLE_WARNED_PM.discard(nick)
                for nck in to_kill:
                    if nck not in list_players():
                        continue
                    if var.ROLE_REVEAL in ("on", "team"):
                        cli.msg(chan, messages["idle_death"].format(nck, get_reveal_role(users._get(nck)))) # FIXME
                    else: # FIXME: Merge these two
                        cli.msg(chan, (messages["idle_death_no_reveal"]).format(nck))
                    user = users._get(nck) # FIXME
                    user.disconnected = True
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(user)
                    if var.IDLE_PENALTY:
                        add_warning(cli, nck, var.IDLE_PENALTY, users.Bot.nick, messages["idle_warning"], expires=var.IDLE_EXPIRY)
                    add_dying(var, user, "bot", "idle", death_triggers=False)
                pl = list_players()
                x = [a for a in to_warn if a in pl]
                if x:
                    cli.msg(chan, messages["channel_idle_warning"].format(x))
                msg_targets = [p for p in to_warn_pm if p in pl]
                mass_privmsg(cli, msg_targets, messages["player_idle_warning"].format(chan), privmsg=True)
            for dcedplayer, (timeofdc, what) in list(var.DISCONNECTED.items()):
                mainrole = get_main_role(dcedplayer)
                revealrole = get_reveal_role(dcedplayer)
                if what in ("quit", "badnick") and (datetime.now() - timeofdc) > timedelta(seconds=var.QUIT_GRACE_TIME):
                    if mainrole != "person" and var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["quit_death"].format(dcedplayer, revealrole))
                    else: # FIXME: Merge those two
                        channels.Main.send(messages["quit_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.PART_PENALTY:
                        add_warning(cli, dcedplayer.nick, var.PART_PENALTY, users.Bot.nick, messages["quit_warning"], expires=var.PART_EXPIRY) # FIXME
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "quit", death_triggers=False)
                elif what == "part" and (datetime.now() - timeofdc) > timedelta(seconds=var.PART_GRACE_TIME):
                    if mainrole != "person" and var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["part_death"].format(dcedplayer, revealrole))
                    else: # FIXME: Merge those two
                        channels.Main.send(messages["part_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.PART_PENALTY:
                        add_warning(cli, dcedplayer.nick, var.PART_PENALTY, users.Bot.nick, messages["part_warning"], expires=var.PART_EXPIRY) # FIXME
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "part", death_triggers=False)
                elif what == "account" and (datetime.now() - timeofdc) > timedelta(seconds=var.ACC_GRACE_TIME):
                    if mainrole != "person" and var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["account_death"].format(dcedplayer, revealrole))
                    else:
                        channels.Main.send(messages["account_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.ACC_PENALTY:
                        add_warning(cli, dcedplayer.nick, var.ACC_PENALTY, users.Bot.nick, messages["acc_warning"], expires=var.ACC_EXPIRY) # FIXME
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "account", death_triggers=False)
            kill_players(var)
        time.sleep(10)

@command("")  # update last said
def update_last_said(var, wrapper, message):
    if wrapper.target is not channels.Main:
        return

    if var.PHASE not in ("join", "none"):
        var.LAST_SAID_TIME[wrapper.source.nick] = datetime.now() # FIXME

@event_listener("chan_join", priority=1)
def on_join(evt, var, chan, user):
    if user is users.Bot:
        plog("Joined {0}".format(chan))
    # FIXME: kill all of this off along with var.USERS
    elif not users.exists(user.nick):
        users.add(user.nick, ident=user.ident,host=user.host,account=user.account,inchan=(chan is channels.Main),modes=set(),moded=set())
    else:
        baduser = users.get(user.nick)
        baduser.ident = user.ident
        baduser.host = user.host
        baduser.account = user.account
        if not baduser.inchan:
            # Will be True if the user joined the main channel, else False
            baduser.inchan = (chan is channels.Main)
    if chan is not channels.Main:
        return
    return_to_village(var, user, show_message=True)

@command("goat")
def goat(var, wrapper, message):
    """Use a goat to interact with anyone in the channel during the day."""

    if wrapper.source in var.LAST_GOAT and var.LAST_GOAT[wrapper.source][0] + timedelta(seconds=var.GOAT_RATE_LIMIT) > datetime.now():
        wrapper.pm(messages["command_ratelimited"])
        return
    target = re.split(" +",message)[0]
    if not target:
        wrapper.pm(messages["not_enough_parameters"])
        return
    victim, _ = users.complete_match(users.lower(target), wrapper.target.users)
    if not victim:
        wrapper.pm(messages["goat_target_not_in_channel"].format(target))
        return

    var.LAST_GOAT[wrapper.source] = [datetime.now(), 1]
    wrapper.send(messages["goat_success"].format(wrapper.source, victim))

@command("fgoat", flag="j")
def fgoat(var, wrapper, message):
    """Forces a goat to interact with anyone or anything, without limitations."""

    nick = message.split(' ')[0].strip()
    victim, _ = users.complete_match(users.lower(nick), wrapper.target.users)
    if victim:
        togoat = victim
    else:
        togoat = message

    wrapper.send(messages["goat_success"].format(wrapper.source, togoat))

@handle_error
def return_to_village(var, target, *, show_message, new_user=None):
    # Note: we do not manipulate or check target.disconnected, as that property
    # is used to determine if they are entirely dc'ed rather than just maybe using
    # a different account or /parting the channel. If they were dced for real and
    # rejoined IRC, the join handler already took care of marking them no longer dced.
    with var.GRAVEYARD_LOCK:
        if target in var.DISCONNECTED:
            del var.DISCONNECTED[target]
            if new_user is None:
                new_user = target

            var.LAST_SAID_TIME[target.nick] = datetime.now()
            var.DCED_LOSERS.discard(target)

            if target.nick in var.DCED_PLAYERS:
                var.PLAYERS[target.nick] = var.DCED_PLAYERS.pop(target.nick)

            if new_user is not target:
                # different users, perform a swap. This will clean up disconnected users.
                target.swap(new_user)

            if target.nick != new_user.nick:
                # have a nickchange, update tracking vars
                rename_player(var, new_user, target.nick)

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
            if var.ACCOUNTS_ONLY or target.account:
                userlist = users._get(account=target.account, allow_multiple=True) # FIXME
            else: # match host (hopefully the ircd uses vhosts to differentiate users)
                userlist = users._get(host=target.host, allow_multiple=True)
            userlist = [u for u in userlist if u in var.DISCONNECTED]
            if len(userlist) == 1:
                return_to_village(var, userlist[0], show_message=show_message, new_user=target)

def rename_player(var, user, prefix):
    nick = user.nick

    event = Event("rename_player", {})
    event.dispatch(var, prefix, nick)

    if user in var.ALL_PLAYERS:
        if var.PHASE in var.GAME_PHASES:
            for k,v in list(var.PLAYERS.items()):
                if prefix == k:
                    var.PLAYERS[nick] = var.PLAYERS.pop(k)

            for dictvar in (var.FINAL_ROLES,):
                if prefix in dictvar.keys():
                    dictvar[nick] = dictvar.pop(prefix)
            with var.GRAVEYARD_LOCK:  # to be safe
                if prefix in var.LAST_SAID_TIME.keys():
                    var.LAST_SAID_TIME[nick] = var.LAST_SAID_TIME.pop(prefix)
                if prefix in getattr(var, "IDLE_WARNED", ()):
                    var.IDLE_WARNED.remove(prefix)
                    var.IDLE_WARNED.add(nick)
                if prefix in getattr(var, "IDLE_WARNED_PM", ()):
                    var.IDLE_WARNED_PM.remove(prefix)
                    var.IDLE_WARNED_PM.add(nick)

        if var.PHASE == "join":
            if prefix in var.GAMEMODE_VOTES:
                var.GAMEMODE_VOTES[nick] = var.GAMEMODE_VOTES.pop(prefix)

@event_listener("account_change")
def account_change(evt, var, user):
    if user not in channels.Main.users:
        return # We only care about game-related changes in this function

    if user.account is None and var.ACCOUNTS_ONLY and user in get_players():
        leave(var, "account", user)
        if var.PHASE == "join":
            user.send(messages["account_midgame_change"], notice=True)
        else:
            channels.Main.mode(["-v", user.nick])
            user.send(messages["account_reidentify"].format(user.account), notice=True)

    # if they were gone, maybe mark them as back
    return_to_village(var, user, show_message=True)

@event_listener("nick_change")
def nick_change(evt, var, user, old_rawnick):
    nick = users.parse_rawnick_as_dict(old_rawnick)["nick"] # FIXME: We won't need that when all variables hold User instances

    if user not in var.DISCONNECTED and user in get_players() and re.search(var.GUEST_NICK_PATTERN, user.nick):
        if var.PHASE != "join":
            channels.Main.mode(["-v", user.nick])
        temp = users.FakeUser(None, nick, user.ident, user.host, user.realname, user.account)
        leave(var, "badnick", temp) # pass in a fake user with the old nick (since the user holds the new nick)
        return # Don't do anything else; they're using a guest/away nick

    if user not in channels.Main.users:
        return

    rename_player(var, user, nick)
    # perhaps mark them as back
    return_to_village(var, user, show_message=True)

@event_listener("cleanup_user")
def cleanup_user(evt, var, user):
    var.LAST_GOAT.pop(user, None)

@event_listener("nick_change")
def update_users(evt, var, user, old_rawnick): # FIXME: This is a temporary hack while var.USERS still exists
    nick = users.parse_rawnick_as_dict(old_rawnick)["nick"]
    if nick in var.USERS:
        var.USERS[user.nick] = var.USERS.pop(nick)

@event_listener("chan_part")
def left_channel(evt, var, chan, user, reason):
    leave(var, "part", user, chan)

@event_listener("chan_kick")
def channel_kicked(evt, var, chan, actor, user, reason):
    leave(var, "kick", user, chan)

@event_listener("server_quit")
def quit_server(evt, var, user, reason):
    leave(var, "quit", user, reason)

def leave(var, what, user, why=None):
    if what in ("part", "kick") and why is not channels.Main:
        return
    if why and why == botconfig.CHANGING_HOST_QUIT_MESSAGE:
        return
    if var.PHASE == "none":
        return

    ps = get_players()
    # Only mark living players as disconnected, unless they were kicked
    if user.nick in var.PLAYERS and (what == "kick" or user in ps): # FIXME: Convert var.PLAYERS
        var.DCED_LOSERS.add(user)
        var.DCED_PLAYERS[user.nick] = var.PLAYERS.pop(user.nick) # FIXME: Convert var.PLAYERS and var.DCED_PLAYERS

    if user not in ps or user in var.DISCONNECTED:
        return

    # If we got that far, the player was in the game. This variable tracks whether or not we want to kill them off.
    killplayer = True

    population = ""

    if var.PHASE == "join":
        lpl = len(ps) - 1
        if lpl < var.MIN_PLAYERS:
            with var.WARNING_LOCK:
                from src.pregame import START_VOTES
                START_VOTES.clear()

        if lpl <= 0:
            population = " " + messages["no_players_remaining"]
        else:
            population = " " + messages["new_player_count"].format(lpl)

    reveal = ""
    if get_main_role(user) == "person" or var.ROLE_REVEAL not in ("on", "team"):
        reveal = "_no_reveal"

    grace_times = {"part": var.PART_GRACE_TIME, "quit": var.QUIT_GRACE_TIME, "account": var.ACC_GRACE_TIME, "leave": 0}

    reason = what
    if reason == "badnick":
        reason = "quit"
    elif reason == "kick":
        reason = "leave"

    if reason in grace_times and (grace_times[reason] <= 0 or var.PHASE == "join"):
        # possible message keys (for easy grep):
        # "quit_death", "quit_death_no_reveal", "leave_death", "leave_death_no_reveal", "account_death", "account_death_no_reveal"
        msg = messages["{0}_death{1}".format(reason, reveal)]
    elif what != "kick": # There's time for the player to rejoin the game
        user.send(messages["part_grace_time_notice"].format(botconfig.CHANNEL, var.PART_GRACE_TIME))
        msg = messages["player_missing"]
        population = ""
        killplayer = False

    channels.Main.send(msg.format(user, get_reveal_role(user)) + population)
    var.SPECTATING_WOLFCHAT.discard(user)
    var.SPECTATING_DEADCHAT.discard(user)
    leave_deadchat(var, user)

    if what not in ("badnick", "account") and user.nick in var.USERS: # FIXME: Need to move mode toggling somewhere saner
        var.USERS[user.nick]["modes"] = set()
        var.USERS[user.nick]["moded"] = set()

    if killplayer:
        add_dying(var, user, "bot", what, death_triggers=False)
        kill_players(var)
    else:
        temp = user.lower()
        var.DISCONNECTED[user] = (datetime.now(), what)

@command("quit", "leave", pm=True, phases=("join", "day", "night"))
def leave_game(var, wrapper, message):
    """Quits the game."""
    if wrapper.target is channels.Main:
        if wrapper.source not in get_players():
            return
        if var.PHASE == "join":
            lpl = len(get_players()) - 1
            if lpl == 0:
                population = " " + messages["no_players_remaining"]
            else:
                population = " " + messages["new_player_count"].format(lpl)
        else:
            if not message.startswith("-force"):
                wrapper.pm(messages["leave_game_ingame_safeguard"].format(botconfig.CMD_CHAR))
                return
            population = ""
    elif wrapper.private:
        if var.PHASE in var.GAME_PHASES and wrapper.source not in get_players() and wrapper.source in var.DEADCHAT_PLAYERS:
            leave_deadchat(var, wrapper.source)
        return
    else:
        return

    if get_main_role(wrapper.source) != "person" and var.ROLE_REVEAL in ("on", "team"):
        role = get_reveal_role(wrapper.source)
        channels.Main.send(messages["quit_reveal"].format(wrapper.source, role) + population)
    else:
        channels.Main.send(messages["quit_no_reveal"].format(wrapper.source) + population)
    if var.PHASE != "join":
        var.DCED_LOSERS.add(wrapper.source)
        if var.LEAVE_PENALTY:
            add_warning(wrapper.client, wrapper.source.nick, var.LEAVE_PENALTY, users.Bot.nick, messages["leave_warning"], expires=var.LEAVE_EXPIRY) # FIXME
        if wrapper.source.nick in var.PLAYERS:
            var.DCED_PLAYERS[wrapper.source.nick] = var.PLAYERS.pop(wrapper.source.nick)

    add_dying(var, wrapper.source, "bot", "quit", death_triggers=False)
    kill_players(var)

def begin_day():
    # Reset nighttime variables
    var.GAMEPHASE = "day"
    var.KILLER = ""  # nickname of who chose the victim
    var.STARTED_DAY_PLAYERS = len(get_players())
    var.LAST_GOAT.clear()
    msg = messages["villagers_lynch"].format(botconfig.CMD_CHAR, len(list_players()) // 2 + 1)
    channels.Main.send(msg)

    var.DAY_ID = time.time()
    if var.DAY_TIME_WARN > 0:
        if var.STARTED_DAY_PLAYERS <= var.SHORT_DAY_PLAYERS:
            t1 = threading.Timer(var.SHORT_DAY_WARN, hurry_up, [var.DAY_ID, False])
            l = var.SHORT_DAY_WARN
        else:
            t1 = threading.Timer(var.DAY_TIME_WARN, hurry_up, [var.DAY_ID, False])
            l = var.DAY_TIME_WARN
        var.TIMERS["day_warn"] = (t1, var.DAY_ID, l)
        t1.daemon = True
        t1.start()

    if var.DAY_TIME_LIMIT > 0:  # Time limit enabled
        if var.STARTED_DAY_PLAYERS <= var.SHORT_DAY_PLAYERS:
            t2 = threading.Timer(var.SHORT_DAY_LIMIT, hurry_up, [var.DAY_ID, True])
            l = var.SHORT_DAY_LIMIT
        else:
            t2 = threading.Timer(var.DAY_TIME_LIMIT, hurry_up, [var.DAY_ID, True])
            l = var.DAY_TIME_LIMIT
        var.TIMERS["day"] = (t2, var.DAY_ID, l)
        t2.daemon = True
        t2.start()

    if var.DEVOICE_DURING_NIGHT:
        modes = []
        for player in get_players():
            if not player.is_fake:
                modes.append(("+v", player.nick))
        channels.Main.mode(*modes)

    event = Event("begin_day", {})
    event.dispatch(var)
    # induce a lynch if we need to (due to lots of pacifism/impatience totems or whatever)
    chk_decision(var)

@handle_error
def night_warn(gameid):
    if gameid != var.NIGHT_ID:
        return

    if var.PHASE != "night":
        return

    channels.Main.send(messages["twilight_warning"])

@handle_error
def transition_day(gameid=0):
    if gameid:
        if gameid != var.NIGHT_ID:
            return
    var.NIGHT_ID = 0

    if var.PHASE not in ("night", "join"):
        return

    var.PHASE = "day"
    var.DAY_COUNT += 1
    var.FIRST_DAY = (var.DAY_COUNT == 1)
    var.DAY_START_TIME = datetime.now()

    event_begin = Event("transition_day_begin", {})
    event_begin.dispatch(var)

    if var.START_WITH_DAY and var.FIRST_DAY:
        # TODO: need to message everyone their roles and give a short thing saying "it's daytime"
        # but this is good enough for now to prevent it from crashing
        begin_day()
        return

    td = var.DAY_START_TIME - var.NIGHT_START_TIME
    var.NIGHT_START_TIME = None
    var.NIGHT_TIMEDELTA += td
    minimum, sec = td.seconds // 60, td.seconds % 60

    # built-in logic runs at the following priorities:
    # 1 = wolf kills
    # 2 = non-wolf kills
    # 3 = fixing killers dict to have correct priority (wolf-side VG kills -> non-wolf kills -> wolf kills)
    # 4 = protections/fallen angel
    #     4.1 = shaman, 4.2 = bodyguard/GA, 4.3 = blessed villager
    # 5 = alpha wolf bite, other custom events that trigger after all protection stuff is resolved
    # 6 = rearranging victim list (ensure bodyguard/harlot messages plays),
    #     fixing killers dict priority again (in case step 4 or 5 added to it)
    # 7 = read-only operations
    # Actually killing off the victims happens in transition_day_resolve
    # We set the variables here first; listeners should mutate, not replace
    # We don't need to use User containers here, as these don't persist long enough
    # This removes the burden of having to clear them at the end or should an error happen
    victims = []
    killers = defaultdict(list)

    evt = Event("transition_day", {
        "victims": victims,
        "killers": killers,
        })
    evt.dispatch(var)

    # remove duplicates
    victims_set = set(victims)
    vappend = []
    victims.clear()
    # Ensures that special events play for bodyguard and harlot-visiting-victim so that kill can
    # be correctly attributed to wolves (for vengeful ghost lover), and that any gunner events
    # can play. Harlot visiting wolf doesn't play special events if they die via other means since
    # that assumes they die en route to the wolves (and thus don't shoot/give out gun/etc.)
    # TODO: this needs to be split off into bodyguard.py and harlot.py
    from src.roles import bodyguard, harlot
    for v in victims_set:
        if is_dying(var, v):
            victims.append(v)
        elif v in var.ROLES["bodyguard"] and v in bodyguard.GUARDED and bodyguard.GUARDED[v] in victims_set:
            vappend.append(v)
        elif harlot.VISITED.get(v) in victims_set:
            vappend.append(v)
        else:
            victims.append(v)
    prevlen = var.MAX_PLAYERS + 10
    while len(vappend) > 0:
        if len(vappend) == prevlen:
            # have a circular dependency, try to break it by appending the next value
            v = vappend[0]
            vappend.remove(v)
            victims.append(v)
            continue

        prevlen = len(vappend)
        for v in vappend[:]:
            if v in var.ROLES["bodyguard"] and bodyguard.GUARDED.get(v) not in vappend:
                vappend.remove(v)
                victims.append(v)
            elif harlot.VISITED.get(v) not in vappend:
                vappend.remove(v)
                victims.append(v)

    message = defaultdict(list)
    message["*"].append(messages["sunrise"].format(minimum, sec))

    dead = []
    vlist = victims[:]
    revt = Event("transition_day_resolve", {
        "message": message,
        "novictmsg": True,
        "dead": dead,
        "killers": killers,
        })
    # transition_day_resolve priorities:
    # 1: target not home
    # 2: protection
    # 6: riders on default logic
    # In general, an event listener < 6 should both stop propagation and prevent default
    # Priority 6 listeners add additional stuff to the default action and should not prevent default
    for victim in vlist:
        if not revt.dispatch(var, victim):
            continue
        if victim not in revt.data["dead"]: # not already dead via some other means
            for killer in list(killers[victim]):
                if killer == "@wolves":
                    attacker = None
                    role = "wolf"
                else:
                    attacker = killer
                    role = get_main_role(killer)
                protected = try_protection(var, victim, attacker, role, reason="night_death")
                if protected is not None:
                    revt.data["message"][victim].extend(protected)
                    killers[victim].remove(killer)
                    revt.data["novictmsg"] = False

            if not killers[victim]:
                continue

            to_send = "death_no_reveal"
            if var.ROLE_REVEAL in ("on", "team"):
                to_send = "death"
            revt.data["message"][victim].append(messages[to_send].format(victim, get_reveal_role(victim)))
            revt.data["dead"].append(victim)

    # Priorities:
    # 1 = harlot/succubus visiting victim (things that kill the role itself)
    # 2 = howl/novictmsg processing, alpha wolf bite/lycan turning (roleswaps)
    # 3 = harlot visiting wolf, bodyguard/GA guarding wolf (things that kill the role itself -- should move to pri 1)
    # 4 = gunner shooting wolf, retribution totem (things that kill the victim's killers)
    # 5 = wolves killing diseased, wolves stealing gun (all deaths must be finalized before pri 5)
    # Note that changing the "novictmsg" data item only makes sense for priority 2 events,
    # as after that point the message was already added (at priority 2.9).
    revt2 = Event("transition_day_resolve_end", {
        "message": message,
        "novictmsg": revt.data["novictmsg"],
        "howl": 0,
        "dead": dead,
        "killers": killers,
        })
    revt2.dispatch(var, victims)

    # flatten message, * goes first then everyone else
    to_send = message["*"]
    del message["*"]
    for msg in message.values():
        to_send.extend(msg)

    if random.random() < var.GIF_CHANCE:
        to_send.append(str(messages["gifs"]))
    channels.Main.send("\n".join(to_send))

    # chilling howl message was played, give roles the opportunity to update !stats
    # to account for this
    event = Event("reconfigure_stats", {"new": []})
    for i in range(revt2.data["howl"]):
        newstats = set()
        for rs in var.ROLE_STATS:
            d = Counter(dict(rs))
            event.data["new"] = [d]
            event.dispatch(var, d, "howl")
            for v in event.data["new"]:
                if min(v.values()) >= 0:
                    newstats.add(frozenset(v.items()))
        var.ROLE_STATS = frozenset(newstats)

    killer_role = {}
    for deadperson in dead:
        if killers.get(deadperson):
            killer = killers[deadperson][0]
            if killer == "@wolves":
                killer_role[deadperson] = "wolf"
            else:
                killer_role[deadperson] = get_main_role(killer)
        else:
            # no killers, so assume suicide
            killer_role[deadperson] = get_main_role(deadperson)

    for deadperson in dead:
        add_dying(var, deadperson, killer_role[deadperson], "night_kill")
    kill_players(var, end_game=False) # temporary hack; end_game=False also prevents kill_players from attempting phase transitions

    event_end = Event("transition_day_end", {"begin_day": begin_day})
    event_end.dispatch(var)

    # make sure that we process ALL of the transition_day events before checking for game end
    if chk_win(): # game ending
        return

    event_end.data["begin_day"]()

@event_listener("transition_day_resolve_end", priority=2.9)
def on_transition_day_resolve_end(evt, var, victims):
    if evt.data["novictmsg"] and len(evt.data["dead"]) == 0:
        evt.data["message"]["*"].append(messages["no_victims"] + messages["no_victims_append"])
    for i in range(evt.data["howl"]):
        evt.data["message"]["*"].append(messages["new_wolf"])

def chk_nightdone():
    if var.PHASE != "night":
        return

    event = Event("chk_nightdone", {"actedcount": 0, "nightroles": [], "transition_day": transition_day})
    event.dispatch(var)
    actedcount = event.data["actedcount"]

    # remove all instances of them if they are silenced (makes implementing the event easier)
    nightroles = [p for p in event.data["nightroles"] if not is_silent(var, p)]

    if var.PHASE == "night" and actedcount >= len(nightroles):
        for x, t in var.TIMERS.items():
            t[0].cancel()

        var.TIMERS = {}
        if var.PHASE == "night":  # Double check
            event.data["transition_day"]()

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
            var.AUTO_TOGGLE_MODES = set(var.AUTO_TOGGLE_MODES)
            if var.AUTO_TOGGLE_MODES: # this is ugly, but I'm too lazy to fix it. it works, so that's fine
                tocheck = set(var.AUTO_TOGGLE_MODES)
                for mode in tocheck:
                    if not mode in var.MODES_PREFIXES.keys() and not mode in var.MODES_PREFIXES.values():
                        var.AUTO_TOGGLE_MODES.remove(mode)
                        continue
                    if not mode in var.MODES_PREFIXES.values():
                        for chp in var.MODES_PREFIXES.keys():
                            if chp == mode:
                                var.AUTO_TOGGLE_MODES.remove(chp)
                                var.AUTO_TOGGLE_MODES.add(var.MODES_PREFIXES[mode])

                if "v" in var.AUTO_TOGGLE_MODES:
                    var.AUTO_TOGGLE_MODES.remove("v")
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
def relay(var, wrapper, message):
    """Wolfchat and Deadchat"""
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

    pl = get_players()

    # FIXME: this IDLE_WARNED_PM handling looks incredibly wrong and should be fixed
    if wrapper.source in pl and wrapper.source.nick in getattr(var, "IDLE_WARNED_PM", ()):
        wrapper.pm(messages["privmsg_idle_warning"].format(channels.Main))
        var.IDLE_WARNED_PM.add(wrapper.source)

    if message.startswith(botconfig.CMD_CHAR):
        return

    badguys = get_players(Wolfchat)
    wolves = get_players(Wolf)

    if wrapper.source not in pl and var.ENABLE_DEADCHAT and wrapper.source in var.DEADCHAT_PLAYERS:
        to_msg = var.DEADCHAT_PLAYERS - {wrapper.source}
        if to_msg or var.SPECTATING_DEADCHAT:
            if message.startswith("\u0001ACTION"):
                message = message[7:-1]
                for user in to_msg:
                    user.queue_message("* \u0002{0}\u0002{1}".format(wrapper.source, message))
                for user in var.SPECTATING_DEADCHAT:
                    user.queue_message("* [deadchat] \u0002{0}\u0002{1}".format(wrapper.source, message))
            else:
                for user in to_msg:
                    user.queue_message("\u0002{0}\u0002 says: {1}".format(wrapper.source, message))
                for user in var.SPECTATING_DEADCHAT:
                    user.queue_message("[deadchat] \u0002{0}\u0002 says: {1}".format(wrapper.source, message))

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
                player.queue_message("* \u0002{0}\u0002{1}".format(wrapper.source, message))
            for player in var.SPECTATING_WOLFCHAT:
                player.queue_message("* [wolfchat] \u0002{0}\u0002{1}".format(wrapper.source, message))
        else:
            for player in badguys:
                player.queue_message("\u0002{0}\u0002 says: {1}".format(wrapper.source, message))
            for player in var.SPECTATING_WOLFCHAT:
                player.queue_message("[wolfchat] \u0002{0}\u0002 says: {1}".format(wrapper.source, message))
        if badguys or var.SPECTATING_WOLFCHAT:
            player.send_messages()

@handle_error
def transition_night():
    if var.PHASE not in ("day", "join"):
        return
    var.PHASE = "night"
    var.GAMEPHASE = "night"

    var.NIGHT_START_TIME = datetime.now()
    var.NIGHT_COUNT += 1

    event_begin = Event("transition_night_begin", {})
    event_begin.dispatch(var)

    if var.DEVOICE_DURING_NIGHT:
        modes = []
        for player in get_players():
            if not player.is_fake:
                modes.append(("-v", player))
        channels.Main.mode(*modes)

    for x, tmr in var.TIMERS.items():  # cancel daytime timer
        tmr[0].cancel()
    var.TIMERS = {}

    # Reset nighttime variables
    var.KILLER = ""  # nickname of who chose the victim

    daydur_msg = ""

    if var.NIGHT_TIMEDELTA or var.START_WITH_DAY:  #  transition from day
        td = var.NIGHT_START_TIME - var.DAY_START_TIME
        var.DAY_START_TIME = None
        var.DAY_TIMEDELTA += td
        min, sec = td.seconds // 60, td.seconds % 60
        daydur_msg = messages["day_lasted"].format(min,sec)

    var.NIGHT_ID = time.time()
    if var.NIGHT_TIME_LIMIT > 0:
        t = threading.Timer(var.NIGHT_TIME_LIMIT, transition_day, [var.NIGHT_ID])
        var.TIMERS["night"] = (t, var.NIGHT_ID, var.NIGHT_TIME_LIMIT)
        t.daemon = True
        t.start()

    if var.NIGHT_TIME_WARN > 0:
        t2 = threading.Timer(var.NIGHT_TIME_WARN, night_warn, [var.NIGHT_ID])
        var.TIMERS["night_warn"] = (t2, var.NIGHT_ID, var.NIGHT_TIME_WARN)
        t2.daemon = True
        t2.start()

    # game ended from bitten / amnesiac turning, narcolepsy totem expiring, or other weirdness
    if chk_win():
        return

    event_end = Event("transition_night_end", {})
    event_end.dispatch(var)

    dmsg = (daydur_msg + messages["night_begin"])

    if var.NIGHT_COUNT > 1:
        dmsg = (dmsg + messages["first_night_begin"])
    channels.Main.send(dmsg)
    debuglog("BEGIN NIGHT")
    # If there are no nightroles that can act, immediately turn it to daytime
    chk_nightdone()

def cgamemode(arg):
    if var.ORIGINAL_SETTINGS:  # needs reset
        reset_settings()

    modeargs = arg.split("=", 1)

    modeargs = [a.strip() for a in modeargs]
    if modeargs[0] in var.GAME_MODES.keys():
        from src.gamemodes import InvalidModeException
        md = modeargs.pop(0)
        try:
            vilgame = var.GAME_MODES.get("villagergame")
            if vilgame is not None and md == "default" and vilgame[1] <= len(var.ALL_PLAYERS) <= vilgame[2] and random.random() < var.VILLAGERGAME_CHANCE:
                md = "villagergame"
            gm = var.GAME_MODES[md][0](*modeargs)
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
        cli.msg(chan, messages["game_mode_not_found"].format(modeargs[0]))

@hook("error")
def on_error(cli, pfx, msg):
    if var.RESTARTING or msg.endswith("(Excess Flood)"):
        _restart_program()
    elif msg.startswith("Closing Link:"):
        raise SystemExit

@command("template", "ftemplate", flag="F", pm=True)
def ftemplate(var, wrapper, message):
    cli, nick, chan, rest = wrapper.client, wrapper.source.name, wrapper.target.name, message # FIXME: @cmd
    params = re.split(" +", rest)

    if params[0] == "":
        # display a list of all templates
        tpls = db.get_templates()
        if not tpls:
            reply(cli, nick, chan, messages["no_templates"])
        else:
            tpls = ["{0} (+{1})".format(name, "".join(sorted(flags))) for name, flags in tpls]
            reply(cli, nick, chan, break_long_message(tpls, ", "))
    elif len(params) == 1:
        reply(cli, nick, chan, messages["not_enough_parameters"])
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
                reply(cli, nick, chan, messages["template_not_found"].format(tpl_name))
                return
            tpl_flags = "".join(sorted(tpl_flags))
            db.update_template(name, tpl_flags)
            reply(cli, nick, chan, messages["template_set"].format(name, tpl_flags))
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
                    reply(cli, nick, chan, messages["invalid_flag"].format(flag, "".join(sorted(var.ALL_FLAGS))))
                    return
                elif adding:
                    cur_flags.add(flag)
                else:
                    cur_flags.discard(flag)
            if cur_flags:
                tpl_flags = "".join(sorted(cur_flags))
                db.update_template(name, tpl_flags)
                reply(cli, nick, chan, messages["template_set"].format(name, tpl_flags))
            elif tid is None:
                reply(cli, nick, chan, messages["template_not_found"].format(name))
            else:
                db.delete_template(name)
                reply(cli, nick, chan, messages["template_deleted"].format(name))

        # re-init var.FLAGS and var.FLAGS_ACCS since they may have changed
        db.init_vars()

@command("fflags", flag="F", pm=True)
def fflags(var, wrapper, message):
    cli, nick, chan, rest = wrapper.client, wrapper.source.name, wrapper.target.name, message # FIXME: @cmd
    params = re.split(" +", rest)

    if params[0] == "":
        # display a list of all access
        parts = []
        for acc, flags in var.FLAGS_ACCS.items():
            if not flags:
                continue
            if var.ACCOUNTS_ONLY:
                parts.append("{0} (+{1})".format(acc, "".join(sorted(flags))))
            else:
                parts.append("{0} (Account) (+{1})".format(acc, "".join(sorted(flags))))
        for hm, flags in var.FLAGS.items():
            if not flags:
                continue
            if var.DISABLE_ACCOUNTS:
                parts.append("{0} (+{1})".format(hm, "".join(sorted(flags))))
            else:
                parts.append("{0} (Host) (+{1})".format(hm, "".join(sorted(flags))))
        if not parts:
            reply(cli, nick, chan, messages["no_access"])
        else:
            reply(cli, nick, chan, break_long_message(parts, ", "))
    elif len(params) == 1:
        # display access for the given user
        acc, hm = parse_warning_target(params[0], lower=True)
        if acc is not None and acc != "*":
            if not var.FLAGS_ACCS[acc]:
                msg = messages["no_access_account"].format(acc)
            else:
                msg = messages["access_account"].format(acc, "".join(sorted(var.FLAGS_ACCS[acc])))
        elif hm is not None:
            if not var.FLAGS[hm]:
                msg = messages["no_access_host"].format(hm)
            else:
                msg = messages["access_host"].format(hm, "".join(sorted(var.FLAGS[hm])))
        reply(cli, nick, chan, msg)
    else:
        acc, hm = parse_warning_target(params[0])
        flags = params[1]
        lhm = hm.lower() if hm else hm
        cur_flags = set(var.FLAGS_ACCS[irc_lower(acc)] + var.FLAGS[lhm])

        if flags[0] != "+" and flags[0] != "-":
            # flags is a template name
            tpl_name = flags.upper()
            tpl_id, tpl_flags = db.get_template(tpl_name)
            if tpl_id is None:
                reply(cli, nick, chan, messages["template_not_found"].format(tpl_name))
                return
            tpl_flags = "".join(sorted(tpl_flags))
            db.set_access(acc, hm, tid=tpl_id)
            if acc is not None and acc != "*":
                reply(cli, nick, chan, messages["access_set_account"].format(acc, tpl_flags))
            else:
                reply(cli, nick, chan, messages["access_set_host"].format(hm, tpl_flags))
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
                    reply(cli, nick, chan, messages["invalid_flag"].format(flag, "".join(sorted(var.ALL_FLAGS))))
                    return
                elif adding:
                    cur_flags.add(flag)
                else:
                    cur_flags.discard(flag)
            if cur_flags:
                flags = "".join(sorted(cur_flags))
                db.set_access(acc, hm, flags=flags)
                if acc is not None:
                    reply(cli, nick, chan, messages["access_set_account"].format(acc, flags))
                else:
                    reply(cli, nick, chan, messages["access_set_host"].format(hm, flags))
            else:
                db.set_access(acc, hm, flags=None)
                if acc is not None and acc != "*":
                    reply(cli, nick, chan, messages["access_deleted_account"].format(acc))
                else:
                    reply(cli, nick, chan, messages["access_deleted_host"].format(hm))

        # re-init var.FLAGS and var.FLAGS_ACCS since they may have changed
        db.init_vars()

@command("fstop", flag="S", phases=("join", "day", "night"))
def reset_game(var, wrapper, message):
    """Forces the game to stop."""
    wrapper.send(messages["fstop_success"].format(wrapper.source))
    if var.PHASE != "join":
        stop_game(var, log=False)
    else:
        pl = [p for p in get_players() if not p.is_fake]
        reset_modes_timers(var)
        reset()
        if pl:
            wrapper.send("PING! {0}".format(" ".join(pl)))

@command("rules", pm=True)
def show_rules(var, wrapper, message):
    """Displays the rules."""
    cli, nick, chan, rest = wrapper.client, wrapper.source.name, wrapper.target.name, message # FIXME: @cmd

    if hasattr(botconfig, "RULES"):
        rules = botconfig.RULES

        # Backwards-compatibility
        pattern = re.compile(r"^\S+ channel rules: ")

        if pattern.search(rules):
            rules = pattern.sub("", rules)

        reply(cli, nick, chan, messages["channel_rules"].format(botconfig.CHANNEL, rules))
    else:
        reply(cli, nick, chan, messages["no_channel_rules"].format(botconfig.CHANNEL))

@command("help", pm=True)
def get_help(var, wrapper, message):
    """Gets help."""
    cli, rnick, chan, rest = wrapper.client, wrapper.source.rawnick, wrapper.target.name, message # FIXME: @cmd
    nick, _, ident, host = parse_nick(rnick)
    fns = []

    rest = rest.strip().replace(botconfig.CMD_CHAR, "", 1).lower()
    splitted = re.split(" +", rest, 1)
    cname = splitted.pop(0)
    rest = splitted[0] if splitted else ""
    if cname:
        if cname in COMMANDS.keys():
            got = False
            for fn in COMMANDS[cname]:
                if fn.__doc__:
                    got = True
                    if callable(fn.__doc__):
                        msg = botconfig.CMD_CHAR+cname+": "+fn.__doc__(rest)
                    else:
                        msg = botconfig.CMD_CHAR+cname+": "+fn.__doc__
                    reply(cli, nick, chan, msg, private=True)
                else:
                    got = False
                    continue
            else:
                if got:
                    return
                reply(cli, nick, chan, messages["documentation_unavailable"], private=True)

        else:
            reply(cli, nick, chan, messages["command_not_found"], private=True)
        return

    # if command was not found, or if no command was given:
    for name, fn in COMMANDS.items():
        if (name and not fn[0].flag and not fn[0].owner_only and
            name not in fn[0].aliases and fn[0].chan):
            fns.append("{0}{1}{0}".format("\u0002", name))
    afns = []
    if is_admin(nick, ident, host):
        for name, fn in COMMANDS.items():
            if fn[0].flag and name not in fn[0].aliases:
                afns.append("{0}{1}{0}".format("\u0002", name))
    fns.sort() # Output commands in alphabetical order
    reply(cli, nick, chan, messages["commands_list"].format(break_long_message(fns, ", ")), private=True)
    if afns:
        afns.sort()
        reply(cli, nick, chan, messages["admin_commands_list"].format(break_long_message(afns, ", ")), private=True)

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
def wiki(var, wrapper, message):
    """Prints information on roles from the wiki."""
    cli, nick, chan, rest = wrapper.client, wrapper.source.name, wrapper.target.name, message # FIXME: @cmd

    # no arguments, just print a link to the wiki
    if not rest:
        reply(cli, nick, chan, "https://werewolf.chat")
        return
    rest = rest.replace(" ", "_").lower()

    # Get suggestions, for autocompletion
    URI = "https://werewolf.chat/w/api.php?action=opensearch&format=json&search={0}".format(rest)
    success, suggestionjson = get_wiki_page(URI)
    if not success:
        reply(cli, nick, chan, suggestionjson, private=True)
        return

    # Parse suggested pages, take the first result
    try:
        suggestion = suggestionjson[1][0].replace(" ", "_")
    except IndexError:
        reply(cli, nick, chan, messages["wiki_no_info"], private=True)
        return

    # Fetch a page from the api, in json format
    URI = "https://werewolf.chat/w/api.php?action=query&prop=extracts&exintro=true&explaintext=true&titles={0}&format=json".format(suggestion)
    success, pagejson = get_wiki_page(URI)
    if not success:
        reply(cli, nick, chan, pagejson, private=True)
        return

    try:
        page = pagejson["query"]["pages"].popitem()[1]["extract"]
    except (KeyError, IndexError):
        reply(cli, nick, chan, messages["wiki_no_info"], private=True)
        return

    # We only want the first paragraph
    if page.find("\n") >= 0:
        page = page[:page.find("\n")]

    wikilink = "https://werewolf.chat/{0}".format(suggestion.capitalize())
    if nick == chan:
        pm(cli, nick, wikilink)
        pm(cli, nick, break_long_message(page.split()))
    else:
        cli.msg(chan, wikilink)
        cli.notice(nick, break_long_message(page.split()))

@hook("invite")
def on_invite(cli, raw_nick, something, chan):
    if chan == botconfig.CHANNEL:
        cli.join(chan)
        return # No questions
    (nick, _, ident, host) = parse_nick(raw_nick)
    if is_admin(nick, ident, host):
        cli.join(chan) # Allows the bot to be present in any channel
        debuglog(nick, "INVITE", chan, display=True)

@command("admins", "ops", pm=True)
def show_admins(var, wrapper, message):
    """Pings the admins that are available."""
    cli, nick, chan, rest = wrapper.client, wrapper.source.name, wrapper.target.name, message # FIXME: @cmd

    admins = []
    pl = list_players()

    if (chan != nick and var.LAST_ADMINS and var.LAST_ADMINS +
            timedelta(seconds=var.ADMINS_RATE_LIMIT) > datetime.now()):
        cli.notice(nick, messages["command_ratelimited"])
        return

    if chan != nick or (var.PHASE in var.GAME_PHASES or nick in pl):
        var.LAST_ADMINS = datetime.now()

    if var.ADMIN_PINGING:
        return

    var.ADMIN_PINGING = True

    def admin_whoreply(event, var, chan, user):
        if not var.ADMIN_PINGING or chan is not channels.Main:
            return

        if is_admin(user.nick): # FIXME: Using the old interface for now; user.is_admin() is better
            if user is not users.Bot and not event.params.away:
                admins.append(user.nick) # FIXME

    def admin_endwho(event, var, target):
        if not var.ADMIN_PINGING or target is not channels.Main:
            return

        admins.sort(key=str.lower)

        msg = messages["available_admins"] + ", ".join(admins)

        reply(cli, nick, chan, msg)

        var.ADMIN_PINGING = False

        events.remove_listener("who_result", admin_whoreply)
        events.remove_listener("who_end", admin_endwho)

    events.add_listener("who_result", admin_whoreply)
    events.add_listener("who_end", admin_endwho)

    channels.Main.who()

@command("coin", pm=True)
def coin(var, wrapper, message):
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

@command("pony", "horse", pm=True)
def pony(var, wrapper, message):
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
def cat(var, wrapper, message):
    """Toss a cat into the air and see what happens!"""
    wrapper.send(messages["cat_toss"].format(wrapper.source), messages["cat_land"].format(), sep="\n")

@command("time", pm=True, phases=("join", "day", "night"))
def timeleft(var, wrapper, message):
    """Returns the time left until the next day/night transition."""
    cli, nick, chan, rest = wrapper.client, wrapper.source.name, wrapper.target.name, message # FIXME: @cmd

    if (chan != nick and var.LAST_TIME and
            var.LAST_TIME + timedelta(seconds=var.TIME_RATE_LIMIT) > datetime.now()):
        cli.notice(nick, messages["command_ratelimited"])
        return

    if chan != nick:
        var.LAST_TIME = datetime.now()

    if var.PHASE == "join":
        dur = int((var.CAN_START_TIME - datetime.now()).total_seconds())
        msg = None
        if dur > 1:
            msg = messages["start_timer_plural"].format(dur)
        elif dur == 1:
            msg = messages["start_timer_singular"]

        if msg is not None:
            reply(cli, nick, chan, msg)

    if var.PHASE in var.TIMERS:
        if var.PHASE == "day":
            what = "sunset"
        elif var.PHASE == "night":
            what = "sunrise"
        elif var.PHASE == "join":
            what = "the game is canceled if it's not started"

        remaining = int((var.TIMERS[var.PHASE][1] + var.TIMERS[var.PHASE][2]) - time.time())
        msg = "There is \u0002{0[0]:0>2}:{0[1]:0>2}\u0002 remaining until {1}.".format(divmod(remaining, 60), what)
    else:
        msg = messages["timers_disabled"].format(var.PHASE.capitalize())

    reply(cli, nick, chan, msg)

@command("roles", pm=True)
def list_roles(var, wrapper, message):
    """Display which roles are in play for a specific gamemode."""

    lpl = len(var.ALL_PLAYERS)
    specific = 0

    pieces = re.split(" +", message.strip())
    gamemode = var.CURRENT_GAMEMODE
    if gamemode.name == "villagergame":
        gamemode = var.GAME_MODES["default"][0]()

    if (not pieces[0] or pieces[0].isdigit()) and not hasattr(gamemode, "ROLE_GUIDE"):
        wrapper.reply("There {0} \u0002{1}\u0002 playing. {2}roles is disabled for the {3} game mode.".format("is" if lpl == 1 else "are", lpl, botconfig.CMD_CHAR, gamemode.name), prefix_nick=True)
        return

    msg = []

    if not pieces[0] and lpl:
        msg.append("There {0} \u0002{1}\u0002 playing.".format("is" if lpl == 1 else "are", lpl))
        if var.PHASE in var.GAME_PHASES:
            msg.append("Using the {0} game mode.".format(gamemode.name))
            pieces[0] = str(lpl)

    if pieces[0] and not pieces[0].isdigit():
        valid = var.GAME_MODES.keys() - var.DISABLED_GAMEMODES - {"roles", "villagergame"}
        mode = pieces.pop(0)
        if mode not in valid:
            matches = complete_match(mode, valid)
            if not matches:
                wrapper.reply(messages["invalid_mode"].format(mode), prefix_nick=True)
                return
            if len(matches) > 1:
                wrapper.reply(messages["ambiguous_mode"].format(mode, matches), prefix_nick=True)
                return

            mode = matches[0]

        gamemode = var.GAME_MODES[mode][0]()

        try:
            gamemode.ROLE_GUIDE
        except AttributeError:
            wrapper.reply("{0}roles is disabled for the {1} game mode.".format(botconfig.CMD_CHAR, gamemode.name), prefix_nick=True)
            return

    strip = lambda x: re.sub("\(.*\)", "", x)
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

        msg.append("[{0}]".format(specific))
        msg.append(", ".join(new))

    else:
        final = []

        for num, role_num in roles:
            snum = "[{0}]".format(num)
            if num <= lpl:
                snum = "\u0002{0}\u0002".format(snum)
            final.append(snum + " ")
            new = []
            for role in role_num:
                if role.startswith("-"):
                    rolecnt[role[1:]] -= 1
                    new.append(role)
                else:
                    rolecnt[role] += 1
                    append = "({0})".format(rolecnt[role]) if rolecnt[role] > 1 else ""
                    new.append(role + append)

            final.append(", ".join(new))

        msg.append(" ".join(final))

    if not msg:
        msg.append("No roles are defined for {0}p games.".format(specific or lpl))

    wrapper.send(*msg)

@command("myrole", pm=True, phases=("day", "night"))
def myrole(var, wrapper, message):
    """Reminds you of your current role."""

    ps = get_participants()
    if wrapper.source not in ps:
        return

    role = get_main_role(wrapper.source)
    if role in Hidden:
        role = var.HIDDEN_ROLE

    evt = Event("myrole", {"role": role, "messages": []})
    if not evt.dispatch(var, wrapper.source):
        return
    role = evt.data["role"]

    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
    wrapper.pm(messages["show_role"].format(an, role))

    for msg in evt.data["messages"]:
        wrapper.pm(msg)

@command("aftergame", "faftergame", flag="D", pm=True)
def aftergame(var, wrapper, message):
    """Schedule a command to be run after the current game."""
    if not message.strip():
        wrapper.pm(messages["incorrect_syntax"])
        return

    args = re.split(" +", message)
    before, prefix, after = args.pop(0).lower().partition(botconfig.CMD_CHAR)
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
                fn.caller(var, context, " ".join(args))
                fn.aftergame = False
    else:
        wrapper.pm(messages["command_not_found"])
        return

    if var.PHASE == "none":
        do_action()
        return

    channels.Main.send(messages["command_scheduled"].format(" ".join([cmd] + args), wrapper.source))
    var.AFTER_FLASTGAME = do_action

def _command_disabled(var, wrapper, message):
    wrapper.send(messages["command_disabled_admin"])

@command("lastgame", "flastgame", flag="D", pm=True)
def flastgame(var, wrapper, message):
    """Disables starting or joining a game, and optionally schedules a command to run after the current game ends."""
    for cmdcls in (COMMANDS["join"] + COMMANDS["start"]):
        cmdcls.func = _command_disabled

    channels.Main.send(messages["disable_new_games"].format(wrapper.source))
    var.ADMIN_TO_PING = wrapper.source

    if message.strip():
        aftergame.func(var, wrapper, message)

@command("gamestats", "gstats", pm=True)
def gamestats(var, wrapper, message):
    """Get the game stats for a given game size or lists game totals for all game sizes if no game size is given."""

    if wrapper.public:
        if (var.GSTATS_RATE_LIMIT and var.LAST_GSTATS and
            var.LAST_GSTATS + timedelta(seconds=var.GSTATS_RATE_LIMIT) > datetime.now()):
            wrapper.pm(messages["command_ratelimited"])
            return

        var.LAST_GSTATS = datetime.now()
        if var.PHASE in var.GAME_PHASES and wrapper.target is channels.Main:
            wrapper.pm(messages["stats_wait_for_game_end"])
            return

    gamemode = "all"
    gamesize = None
    msg = message.split()
    # Check for gamemode
    if msg and not msg[0].isdigit():
        gamemode = msg[0]
        if gamemode != "all" and gamemode not in var.GAME_MODES:
            matches = complete_match(gamemode, var.GAME_MODES)
            if len(matches) == 1:
                gamemode = matches[0]
            if not matches:
                wrapper.pm(messages["invalid_mode"].format(msg[0]))
                return
            if len(matches) > 1:
                wrapper.pm(messages["ambiguous_mode"].format(msg[0], matches))
                return
        msg.pop(0)

    # Check for invalid input
    if msg and msg[0].isdigit():
        gamesize = int(msg[0])
        if gamemode != "all" and not (var.GAME_MODES[gamemode][1] <= gamesize <= var.GAME_MODES[gamemode][2]):
            wrapper.pm(messages["integer_range"].format(var.GAME_MODES[gamemode][1], var.GAME_MODES[gamemode][2]))
            return

    # List all games sizes and totals if no size is given
    if not gamesize:
        wrapper.send(db.get_game_totals(gamemode))
    else:
        # Attempt to find game stats for the given game size
        wrapper.send(db.get_game_stats(gamemode, gamesize))

@command("playerstats", "pstats", "player", "p", pm=True)
def player_stats(var, wrapper, message):
    """Gets the stats for the given player and role or a list of role totals if no role is given."""
    cli, nick, chan, rest = wrapper.client, wrapper.source.nick, wrapper.target.name, message # FIXME: @cmd
    if (chan != nick and var.LAST_PSTATS and var.PSTATS_RATE_LIMIT and
            var.LAST_PSTATS + timedelta(seconds=var.PSTATS_RATE_LIMIT) >
            datetime.now()):
        cli.notice(nick, messages["command_ratelimited"])
        return

    if chan != nick and chan == botconfig.CHANNEL and var.PHASE not in ("none", "join"):
        cli.notice(nick, messages["no_command_in_channel"])
        return

    if chan != nick:
        var.LAST_PSTATS = datetime.now()

    params = rest.split()

    # Check if we have enough parameters
    if params:
        user = params[0]
    else:
        user = nick

    # Find the player's account if possible
    luser = user.lower()
    lusers = {k.lower(): v for k, v in var.USERS.items()}
    if luser in lusers:
        acc = irc_lower(lusers[luser]["account"])
        hostmask = luser + "!" + irc_lower(lusers[luser]["ident"]) + "@" + lusers[luser]["host"].lower()
        if acc == "*" and var.ACCOUNTS_ONLY:
            if luser == nick.lower():
                cli.notice(nick, messages["not_logged_in"])
            else:
                cli.notice(nick, messages["account_not_logged_in"].format(user))
            return
    elif "@" in user:
        acc = None
        hml, hmr = user.split("@", 1)
        hostmask = irc_lower(hml) + "@" + hmr.lower()
        luser = hostmask
    else:
        acc = irc_lower(user)
        hostmask = None

    # List the player's total games for all roles if no role is given
    if len(params) < 2:
        reply(cli, nick, chan, db.get_player_totals(acc, hostmask), private=True)
    else:
        role = " ".join(params[1:])
        matches = complete_role(var, role)
        if not matches:
            reply(cli, nick, chan, messages["no_such_role"].format(role))
            return
        if len(matches) > 1:
            reply(cli, nick, chan, messages["ambiguous_role"].format(", ".join(matches)))
            return
        role = matches[0]
        # Attempt to find the player's stats
        reply(cli, nick, chan, db.get_player_stats(acc, hostmask, role))

@command("mystats", "m", pm=True)
def my_stats(var, wrapper, message):
    """Get your own stats."""
    message = message.split()
    player_stats.func(var, wrapper, " ".join([wrapper.source.nick] + message))

@command("rolestats", "rstats", pm=True)
def role_stats(var, wrapper, rest):
    """Gets the stats for a given role in a given gamemode or lists role totals across all games if no role is given."""
    if (wrapper.target != users.Bot and var.LAST_RSTATS and var.RSTATS_RATE_LIMIT and
            var.LAST_RSTATS + timedelta(seconds=var.RSTATS_RATE_LIMIT) > datetime.now()):
        wrapper.pm(messages["command_ratelimited"])
        return

    if wrapper.target != users.Bot:
        var.LAST_RSTATS = datetime.now()
    
    if var.PHASE not in ("none", "join") and wrapper.target is not channels.Main:
            wrapper.pm(messages["stats_wait_for_game_end"])
            return

    params = rest.split()
    
    if len(params) == 0:
        # this is a long message
        wrapper.pm(db.get_role_totals())
        return

    roles = complete_role(var, rest)
    if params[-1] == "all" and len(roles) != 1:
        roles = complete_role(var, " ".join(params[:-1]))
    if len(roles) == 1:
        wrapper.reply(db.get_role_stats(roles[0]))
        return

    gamemode = params[-1]
    if gamemode not in var.GAME_MODES.keys():
        matches = complete_match(gamemode, var.GAME_MODES.keys())
        if len(matches) == 1:
            gamemode = matches[0]
        else:
            if len(roles) > 0:
                wrapper.pm(messages["ambiguous_role"].format(roles))
            elif len(matches) > 0:
                wrapper.pm(messages["ambiguous_mode"].format(gamemode, matches))
            else:
                wrapper.pm(messages["no_such_role"].format(rest))
            return

    if len(params) == 1:
        wrapper.pm(db.get_role_totals(gamemode))
        return

    role = " ".join(params[:-1])
    roles = complete_role(var, role)
    if len(roles) != 1:
        if len(roles) == 0:
            wrapper.pm(messages["no_such_role"].format(role))
        else:
            wrapper.pm(messages["ambiguous_role"].format(", ".join(roles)))
        return
    wrapper.reply(db.get_role_stats(roles[0], gamemode))

# Called from !game and !join, used to vote for a game mode
def vote_gamemode(var, wrapper, gamemode, doreply):
    if var.FGAMED:
        if doreply:
            wrapper.pm(messages["admin_forced_game"])
        return

    if gamemode not in var.GAME_MODES.keys():
        matches = complete_match(gamemode, var.GAME_MODES.keys() - {"roles", "villagergame"} - var.DISABLED_GAMEMODES)
        if not matches:
            if doreply:
                wrapper.pm(messages["invalid_mode"].format(gamemode))
            return
        if len(matches) > 1:
            if doreply:
                wrapper.pm(messages["ambiguous_mode"].format(gamemode, matches))
            return
        if len(matches) == 1:
            gamemode = matches[0]

    if gamemode != "roles" and gamemode != "villagergame" and gamemode not in var.DISABLED_GAMEMODES:
        if var.GAMEMODE_VOTES.get(wrapper.source.nick) == gamemode:
            wrapper.pm(messages["already_voted_game"].format(gamemode))
        else:
            var.GAMEMODE_VOTES[wrapper.source.nick] = gamemode
            wrapper.send(messages["vote_game_mode"].format(wrapper.source, gamemode))
    else:
        if doreply:
            wrapper.pm(messages["vote_game_fail"])

@command("game", playing=True, phases=("join",))
def game(var, wrapper, message):
    """Vote for a game mode to be picked."""
    if message:
        vote_gamemode(var, wrapper, message.lower().split()[0], doreply=True)
    else:
        gamemodes = ", ".join("\u0002{0}\u0002".format(gamemode) if len(list_players()) in range(var.GAME_MODES[gamemode][1],
            var.GAME_MODES[gamemode][2]+1) else gamemode for gamemode in var.GAME_MODES.keys() if gamemode != "roles" and
            gamemode != "villagergame" and gamemode not in var.DISABLED_GAMEMODES)
        wrapper.pm(messages["no_mode_specified"] + gamemodes)
        return

@command("games", "modes", pm=True)
def show_modes(var, wrapper, message):
    """Show the available game modes."""
    modes = "\u0002, \u0002".join(sorted(var.GAME_MODES.keys() - {"roles", "villagergame"} - var.DISABLED_GAMEMODES))

    wrapper.pm("{0}{1}\u0002".format(messages["available_modes"], modes))

def game_help(args=""):
    return (messages["available_mode_setters_help"] +
        ", ".join("\u0002{0}\u0002".format(gamemode) if len(list_players()) in range(var.GAME_MODES[gamemode][1], var.GAME_MODES[gamemode][2]+1)
        else gamemode for gamemode in var.GAME_MODES.keys() if gamemode != "roles" and gamemode not in var.DISABLED_GAMEMODES))
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

    return (ret, out)

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

    (ret, _) = _call_command(wrapper, "git rebase --stat --preserve-merges")
    return (ret == 0)


@command("pull", "fpull", flag="D", pm=True)
def fpull(var, wrapper, message):
    """Pulls from the repository to update the bot."""
    _git_pull(wrapper)

@command("update", flag="D", pm=True)
def update(var, wrapper, message):
    """Pulls from the repository and restarts the bot to update it."""

    force = (message.strip() == "-force")

    if var.PHASE in var.GAME_PHASES:
        if var.PHASE == "join" or force:
            stop_game(var, log=False)
        else:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(
                what="restart", cmd="update", prefix=botconfig.CMD_CHAR))
            return

    if update.aftergame:
        # Display "Scheduled restart" instead of "Forced restart" when called with !faftergame
        restart_program.aftergame = True

    ret = _git_pull(wrapper)
    if ret:
        restart_program.func(var, wrapper, "Updating bot")

@command("fsend", flag="F", pm=True)
def fsend(var, wrapper, message):
    """Forcibly send raw IRC commands to the server."""
    wrapper.source.client.send(message)

def _say(wrapper, rest, cmd, action=False):
    rest = rest.split(" ", 1)

    if len(rest) < 2:
        wrapper.pm(messages["fsend_usage"].format(botconfig.CMD_CHAR, cmd))
        return

    target, message = rest

    if target.startswith(tuple(hooks.Features["CHANTYPES"])):
        targ = channels.get(target, allow_none=True)
    else:
        targ = users._get(target, allow_multiple=True) # FIXME
        if len(targ) == 1:
            targ = targ[0]
        else:
            targ = None

    if targ is None:
        targ = IRCContext(target, wrapper.source.client)

    if not wrapper.source.is_admin():
        if targ is not channels.Main:
            wrapper.pm(messages["invalid_fsend_permissions"])
            return

    if action:
        message = "\u0001ACTION {0}\u0001".format(message)

    targ.send(message, privmsg=True)

@command("fsay", flag="s", pm=True)
def fsay(var, wrapper, message):
    """Talk through the bot as a normal message."""
    _say(wrapper, message, "say")

@command("fdo", "fme", flag="s", pm=True)
def fdo(var, wrapper, message):
    """Act through the bot as an action."""
    _say(wrapper, message, "act", action=True)

def can_run_restricted_cmd(user):
    # if allowed in normal games, restrict it so that it can only be used by dead players and
    # non-players (don't allow active vengeful ghosts either).
    # also don't allow in-channel (e.g. make it pm only)

    if botconfig.DEBUG_MODE:
        return True

    pl = get_participants()

    if user in pl:
        return False

    if not var.DISABLE_ACCOUNTS and user.account in {player.account for player in pl}:
        return False

    if user.userhost in {player.userhost for player in pl}:
        return False

    return True

def spectate_chat(var, wrapper, message, *, is_fspectate):
    if not can_run_restricted_cmd(wrapper.source):
        wrapper.pm(messages["fspectate_restricted"])
        return

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
            players = [p for p in get_players() if in_wolflist(p.nick, p.nick)]
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
def spectate(var, wrapper, message):
    """Spectate wolfchat or deadchat."""
    spectate_chat(var, wrapper, message, is_fspectate=False)

@command("fspectate", flag="F", pm=True, phases=("day", "night"))
def fspectate(var, wrapper, message):
    """Spectate wolfchat or deadchat."""
    spectate_chat(var, wrapper, message, is_fspectate=True)

@command("revealroles", flag="a", pm=True, phases=("day", "night"))
def revealroles(var, wrapper, message):
    """Reveal role information."""

    if not can_run_restricted_cmd(wrapper.source):
        wrapper.pm(messages["temp_invalid_perms"])
        return

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
                            special_case.append("was {0}".format(old_role))
                            break
                if special_case:
                    out.append("".join((user.nick, " (", ", ".join(special_case), ")")))
                else:
                    out.append(user.nick)

            output.append("\u0002{0}\u0002: {1}".format(role, ", ".join(out)))

    evt = Event("revealroles", {"output": output})
    evt.dispatch(var, wrapper)

    if botconfig.DEBUG_MODE:
        wrapper.send(*output, sep=" | ")
    else:
        wrapper.pm(*output, sep=" | ")

@command("fgame", flag="g", phases=("join",))
def fgame(var, wrapper, message):
    """Force a certain game mode to be picked. Disable voting for game modes upon use."""

    if message:
        gamemode = message.strip().lower()
        parts = gamemode.replace("=", " ", 1).split(None, 1)
        if len(parts) > 1:
            gamemode, modeargs = parts
        else:
            gamemode = parts[0]
            modeargs = None

        if gamemode not in var.GAME_MODES.keys() - var.DISABLED_GAMEMODES:
            gamemode = gamemode.split()[0]
            gamemode = complete_one_match(gamemode, var.GAME_MODES.keys() - var.DISABLED_GAMEMODES)
            if not gamemode:
                wrapper.pm(messages["invalid_mode"].format(message.split()[0]))
                return
            parts[0] = gamemode

        if cgamemode("=".join(parts)):
            channels.Main.send(messages["fgame_success"].format(wrapper.source))
            var.FGAMED = True
    else:
        wrapper.pm(fgame.__doc__())

def fgame_help(args=""):
    args = args.strip()

    if not args:
        return messages["available_mode_setters"] + ", ".join(var.GAME_MODES.keys() - var.DISABLED_GAMEMODES)
    elif args in var.GAME_MODES.keys() and args not in var.DISABLED_GAMEMODES:
        return var.GAME_MODES[args][0].__doc__ or messages["setter_no_doc"].format(args)
    else:
        return messages["setter_not_found"].format(args)


fgame.__doc__ = fgame_help

# eval/exec are owner-only but also marked with "d" flag
# to disable them outside of debug mode
@command("eval", owner_only=True, flag="d", pm=True)
def pyeval(var, wrapper, message):
    """Evaluate a Python expression."""
    try:
        wrapper.send(str(eval(message))[:500])
    except Exception as e:
        wrapper.send("{e.__class__.__name__}: {e}".format(e=e))

@command("exec", owner_only=True, flag="d", pm=True)
def py(var, wrapper, message):
    """Execute arbitrary Python code."""
    try:
        exec(message)
    except Exception as e:
        wrapper.send("{e.__class__.__name__}: {e}".format(e=e))


def _force_command(var, wrapper, name, players, message):
    for user in players:
        handler.parse_and_dispatch(var, wrapper, name, message, force=user)
    wrapper.send(messages["operation_successful"])


@command("force", flag="d")
def force(var, wrapper, message):
    """Force a certain player to use a specific command."""
    msg = re.split(" +", message)
    if len(msg) < 2:
        wrapper.send(messages["incorrect_syntax"])
        return

    target = msg.pop(0).strip()
    match, _ = users.complete_match(target, get_participants())
    if target == "*":
        players = get_players()
    elif match is None:
        wrapper.send(messages["invalid_target"])
        return
    else:
        players = [match]

    _force_command(var, wrapper, msg.pop(0), players, " ".join(msg))

@command("rforce", flag="d")
def rforce(var, wrapper, message):
    """Force all players of a given role to perform a certain action."""
    msg = re.split(" +", message)
    if len(msg) < 2:
        wrapper.send(messages["incorrect_syntax"])
        return

    target = msg.pop(0).strip().lower()
    possible = complete_role(var, target)
    if target == "*":
        players = get_players()
    elif len(possible) == 1:
        players = get_all_players((possible[0],))
    else:
        wrapper.send("Invalid role")
        return

    _force_command(var, wrapper, msg.pop(0), players, " ".join(msg))

@command("frole", flag="d", phases=("join",))
def frole(var, wrapper, message):
    """Force a player into a certain role."""
    pl = get_players()

    parts = message.lower().split(",")
    for part in parts:
        try:
            (name, role) = part.split(":", 1)
        except ValueError:
            wrapper.send(messages["frole_incorrect"].format(part))
            return
        user, _ = users.complete_match(name.strip(), pl)
        matches = complete_role(var, role.strip())
        role = None
        if len(matches) == 1:
            role = matches[0]
        if user is None or role not in role_order() or role == var.DEFAULT_ROLE:
            wrapper.send(messages["frole_incorrect"].format(part))
            return
        var.FORCE_ROLES[role].add(user)

    wrapper.send(messages["operation_successful"])

@command("ftotem", flag="d", phases=("night",))
def ftotem(var, wrapper, message):
    """Force a shaman to have a particular totem."""
    msg = re.split(" +", message)
    if len(msg) < 2:
        wrapper.send(messages["incorrect_syntax"])
        return

    target = msg.pop(0).strip()
    match, _ = users.complete_match(target, get_players())
    if match is None:
        wrapper.send(messages["invalid_target"])
        return

    from src.roles.helper.shamans import change_totem
    try:
        change_totem(var, match, " ".join(msg))
    except ValueError as e:
        wrapper.send(str(e))
        return

    wrapper.send(messages["operation_successful"])

# vim: set sw=4 expandtab:
