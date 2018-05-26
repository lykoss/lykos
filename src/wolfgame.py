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
import itertools
import functools
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
import json
from datetime import datetime, timedelta

from oyoyo.parse import parse_nick

import botconfig
import src
import src.settings as var
from src.utilities import *
from src import db, events, dispatcher, channels, users, hooks, logger, debuglog, errlog, plog
from src.decorators import command, cmd, hook, handle_error, event_listener, COMMANDS
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.functions import get_players, get_all_players, get_participants, get_main_role, get_all_roles, get_reveal_role, get_target
from src.messages import messages
from src.warnings import *
from src.context import IRCContext

# done this way so that events is accessible in !eval (useful for debugging)
Event = events.Event

# Game Logic Begins:

var.LAST_STATS = None
var.LAST_VOTES = None
var.LAST_ADMINS = None
var.LAST_GSTATS = None
var.LAST_PSTATS = None
var.LAST_TIME = None
var.LAST_START = {}
var.LAST_WAIT = {}
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
var.OLD_MODES = defaultdict(set)

var.ROLES = UserDict() # type: Dict[str, Set[users.User]]
var.ORIGINAL_ROLES = UserDict() # type: Dict[str, Set[users.User]]
var.MAIN_ROLES = UserDict() # type: Dict[users.User, str]
var.ORIGINAL_MAIN_ROLES = UserDict() # type: Dict[users.User, str]
var.ALL_PLAYERS = UserList()
var.FORCE_ROLES = DefaultUserDict(UserSet)

var.DYING = UserSet()
var.WOUNDED = UserSet()
var.CONSECRATING = UserSet()
var.GUNNERS = UserDict()

var.NO_LYNCH = UserSet()
var.VOTES = UserDict()

var.DEADCHAT_PLAYERS = UserSet()

var.SPECTATING_WOLFCHAT = UserSet()
var.SPECTATING_DEADCHAT = UserSet()

var.ORIGINAL_SETTINGS = {}
var.CURRENT_GAMEMODE = var.GAME_MODES["default"][0]()

var.LAST_SAID_TIME = {}

var.GAME_START_TIME = datetime.now()  # for idle checker only
var.CAN_START_TIME = 0
var.STARTED_DAY_PLAYERS = 0

var.DISCONNECTED = {}  # players who are still alive but disconnected

var.RESTARTING = False

var.BITTEN_ROLES = {}
var.LYCAN_ROLES = {}
var.START_VOTES = UserSet()

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
            if not is_fake_nick(deadguy):
                cmodes.append(("-{0}".format(var.QUIET_MODE), var.QUIET_PREFIX+deadguy+"!*@*"))
    channels.Main.mode("-m", *cmodes)

def reset():
    var.PHASE = "none" # "join", "day", or "night"
    var.GAME_ID = 0
    var.ALL_PLAYERS.clear()
    var.RESTART_TRIES = 0
    var.DEAD = set()
    var.JOINED_THIS_GAME = set() # keeps track of who already joined this game at least once (hostmasks)
    var.JOINED_THIS_GAME_ACCS = set() # same, except accounts
    var.PINGED_ALREADY = set()
    var.PINGED_ALREADY_ACCS = set()
    var.NO_LYNCH.clear()
    var.FGAMED = False
    var.GAMEMODE_VOTES = {} #list of players who have used !game
    var.START_VOTES.clear() # list of players who have voted to !start
    var.ROLE_STATS = frozenset() # type: FrozenSet[FrozenSet[Tuple[str, int]]]
    var.ROLE_SETS = [] # type: List[Tuple[Counter[str], int]]
    var.VOTES.clear()

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

reset()

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
    wrapper.reply(random.choice(messages["ping"]).format(
        nick=wrapper.source, bot_nick=users.Bot,
        cmd_char=botconfig.CMD_CHAR,
        goat_action=random.choice(messages["goat_actions"])))

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
            wrapper.pm(messages["target_no_longer_playing" if target.nick in var.DEAD else "target_not_playing"]) # FIXME: Need to fix once var.DEAD holds User instances
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
        myrole.caller(wrapper.source.client, wrapper.source.nick, wrapper.target.name, "") # FIXME: Old API


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

                    msg_prefix = messages["ping_player"].format(len(pl), "" if len(pl) == 1 else "s")
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
        user.queue_message(messages["players_list"].format(", ".join([user.nick for user in people])))

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
            decrement_stasis(wrapper.source.nick)
        else:
            who.send(messages["stasis"].format(
                "you are" if wrapper.source is who else wrapper.source.nick + " is", stasis,
                "s" if stasis != 1 else ""), notice=True)
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
        with var.WAIT_TB_LOCK:
            var.WAIT_TB_TOKENS = var.WAIT_TB_INIT
            var.WAIT_TB_LAST   = time.time()
        var.GAME_ID = time.time()
        var.PINGED_ALREADY_ACCS = set()
        var.PINGED_ALREADY = set()
        if wrapper.source.userhost:
            var.JOINED_THIS_GAME.add(wrapper.source.userhost)
        if wrapper.source.account:
            var.JOINED_THIS_GAME_ACCS.add(wrapper.source.account)
        var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.MINIMUM_WAIT)
        wrapper.send(messages["new_game"].format(wrapper.source.nick, botconfig.CMD_CHAR))

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

            del_player(target, death_triggers=False)

        elif dead_target is not None:
            leave_deadchat(var, dead_target, force=wrapper.source)
            if wrapper.source not in var.DEADCHAT_PLAYERS:
                wrapper.pm(messages["admin_fleave_deadchat"].format(dead_target))

        else:
            wrapper.send(messages["not_playing"].format(person))
            return

@cmd("fstart", flag="S", phases=("join",))
def fstart(cli, nick, chan, rest):
    """Forces the game to start immediately."""
    cli.msg(botconfig.CHANNEL, messages["fstart_success"].format(nick))
    start(cli, nick, botconfig.CHANNEL, forced = True)

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

@cmd("stats", "players", pm=True, phases=("join", "day", "night"))
def stats(cli, nick, chan, rest):
    """Displays the player statistics."""

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

    badguys = var.WOLFCHAT_ROLES
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            badguys = var.WOLF_ROLES
        else:
            badguys = var.WOLF_ROLES | {"traitor"}

    role = None
    if nick in pl:
        role = get_role(nick)
    if chan == nick and role in badguys | {"warlock"}:
        ps = pl[:]
        if role in badguys:
            for i, player in enumerate(ps):
                prole = get_role(player)
                wevt = Event("wolflist", {"tags": set()})
                wevt.dispatch(var, users._get(player), users._get(nick)) # FIXME
                tags = " ".join(wevt.data["tags"])
                if prole in badguys:
                    if tags:
                        tags += " "
                    ps[i] = "\u0002{0}\u0002 ({1}{2})".format(player, tags, prole)
                elif tags:
                    ps[i] = "{0} ({1})".format(player, tags)
        elif role == "warlock":
            # warlock not in wolfchat explicitly only sees cursed
            for i, player in enumerate(pl):
                if player in get_roles("cursed villager"): # FIXME
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

    # Instead of looping over the current roles, we start with the original set and apply
    # changes to it as public game events occur. This way, !stats output should duplicate
    # what a player would have if they were manually tracking who is what and did not
    # have any non-public information. The comments below explain the logic such a player
    # would be using to derive the list. Note that this logic is based on the assumption
    # that role reveal is on. If role reveal is off or team, stats type should probably be
    # set to disabled or team respectively instead of this, as this will then leak info.
    if var.STATS_TYPE == "default":
        # role: [min, max] -- "we may not necessarily know *exactly* how
        # many of a particular role there are, but we know that there is
        # between min and max of them"
        rolecounts = defaultdict(lambda: [0, 0])
        start_roles = set()
        orig_roles = {}
        equiv_sets = {}
        total_immunizations = 0
        extra_lycans = 0
        # Step 1. Get our starting set of roles. This also calculates the maximum numbers for equivalency sets
        # (sets of roles that are decremented together because we can't know for sure which actually died).
        for r, v in var.ORIGINAL_ROLES.items():
            if r in var.TEMPLATE_RESTRICTIONS.keys():
                continue
            if len(v) == 0:
                continue
            start_roles.add(r)
            rolecounts[r] = [len(v), len(v)]
            for p in v:
                orig_roles[p.nick] = r

        if var.CURRENT_GAMEMODE.name == "villagergame":
            # hacky hacks that hack
            pcount = len(var.ALL_PLAYERS)
            if pcount >= 8:
                rolecounts["villager"][0] -= 2
                rolecounts["villager"][1] -= 2
                rolecounts["wolf"] = [1, 1]
                rolecounts["traitor"] = [1, 1]
            elif pcount == 7:
                rolecounts["villager"][0] -= 2
                rolecounts["villager"][1] -= 2
                rolecounts["wolf"] = [1, 1]
                rolecounts["cultist"] = [1, 1]
            else:
                rolecounts["villager"][0] -= 1
                rolecounts["villager"][1] -= 1
                rolecounts["wolf"] = [1, 1]

        total_immunizations = rolecounts["doctor"][0] * math.ceil(len(var.ALL_PLAYERS) * var.DOCTOR_IMMUNIZATION_MULTIPLIER)
        if "amnesiac" in start_roles and "doctor" not in var.AMNESIAC_BLACKLIST:
            total_immunizations += rolecounts["amnesiac"][0] * math.ceil(len(var.ALL_PLAYERS) * var.DOCTOR_IMMUNIZATION_MULTIPLIER)

        extra_lycans = rolecounts["lycan"][0] - min(total_immunizations, rolecounts["lycan"][0])

        equiv_sets["traitor_default"] = rolecounts["traitor"][0] + rolecounts[var.DEFAULT_ROLE][0]
        equiv_sets["lycan_villager"] = min(rolecounts["lycan"][0], total_immunizations) + rolecounts["villager"][0]
        equiv_sets["traitor_lycan_villager"] = equiv_sets["traitor_default"] + equiv_sets["lycan_villager"] - rolecounts[var.DEFAULT_ROLE][0]
        equiv_sets["amnesiac_clone"] = rolecounts["amnesiac"][0] + rolecounts["clone"][0]
        equiv_sets["amnesiac_clone_cub"] = rolecounts["amnesiac"][0] + rolecounts["clone"][0] + rolecounts["wolf cub"][0]
        equiv_sets["wolf_fallen"] = 0
        equiv_sets["fallen_guardian"] = 0
        if var.TRAITOR_TURNED:
            equiv_sets["traitor_default"] -= rolecounts["traitor"][0]
            equiv_sets["traitor_lycan_villager"] -= rolecounts["traitor"][0]
            rolecounts["wolf"][0] += rolecounts["traitor"][0]
            rolecounts["wolf"][1] += rolecounts["traitor"][1]
            rolecounts["traitor"] = [0, 0]
        # Step 2. Handle role swaps via exchange totem by modifying orig_roles -- the original
        # roles themselves didn't change, just who has them. By doing the swap early on we greatly
        # simplify the death logic below in step 3 -- to an outsider that doesn't know any info
        # the role swap might as well never happened and those people simply started with those roles;
        # they can't really tell the difference.
        for a, b in var.EXCHANGED_ROLES:
            orig_roles[a], orig_roles[b] = orig_roles[b], orig_roles[a]
        # Step 3. Work out people that turned into wolves via either alpha wolf, lycan, or lycanthropy totem
        # All three of those play the same "chilling howl" message, once per additional wolf
        num_alpha = rolecounts["alpha wolf"][0]
        num_angel = rolecounts["guardian angel"][0]
        if "amnesiac" in start_roles and "guardian angel" not in var.AMNESIAC_BLACKLIST:
            num_angel += rolecounts["amnesiac"][0]
        have_lycan_totem = False
        for idx, shaman in enumerate(var.TOTEM_ORDER):
            if (shaman in start_roles or ("amnesiac" in start_roles and shaman not in var.AMNESIAC_BLACKLIST)) and var.TOTEM_CHANCES["lycanthropy"][idx] > 0:
                have_lycan_totem = True

        extra_wolves = var.EXTRA_WOLVES
        num_wolves = rolecounts["wolf"][0]
        num_fallen = rolecounts["fallen angel"][0]
        while extra_wolves > 0:
            extra_wolves -= 1
            if num_alpha == 0 and not have_lycan_totem:
                # This is easy, all of our extra wolves are actual lycans, and we know this for a fact
                rolecounts["wolf"][0] += 1
                rolecounts["wolf"][1] += 1
                num_wolves += 1

                if rolecounts["lycan"][1] > 0:
                    rolecounts["lycan"][0] -= 1
                    rolecounts["lycan"][1] -= 1
                else:
                    # amnesiac or clone became lycan and was subsequently turned
                    maxcount = max(0, equiv_sets["amnesiac_clone"] - 1)

                    rolecounts["amnesiac"][0] = max(0, rolecounts["amnesiac"][0] - 1)
                    if rolecounts["amnesiac"][1] > maxcount:
                        rolecounts["amnesiac"][1] = maxcount

                    rolecounts["clone"][0] = max(0, rolecounts["clone"][0] - 1)
                    if rolecounts["clone"][1] > maxcount:
                        rolecounts["clone"][1] = maxcount

                    equiv_sets["amnesiac_clone"] = maxcount


                if extra_lycans > 0:
                    extra_lycans -= 1
                else:
                    equiv_sets["lycan_villager"] = max(0, equiv_sets["lycan_villager"] - 1)
                    equiv_sets["traitor_lycan_villager"] = max(0, equiv_sets["traitor_lycan_villager"] - 1)
            elif num_alpha == 0 or num_angel == 0:
                # We are guaranteed to have gotten an additional wolf, but we can't guarantee it was an actual lycan
                rolecounts["wolf"][0] += 1
                rolecounts["wolf"][1] += 1
                num_wolves += 1
                rolecounts["lycan"][0] = max(0, rolecounts["lycan"][0] - 1)

                # apply alphas before lycan totems (in case we don't actually have lycan totems)
                # this way if we don't have totems and alphas is 0 we hit guaranteed lycans above
                if num_alpha > 0:
                    num_alpha -= 1
            else:
                # We may have gotten an additional wolf or an additional fallen angel, we don't necessarily know which
                num_alpha -= 1
                num_angel -= 1
                rolecounts["lycan"][0] = max(0, rolecounts["lycan"][0] - 1)
                rolecounts["wolf"][1] += 1
                rolecounts["fallen angel"][1] += 1
                rolecounts["guardian angel"][0] -= 1
                equiv_sets["wolf_fallen"] += 1
                equiv_sets["fallen_guardian"] += 1

        # Step 4. Remove all dead players
        # When rolesets are a thing (e.g. one of x, y, or z), those will be resolved here as well
        for p in var.ALL_PLAYERS:
            p = p.nick # FIXME: Need to modify this block to handle User instances
            if p in pl:
                continue
            # pr should be the role the person gets revealed as should they die
            pr = orig_roles[p]
            if p in var.FINAL_ROLES and pr not in ("amnesiac", "clone"):
                pr = var.FINAL_ROLES[p]
            elif pr == "amnesiac" and not var.HIDDEN_AMNESIAC and p in var.FINAL_ROLES:
                pr = var.FINAL_ROLES[p]
            elif pr == "clone" and not var.HIDDEN_CLONE and p in var.FINAL_ROLES:
                pr = var.FINAL_ROLES[p]
            elif pr == "traitor" and var.TRAITOR_TURNED:
                # we turned every traitor into wolf above, which means even though
                # this person died as traitor, we need to deduct the count from wolves
                pr = "wolf"
            elif pr == "traitor" and var.HIDDEN_TRAITOR:
                pr = var.DEFAULT_ROLE

            # set to true if we kill more people than exist in a given role,
            # which means that amnesiac or clone must have became that role
            overkill = False

            if pr == var.DEFAULT_ROLE:
                # the person that died could have been traitor or an immunized lycan
                if var.DEFAULT_ROLE == "villager":
                    maxcount = equiv_sets["traitor_lycan_villager"]
                else:
                    maxcount = equiv_sets["traitor_default"]

                if maxcount == 0:
                    overkill = True

                maxcount = max(0, maxcount - 1)
                if var.HIDDEN_TRAITOR and not var.TRAITOR_TURNED:
                    rolecounts["traitor"][0] = max(0, rolecounts["traitor"][0] - 1)
                    if rolecounts["traitor"][1] > maxcount:
                        rolecounts["traitor"][1] = maxcount

                if var.DEFAULT_ROLE == "villager" and total_immunizations > 0:
                    total_immunizations -= 1
                    rolecounts["lycan"][0] = max(0, rolecounts["lycan"][0] - 1)
                    if rolecounts["lycan"][1] > maxcount + extra_lycans:
                        rolecounts["lycan"][1] = maxcount + extra_lycans

                rolecounts[pr][0] = max(0, rolecounts[pr][0] - 1)
                if rolecounts[pr][1] > maxcount:
                    rolecounts[pr][1] = maxcount

                if var.DEFAULT_ROLE == "villager":
                    equiv_sets["traitor_lycan_villager"] = maxcount
                else:
                    equiv_sets["traitor_default"] = maxcount
            elif pr == "villager":
                # the villager that died could have been an immunized lycan
                maxcount = max(0, equiv_sets["lycan_villager"] - 1)

                if equiv_sets["lycan_villager"] == 0:
                    overkill = True

                if total_immunizations > 0:
                    total_immunizations -= 1
                    rolecounts["lycan"][0] = max(0, rolecounts["lycan"][0] - 1)
                    if rolecounts["lycan"][1] > maxcount + extra_lycans:
                        rolecounts["lycan"][1] = maxcount + extra_lycans

                rolecounts[pr][0] = max(0, rolecounts[pr][0] - 1)
                if rolecounts[pr][1] > maxcount:
                    rolecounts[pr][1] = maxcount

                equiv_sets["lycan_villager"] = maxcount
            elif pr == "lycan":
                # non-immunized lycan, reduce counts appropriately
                if rolecounts[pr][1] == 0:
                    overkill = True
                rolecounts[pr][0] = max(0, rolecounts[pr][0] - 1)
                rolecounts[pr][1] = max(0, rolecounts[pr][1] - 1)

                if extra_lycans > 0:
                    extra_lycans -= 1
                else:
                    equiv_sets["lycan_villager"] = max(0, equiv_sets["lycan_villager"] - 1)
                    equiv_sets["traitor_lycan_villager"] = max(0, equiv_sets["traitor_lycan_villager"] - 1)
            elif pr == "wolf":
                # person that died could have possibly been turned by alpha
                if rolecounts[pr][1] == 0:
                    # this overkill either means that we're hitting amnesiac/clone or that cubs turned
                    overkill = True
                rolecounts[pr][0] = max(0, rolecounts[pr][0] - 1)
                rolecounts[pr][1] = max(0, rolecounts[pr][1] - 1)

                if num_wolves > 0:
                    num_wolves -= 1
                elif equiv_sets["wolf_fallen"] > 0:
                    equiv_sets["wolf_fallen"] -= 1
                    equiv_sets["fallen_guardian"] = max(0, equiv_sets["fallen_guardian"] - 1)
                    rolecounts["fallen angel"][1] = max(0, rolecounts["fallen angel"][1] - 1)
                    rolecounts["guardian angel"][0] = max(rolecounts["guardian angel"][0] + 1, rolecounts["guardian angel"][1])
                    rolecounts["fallen angel"][0] = min(rolecounts["fallen angel"][0], rolecounts["fallen angel"][1])
            elif pr == "fallen angel":
                # person that died could have possibly been turned by alpha
                if rolecounts[pr][1] == 0:
                    overkill = True
                rolecounts[pr][0] = max(0, rolecounts[pr][0] - 1)
                rolecounts[pr][1] = max(0, rolecounts[pr][1] - 1)

                if num_fallen > 0:
                    num_fallen -= 1
                elif equiv_sets["wolf_fallen"] > 0:
                    equiv_sets["wolf_fallen"] -= 1
                    equiv_sets["fallen_guardian"] = max(0, equiv_sets["fallen_guardian"] - 1)
                    rolecounts["wolf"][1] = max(0, rolecounts["wolf"][1] - 1)
                    rolecounts["wolf"][0] = min(rolecounts["wolf"][0], rolecounts["wolf"][1])
                    # this also means a GA died for sure (we lowered the lower bound previously)
                    rolecounts["guardian angel"][1] = max(0, rolecounts["guardian angel"][1] - 1)
            elif pr == "guardian angel":
                if rolecounts[pr][1] == 0:
                    overkill = True
                if rolecounts[pr][1] <= equiv_sets["fallen_guardian"] and equiv_sets["fallen_guardian"] > 0:
                    # we got rid of a GA that was an FA candidate, so get rid of the FA as well
                    # (this also means that there is a guaranteed wolf so add that in)
                    equiv_sets["fallen_guardian"] = max(0, equiv_sets["fallen_guardian"] - 1)
                    equiv_sets["wolf_fallen"] = max(0, equiv_sets["wolf_fallen"] - 1)
                    rolecounts["fallen angel"][1] = max(rolecounts["fallen angel"][0], rolecounts["fallen angel"][1] - 1)
                    rolecounts["wolf"][0] = min(rolecounts["wolf"][0] + 1, rolecounts["wolf"][1])
                rolecounts[pr][0] = max(0, rolecounts[pr][0] - 1)
                rolecounts[pr][1] = max(0, rolecounts[pr][1] - 1)
            elif pr == "wolf cub":
                if rolecounts[pr][1] == 0:
                    overkill = True
                rolecounts[pr][0] = max(0, rolecounts[pr][0] - 1)
                rolecounts[pr][1] = max(0, rolecounts[pr][1] - 1)
                equiv_sets["amnesiac_clone_cub"] = max(0, equiv_sets["amnesiac_clone_cub"] - 1)
            else:
                # person that died is guaranteed to be that role (e.g. not in an equiv_set)
                if rolecounts[pr][1] == 0:
                    overkill = True
                rolecounts[pr][0] = max(0, rolecounts[pr][0] - 1)
                rolecounts[pr][1] = max(0, rolecounts[pr][1] - 1)

            if overkill:
                # we tried killing more people than exist in a role, so deduct from amnesiac/clone count instead
                if var.CURRENT_GAMEMODE.name == "sleepy" and pr == "doomsayer":
                    rolecounts["seer"][0] = max(0, rolecounts["seer"][0] - 1)
                    rolecounts["seer"][1] = max(0, rolecounts["seer"][1] - 1)
                elif var.CURRENT_GAMEMODE.name == "sleepy" and pr == "demoniac":
                    rolecounts["cultist"][0] = max(0, rolecounts["cultist"][0] - 1)
                    rolecounts["cultist"][1] = max(0, rolecounts["cultist"][1] - 1)
                elif var.CURRENT_GAMEMODE.name == "sleepy" and pr == "succubus":
                    rolecounts["harlot"][0] = max(0, rolecounts["harlot"][0] - 1)
                    rolecounts["harlot"][1] = max(0, rolecounts["harlot"][1] - 1)
                elif pr == "clone":
                    # in this case, it means amnesiac became a clone (clone becoming amnesiac is impossible so we
                    # do not have the converse check in here - clones always inherit what amnesiac turns into).
                    equiv_sets["amnesiac_clone"] = max(0, equiv_sets["amnesiac_clone"] - 1)
                    equiv_sets["amnesiac_clone_cub"] = max(0, equiv_sets["amnesiac_clone_cub"] - 1)
                    rolecounts["amnesiac"][0] = max(0, rolecounts["amnesiac"][0] - 1)
                    rolecounts["amnesiac"][1] = max(0, rolecounts["amnesiac"][1] - 1)
                elif pr == "wolf":
                    # This could potentially be caused by a cub, not necessarily amnesiac/clone
                    # as such we use a different equiv_set to reflect this
                    maybe_cub = True
                    num_realwolves = sum([rolecounts[r][1] for r in var.WOLF_ROLES if r != "wolf cub"])
                    if rolecounts["wolf cub"][1] == 0 or num_realwolves > 0:
                        maybe_cub = False

                    if (var.HIDDEN_AMNESIAC or rolecounts["amnesiac"][1] == 0) and (var.HIDDEN_CLONE or rolecounts["clone"][1] == 0):
                        # guaranteed to be cub
                        equiv_sets["amnesiac_clone_cub"] = max(0, equiv_sets["amnesiac_clone_cub"] - 1)
                        rolecounts["wolf cub"][0] = max(0, rolecounts["wolf cub"][0] - 1)
                        rolecounts["wolf cub"][1] = max(0, rolecounts["wolf cub"][1] - 1)
                    elif (var.HIDDEN_CLONE or rolecounts["clone"][1] == 0) and not maybe_cub:
                        # guaranteed to be amnesiac
                        equiv_sets["amnesiac_clone"] = max(0, equiv_sets["amnesiac_clone"] - 1)
                        equiv_sets["amnesiac_clone_cub"] = max(0, equiv_sets["amnesiac_clone_cub"] - 1)
                        rolecounts["amnesiac"][0] = max(0, rolecounts["amnesiac"][0] - 1)
                        rolecounts["amnesiac"][1] = max(0, rolecounts["amnesiac"][1] - 1)
                    elif (var.HIDDEN_AMNESIAC or rolecounts["amnesiac"][1] == 0) and not maybe_cub:
                        # guaranteed to be clone
                        equiv_sets["amnesiac_clone"] = max(0, equiv_sets["amnesiac_clone"] - 1)
                        equiv_sets["amnesiac_clone_cub"] = max(0, equiv_sets["amnesiac_clone_cub"] - 1)
                        rolecounts["clone"][0] = max(0, rolecounts["clone"][0] - 1)
                        rolecounts["clone"][1] = max(0, rolecounts["clone"][1] - 1)
                    else:
                        # could be anything, how exciting!
                        if maybe_cub:
                            maxcount = max(0, equiv_sets["amnesiac_clone_cub"] - 1)
                        else:
                            maxcount = max(0, equiv_sets["amnesiac_clone"] - 1)

                        rolecounts["amnesiac"][0] = max(0, rolecounts["amnesiac"][0] - 1)
                        if rolecounts["amnesiac"][1] > maxcount:
                            rolecounts["amnesiac"][1] = maxcount

                        rolecounts["clone"][0] = max(0, rolecounts["clone"][0] - 1)
                        if rolecounts["clone"][1] > maxcount:
                            rolecounts["clone"][1] = maxcount

                        if maybe_cub:
                            rolecounts["wolf cub"][0] = max(0, rolecounts["wolf cub"][0] - 1)
                            if rolecounts["wolf cub"][1] > maxcount:
                                rolecounts["wolf cub"][1] = maxcount

                        if maybe_cub:
                            equiv_sets["amnesiac_clone_cub"] = maxcount
                            equiv_sets["amnesiac_clone"] = min(equiv_sets["amnesiac_clone"], maxcount)
                        else:
                            equiv_sets["amnesiac_clone"] = maxcount
                            equiv_sets["amnesiac_clone_cub"] = max(maxcount, equiv_sets["amnesiac_clone_cub"] - 1)

                elif not var.HIDDEN_AMNESIAC and (var.HIDDEN_CLONE or rolecounts["clone"][1] == 0):
                    # guaranteed to be amnesiac overkilling as clone reports as clone
                    equiv_sets["amnesiac_clone"] = max(0, equiv_sets["amnesiac_clone"] - 1)
                    equiv_sets["amnesiac_clone_cub"] = max(0, equiv_sets["amnesiac_clone_cub"] - 1)
                    rolecounts["amnesiac"][0] = max(0, rolecounts["amnesiac"][0] - 1)
                    rolecounts["amnesiac"][1] = max(0, rolecounts["amnesiac"][1] - 1)
                elif not var.HIDDEN_CLONE and (var.HIDDEN_AMNESIAC or rolecounts["amnesiac"][1] == 0):
                    # guaranteed to be clone overkilling as amnesiac reports as amnesiac
                    equiv_sets["amnesiac_clone"] = max(0, equiv_sets["amnesiac_clone"] - 1)
                    equiv_sets["amnesiac_clone_cub"] = max(0, equiv_sets["amnesiac_clone_cub"] - 1)
                    rolecounts["clone"][0] = max(0, rolecounts["clone"][0] - 1)
                    rolecounts["clone"][1] = max(0, rolecounts["clone"][1] - 1)
                else:
                    # could be either
                    maxcount = max(0, equiv_sets["amnesiac_clone"] - 1)

                    rolecounts["amnesiac"][0] = max(0, rolecounts["amnesiac"][0] - 1)
                    if rolecounts["amnesiac"][1] > maxcount:
                        rolecounts["amnesiac"][1] = maxcount

                    rolecounts["clone"][0] = max(0, rolecounts["clone"][0] - 1)
                    if rolecounts["clone"][1] > maxcount:
                        rolecounts["clone"][1] = maxcount

                    equiv_sets["amnesiac_clone"] = maxcount
                    equiv_sets["amnesiac_clone_cub"] = max(maxcount, equiv_sets["amnesiac_clone_cub"] - 1)
        # Step 5. Handle cub growing up. Bot does not send out a message for this, so we need
        # to puzzle it out ourselves. If there are no amnesiacs or clones
        # then we can deterministically figure out cubs growing up. Otherwise we don't know for
        # sure whether or not they grew up.
        num_realwolves = sum([rolecounts[r][1] for r in var.WOLF_ROLES if r != "wolf cub"])
        if num_realwolves == 0:
            # no wolves means cubs may have turned, set the min cub and max wolf appropriately
            rolecounts["wolf"][1] += rolecounts["wolf cub"][1]
            if rolecounts["amnesiac"][1] == 0 and rolecounts["clone"][1] == 0:
                # we know for sure they grew up
                rolecounts["wolf"][0] += rolecounts["wolf cub"][0]
                rolecounts["wolf cub"][1] = 0
            rolecounts["wolf cub"][0] = 0
        # Finally, combine all of our rolecounts into a message, with the default role last
        order = [r for r in role_order() if r in rolecounts]
        if var.DEFAULT_ROLE in order:
            order.remove(var.DEFAULT_ROLE)
        order.append(var.DEFAULT_ROLE)
        first = rolecounts[order[0]]
        if first[0] == first[1] == 1:
            vb = "is"
        else:
            vb = "are"

        for role in order:
            count = rolecounts[role]
            if count[0] == count[1]:
                if count[0] > 1 or count[0] == 0:
                    if count[0] == 0 and role not in start_roles:
                        continue
                    message.append("\u0002{0}\u0002 {1}".format(count[0] if count[0] else "\u0002no\u0002", plural(role)))
                else:
                    message.append("\u0002{0}\u0002 {1}".format(count[0], role))
            else:
                message.append("\u0002{0}-{1}\u0002 {2}".format(count[0], count[1], plural(role)))

    # Experimental replacement for default, not yet ready for prime-time
    # Uses events in order to enable roles to modify logic
    # The events are fired off as part of transition_day and del_player, and are not calculated here
    elif var.STATS_TYPE == "experimental":
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
            if r in var.TEMPLATE_RESTRICTIONS or len(v) == 0:
                continue
            start_roles.add(r)
        for r in start_roles:
            if r not in role_stats:
                role_stats[r] = (0, 0)
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
            count = role_stats[role]
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
            if role in var.TEMPLATE_RESTRICTIONS.keys():
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
            if role in var.TEMPLATE_RESTRICTIONS.keys():
                continue
            if role in var.WOLFTEAM_ROLES:
                wolfteam += len(players)
            elif role in var.TRUE_NEUTRAL_ROLES:
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

    pl = set(get_players()) - (var.WOUNDED | var.CONSECRATING)
    evt = Event("get_voters", {"voters": pl})
    evt.dispatch(var)
    pl = evt.data["voters"]
    not_lynching = set(var.NO_LYNCH)

    avail = len(pl)
    votesneeded = avail // 2 + 1

    with copy.deepcopy(var.VOTES) as votelist:
        # Note: this event can be differentiated between regular chk_decision
        # by checking evt.params.timeout.
        event = Event("chk_decision", {
            "not_lynching": not_lynching,
            "votelist": votelist,
            "numvotes": {}, # filled as part of a priority 1 event
            "weights": {}, # filled as part of a priority 1 event
            "transition_night": transition_night
            }, voters=pl, timeout=True)
        if not event.dispatch(var, None):
            return
        numvotes = event.data["numvotes"]

        found_dup = False
        maxfound = (0, "")
        for votee, voters in votelist.items():
            if numvotes[votee] > maxfound[0]:
                maxfound = (numvotes[votee], votee)
                found_dup = False
            elif numvotes[votee] == maxfound[0]:
                found_dup = True

    if maxfound[0] > 0 and not found_dup:
        channels.Main.send(messages["sunset_lynch"])
        chk_decision(force=maxfound[1])  # Induce a lynch
    else:
        channels.Main.send(messages["sunset"])
        event.data["transition_night"]()

@cmd("fnight", flag="N")
def fnight(cli, nick, chan, rest):
    """Forces the day to end and night to begin."""
    if var.PHASE != "day":
        cli.notice(nick, messages["not_daytime"])
    else:
        hurry_up(0, True)


@cmd("fday", flag="N")
def fday(cli, nick, chan, rest):
    """Forces the night to end and the next day to begin."""
    if var.PHASE != "night":
        cli.notice(nick, messages["not_nighttime"])
    else:
        transition_day()

# Specify force = user to force user to be lynched
def chk_decision(force=None, end_game=True, deadlist=None):
    if deadlist is None:
        deadlist = []
    with var.GRAVEYARD_LOCK:
        if var.PHASE != "day":
            return
        # Even if the lynch fails, we want to go to night phase if we are forcing a lynch (day timeout)
        do_night_transision = True if force else False
        pl = set(get_players()) - (var.WOUNDED | var.CONSECRATING)
        evt = Event("get_voters", {"voters": pl})
        evt.dispatch(var)
        pl = evt.data["voters"]
        not_lynching = set(var.NO_LYNCH)

        avail = len(pl)
        votesneeded = avail // 2 + 1

        with copy.deepcopy(var.VOTES) as votelist:

            event = Event("chk_decision", {
                "not_lynching": not_lynching,
                "votelist": votelist,
                "numvotes": {}, # filled as part of a priority 1 event
                "weights": {}, # filled as part of a priority 1 event
                "transition_night": transition_night
                }, voters=pl, timeout=False)
            if not event.dispatch(var, force):
                return

            numvotes = event.data["numvotes"]

            # we only need 50%+ to not lynch, instead of an actual majority, because a tie would time out day anyway
            # don't check for ABSTAIN_ENABLED here since we may have a case where the majority of people have pacifism totems or something
            if len(not_lynching) >= math.ceil(avail / 2):
                abs_evt = Event("chk_decision_abstain", {}, votelist=votelist, numvotes=numvotes)
                abs_evt.dispatch(var, not_lynching)
                channels.Main.send(messages["village_abstain"])
                var.ABSTAINED = True
                event.data["transition_night"]()
                return
            for votee, voters in votelist.items():
                if numvotes[votee] >= votesneeded or votee is force:
                    # priorities:
                    # 1 = displaying impatience totem messages
                    # 3 = mayor/revealing totem
                    # 4 = fool
                    # 5 = desperation totem, other things that happen on generic lynch
                    vote_evt = Event("chk_decision_lynch", {"votee": votee, "deadlist": deadlist},
                        del_player=del_player,
                        original_votee=votee,
                        force=(votee is force),
                        votelist=votelist,
                        not_lynching=not_lynching)
                    if vote_evt.dispatch(var, voters):
                        votee = vote_evt.data["votee"]
                        # roles that end the game upon being lynched
                        if votee in get_all_players(("fool",)):
                            # ends game immediately, with fool as only winner
                            # hardcode "fool" as the role since game is ending due to them being lynched,
                            # so we want to show "fool" even if it's a template
                            lmsg = random.choice(messages["lynch_reveal"]).format(votee, "", "fool")
                            channels.Main.send(lmsg)
                            if chk_win(winner="@" + votee.nick):
                                return
                        deadlist.append(votee)
                        # Other
                        if votee in get_all_players(("jester",)):
                            var.JESTERS.add(votee.nick)

                        if var.ROLE_REVEAL in ("on", "team"):
                            rrole = get_reveal_role(votee)
                            an = "n" if rrole.startswith(("a", "e", "i", "o", "u")) else ""
                            lmsg = random.choice(messages["lynch_reveal"]).format(votee, an, rrole)
                        else:
                            lmsg = random.choice(messages["lynch_no_reveal"]).format(votee)
                        channels.Main.send(lmsg)
                        if not del_player(votee, killer_role="villager", deadlist=deadlist, end_game=end_game):
                            return
                    do_night_transision = True
                    break
            if do_night_transision:
                event.data["transition_night"]()

@cmd("votes", pm=True, phases=("join", "day", "night"))
def show_votes(cli, nick, chan, rest):
    """Displays the voting statistics."""

    pl = list_players()
    if var.PHASE == "join":
        #get gamemode votes in a dict (key = mode, value = number of votes)
        gamemode_votes = {}
        for vote in var.GAMEMODE_VOTES.values():
            gamemode_votes[vote] = gamemode_votes.get(vote, 0) + 1

        votelist = []
        majority = False
        for gamemode,num_votes in sorted(gamemode_votes.items(), key=lambda x: x[1], reverse=True):
            #bold the game mode if: we have the right number of players, another game mode doesn't already have the majority, and this gamemode can be picked randomly or has the majority
            if (len(pl) >= var.GAME_MODES[gamemode][1] and len(pl) <= var.GAME_MODES[gamemode][2] and
               (not majority or num_votes >= len(pl)/2) and (var.GAME_MODES[gamemode][3] > 0 or num_votes >= len(pl)/2)):
                votelist.append("\u0002{0}\u0002: {1}".format(gamemode, num_votes))
                if num_votes >= len(pl)/2:
                    majority = True
            else:
                votelist.append("{0}: {1}".format(gamemode, num_votes))
        the_message = ", ".join(votelist)
        if len(pl) >= var.MIN_PLAYERS:
            the_message += messages["majority_votes"].format("; " if votelist else "", int(math.ceil(len(pl)/2)))

        with var.WARNING_LOCK:
            if var.START_VOTES:
                the_message += messages["start_votes"].format(len(var.START_VOTES), ", ".join(p.nick for p in var.START_VOTES))

    elif var.PHASE == "night":
        cli.notice(nick, messages["voting_daytime_only"])
        return
    else:
        if (chan != nick and var.LAST_VOTES and var.VOTES_RATE_LIMIT and
                var.LAST_VOTES + timedelta(seconds=var.VOTES_RATE_LIMIT) >
                datetime.now()):
            cli.notice(nick, messages["command_ratelimited"])
            return

        _nick = nick + ": "
        if chan == nick:
            _nick = ""

        if chan != nick and nick in pl:
            var.LAST_VOTES = datetime.now()

        if not var.VOTES.values():
            msg = _nick + messages["no_votes"]

            if nick in pl:
                var.LAST_VOTES = None  # reset
        else:
            votelist = ["{0}: {1} ({2})".format(votee,
                                             len(var.VOTES[votee]),
                                             " ".join(p.nick for p in var.VOTES[votee]))
                        for votee in var.VOTES.keys()]
            msg = "{0}{1}".format(_nick, ", ".join(votelist))

        reply(cli, nick, chan, msg)

        pl = set(get_players()) - (var.WOUNDED | var.CONSECRATING)
        evt = Event("get_voters", {"voters": pl})
        evt.dispatch(var)
        pl = evt.data["voters"]

        avail = len(pl)
        votesneeded = avail // 2 + 1
        not_voting = len(var.NO_LYNCH)
        if not_voting == 1:
            plural = " has"
        else:
            plural = "s have"
        the_message = messages["vote_stats"].format(_nick, len(list_players()), votesneeded, avail)
        if var.ABSTAIN_ENABLED:
            the_message += messages["vote_stats_abstain"].format(not_voting, plural)

    reply(cli, nick, chan, the_message)

def stop_game(var, winner="", abort=False, additional_winners=None, log=True):
    if abort:
        channels.Main.send(messages["role_attribution_failed"])
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
            splr = plr.nick # FIXME: for backwards-compat
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
                if rol in var.WOLFTEAM_ROLES or (var.DEFAULT_ROLE == "cultist" and role in var.HIDDEN_ROLES):
                    if winner == "wolves":
                        won = True
                        iwon = plr in survived
                elif rol not in var.TRUE_NEUTRAL_ROLES and winner == "villagers":
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

            # determine if this player's team won
            if rol in var.TRUE_NEUTRAL_ROLES:
                # most true neutral roles never have a team win, only individual wins. Exceptions to that are here
                teams = {"monster":"monsters", "demoniac":"demoniacs"}
                if rol in teams and winner == teams[rol]:
                    won = True
                elif rol == "turncoat" and splr in var.TURNCOATS and var.TURNCOATS[splr][0] != "none":
                    won = (winner == var.TURNCOATS[splr][0])
                elif rol == "fool" and "@" + splr == winner:
                    won = True

            if pentry["dced"]:
                # You get NOTHING! You LOSE! Good DAY, sir!
                won = False
                iwon = False
            elif rol == "fool" and "@" + splr == winner:
                iwon = True
            elif rol == "monster" and plr in survived and winner == "monsters":
                iwon = True
            elif rol == "demoniac" and plr in survived and winner == "demoniacs":
                iwon = True
            elif rol == "clone":
                # this means they ended game while being clone and not some other role
                if plr in survived and not winner.startswith("@") and singular(winner) not in var.WIN_STEALER_ROLES:
                    iwon = True
            elif rol == "jester" and splr in var.JESTERS:
                iwon = True
            elif not iwon:
                iwon = won and plr in survived  # survived, team won = individual win

            if winner == "":
                pentry["won"] = False
                pentry["iwon"] = False
            else:
                pentry["won"] = won
                pentry["iwon"] = iwon
                if won or iwon:
                    winners.add(plr.nick)

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

        # normalize fool wins; to determine which fool won look for who got a team win for the game
        # not plural (unlike other winner values) since only a singular fool wins
        if winner.startswith("@"):
            winner = "fool"

        db.add_game(var.CURRENT_GAMEMODE.name,
                    len(survived) + len(var.DEAD),
                    time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(var.GAME_ID)),
                    time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                    winner,
                    player_list,
                    game_options)

        # spit out the list of winners
        winners = sorted(winners)
        if len(winners) == 1:
            channels.Main.send(messages["single_winner"].format(winners[0]))
        elif len(winners) == 2:
            channels.Main.send(messages["two_winners"].format(winners[0], winners[1]))
        elif len(winners) > 2:
            nicklist = ("\u0002" + x + "\u0002" for x in winners[0:-1])
            channels.Main.send(messages["many_winners"].format(", ".join(nicklist), winners[-1]))

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

    return True

def chk_win(*, end_game=True, winner=None):
    """ Returns True if someone won """
    lpl = len(list_players())

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
            pl = set(get_players()) - (var.WOUNDED | var.CONSECRATING)
            evt = Event("get_voters", {"voters": pl})
            evt.dispatch(var)
            pl = evt.data["voters"]
            lpl = len(pl)
        else:
            pl = set(get_players(mainroles=mainroles))
            lpl = len(pl)

        if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
            if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
                wcroles = var.WOLF_ROLES
            else:
                wcroles = var.WOLF_ROLES | {"traitor"}
        else:
            wcroles = var.WOLFCHAT_ROLES

        wolves = set(get_players(wcroles, mainroles=mainroles))
        lwolves = len(wolves & pl)
        lcubs = len(rolemap.get("wolf cub", ()))
        lrealwolves = len(get_players(var.WOLF_ROLES - {"wolf cub"}, mainroles=mainroles))
        lmonsters = len(rolemap.get("monster", ()))
        ldemoniacs = len(rolemap.get("demoniac", ()))
        ltraitors = len(rolemap.get("traitor", ()))

        message = ""
        # fool won, chk_win was called from !lynch
        if winner and winner.startswith("@"):
            message = messages["fool_win"]
        elif lpl < 1:
            message = messages["no_win"]
            # still want people like jesters, dullahans, etc. to get wins if they fulfilled their win conds
            winner = "no_team_wins"
        elif lrealwolves == 0 and ltraitors == 0 and lcubs == 0:
            if ldemoniacs > 0:
                s = "s" if ldemoniacs > 1 else ""
                message = (messages["demoniac_win"]).format(s)
                winner = "demoniacs"
            elif lmonsters > 0:
                s = "s" if lmonsters > 1 else ""
                message = messages["monster_win"].format(s, "" if s else "s")
                winner = "monsters"
        elif lwolves == lpl / 2:
            if lmonsters > 0:
                s = "s" if lmonsters > 1 else ""
                message = messages["monster_wolf_win"].format(s)
                winner = "monsters"
        elif lwolves > lpl / 2:
            if lmonsters > 0:
                s = "s" if lmonsters > 1 else ""
                message = messages["monster_wolf_win"].format(s)
                winner = "monsters"

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

@handle_error
def del_player(player, *, devoice=True, end_game=True, death_triggers=True, killer_role="", deadlist=[], original=None, cmode=[], deadchat=[], ismain=True):
    """
    Returns: False if one side won.
    """

    def refresh_pl(old_pl):
        return set(p for p in get_players() if p in old_pl)

    t = time.time()  #  time

    var.LAST_STATS = None # reset
    var.LAST_VOTES = None

    if original is None:
        original = player

    with var.GRAVEYARD_LOCK:
        if not var.GAME_ID or var.GAME_ID > t:
            #  either game ended, or a new game has started.
            return False
        ret = True
        pl = set(get_players()).difference(deadlist)
        if player is not None and (player is original or player in pl):
            mainrole = get_main_role(player)
            revealrole = get_reveal_role(player)
            allroles = get_all_roles(player)
            del var.MAIN_ROLES[player]
            for r in allroles:
                var.ROLES[r].remove(player)
            if player.nick in var.BITTEN_ROLES:
                del var.BITTEN_ROLES[player.nick] # FIXME
            pl.discard(player)
            # handle roles that trigger on death
            # clone happens regardless of death_triggers being true or not
            if var.PHASE in var.GAME_PHASES:
                clones = get_all_players(("clone",))
                for clone in clones:
                    # clone is a User, var.CLONED is a Dict[str,str]
                    # dealist is a List[User]; ensure we add .nick appropriately
                    # FIXME: someone should convert var.CLONED
                    if clone.nick in var.CLONED and clone not in deadlist:
                        target = var.CLONED[clone.nick]
                        if player.nick == target and clone.nick in var.CLONED:
                            # clone is cloning nick, so clone becomes nick's role
                            # clone does NOT get any of nick's templates (gunner/assassin/etc.)
                            del var.CLONED[clone.nick]
                            if mainrole == "amnesiac":
                                from src.roles.amnesiac import ROLES
                                # clone gets the amnesiac's real role
                                sayrole = ROLES[player]
                            else:
                                sayrole = mainrole
                            change_role(clone, "clone", sayrole)
                            debuglog("{0} (clone) CLONE DEAD PLAYER: {1} ({2})".format(clone, target, sayrole))
                            if sayrole in var.HIDDEN_VILLAGERS:
                                sayrole = "villager"
                            elif sayrole in var.HIDDEN_ROLES:
                                sayrole = var.DEFAULT_ROLE
                            an = "n" if sayrole.startswith(("a", "e", "i", "o", "u")) else ""
                            clone.send(messages["clone_turn"].format(an, sayrole))
                            # if a clone is cloning a clone, clone who the old clone cloned
                            if mainrole == "clone" and player.nick in var.CLONED:
                                if var.CLONED[player.nick] == clone.nick:
                                    clone.send(messages["forever_aclone"].format(player))
                                else:
                                    var.CLONED[clone.nick] = var.CLONED[player.nick]
                                    clone.send(messages["clone_success"].format(var.CLONED[clone.nick]))
                                    # FIXME: change below to get_main_role(var.CLONED[clone]) once var.CLONED is converted
                                    debuglog("{0} (clone) CLONE: {1} ({2})".format(clone, var.CLONED[clone.nick], get_role(var.CLONED[clone.nick])))
                            elif mainrole in var.WOLFCHAT_ROLES:
                                wolves = get_players(var.WOLFCHAT_ROLES)
                                wolves.remove(clone) # remove self from list
                                for wolf in wolves:
                                    wolf.queue_message(messages["clone_wolf"].format(clone, player))
                                if wolves:
                                    wolf.send_messages()
                                if var.PHASE == "day":
                                    random.shuffle(wolves)
                                    for i, wolf in enumerate(wolves):
                                        wolfrole = get_main_role(wolf)
                                        wevt = Event("wolflist", {"tags": set()})
                                        wevt.dispatch(var, wolf, clone)
                                        tags = " ".join(wevt.data["tags"])
                                        if tags:
                                            tags += " "
                                        wolves[i] = "\u0002{0}\u0002 ({1}{2})".format(wolf, tags, wolfrole)

                                    if wolves:
                                        clone.send(messages["wolves_list"].format(wolves))
                                    else:
                                        clone.send(messages["no_other_wolves"])
                            elif mainrole == "turncoat":
                                var.TURNCOATS[clone.nick] = ("none", -1) # FIXME

                if mainrole == "clone" and player.nick in var.CLONED:
                    del var.CLONED[player.nick]

            pl = refresh_pl(pl)
            # i herd u liek parameters
            evt_death_triggers = death_triggers and var.PHASE in var.GAME_PHASES
            event = Event("del_player", {"pl": pl},
                    end_game=end_game,
                    deadlist=deadlist, original=original, killer_role=killer_role,
                    ismain=ismain, refresh_pl=refresh_pl, del_player=del_player)
            event.dispatch(var, player, mainrole, allroles, evt_death_triggers)

            # update var.ROLE_STATS
            # Event priorities:
            # 1 = Expanding the possible set (e.g. traitor would add themselves if nickrole is villager)
            # 3 = Removing from the possible set (e.g. can't be traitor if was a night kill and only wolves could kill at night),
            # 5 = Setting known_role to True if the role is actually known for sure publically (e.g. revealing totem)
            # 2 and 4 are not used by included roles, but may be useful expansion points for custom roles to modify stats
            event = Event("update_stats", {"possible": {mainrole, revealrole}, "known_role": False},
                    killer_role=killer_role, ismain=ismain)
            event.dispatch(var, player, mainrole, revealrole, allroles)
            # Given the set of possible roles this nick could be (or its actual role if known_role is True),
            # figure out the set of roles that need deducting from their counts in var.ROLE_STATS
            if event.data["known_role"]:
                # we somehow know the exact role that died (for example, we know traitor died even though they revealed as villager)
                # as a result, deduct only them
                possible = {mainrole}
            else:
                possible = set(event.data["possible"])
            newstats = set()
            # For every possible role this person is, try to deduct 1 from that role's count in our stat sets
            # if a stat set doesn't contain the role, then that would lead to an impossible condition and therefore
            # that set is not added to newstats to indicate that set is no longer possible
            # The reconfigure_stats event can be used to shift things around (for example, it is used to reflect wolf cub growing up)
            event = Event("reconfigure_stats", {})
            for p in possible:
                for rs in var.ROLE_STATS:
                    d = dict(rs)
                    if p in d and d[p] >= 1:
                        d[p] -= 1
                        event.dispatch(var, d)
                        if min(d.values()) >= 0:
                            newstats.add(frozenset(d.items()))
            var.ROLE_STATS = frozenset(newstats)

            if not player.is_fake:
                if devoice and (var.PHASE != "night" or not var.DEVOICE_DURING_NIGHT):
                    cmode.append(("-v", player.nick))
                lplayer = player.lower()
                if lplayer.account not in var.DEADCHAT_PREFS_ACCS and lplayer.host not in var.DEADCHAT_PREFS:
                    deadchat.append(player)
            # devoice all players that died as a result, if we are in the original del_player
            if ismain:
                channels.Main.mode(*cmode)
                del cmode[:]
            if var.PHASE == "join":
                if player.nick in var.GAMEMODE_VOTES:
                    del var.GAMEMODE_VOTES[player.nick]

                with var.WARNING_LOCK:
                    var.START_VOTES.discard(player)

                    # Cancel the start vote timer if there are no votes left
                    if not var.START_VOTES and "start_votes" in var.TIMERS:
                        var.TIMERS["start_votes"][0].cancel()
                        del var.TIMERS["start_votes"]

                # Died during the joining process as a person
                for mode in var.OLD_MODES[player]:
                    cmode.append(("+" + mode, player.nick))
                del var.OLD_MODES[player]
                var.ALL_PLAYERS.remove(player)
                ret = not chk_win()
            else:
                # Died during the game, so quiet!
                if var.QUIET_DEAD_PLAYERS and not player.is_fake:
                    cmode.append(("+{0}".format(var.QUIET_MODE), var.QUIET_PREFIX+player.nick+"!*@*"))
                var.DEAD.add(player.nick)
                ret = not chk_win(end_game=end_game)
            # only join to deadchat if the game isn't about to end
            if ismain:
                if ret:
                    join_deadchat(var, *deadchat)
                del deadchat[:]
            if var.PHASE in var.GAME_PHASES:
                # remove the player from variables if they're in there
                if ret:
                    for x in (var.OBSERVED, var.LASTHEXED):
                        for k in list(x):
                            if player.nick in (k, x[k]):
                                del x[k]
                    var.DISCONNECTED.pop(player, None)
            if var.PHASE == "night":
                # remove players from night variables
                # the dicts are handled above, these are the lists of who has acted which is used to determine whether night should end
                # if these aren't cleared properly night may end prematurely
                for x in (var.PASSED, var.HEXED, var.CURSED):
                    x.discard(player.nick)
            if var.PHASE == "day" and ret:
                if player in var.VOTES:
                    del var.VOTES[player] # Delete other people's votes on the player
                for k in list(var.VOTES.keys()):
                    if player in var.VOTES[k]:
                        var.VOTES[k].remove(player)
                        if not var.VOTES[k]:  # no more votes on that person
                            del var.VOTES[k]
                        break # can only vote once

                var.NO_LYNCH.discard(player)
                var.WOUNDED.discard(player)
                var.CONSECRATING.discard(player)
                # note: PHASE = "day" and GAMEPHASE = "night" during transition_day;
                # we only want to induce a lynch if it's actually day and we aren't in a chained death
                if var.GAMEPHASE == "day" and ismain and not end_game:
                    chk_decision()
            elif var.PHASE == "night" and ret and ismain:
                chk_nightdone()

        return ret

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
                    else:
                        cli.msg(chan, (messages["idle_death_no_reveal"]).format(nck))
                    user = users._get(nck) # FIXME
                    user.disconnected = True
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(user)
                    if var.IDLE_PENALTY:
                        add_warning(cli, nck, var.IDLE_PENALTY, users.Bot.nick, messages["idle_warning"], expires=var.IDLE_EXPIRY)
                    del_player(user, end_game=False, death_triggers=False)
                win = chk_win()
                if not win and var.PHASE == "day" and var.GAMEPHASE == "day":
                    chk_decision()
                pl = list_players()
                x = [a for a in to_warn if a in pl]
                if x:
                    cli.msg(chan, messages["channel_idle_warning"].format(", ".join(x)))
                msg_targets = [p for p in to_warn_pm if p in pl]
                mass_privmsg(cli, msg_targets, messages["player_idle_warning"].format(chan), privmsg=True)
            for dcedplayer, (timeofdc, what) in list(var.DISCONNECTED.items()):
                mainrole = get_main_role(dcedplayer)
                revealrole = get_reveal_role(dcedplayer)
                if what in ("quit", "badnick") and (datetime.now() - timeofdc) > timedelta(seconds=var.QUIT_GRACE_TIME):
                    if mainrole != "person" and var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["quit_death"].format(dcedplayer, revealrole))
                    else:
                        channels.Main.send(messages["quit_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.PART_PENALTY:
                        add_warning(cli, dcedplayer.nick, var.PART_PENALTY, users.Bot.nick, messages["quit_warning"], expires=var.PART_EXPIRY) # FIXME
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(dcedplayer)
                    if not del_player(dcedplayer, devoice=False, death_triggers=False):
                        return
                elif what == "part" and (datetime.now() - timeofdc) > timedelta(seconds=var.PART_GRACE_TIME):
                    if mainrole != "person" and var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["part_death"].format(dcedplayer, revealrole))
                    else:
                        channels.Main.send(messages["part_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.PART_PENALTY:
                        add_warning(cli, dcedplayer.nick, var.PART_PENALTY, users.Bot.nick, messages["part_warning"], expires=var.PART_EXPIRY) # FIXME
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(dcedplayer)
                    if not del_player(dcedplayer, devoice=False, death_triggers=False):
                        return
                elif what == "account" and (datetime.now() - timeofdc) > timedelta(seconds=var.ACC_GRACE_TIME):
                    if mainrole != "person" and var.ROLE_REVEAL in ("on", "team"):
                        channels.Main.send(messages["account_death"].format(dcedplayer, revealrole))
                    else:
                        channels.Main.send(messages["account_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.ACC_PENALTY:
                        add_warning(cli, dcedplayer.nick, var.ACC_PENALTY, users.Bot.nick, messages["acc_warning"], expires=var.ACC_EXPIRY) # FIXME
                    if var.PHASE in var.GAME_PHASES:
                        var.DCED_LOSERS.add(dcedplayer)
                    if not del_player(dcedplayer, devoice=False, death_triggers=False):
                        return
        time.sleep(10)

@cmd("")  # update last said
def update_last_said(cli, nick, chan, rest):
    if chan != botconfig.CHANNEL:
        return

    if var.PHASE not in ("join", "none"):
        var.LAST_SAID_TIME[nick] = datetime.now()

    fullstring = "".join(rest)

def dispatch_role_prefix(var, wrapper, message, *, role):
    from src import handler
    _ignore_locals_ = True
    handler.on_privmsg(wrapper.client, wrapper.source.rawnick, wrapper.target.name, message, force_role=role)

def setup_role_commands(evt):
    aliases = defaultdict(set)
    for alias, role in var.ROLE_ALIASES.items():
        aliases[role].add(alias)
    for role in var.ROLE_GUIDE.keys() - var.ROLE_COMMAND_EXCEPTIONS:
        keys = ["".join(c for c in role if c.isalpha())]
        keys.extend(aliases[role])
        fn = functools.partial(dispatch_role_prefix, role=role)
        fn.__doc__ = "Execute {0} command".format(role)
        # don't allow these in-channel, as it could be used to prove that someone is a particular role
        # (there are no examples of this right now, but it could be possible in the future). For example,
        # if !shoot was rewritten so that there was a "gunner" and "sharpshooter" template, one could
        # prove they are sharpshooter -- and therefore prove should they miss that the target is werekitten,
        # as opposed to the possiblity of them being a wolf with 1 bullet who stole the gun from a dead gunner --
        # by using !sharpshooter shoot target.
        command(*keys, exclusive=True, pm=True, chan=False, playing=True)(fn)

# event_listener decorator wraps callback in handle_error, which we don't want for the init event
# (as no IRC connection exists at this point)
events.add_listener("init", setup_role_commands, priority=10000)

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
    goatact = random.choice(messages["goat_actions"])
    wrapper.send(messages["goat_success"].format(wrapper.source, goatact, victim))

@command("fgoat", flag="j")
def fgoat(var, wrapper, message):
    """Forces a goat to interact with anyone or anything, without limitations."""

    nick = message.split(' ')[0].strip()
    victim, _ = users.complete_match(users.lower(nick), wrapper.target.users)
    if victim:
        togoat = victim
    else:
        togoat = message
    goatact = random.choice(messages["goat_actions"])

    wrapper.send(messages["goat_success"].format(wrapper.source, goatact, togoat))

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

            kvp = []
            # Looks like {'nick': [_, 'nick1', _, {'nick2': [_]}]}
            for a,b in var.PRAYED.items():
                kvp2 = []
                if a == prefix:
                    a = nick
                if b[1] == prefix:
                    b[1] = nick
                for c,d in b[3].items():
                    if c == prefix:
                        c = nick
                    kvp2.append((c,d))
                b[3].update(kvp2)
                kvp.append((a,b))
            var.PRAYED.update(kvp)
            if prefix in var.PRAYED.keys():
                del var.PRAYED[prefix]

            for dictvar in (var.OBSERVED, var.CLONED, var.LASTHEXED, var.BITE_PREFERENCES):
                kvp = []
                for a,b in dictvar.items():
                    if a == prefix:
                        a = nick
                    if b == prefix:
                        b = nick
                    kvp.append((a,b))
                dictvar.update(kvp)
                if prefix in dictvar.keys():
                    del dictvar[prefix]
            for dictvar in (var.FINAL_ROLES, var.TURNCOATS,
                            var.DOCTORS, var.BITTEN_ROLES, var.LYCAN_ROLES):
                if prefix in dictvar.keys():
                    dictvar[nick] = dictvar.pop(prefix)
            # defaultdict(list), where keys are nicks and items in list do not matter
            if prefix in var.ACTIVE_PROTECTIONS.keys():
                var.ACTIVE_PROTECTIONS[nick] = var.ACTIVE_PROTECTIONS.pop(prefix)
            for idx, tup in enumerate(var.EXCHANGED_ROLES):
                a, b = tup
                if a == prefix:
                    a = nick
                if b == prefix:
                    b = nick
                var.EXCHANGED_ROLES[idx] = (a, b)
            for setvar in (var.HEXED, var.SILENCED, var.PASSED,
                           var.JESTERS, var.LYCANTHROPES, var.LUCKY, var.DISEASED,
                           var.MISDIRECTED, var.EXCHANGED, var.IMMUNIZED, var.CURED_LYCANS,
                           var.ALPHA_WOLVES, var.CURSED, var.PRIESTS):
                if prefix in setvar:
                    setvar.remove(prefix)
                    setvar.add(nick)
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
                var.START_VOTES.clear()

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
        del_player(user, death_triggers=False)
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
        an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
        if var.DYNQUIT_DURING_GAME:
            lmsg = random.choice(messages["quit"]).format(wrapper.source.nick, an, role)
            channels.Main.send(lmsg)
        else:
            channels.Main.send((messages["static_quit"] + "{2}").format(wrapper.source.nick, role, population))
    else:
        # DYNQUIT_DURING_GAME should not have any effect during the join phase, so only check if we aren't in that
        if var.PHASE != "join" and not var.DYNQUIT_DURING_GAME:
            channels.Main.send((messages["static_quit_no_reveal"] + "{1}").format(wrapper.source.nick, population))
        else:
            lmsg = random.choice(messages["quit_no_reveal"]).format(wrapper.source.nick) + population
            channels.Main.send(lmsg)
    if var.PHASE != "join":
        var.DCED_LOSERS.add(wrapper.source)
        if var.LEAVE_PENALTY:
            add_warning(wrapper.client, wrapper.source.nick, var.LEAVE_PENALTY, users.Bot.nick, messages["leave_warning"], expires=var.LEAVE_EXPIRY) # FIXME
        if wrapper.source.nick in var.PLAYERS:
            var.DCED_PLAYERS[wrapper.source.nick] = var.PLAYERS.pop(wrapper.source.nick)

    del_player(wrapper.source, death_triggers=False)

def begin_day():
    # Reset nighttime variables
    var.GAMEPHASE = "day"
    var.KILLER = ""  # nickname of who chose the victim
    var.HEXED = set() # set of hags that have silenced others
    var.OBSERVED = {}  # those whom werecrows/sorcerers have observed
    var.PASSED = set() # set of certain roles that have opted not to act
    var.STARTED_DAY_PLAYERS = len(list_players())
    var.SILENCED = copy.copy(var.TOBESILENCED)
    var.EXCHANGED = set()
    var.LYCANTHROPES = set()
    var.LUCKY = set()
    var.DISEASED = set()
    var.MISDIRECTED = set()
    var.DYING.clear()
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
    chk_decision()

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

    if var.PHASE == "day":
        return

    var.PHASE = "day"
    var.DAY_COUNT += 1
    var.FIRST_DAY = (var.DAY_COUNT == 1)
    var.DAY_START_TIME = datetime.now()
    var.VOTES.clear()

    event_begin = Event("transition_day_begin", {})
    event_begin.dispatch(var)

    pl = get_players()

    if not var.START_WITH_DAY or not var.FIRST_DAY:
        if len(var.HEXED) < len(var.ROLES["hag"]):
            for hag in var.ROLES["hag"]:
                if hag.nick not in var.HEXED: # FIXME
                    var.LASTHEXED[hag.nick] = None # FIXME

        # NOTE: Random assassin selection is further down, since if we're choosing at random we pick someone
        # that isn't going to be dying today, meaning we need to know who is dying first :)

        if var.FIRST_NIGHT:
            # Select a random target for clone if they didn't choose someone
            for clone in get_all_players(("clone",)):
                if clone.nick not in var.CLONED:
                    ps = pl[:]
                    ps.remove(clone)
                    if len(ps) > 0:
                        target = random.choice(ps)
                        var.CLONED[clone.nick] = target.nick
                        clone.send(messages["random_clone"].format(target))

    # Reset daytime variables
    var.WOUNDED.clear()
    var.NO_LYNCH.clear()

    for crow, target in iter(var.OBSERVED.items()):
        if crow not in get_roles("werecrow"): # FIXME
            continue
        actor = users._get(crow) # FIXME
        user = users._get(target) # FIXME
        evt = Event("night_acted", {"acted": False})
        evt.dispatch(var, user, actor)
        if ((target in var.PRAYED and var.PRAYED[target][0] > 0) or
                target in var.OBSERVED or target in var.HEXED or target in var.CURSED or evt.data["acted"]):
            actor.send(messages["werecrow_success"].format(user))
        else:
            actor.send(messages["werecrow_failure"].format(user))

    if var.START_WITH_DAY and var.FIRST_DAY:
        # TODO: need to message everyone their roles and give a short thing saying "it's daytime"
        # but this is good enough for now to prevent it from crashing
        begin_day()
        return

    td = var.DAY_START_TIME - var.NIGHT_START_TIME
    var.NIGHT_START_TIME = None
    var.NIGHT_TIMEDELTA += td
    min, sec = td.seconds // 60, td.seconds % 60

    # this keeps track of the protections active on each nick, stored in var since del_player needs to access it for sake of assassin
    var.ACTIVE_PROTECTIONS = defaultdict(list)

    # built-in logic runs at the following priorities:
    # 1 = wolf kills
    # 2 = non-wolf kills
    # 3 = fixing killers dict to have correct priority (wolf-side VG kills -> non-wolf kills -> wolf kills)
    # 4 = protections/fallen angel
    #     4.1 = shaman, 4.2 = bodyguard/GA, 4.3 = blessed villager, 4.8 = fallen angel
    # 5 = alpha wolf bite, other custom events that trigger after all protection stuff is resolved
    # 6 = rearranging victim list (ensure bodyguard/harlot messages plays),
    #     fixing killers dict priority again (in case step 4 or 5 added to it)
    # 7 = killer-less deaths (i.e. var.DYING)
    # 8 = read-only operations
    # Actually killing off the victims happens in transition_day_resolve
    # We set the variables here first; listeners should mutate, not replace
    # We don't need to use User containers here, as these don't persist long enough
    # This removes the burden of having to clear them at the end or should an error happen
    victims = []
    killers = defaultdict(list)
    bywolves = set()
    onlybywolves = set()
    protected = {}
    bitten = []
    numkills = {}

    evt = Event("transition_day", {
        "victims": victims,
        "killers": killers,
        "bywolves": bywolves,
        "onlybywolves": onlybywolves,
        "protected": protected,
        "bitten": bitten,
        "numkills": numkills, # populated at priority 3
        })
    evt.dispatch(var)

    # remove duplicates
    victims_set = set(victims)
    vappend = []

    # set to True if we play chilling howl message due to a bitten person turning
    new_wolf = False
    if var.ALPHA_ENABLED: # check for bites
        for (alpha, target) in var.BITE_PREFERENCES.items():
            actor = users._get(alpha) # FIXME
            user = users._get(target) # FIXME
            # bite is now separate but some people may try to double up still, if bitten person is
            # also being killed by wolves, make the kill not apply
            # note that we cannot bite visiting harlots unless they are visiting a wolf,
            # and lycans/immunized people turn/die instead of being bitten, so keep the kills valid on those
            got_bit = False
            bite_evt = Event("bite", {
                "can_bite": True,
                "kill": user in var.ROLES["lycan"] or target in var.LYCANTHROPES or target in var.IMMUNIZED
                },
                victims=victims,
                killers=killers,
                bywolves=bywolves,
                onlybywolves=onlybywolves,
                protected=protected,
                bitten=bitten,
                numkills=numkills)
            bite_evt.dispatch(var, actor, user)
            if bite_evt.data["can_bite"] and not bite_evt.data["kill"]:
                # mark them as bitten
                got_bit = True
                # if they were also being killed by wolves, undo that
                if user in bywolves:
                    victims.remove(user)
                    bywolves.discard(user)
                    onlybywolves.discard(user)
                    killers[user].remove("@wolves")
                    if user not in victims:
                        victims_set.discard(user)

            if user in victims_set:
                # bite was unsuccessful due to someone else killing them
                var.ALPHA_WOLVES.remove(actor.nick)
            elif bite_evt.data["kill"]:
                # target immunized or a lycan, kill them instead and refund the bite
                var.ALPHA_WOLVES.remove(actor.nick)
                if var.ACTIVE_PROTECTIONS[user.nick]:
                    # target was protected
                    protected[user] = var.ACTIVE_PROTECTIONS[user.nick].pop(0)
                elif user in protected:
                    del protected[user]
                # add them as a kill even if protected so that protection message plays
                if user not in victims:
                    onlybywolves.add(user)
                killers[user].append(actor)
                victims.append(user)
                victims_set.add(user)
                bywolves.add(user)
            elif got_bit:
                new_wolf = True
                bitten.append(user)
            else:
                # bite failed due to some other reason (namely harlot)
                var.ALPHA_WOLVES.remove(actor.nick)

            to_send = "alpha_bite_failure"
            if actor.nick in var.ALPHA_WOLVES:
                to_send = "alpha_bite_success"
            actor.send(messages[to_send].format(user))


    var.BITE_PREFERENCES = {}
    victims.clear()
    # Ensures that special events play for bodyguard and harlot-visiting-victim so that kill can
    # be correctly attributed to wolves (for vengeful ghost lover), and that any gunner events
    # can play. Harlot visiting wolf doesn't play special events if they die via other means since
    # that assumes they die en route to the wolves (and thus don't shoot/give out gun/etc.)
    # TODO: this needs to be split off into angel.py, but all the stuff above it needs to be split off first
    # so even though angel.py exists we can't exactly do this now
    # TODO: also needs to be split off into harlot.py
    from src.roles import angel, harlot
    for v in victims_set:
        if v in var.DYING:
            victims.append(v)
        elif v in var.ROLES["bodyguard"] and v.nick in angel.GUARDED and users._get(angel.GUARDED[v.nick]) in victims_set: # FIXME
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
            if v in var.ROLES["bodyguard"] and users._get(angel.GUARDED.get(v.nick)) not in vappend: # FIXME
                vappend.remove(v)
                victims.append(v)
            elif harlot.VISITED.get(v) not in vappend:
                vappend.remove(v)
                victims.append(v)

    message = [messages["sunrise"].format(min, sec)]

    # This needs to go down here since having them be their night value matters above
    var.DISEASED_WOLVES = False
    var.ALPHA_ENABLED = False

    dead = []
    vlist = victims[:]
    novictmsg = True
    if new_wolf:
        message.append(messages["new_wolf"])
        var.EXTRA_WOLVES += 1
        novictmsg = False

    revt = Event("transition_day_resolve", {
        "message": message,
        "novictmsg": novictmsg,
        "dead": dead,
        "bywolves": bywolves,
        "onlybywolves": onlybywolves,
        "killers": killers,
        "protected": protected,
        "bitten": bitten
        })
    # transition_day_resolve priorities:
    # 1: target not home
    # 2: protection
    # 3: lycans
    # 6: riders on default logic
    # In general, an event listener < 6 should both stop propagation and prevent default
    # Priority 6 listeners add additional stuff to the default action and should not prevent default
    for victim in vlist:
        if not revt.dispatch(var, victim):
            continue
        if (victim in var.ROLES["lycan"] or victim.nick in var.LYCANTHROPES) and victim in revt.data["onlybywolves"] and victim.nick not in var.IMMUNIZED:
            vrole = get_main_role(victim)
            if vrole not in var.WOLFCHAT_ROLES:
                revt.data["message"].append(messages["new_wolf"])
                var.EXTRA_WOLVES += 1
                victim.send(messages["lycan_turn"])
                var.LYCAN_ROLES[victim.nick] = vrole
                change_role(victim, vrole, "wolf")
                var.ROLES["lycan"].discard(victim) # in the event lycan was a template, we want to ensure it gets purged
                wolves = get_players(var.WOLFCHAT_ROLES)
                random.shuffle(wolves)
                wolves.remove(victim)  # remove self from list
                to_send = []
                for wolf in wolves:
                    wolf.queue_message(messages["lycan_wc_notification"].format(victim))
                    role = get_main_role(wolf)
                    wevt = Event("wolflist", {"tags": set()})
                    wevt.dispatch(var, wolf, victim)
                    tags = " ".join(wevt.data["tags"])
                    if tags:
                        tags += " "
                    to_send.append("\u0002{0}\u0002 ({1}{2})".format(wolf, tags, role))

                if wolves:
                    wolf.send_messages()

                victim.send(messages["wolves_list"].format(", ".join(to_send)))
                revt.data["novictmsg"] = False
        elif victim not in revt.data["dead"]: # not already dead via some other means
            if var.ROLE_REVEAL in ("on", "team"):
                role = get_reveal_role(victim)
                an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                revt.data["message"].append(messages["death"].format(victim, an, role))
            else:
                revt.data["message"].append(messages["death_no_reveal"].format(victim))
            revt.data["dead"].append(victim)
            if random.random() < var.GIF_CHANCE:
                revt.data["message"].append(random.choice(
                    ["https://i.imgur.com/nO8rZ.gifv",
                    "https://i.imgur.com/uGVfZ.gifv",
                    "https://i.imgur.com/mUcM09n.gifv",
                    "https://i.imgur.com/P7TEGyQ.gifv",
                    "https://i.imgur.com/b8HAvjL.gifv",
                    "https://i.imgur.com/PIIfL15.gifv",
                    "https://i.imgur.com/eJiMG5z.gifv"]
                    ))

    # Priorities:
    # 1 = harlot/succubus visiting victim
    # 2 = determining whether or not we should print the "no victims" message
    # 3 = harlot visiting wolf
    # 4 = gunner shooting wolf
    # 5 = wolves killing diseased, wolves stealing gun
    # 10 = alpha wolf bite
    # Note that changing the "novictmsg" data item only makes sense for priority 1 events,
    # as after that point the message was already added. Events that could kill more people
    # should do so before priority 10. Events that require everyone that can be killed to
    # be listed as dead should be priority 10 or later.
    revt2 = Event("transition_day_resolve_end", {
        "message": revt.data["message"],
        "novictmsg": revt.data["novictmsg"],
        "dead": dead,
        "bywolves": bywolves,
        "onlybywolves": onlybywolves,
        "killers": killers,
        "protected": protected,
        "bitten": bitten
        })
    revt2.dispatch(var, victims)
    message = revt2.data["message"]
    novictmsg = revt2.data["novictmsg"]

    for victim in list(dead):
        if victim in var.GUNNERS and var.GUNNERS[victim] > 0 and victim in bywolves:
            if random.random() < var.GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE:
                # pick a random wofl to be shot
                woflset = {wolf for wolf in get_players(var.WOLF_ROLES) if wolf not in dead}
                # TODO: split into werekitten.py
                woflset.difference_update(get_all_players(("werekitten",)))
                wolf_evt = Event("gunner_overnight_kill_wolflist", {"wolves": woflset})
                wolf_evt.dispatch(var)
                woflset = wolf_evt.data["wolves"]
                if woflset:
                    deadwolf = random.choice(tuple(woflset))
                    if var.ROLE_REVEAL in ("on", "team"):
                        message.append(messages["gunner_killed_wolf_overnight"].format(victim, deadwolf, get_reveal_role(deadwolf)))
                    else:
                        message.append(messages["gunner_killed_wolf_overnight_no_reveal"].format(victim, deadwolf))
                    dead.append(deadwolf)
                    killers[deadwolf].append(victim)
                    var.GUNNERS[victim] -= 1 # deduct the used bullet

    for victim in dead:
        if victim in bywolves and victim in var.DISEASED:
            var.DISEASED_WOLVES = True
        if var.WOLF_STEALS_GUN and victim in bywolves and victim in var.GUNNERS and var.GUNNERS[victim] > 0:
            # victim has bullets
            try:
                looters = get_players(var.WOLFCHAT_ROLES)
                while len(looters) > 0:
                    guntaker = random.choice(looters)  # random looter
                    if guntaker not in dead:
                        break
                    else:
                        looters.remove(guntaker)
                if guntaker not in dead:
                    numbullets = var.GUNNERS[victim]
                    if guntaker.nick not in var.GUNNERS:
                        var.GUNNERS[guntaker] = 0
                    if guntaker not in get_all_players(("gunner", "sharpshooter")):
                        var.ROLES["gunner"].add(guntaker)
                    var.GUNNERS[guntaker] += 1  # only transfer one bullet
                    guntaker.send(messages["wolf_gunner"].format(victim))
            except IndexError:
                pass # no wolves to give gun to (they were all killed during night or something)
            var.GUNNERS[victim] = 0  # just in case

    channels.Main.send("\n".join(message))

    for chump in bitten:
        # turn all bitten people into wolves
        # short-circuit if they are already a wolf or are dying
        chumprole = get_main_role(chump)
        if chump in dead or chumprole in var.WOLF_ROLES:
            continue

        newrole = "wolf"
        if chumprole == "guardian angel":
            chump.send(messages["fallen_angel_turn"])
            # fallen angels also automatically gain the assassin template if they don't already have it
            newrole = "fallen angel"
            var.ROLES["assassin"].add(chump)
            debuglog("{0} (guardian angel) TURNED FALLEN ANGEL".format(chump))
        elif chumprole in ("seer", "oracle", "augur"):
            chump.send(messages["seer_turn"])
            newrole = "doomsayer"
            debuglog("{0} ({1}) TURNED DOOMSAYER".format(chump, chumprole))
        elif chumprole in var.TOTEM_ORDER:
            chump.send(messages["shaman_turn"])
            newrole = "wolf shaman"
            debuglog("{0} ({1}) TURNED WOLF SHAMAN".format(chump, chumprole))
        elif chumprole == "harlot":
            chump.send(messages["harlot_turn"])
            debuglog("{0} (harlot) TURNED WOLF".format(chump))
        else:
            chump.send(messages["bitten_turn"])
            debuglog("{0} ({1}) TURNED WOLF".format(chump, chumprole))
        var.BITTEN_ROLES[chump.nick] = chumprole
        change_role(chump, chumprole, newrole)
        relay_wolfchat_command(chump.client, chump.nick, messages["wolfchat_new_member"].format(chump, newrole), var.WOLF_ROLES, is_wolf_command=True, is_kill_command=True)

    killer_role = {}
    for deadperson in dead:
        if deadperson in killers:
            killer = killers[deadperson][0]
            if killer == "@wolves":
                killer_role[deadperson] = "wolf"
            else:
                killer_role[deadperson] = get_main_role(killer)
        else:
            # no killers, so assume suicide
            killer_role[deadperson] = get_main_role(deadperson)

    for deadperson in dead[:]:
        # check if they have already been killed since del_player could do chain reactions and we want
        # to avoid sending duplicate messages.
        if deadperson in get_players():
            del_player(deadperson, end_game=False, killer_role=killer_role[deadperson], deadlist=dead)

    event_end = Event("transition_day_end", {"begin_day": begin_day})
    event_end.dispatch(var)

    if chk_win():  # if after the last person is killed, one side wins, then actually end the game here
        return

    event_end.data["begin_day"]()

@event_listener("transition_day_resolve_end", priority=2)
def on_transition_day_resolve_end(evt, var, victims):
    if evt.data["novictmsg"] and len(evt.data["dead"]) == 0:
        evt.data["message"].append(random.choice(messages["no_victims"]) + messages["no_victims_append"])

def chk_nightdone():
    if var.PHASE != "night":
        return

    pl = get_players()
    spl = set(pl)
    actedcount = sum(map(len, (var.PASSED, var.OBSERVED, var.HEXED, var.CURSED)))

    nightroles = list(get_all_players(("sorcerer", "hag", "warlock", "werecrow", "prophet")))

    for nick, info in var.PRAYED.items():
        if info[0] > 0:
            actedcount += 1

    if var.FIRST_NIGHT:
        actedcount += len(var.CLONED.keys())
        nightroles.extend(get_all_players(("clone",)))

    if var.ALPHA_ENABLED:
        # alphas both kill and bite if they're activated at night, so add them into the counts
        nightroles.extend(get_all_players(("alpha wolf",)))
        actedcount += len([p for p in var.ALPHA_WOLVES if p in get_roles("alpha wolf")]) # FIXME

    # add in turncoats who should be able to act -- if they passed they're already in var.PASSED
    # but if they can act they're in var.TURNCOATS where the second tuple item is the current night
    # (if said tuple item is the previous night, then they are not allowed to act tonight)
    for tc, tu in var.TURNCOATS.items():
        user = users._get(tc) # FIXME
        if user not in pl:
            continue
        if tu[1] == var.NIGHT_COUNT:
            nightroles.append(user)
            actedcount += 1
        elif tu[1] < var.NIGHT_COUNT - 1:
            nightroles.append(user)

    event = Event("chk_nightdone", {"actedcount": actedcount, "nightroles": nightroles, "transition_day": transition_day})
    event.dispatch(var)
    actedcount = event.data["actedcount"]

    # remove all instances of them if they are silenced (makes implementing the event easier)
    nightroles = [p for p in nightroles if p.nick not in var.SILENCED]

    if var.PHASE == "night" and actedcount >= len(nightroles):
        for x, t in var.TIMERS.items():
            t[0].cancel()

        var.TIMERS = {}
        if var.PHASE == "night":  # Double check
            event.data["transition_day"]()

@command("nolynch", "nl", "novote", "nv", "abstain", "abs", playing=True, phases=("day",))
def no_lynch(var, wrapper, message):
    """Allows you to abstain from voting for the day."""
    evt = Event("abstain", {})
    if not var.ABSTAIN_ENABLED:
        wrapper.pm(messages["command_disabled"])
        return
    elif var.LIMIT_ABSTAIN and var.ABSTAINED:
        wrapper.pm(messages["exhausted_abstain"])
        return
    elif var.LIMIT_ABSTAIN and var.FIRST_DAY:
        wrapper.pm(messages["no_abstain_day_one"])
        return
    elif not evt.dispatch(var, wrapper.source):
        return
    elif wrapper.source in var.WOUNDED:
        channels.Main.send(messages["wounded_no_vote"].format(wrapper.source))
        return
    elif wrapper.source in var.CONSECRATING:
        wrapper.pm(messages["consecrating_no_vote"])
        return
    for voter in list(var.VOTES):
        if wrapper.source in var.VOTES[voter]:
            var.VOTES[voter].remove(wrapper.source)
            if not var.VOTES[voter]:
                del var.VOTES[voter]
    var.NO_LYNCH.add(wrapper.source)
    channels.Main.send(messages["player_abstain"].format(wrapper.source))

    chk_decision()

@command("lynch", playing=True, pm=True, phases=("day",))
def lynch(var, wrapper, message):
    """Use this to vote for a candidate to be lynched."""
    if not message:
        show_votes.caller(wrapper.client, wrapper.source.nick, wrapper.target.name, message)
        return
    if wrapper.private:
        return
    if wrapper.source in var.WOUNDED:
        wrapper.send(messages["wounded_no_vote"].format(wrapper.source))
        return
    if wrapper.source in var.CONSECRATING:
        wrapper.pm(messages["consecrating_no_vote"])
        return

    msg = re.split(" +", message)[0].strip()

    troll = False
    if ((var.CURRENT_GAMEMODE.name == "default" or var.CURRENT_GAMEMODE.name == "villagergame")
            and var.VILLAGERGAME_CHANCE > 0 and len(var.ALL_PLAYERS) <= 9):
        troll = True

    no_vote_self = "save_self"
    if wrapper.source in get_all_players(("fool", "jester")):
        no_vote_self = "no_self_lynch"

    voted = get_target(var, wrapper, msg, allow_self=var.SELF_LYNCH_ALLOWED, allow_bot=troll, not_self_message=no_vote_self)
    if not voted:
        return

    evt = Event("lynch", {"target": voted})
    if not evt.dispatch(var, wrapper.source):
        return
    voted = evt.data["target"]

    var.NO_LYNCH.discard(wrapper.source)

    lcandidates = list(var.VOTES.keys())
    for voters in lcandidates:  # remove previous vote
        if voters is voted and wrapper.source in var.VOTES[voters]:
            break
        if wrapper.source in var.VOTES[voters]:
            var.VOTES[voters].remove(wrapper.source)
            if not var.VOTES.get(voters) and voters is not voted:
                del var.VOTES[voters]
            break

    if voted not in var.VOTES:
        var.VOTES[voted] = UserList()
    if wrapper.source not in var.VOTES[voted]:
        var.VOTES[voted].append(wrapper.source)
        channels.Main.send(messages["player_vote"].format(wrapper.source, voted))

    var.LAST_VOTES = None # reset

    chk_decision()

# chooses a target given nick, taking luck totem/misdirection totem into effect
# returns the actual target
def choose_target(actor, nick):
    pl = list_players()
    if actor in var.MISDIRECTED:
        for i, user in enumerate(var.ALL_PLAYERS):
            if user.nick == nick:
                break
        if random.randint(0, 1) == 0:
            # going left
            while True:
                i -= 1
                if var.ALL_PLAYERS[i].nick in pl:
                    nick = var.ALL_PLAYERS[i].nick
                    break
        else:
            # going right
            while True:
                i += 1
                if i >= len(var.ALL_PLAYERS):
                    i = 0
                if var.ALL_PLAYERS[i].nick in pl:
                    nick = var.ALL_PLAYERS[i].nick
                    break
    if nick in var.LUCKY:
        for i, user in enumerate(var.ALL_PLAYERS):
            if user.nick == nick:
                break
        if random.randint(0, 1) == 0:
            # going left
            while True:
                i -= 1
                if var.ALL_PLAYERS[i].nick in pl:
                    nick = var.ALL_PLAYERS[i].nick
                    break
        else:
            # going right
            while True:
                i += 1
                if i >= len(var.ALL_PLAYERS):
                    i = 0
                if var.ALL_PLAYERS[i].nick in pl:
                    nick = var.ALL_PLAYERS[i].nick
                    break
    return nick

# returns true if a swap happened
# check for that to short-circuit the nightrole
def check_exchange(cli, actor, nick):
    #some roles can act on themselves, ignore this
    if actor == nick:
        return False

    user = users._get(actor) # FIXME
    target = users._get(nick) # FIXME

    if nick in var.EXCHANGED:
        var.EXCHANGED.remove(nick)
        actor_role = get_role(actor)
        nick_role = get_role(nick)

        # var.PASSED is used by many roles
        var.PASSED.discard(actor)

        if actor_role == "clone":
            if actor in var.CLONED:
                actor_target = var.CLONED.pop(actor)
        elif actor_role in ("werecrow", "sorcerer"):
            if actor in var.OBSERVED:
                del var.OBSERVED[actor]
        elif actor_role == "hag":
            if actor in var.LASTHEXED:
                if var.LASTHEXED[actor] in var.TOBESILENCED and actor in var.HEXED:
                    var.TOBESILENCED.remove(var.LASTHEXED[actor])
                del var.LASTHEXED[actor]
            var.HEXED.discard(actor)
        elif actor_role == "doctor":
            if nick_role == "doctor":
                var.DOCTORS[actor], var.DOCTORS[nick] = var.DOCTORS[nick], var.DOCTORS[actor]
            else:
                var.DOCTORS[nick] = var.DOCTORS.pop(actor)
        elif actor_role == "alpha wolf":
            var.ALPHA_WOLVES.discard(actor)
        elif actor_role == "warlock":
            var.CURSED.discard(actor)
        elif actor_role == "turncoat":
            del var.TURNCOATS[actor]


        # var.PASSED is used by many roles
        var.PASSED.discard(nick)

        if nick_role == "clone":
            if nick in var.CLONED:
                nick_target = var.CLONED.pop(nick)
        elif nick_role in ("werecrow", "sorcerer"):
            if nick in var.OBSERVED:
                del var.OBSERVED[nick]
        elif nick_role == "hag":
            if nick in var.LASTHEXED:
                if var.LASTHEXED[nick] in var.TOBESILENCED and nick in var.HEXED:
                    var.TOBESILENCED.remove(var.LASTHEXED[nick])
                del var.LASTHEXED[nick]
            var.HEXED.discard(nick)
        elif nick_role == "doctor":
            # Both being doctors is handled above
            if actor_role != "doctor":
                var.DOCTORS[actor] = var.DOCTORS.pop(nick)
        elif nick_role == "alpha wolf":
            var.ALPHA_WOLVES.discard(nick)
        elif nick_role == "warlock":
            var.CURSED.discard(nick)
        elif nick_role == "turncoat":
            del var.TURNCOATS[nick]

        evt = Event("exchange_roles", {"actor_messages": [], "target_messages": [], "actor_role": actor_role, "target_role": nick_role})
        evt.dispatch(var, user, target, actor_role, nick_role)

        actor_role = evt.data["actor_role"]
        nick_role = evt.data["target_role"]

        change_role(user, actor_role, nick_role)
        change_role(target, nick_role, actor_role)
        if actor in var.BITTEN_ROLES.keys():
            if nick in var.BITTEN_ROLES.keys():
                var.BITTEN_ROLES[actor], var.BITTEN_ROLES[nick] = var.BITTEN_ROLES[nick], var.BITTEN_ROLES[actor]
            else:
                var.BITTEN_ROLES[nick] = var.BITTEN_ROLES[actor]
                del var.BITTEN_ROLES[actor]
        elif nick in var.BITTEN_ROLES.keys():
            var.BITTEN_ROLES[actor] = var.BITTEN_ROLES[nick]
            del var.BITTEN_ROLES[nick]

        if actor in var.LYCAN_ROLES.keys():
            if nick in var.LYCAN_ROLES.keys():
                var.LYCAN_ROLES[actor], var.LYCAN_ROLES[nick] = var.LYCAN_ROLES[nick], var.LYCAN_ROLES[actor]
            else:
                var.LYCAN_ROLES[nick] = var.LYCAN_ROLES[actor]
                del var.LYCAN_ROLES[actor]
        elif nick in var.LYCAN_ROLES.keys():
            var.LYCAN_ROLES[actor] = var.LYCAN_ROLES[nick]
            del var.LYCAN_ROLES[nick]

        actor_rev_role = actor_role
        if actor_role in var.HIDDEN_ROLES:
            actor_rev_role = var.DEFAULT_ROLE
        elif actor_role in var.HIDDEN_VILLAGERS:
            actor_rev_role = "villager"

        nick_rev_role = nick_role
        if nick_role in var.HIDDEN_ROLES:
            nick_rev_role = var.DEFAULT_ROLE
        elif actor_role in var.HIDDEN_VILLAGERS:
            nick_rev_role = "villager"

        # don't say who, since misdirection/luck totem may have switched it
        # and this makes life far more interesting
        user.send(messages["role_swap"].format(nick_rev_role))
        target.send(messages["role_swap"].format(actor_rev_role))
        user.send(*evt.data["actor_messages"])
        target.send(*evt.data["target_messages"])

        wcroles = var.WOLFCHAT_ROLES
        if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
            if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
                wcroles = var.WOLF_ROLES
            else:
                wcroles = var.WOLF_ROLES | {"traitor"}

        if nick_role == "clone":
            pm(cli, actor, messages["clone_target"].format(nick_target))
        elif nick_role not in wcroles and nick_role == "warlock":
            # this means warlock isn't in wolfchat, so only give cursed list
            pl = list_players()
            random.shuffle(pl)
            pl.remove(actor)  # remove self from list
            for i, player in enumerate(pl):
                if player in get_roles("cursed villager"): # FIXME
                    pl[i] = player + " (cursed)"
            pm(cli, actor, messages["players_list"].format(", ".join(pl)))
        elif nick_role == "turncoat":
            var.TURNCOATS[actor] = ("none", -1)

        if actor_role == "clone":
            pm(cli, nick, messages["clone_target"].format(actor_target))
        elif actor_role not in wcroles and actor_role == "warlock":
            # this means warlock isn't in wolfchat, so only give cursed list
            pl = list_players()
            random.shuffle(pl)
            pl.remove(nick)  # remove self from list
            for i, player in enumerate(pl):
                if player in get_roles("cursed villager"): # FIXME
                    pl[i] = player + " (cursed)"
            pm(cli, nick, messages["players_list"].format(", ".join(pl)))
        elif actor_role == "turncoat":
            var.TURNCOATS[nick] = ("none", -1)

        var.EXCHANGED_ROLES.append((actor, nick))
        return True
    return False

@command("retract", "r", phases=("day", "join"))
def retract(var, wrapper, message):
    """Takes back your vote during the day (for whom to lynch)."""
    if wrapper.source not in get_players() or wrapper.source in var.DISCONNECTED:
        return

    with var.GRAVEYARD_LOCK, var.WARNING_LOCK:
        if var.PHASE == "join":
            if not wrapper.source in var.START_VOTES:
                wrapper.pm(messages["start_novote"])
            else:
                var.START_VOTES.discard(wrapper.source)
                wrapper.send(messages["start_retract"].format(wrapper.source))

                if len(var.START_VOTES) < 1:
                    var.TIMERS["start_votes"][0].cancel()
                    del var.TIMERS["start_votes"]

    if var.PHASE != "day":
        return
    if wrapper.source in var.NO_LYNCH:
        var.NO_LYNCH.remove(wrapper.source)
        wrapper.send(messages["retracted_vote"].format(wrapper.source))
        var.LAST_VOTES = None # reset
        return

    for voter in list(var.VOTES):
        if wrapper.source in var.VOTES[voter]:
            var.VOTES[voter].remove(wrapper.source)
            if not var.VOTES[voter]:
                del var.VOTES[voter]
            wrapper.send(messages["retracted_vote"].format(wrapper.source))
            var.LAST_VOTES = None # reset
            break
    else:
        wrapper.pm(messages["pending_vote"])

@command("shoot", playing=True, silenced=True, phases=("day",))
def shoot(var, wrapper, message):
    """Use this to fire off a bullet at someone in the day if you have bullets."""
    if wrapper.source not in var.GUNNERS.keys():
        wrapper.pm(messages["no_gun"])
        return
    elif not var.GUNNERS.get(wrapper.source):
        wrapper.pm(messages["no_bullets"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="gunner_target_self")
    if not target:
        return

    # get actual victim
    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    if not evt.dispatch(var, wrapper.source, target):
        return

    target = evt.data["target"]

    wolfshooter = wrapper.source in get_players(var.WOLFCHAT_ROLES)
    var.GUNNERS[wrapper.source] -= 1

    rand = random.random()
    if wrapper.source in var.ROLES["village drunk"]:
        chances = var.DRUNK_GUN_CHANCES
    elif wrapper.source in var.ROLES["sharpshooter"]:
        chances = var.SHARPSHOOTER_GUN_CHANCES
    else:
        chances = var.GUN_CHANCES

    # TODO: make this into an event once we split off gunner
    if target in get_all_players(("succubus",)):
        chances = chances[:3] + (0,)

    wolfvictim = target in get_players(var.WOLF_ROLES)
    realrole = get_main_role(target)
    targrole = get_reveal_role(target)

    alwaysmiss = (realrole == "werekitten")

    if rand <= chances[0] and not (wolfshooter and wolfvictim) and not alwaysmiss:
        # didn't miss or suicide and it's not a wolf shooting another wolf

        wrapper.send(messages["shoot_success"].format(wrapper.source, target))
        an = "n" if targrole.startswith(("a", "e", "i", "o", "u")) else ""
        if realrole in var.WOLF_ROLES:
            if var.ROLE_REVEAL == "on":
                wrapper.send(messages["gunner_victim_wolf_death"].format(target, an, targrole))
            else: # off and team
                wrapper.send(messages["gunner_victim_wolf_death_no_reveal"].format(target))
            if not del_player(target, killer_role=get_main_role(wrapper.source)):
                return
        elif random.random() <= chances[3]:
            accident = "accidentally "
            if wrapper.source in var.ROLES["sharpshooter"]:
                accident = "" # it's an accident if the sharpshooter DOESN'T headshot :P
            wrapper.send(messages["gunner_victim_villager_death"].format(target, accident))
            if var.ROLE_REVEAL in ("on", "team"):
                wrapper.send(messages["gunner_victim_role"].format(an, targrole))
            if not del_player(target, killer_role=get_main_role(wrapper.source)):
                return
        else:
            wrapper.send(messages["gunner_victim_injured"].format(target))
            var.WOUNDED.add(target)
            lcandidates = list(var.VOTES.keys())
            for cand in lcandidates:  # remove previous vote
                if target in var.VOTES[cand]:
                    var.VOTES[cand].remove(target)
                    if not var.VOTES.get(cand):
                        del var.VOTES[cand]
                    break
            chk_decision()
            chk_win()

    elif rand <= chances[0] + chances[1]:
        wrapper.send(messages["gunner_miss"].format(wrapper.source))
    else:
        if var.ROLE_REVEAL in ("on", "team"):
            wrapper.send(messages["gunner_suicide"].format(wrapper.source, get_reveal_role(wrapper.source)))
        else:
            wrapper.send(messages["gunner_suicide_no_reveal"].format(wrapper.source))
        del_player(wrapper.source, killer_role="villager") # blame explosion on villager's shoddy gun construction or something

@cmd("bless", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("priest",))
def bless(cli, nick, chan, rest):
    """Bless a player, preventing them from being killed for the remainder of the game."""
    if nick in var.PRIESTS:
        pm(cli, nick, messages["already_blessed"])
        return

    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if victim == nick:
        pm(cli, nick, messages["no_bless_self"])
        return

    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return

    var.PRIESTS.add(nick)
    var.ROLES["blessed villager"].add(users._get(victim)) # FIXME
    pm(cli, nick, messages["blessed_success"].format(victim))
    pm(cli, victim, messages["blessed_notify_target"])
    debuglog("{0} ({1}) BLESS: {2} ({3})".format(nick, get_role(nick), victim, get_role(victim)))

@cmd("consecrate", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("priest",))
def consecrate(cli, nick, chan, rest):
    """Consecrates a corpse, putting its spirit to rest and preventing other unpleasant things from happening."""
    alive = list_players()
    victim = re.split(" +", rest)[0]
    if not victim:
        pm(cli, nick, messages["not_enough_parameters"])
        return
    dead = [x.nick for x in var.ALL_PLAYERS if x.nick not in alive]
    deadl = [x.lower() for x in dead]

    tempvictim = complete_one_match(victim.lower(), deadl)
    if not tempvictim:
        pm(cli, nick, messages["consecrate_fail"].format(victim))
        return
    victim = dead[deadl.index(tempvictim)] #convert back to normal casing

    # we have a target, so mark them as consecrated, right now all this does is silence a VG for a night
    # but other roles that do stuff after death or impact dead players should have functionality here as well
    # (for example, if there was a role that could raise corpses as undead somethings, this would prevent that from working)
    # regardless if this has any actual effect or not, it still removes the priest from being able to vote
    from src.roles import vengefulghost
    if users._get(victim) in vengefulghost.GHOSTS:
        var.SILENCED.add(victim)

    var.CONSECRATING.add(users._get(nick)) # FIXME
    pm(cli, nick, messages["consecrate_success"].format(victim))
    debuglog("{0} ({1}) CONSECRATE: {2}".format(nick, get_role(nick), victim))
    # consecrating can possibly cause game to end, so check for that
    chk_win()

@cmd("observe", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("werecrow", "sorcerer"))
def observe(cli, nick, chan, rest):
    """Observe a player to obtain various information."""
    role = get_role(nick)
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if victim == nick:
        if role == "werecrow":
            pm(cli, nick, messages["werecrow_no_observe_self"])
        else:
            pm(cli, nick, messages["no_observe_self"])
        return
    if nick in var.OBSERVED.keys():
        if role == "werecrow":
            pm(cli, nick, messages["werecrow_already_observing"].format(var.OBSERVED[nick]))
        else:
            pm(cli, nick, messages["already_observed"])
        return
    if in_wolflist(nick, victim):
        if role == "werecrow":
            pm(cli, nick, messages["werecrow_no_target_wolf"])
        else:
            pm(cli, nick, messages["no_observe_wolf"])
        return
    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return
    var.OBSERVED[nick] = victim
    if role == "werecrow":
        pm(cli, nick, messages["werecrow_observe_success"].format(victim))
        relay_wolfchat_command(cli, nick, messages["wolfchat_observe"].format(nick, victim), ("werecrow",), is_wolf_command=True)

    elif role == "sorcerer":
        vrole = get_role(victim)
        if vrole == "amnesiac":
            from src.roles.amnesiac import ROLES
            vrole = ROLES[users._get(victim)] # FIXME
        if vrole in ("seer", "oracle", "augur", "sorcerer"):
            an = "n" if vrole.startswith(("a", "e", "i", "o", "u")) else ""
            pm(cli, nick, (messages["sorcerer_success"]).format(victim, an, vrole))
        else:
            pm(cli, nick, messages["sorcerer_fail"].format(victim))
        relay_wolfchat_command(cli, nick, messages["sorcerer_success_wolfchat"].format(nick, victim), ("sorcerer"))

    debuglog("{0} ({1}) OBSERVE: {2} ({3})".format(nick, role, victim, get_role(victim)))

@cmd("pray", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("prophet",))
def pray(cli, nick, chan, rest):
    """Receive divine visions of who has a role."""
    # this command may be used multiple times in the course of the night, however it only needs
    # to be used once to count towards ending night (additional uses don't count extra)
    if nick in var.PRAYED and var.PRAYED[nick][0] == 2:
        pm(cli, nick, messages["already_prayed"])
        return
    elif nick not in var.PRAYED:
        # [number of times prayed tonight, current target, target role, {target: [roles]}]
        var.PRAYED[nick] = [0, None, None, defaultdict(set)]

    if var.PRAYED[nick][0] == 0:
        what = re.split(" +", rest)[0]
        if not what:
            pm(cli, nick, messages["not_enough_parameters"])
            return
        # complete this as a match with other roles (so "cursed" can match "cursed villager" for instance)
        role = complete_one_match(what.lower(), var.ROLE_GUIDE.keys())
        if role is None:
            if what.lower() in var.ROLE_ALIASES:
                role = var.ROLE_ALIASES[what.lower()]
            else:
                # typo, let them fix it
                pm(cli, nick, messages["specific_invalid_role"].format(what))
                return

        # get a list of all roles actually in the game, including roles that amnesiacs will be turning into
        # (amnesiacs are special since they're also listed as amnesiac; that way a prophet can see both who the
        # amnesiacs themselves are as well as what they'll become)
        pl = list_players()
        from src.roles.amnesiac import ROLES
        valid_roles = {r for r, p in var.ROLES.items() if p} | {r for p, r in ROLES.items() if p.nick in pl} # FIXME

        if role in valid_roles:
            # this sees through amnesiac, so the amnesiac's final role counts as their role
            # also, if we're the only person with that role, say so and don't allow a second vision
            people = set(get_roles(role)) | {p.nick for p, r in ROLES.items() if p.nick in pl and r == role} # FIXME
            if len(people) == 1 and nick in people:
                pm(cli, nick, messages["vision_only_role_self"].format(role))
                var.PRAYED[nick][0] = 2
                debuglog("{0} ({1}) PRAY {2} - ONLY".format(nick, get_role(nick), role))
                return
            # select someone with the role that we haven't looked at before for this particular role
            prevlist = (p for p, rl in var.PRAYED[nick][3].items() if role in rl)
            for p in prevlist:
                people.discard(p)
            if len(people) == 0 or (len(people) == 1 and nick in people):
                pm(cli, nick, messages["vision_no_more_role"].format(plural(role)))
                var.PRAYED[nick][0] = 2
                debuglog("{0} ({1}) PRAY {2} - NO OTHER".format(nick, get_role(nick), role))
                return
            target = random.choice(list(people))
            var.PRAYED[nick][0] = 1
            var.PRAYED[nick][1] = target
            var.PRAYED[nick][2] = role
            var.PRAYED[nick][3][target].add(role)
            half = random.sample(pl, math.ceil(len(pl) / 2))
            if target not in half:
                half[0] = target
            random.shuffle(half)
            # if prophet never reveals, there is no point making them pray twice,
            # so just give them the player the first time around
            if len(half) > 1 and (var.PROPHET_REVEALED_CHANCE[0] > 0 or var.PROPHET_REVEALED_CHANCE[1] > 0):
                msg = messages["vision_players"].format(role)
                if len(half) > 2:
                    msg += "{0}, and {1}.".format(", ".join(half[:-1]), half[-1])
                else:
                    msg += "{0} and {1}.".format(half[0], half[1])
                pm(cli, nick, msg)
                debuglog("{0} ({1}) PRAY {2} ({3}) - HALF".format(nick, get_role(nick), role, target))
                if random.random() < var.PROPHET_REVEALED_CHANCE[0]:
                    pm(cli, target, messages["vision_prophet"].format(nick))
                    debuglog("{0} ({1}) PRAY REVEAL".format(nick, get_role(nick), role))
                    var.PRAYED[nick][0] = 2
            else:
                # only one, go straight to second chance
                var.PRAYED[nick][0] = 2
                pm(cli, nick, messages["vision_role"].format(target, role))
                debuglog("{0} ({1}) PRAY {2} ({3}) - FULL".format(nick, get_role(nick), role, target))
                if random.random() < var.PROPHET_REVEALED_CHANCE[1]:
                    pm(cli, target, messages["vision_prophet"].format(nick))
                    debuglog("{0} ({1}) PRAY REVEAL".format(nick, get_role(nick)))
        else:
            # role is not in this game, this still counts as a successful activation of the power!
            pm(cli, nick, messages["vision_none"].format(plural(role)))
            debuglog("{0} ({1}) PRAY {2} - NONE".format(nick, get_role(nick), role))
            var.PRAYED[nick][0] = 2
    elif var.PRAYED[nick][1] is None:
        # the previous vision revealed the prophet, so they cannot receive any more visions tonight
        pm(cli, nick, messages["vision_recovering"])
        return
    else:
        # continuing a praying session from this night to obtain more information, give them the actual person
        var.PRAYED[nick][0] = 2
        target = var.PRAYED[nick][1]
        role = var.PRAYED[nick][2]
        pm(cli, nick, messages["vision_role"].format(target, role))
        debuglog("{0} ({1}) PRAY {2} ({3}) - FULL".format(nick, get_role(nick), role, target))
        if random.random() < var.PROPHET_REVEALED_CHANCE[1]:
            pm(cli, target, messages["vision_prophet"].format(nick))
            debuglog("{0} ({1}) PRAY REVEAL".format(nick, get_role(nick)))

@cmd("give", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("doctor",))
@cmd("immunize", "immunise", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("doctor",))
def immunize(cli, nick, chan, rest):
    """Immunize a player, preventing them from turning into a wolf."""
    if nick not in var.DOCTORS: # something with amnesiac or clone or exchange totem
        var.DOCTORS[nick] = math.ceil(var.DOCTOR_IMMUNIZATION_MULTIPLIER * len(var.ALL_PLAYERS))
    if not var.DOCTORS.get(nick):
        pm(cli, nick, messages["doctor_fail"])
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, True)
    if not victim:
        return
    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return
    evt = Event("doctor_immunize", {"success": True, "message": "villager_immunized"})
    if evt.dispatch(var, nick, victim):
        pm(cli, nick, messages["doctor_success"].format(victim))
        lycan = False
        if victim in var.DISEASED:
            var.DISEASED.remove(victim)
        if victim in get_roles("lycan"): # FIXME
            lycan = True
            lycan_message = (messages["lycan_cured"])
            if get_role(victim) == "lycan":
                change_role(users._get(victim), "lycan", "villager") # FIXME
            else:
                var.ROLES["lycan"].remove(users._get(victim)) # FIXME
            var.CURED_LYCANS.add(victim)
        else:
            lycan_message = messages[evt.data["message"]]
        pm(cli, victim, (messages["immunization_success"]).format(lycan_message))
    if evt.data["success"]:
        var.IMMUNIZED.add(victim)
        var.DOCTORS[nick] -= 1
    debuglog("{0} (doctor) IMMUNIZE: {1} ({2})".format(nick, victim, "lycan" if lycan else get_role(victim)))

@cmd("bite", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("alpha wolf",))
def bite_cmd(cli, nick, chan, rest):
    """Bite a player, turning them into a wolf."""
    if nick in var.ALPHA_WOLVES and nick not in var.BITE_PREFERENCES:
        pm(cli, nick, messages["alpha_already_bit"])
        return
    if not var.ALPHA_ENABLED:
        pm(cli, nick, messages["alpha_no_bite"])
        return

    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, False)

    if not victim:
        pm(cli, nick, messages["bite_error"])
        return

    vrole = get_role(victim)
    actual = choose_target(nick, victim)

    if in_wolflist(nick, victim):
        pm(cli, nick,  messages["alpha_no_bite_wolf"])
        return
    if check_exchange(cli, nick, actual):
        return

    var.ALPHA_WOLVES.add(nick)
    var.BITE_PREFERENCES[nick] = actual

    pm(cli, nick, messages["alpha_bite_target"].format(victim))
    relay_wolfchat_command(cli, nick, messages["alpha_bite_wolfchat"].format(nick, victim), ("alpha wolf",), is_wolf_command=True)
    debuglog("{0} ({1}) BITE: {2} ({3})".format(nick, get_role(nick), actual, get_role(actual)))

@cmd("pass", chan=False, pm=True, playing=True, phases=("night",), roles=("turncoat", "warlock"))
def pass_cmd(cli, nick, chan, rest):
    """Decline to use your special power for that night."""
    nickrole = get_role(nick)

    # turncoats can change roles and pass even if silenced
    if nickrole != "turncoat" and nick in var.SILENCED:
        if chan == nick:
            pm(cli, nick, messages["silenced"])
        else:
            cli.notice(nick, messages["silenced"])
        return

    if nickrole == "turncoat":
        if var.TURNCOATS[nick][1] == var.NIGHT_COUNT:
            # theoretically passing would revert them to how they were before, but
            # we aren't tracking that, so just tell them to change it back themselves.
            pm(cli, nick, messages["turncoat_fail"])
            return
        pm(cli, nick, messages["turncoat_pass"])
        if var.TURNCOATS[nick][1] == var.NIGHT_COUNT - 1:
            # don't add to var.PASSED since we aren't counting them anyway for nightdone
            # let them still use !pass though to make them feel better or something
            return
        var.PASSED.add(nick)
    elif nickrole == "warlock":
        if nick in var.CURSED:
            pm(cli, nick, messages["already_cursed"])
            return
        pm(cli, nick, messages["warlock_pass"])
        relay_wolfchat_command(cli, nick, messages["warlock_pass_wolfchat"].format(nick), ("warlock",))
        var.PASSED.add(nick)

    debuglog("{0} ({1}) PASS".format(nick, get_role(nick)))

@cmd("side", chan=False, pm=True, playing=True, phases=("night",), roles=("turncoat",))
def change_sides(cli, nick, chan, rest, sendmsg=True):
    if var.TURNCOATS[nick][1] == var.NIGHT_COUNT - 1:
        pm(cli, nick, messages["turncoat_already_turned"])
        return

    team = re.split(" +", rest)[0]
    team = complete_one_match(team, ("villagers", "wolves"))
    if not team:
        pm(cli, nick, messages["turncoat_error"])
        return

    pm(cli, nick, messages["turncoat_success"].format(team))
    var.TURNCOATS[nick] = (team, var.NIGHT_COUNT)
    debuglog("{0} ({1}) SIDE {2}".format(nick, get_role(nick), team))

@cmd("hex", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hag",))
def hex_target(cli, nick, chan, rest):
    """Hex someone, preventing them from acting the next day and night."""
    if nick in var.HEXED:
        pm(cli, nick, messages["already_hexed"])
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if nick == victim:
        pm(cli, nick, messages["no_target_self"])
        return
    if var.LASTHEXED.get(nick) == victim:
        pm(cli, nick, messages["no_multiple_hex"].format(victim))
        return

    victim = choose_target(nick, victim)
    if in_wolflist(nick, victim):
        pm(cli, nick, messages["no_hex_wolf"])
        return
    if check_exchange(cli, nick, victim):
        return

    vrole = get_role(victim)
    var.HEXED.add(nick)
    var.LASTHEXED[nick] = victim
    wroles = var.WOLF_ROLES
    if not var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
        wroles = var.WOLF_ROLES | {"traitor"}
    if vrole not in wroles:
        var.TOBESILENCED.add(victim)

    pm(cli, nick, messages["hex_success"].format(victim))
    relay_wolfchat_command(cli, nick, messages["hex_success_wolfchat"].format(nick, victim), ("hag",))

    debuglog("{0} ({1}) HEX: {2} ({3})".format(nick, get_role(nick), victim, get_role(victim)))

@cmd("curse", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def curse(cli, nick, chan, rest):
    if nick in var.CURSED:
        # CONSIDER: this happens even if they choose to not curse, should maybe let them
        # pick again in that case instead of locking them into doing nothing.
        pm(cli, nick, messages["already_cursed"])
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return
    # There may actually be valid strategy in cursing other wolfteam members,
    # but for now it is not allowed. If someone seems suspicious and shows as
    # villager across multiple nights, safes can use that as a tell that the
    # person is likely wolf-aligned.
    if victim in get_roles("cursed villager"): # FIXME
        pm(cli, nick, messages["target_already_cursed"].format(victim))
        return

    if in_wolflist(nick, victim):
        pm(cli, nick, messages["no_curse_wolf"])
        return

    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return

    var.CURSED.add(nick)
    var.PASSED.discard(nick)
    vrole = get_role(victim)
    wroles = var.WOLF_ROLES
    if not var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
        wroles = var.WOLF_ROLES | {"traitor"}
    if vrole not in wroles:
        var.ROLES["cursed villager"].add(users._get(victim)) # FIXME

    pm(cli, nick, messages["curse_success"].format(victim))
    relay_wolfchat_command(cli, nick, messages["curse_success_wolfchat"].format(nick, victim), ("warlock",))

    debuglog("{0} ({1}) CURSE: {2} ({3})".format(nick, get_role(nick), victim, vrole))

@cmd("clone", chan=False, pm=True, playing=True, phases=("night",), roles=("clone",))
def clone(cli, nick, chan, rest):
    """Clone another player. You will turn into their role if they die."""
    if not var.FIRST_NIGHT:
        return
    if nick in var.CLONED.keys():
        pm(cli, nick, messages["already_cloned"])
        return

    params = re.split(" +", rest)
    # allow for role-prefixed command such as !clone clone target
    # if we get !clone clone (with no 3rd arg), we give preference to prefixed version;
    # meaning if the person wants to clone someone named clone, they must type !clone clone clone
    # (or just !clone clon, !clone clo, etc. assuming thos would be unambiguous matches)
    if params[0] == "clone":
        if len(params) > 1:
           del params[0]
        else:
            pm(cli, nick, messages["clone_clone_clone"])
            return

    # no var.SILENCED check for night 1 only roles; silence should only apply for the night after
    # but just in case, it also sucks if the one night you're allowed to act is when you are
    # silenced, so we ignore it here anyway.

    victim = get_victim(cli, nick, params[0], False)
    if not victim:
        return

    if nick == victim:
        pm(cli, nick, messages["no_target_self"])
        return

    var.CLONED[nick] = victim
    pm(cli, nick, messages["clone_target_success"].format(victim))

    debuglog("{0} ({1}) CLONE: {2} ({3})".format(nick, get_role(nick), victim, get_role(victim)))

var.ROLE_COMMAND_EXCEPTIONS.add("clone")

@event_listener("targeted_command", priority=9)
def on_targeted_command(evt, var, actor, orig_target):
    if evt.data["misdirection"]:
        evt.data["target"] = users._get(choose_target(actor.nick, evt.data["target"].nick)) # FIXME

    if evt.data["exchange"] and check_exchange(actor.client, actor.nick, evt.data["target"].nick):
        evt.stop_processing = True
        evt.prevent_default = True

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

    badguys = get_players(var.WOLFCHAT_ROLES)
    wolves = get_players(var.WOLF_ROLES)

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
        to_msg = set(u.nick for u in badguys) # FIXME: replace mass_privmsg with something user-aware below
        if message.startswith("\u0001ACTION"):
            message = message[7:-1]
            mass_privmsg(wrapper.client, to_msg, "* \u0002{0}\u0002{1}".format(wrapper.source, message))
            for player in var.SPECTATING_WOLFCHAT:
                player.queue_message("* [wolfchat] \u0002{0}\u0002{1}".format(wrapper.source, message))
            if var.SPECTATING_WOLFCHAT:
                player.send_messages()
        else:
            mass_privmsg(wrapper.client, to_msg, "\u0002{0}\u0002 says: {1}".format(wrapper.source, message))
            for player in var.SPECTATING_WOLFCHAT:
                player.queue_message("[wolfchat] \u0002{0}\u0002 says: {1}".format(wrapper.source, message))
            if var.SPECTATING_WOLFCHAT:
                player.send_messages()

@handle_error
def transition_night():
    if var.PHASE == "night":
        return
    var.PHASE = "night"
    var.GAMEPHASE = "night"

    var.NIGHT_START_TIME = datetime.now()
    var.NIGHT_COUNT += 1
    var.FIRST_NIGHT = (var.NIGHT_COUNT == 1)

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
    var.HEXED = set() # set of hags that have hexed
    var.CURSED = set() # set of warlocks that have cursed
    var.PASSED = set()
    var.OBSERVED = {}  # those whom werecrows have observed
    var.TOBESILENCED = set()
    var.CONSECRATING.clear()
    for nick in var.PRAYED:
        var.PRAYED[nick][0] = 0
        var.PRAYED[nick][1] = None
        var.PRAYED[nick][2] = None

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

    if var.FIRST_NIGHT and chk_win(end_game=False): # prevent game from ending as soon as it begins (useful for the random game mode)
        start(channels.Main.client, users.Bot.nick, channels.Main.name, restart=var.CURRENT_GAMEMODE.name)
        return

    # game ended from bitten / amnesiac turning, narcolepsy totem expiring, or other weirdness
    if chk_win():
        return

    # send PMs
    ps = get_players()

    for pht in get_all_players(("prophet",)):
        chance1 = math.floor(var.PROPHET_REVEALED_CHANCE[0] * 100)
        chance2 = math.floor(var.PROPHET_REVEALED_CHANCE[1] * 100)
        an1 = "n" if chance1 >= 80 and chance1 < 90 else ""
        an2 = "n" if chance2 >= 80 and chance2 < 90 else ""
        if pht.prefers_simple():
            pht.send(messages["prophet_simple"])
        else:
            if chance1 > 0:
                pht.send(messages["prophet_notify_both"].format(an1, chance1, an2, chance2))
            elif chance2 > 0:
                pht.send(messages["prophet_notify_second"].format(an2, chance2))
            else:
                pht.send(messages["prophet_notify_none"])

    for drunk in get_all_players(("village drunk",)):
        if drunk.prefers_simple():
            drunk.send(messages["drunk_simple"])
        else:
            drunk.send(messages["drunk_notification"])

    for doctor in get_all_players(("doctor",)):
        if doctor.nick in var.DOCTORS and var.DOCTORS[doctor.nick] > 0: # has immunizations remaining
            pl = ps[:]
            random.shuffle(pl)
            if doctor.prefers_simple():
                doctor.send(messages["doctor_simple"])
            else:
                doctor.send(messages["doctor_notify"])
            doctor.send(messages["doctor_immunizations"].format(var.DOCTORS[doctor.nick], 's' if var.DOCTORS[doctor.nick] > 1 else ''))

    for fool in get_all_players(("fool",)):
        if fool.prefers_simple():
            fool.send(messages["fool_simple"])
        else:
            fool.send(messages["fool_notify"])

    for jester in get_all_players(("jester",)):
        if jester.prefers_simple():
            jester.send(messages["jester_simple"])
        else:
            jester.send(messages["jester_notify"])

    for monster in get_all_players(("monster",)):
        if monster.prefers_simple():
            monster.send(messages["monster_simple"])
        else:
            monster.send(messages["monster_notify"])

    for demoniac in get_all_players(("demoniac",)):
        if demoniac.prefers_simple():
            demoniac.send(messages["demoniac_simple"])
        else:
            demoniac.send(messages["demoniac_notify"])


    for lycan in get_all_players(("lycan",)):
        if lycan.prefers_simple():
            lycan.send(messages["lycan_simple"])
        else:
            lycan.send(messages["lycan_notify"])

    for turncoat in get_all_players(("turncoat",)):
        # they start out as unsided, but can change n1
        if turncoat.nick not in var.TURNCOATS:
            var.TURNCOATS[turncoat.nick] = ("none", -1)

        if turncoat.prefers_simple():
            turncoat.send(messages["turncoat_simple"].format(var.TURNCOATS[turncoat.nick][0]))
        else:
            message = messages["turncoat_notify"]
            if var.TURNCOATS[turncoat.nick][0] != "none":
                message += messages["turncoat_current_team"].format(var.TURNCOATS[turncoat.nick][0])
            else:
                message += messages["turncoat_no_team"]
            turncoat.send(message)

    for priest in get_all_players(("priest",)):
        if priest.prefers_simple():
            priest.send(messages["priest_simple"])
        else:
            priest.send(messages["priest_notify"])

    if var.FIRST_NIGHT or var.ALWAYS_PM_ROLE:
        for clone in get_all_players(("clone",)):
            pl = ps[:]
            random.shuffle(pl)
            pl.remove(clone)
            if clone.prefers_simple():
                clone.send(messages["clone_simple"])
            else:
                clone.send(messages["clone_notify"])
            clone.send(messages["players_list"].format(", ".join(p.nick for p in pl)))

    for g in var.GUNNERS:
        if g not in ps:
            continue
        elif not var.GUNNERS[g]:
            continue
        elif var.GUNNERS[g] == 0:
            continue
        role = "gunner"
        if g in get_all_players(("sharpshooter",)):
            role = "sharpshooter"
        if g.prefers_simple():
            gun_msg = messages["gunner_simple"].format(role, str(var.GUNNERS[g]), "s" if var.GUNNERS[g] > 1 else "")
        else:
            if role == "gunner":
                gun_msg = messages["gunner_notify"].format(role, botconfig.CMD_CHAR, str(var.GUNNERS[g]), "s" if var.GUNNERS[g] > 1 else "")
            elif role == "sharpshooter":
                gun_msg = messages["sharpshooter_notify"].format(role, botconfig.CMD_CHAR, str(var.GUNNERS[g]), "s" if var.GUNNERS[g] > 1 else "")

        g.send(gun_msg)

    event_end = Event("transition_night_end", {})
    event_end.dispatch(var)

    dmsg = (daydur_msg + messages["night_begin"])

    if not var.FIRST_NIGHT:
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
        md = modeargs.pop(0)
        try:
            if md == "default" and len(var.ALL_PLAYERS) <= 9 and random.random() < var.VILLAGERGAME_CHANCE:
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

@handle_error
def expire_start_votes(cli, chan):
    # Should never happen as the timer is removed on game start, but just to be safe
    if var.PHASE != 'join':
        return

    with var.WARNING_LOCK:
        var.START_VOTES.clear()
        cli.msg(chan, messages["start_expired"])

@cmd("start", phases=("none", "join"))
def start_cmd(cli, nick, chan, rest):
    """Starts a game of Werewolf."""
    start(cli, nick, chan)

def start(cli, nick, chan, forced = False, restart = ""):
    if (not forced and var.LAST_START and nick in var.LAST_START and
            var.LAST_START[nick][0] + timedelta(seconds=var.START_RATE_LIMIT) >
            datetime.now() and not restart):
        var.LAST_START[nick][1] += 1
        cli.notice(nick, messages["command_ratelimited"])
        return

    if restart:
        var.RESTART_TRIES += 1
    if var.RESTART_TRIES > 3:
        stop_game(var, abort=True)
        return

    if not restart:
        var.LAST_START[nick] = [datetime.now(), 1]

    if chan != botconfig.CHANNEL:
        return

    villagers = list_players()
    vils = set(get_players())
    pl = villagers[:]

    if not restart:
        if var.PHASE == "none":
            cli.notice(nick, messages["no_game_running"].format(botconfig.CMD_CHAR))
            return
        if var.PHASE != "join":
            cli.notice(nick, messages["werewolf_already_running"])
            return
        if nick not in villagers and nick != chan and not forced:
            return

        now = datetime.now()
        var.GAME_START_TIME = now  # Only used for the idler checker
        dur = int((var.CAN_START_TIME - now).total_seconds())
        if dur > 0 and not forced:
            plural = "" if dur == 1 else "s"
            cli.msg(chan, messages["please_wait"].format(dur, plural))
            return

        if len(villagers) < var.MIN_PLAYERS:
            cli.msg(chan, messages["not_enough_players"].format(nick, var.MIN_PLAYERS))
            return

        if len(villagers) > var.MAX_PLAYERS:
            cli.msg(chan, messages["max_players"].format(nick, var.MAX_PLAYERS))
            return

        with var.WARNING_LOCK:
            user = users._get(nick) # FIXME
            if not forced and user in var.START_VOTES:
                user.send(messages["start_already_voted"], notice=True)
                return

            start_votes_required = min(math.ceil(len(villagers) * var.START_VOTES_SCALE), var.START_VOTES_MAX)
            if not forced and len(var.START_VOTES) < start_votes_required:
                # If there's only one more vote required, start the game immediately.
                # Checked here to make sure that a player that has already voted can't
                # vote again for the final start.
                if len(var.START_VOTES) < start_votes_required - 1:
                    var.START_VOTES.add(user)
                    msg = messages["start_voted"]
                    remaining_votes = start_votes_required - len(var.START_VOTES)

                    if remaining_votes == 1:
                        cli.msg(chan, msg.format(nick, remaining_votes, 'vote'))
                    else:
                        cli.msg(chan, msg.format(nick, remaining_votes, 'votes'))

                    # If this was the first vote
                    if len(var.START_VOTES) == 1:
                        t = threading.Timer(60, expire_start_votes, (cli, chan))
                        var.TIMERS["start_votes"] = (t, time.time(), 60)
                        t.daemon = True
                        t.start()
                    return

        if not var.FGAMED:
            votes = {} #key = gamemode, not hostmask
            for gamemode in var.GAMEMODE_VOTES.values():
                if len(villagers) >= var.GAME_MODES[gamemode][1] and len(villagers) <= var.GAME_MODES[gamemode][2]:
                    votes[gamemode] = votes.get(gamemode, 0) + 1
            voted = [gamemode for gamemode in votes if votes[gamemode] == max(votes.values()) and votes[gamemode] >= len(villagers)/2]
            if len(voted):
                cgamemode(random.choice(voted))
            else:
                possiblegamemodes = []
                for gamemode in var.GAME_MODES.keys() - var.DISABLED_GAMEMODES:
                    if len(villagers) >= var.GAME_MODES[gamemode][1] and len(villagers) <= var.GAME_MODES[gamemode][2] and var.GAME_MODES[gamemode][3] > 0:
                        possiblegamemodes += [gamemode]*(var.GAME_MODES[gamemode][3]+votes.get(gamemode, 0)*15)
                cgamemode(random.choice(possiblegamemodes))

    else:
        cgamemode(restart)
        var.GAME_ID = time.time() # restart reaper timer

    addroles = {}

    event = Event("role_attribution", {"addroles": addroles})
    if event.dispatch(var, chk_win_conditions, villagers):
        addroles = event.data["addroles"]
        for index in range(len(var.ROLE_INDEX) - 1, -1, -1):
            if var.ROLE_INDEX[index] <= len(villagers):
                for role, num in var.ROLE_GUIDE.items(): # allow event to override some roles
                    addroles[role] = max(addroles.get(role, num[index]), len(var.FORCE_ROLES.get(role, ())))
                break
        else:
            cli.msg(chan, messages["no_settings_defined"].format(nick, len(villagers)))
            return

        if sum([addroles[r] for r in addroles if r not in var.TEMPLATE_RESTRICTIONS]) > len(villagers):
            channels.Main.send(messages["too_many_roles"])
            return

    possible_rolesets = []
    roleset_roles = defaultdict(int)
    for rs, amt in var.ROLE_SETS:
        toadd = random.sample(list(rs.elements()), amt)
        for r in toadd:
            addroles[r] += 1
            roleset_roles[r] += 1
        add_rolesets = []
        temp_rolesets = []
        for c in itertools.combinations(rs.elements(), amt):
            add_rolesets.append(Counter(c))
        for pr in possible_rolesets:
            for ar in add_rolesets:
                temp = Counter(pr)
                temp.update(ar)
                temp_rolesets.append(temp)
        possible_rolesets = temp_rolesets
    if not possible_rolesets:
        # if there are no randomized roles, ensure that we have 1 element
        # to account for the only possibility (all role counts known)
        possible_rolesets.append(Counter())

    if var.ORIGINAL_SETTINGS and not restart:  # Custom settings
        need_reset = True
        wvs = sum(addroles[r] for r in var.WOLFCHAT_ROLES)
        if len(villagers) < (sum(addroles.values()) - sum(addroles[r] for r in var.TEMPLATE_RESTRICTIONS.keys())):
            cli.msg(chan, messages["too_few_players_custom"])
        elif not wvs and var.CURRENT_GAMEMODE.name != "villagergame":
            cli.msg(chan, messages["need_one_wolf"])
        elif wvs > (len(villagers) / 2):
            cli.msg(chan, messages["too_many_wolves"])
        elif set(addroles) != set(var.ROLE_GUIDE):
            cli.msg(chan, messages["error_role_players_count"])
        else:
            need_reset = False

        if need_reset:
            reset_settings()
            cli.msg(chan, messages["default_reset"].format(botconfig.CMD_CHAR))
            var.PHASE = "join"
            return

    if var.ADMIN_TO_PING is not None and not restart:
        for decor in (COMMANDS["join"] + COMMANDS["start"]):
            decor(_command_disabled)

    var.ROLES.clear()
    var.ROLES[var.DEFAULT_ROLE] = UserSet()
    var.MAIN_ROLES.clear()
    var.GUNNERS.clear()
    var.OBSERVED = {}
    var.CLONED = {}
    var.LASTHEXED = {}
    var.SILENCED = set()
    var.TOBESILENCED = set()
    var.JESTERS = set()
    var.NIGHT_COUNT = 0
    var.DAY_COUNT = 0
    var.DISEASED_WOLVES = False
    var.TRAITOR_TURNED = False
    var.FINAL_ROLES = {}
    var.LYCANTHROPES = set()
    var.LUCKY = set()
    var.DISEASED = set()
    var.MISDIRECTED = set()
    var.EXCHANGED = set()
    var.HEXED = set()
    var.ABSTAINED = False
    var.DOCTORS = {}
    var.IMMUNIZED = set()
    var.CURED_LYCANS = set()
    var.ALPHA_WOLVES = set()
    var.ALPHA_ENABLED = False
    var.BITE_PREFERENCES = {}
    var.BITTEN_ROLES = {}
    var.LYCAN_ROLES = {}
    var.ACTIVE_PROTECTIONS = defaultdict(list)
    var.TURNCOATS = {}
    var.EXCHANGED_ROLES = []
    var.EXTRA_WOLVES = 0
    var.PRIESTS = set()
    var.CONSECRATING.clear()
    var.DYING.clear()
    var.PRAYED = {}

    var.DEADCHAT_PLAYERS.clear()
    var.SPECTATING_WOLFCHAT.clear()
    var.SPECTATING_DEADCHAT.clear()

    for role, ps in var.FORCE_ROLES.items():
        if role not in var.TEMPLATE_RESTRICTIONS.keys():
            vils.difference_update(ps)

    for role, count in addroles.items():
        if role in var.TEMPLATE_RESTRICTIONS.keys():
            var.ROLES[role] = [None] * count
            continue # We deal with those later, see below

        to_add = set()

        if role in var.FORCE_ROLES:
            # Templates are handled later
            if role in var.TEMPLATE_RESTRICTIONS:
                continue
            if len(var.FORCE_ROLES[role]) > count:
                channels.Main.send(messages["error_frole_too_many"].format(role))
                return
            for user in var.FORCE_ROLES[role]:
                # If multiple main roles were forced, only first one is put in MAIN_ROLES
                if not user in var.MAIN_ROLES:
                    var.MAIN_ROLES[user] = role
                var.ORIGINAL_MAIN_ROLES[user] = role
                to_add.add(user)
                count -= 1

        selected = random.sample(vils, count)
        for x in selected:
            var.MAIN_ROLES[x] = role
            var.ORIGINAL_MAIN_ROLES[x] = role
            vils.remove(x)
        var.ROLES[role] = UserSet(selected)
        var.ROLES[role].update(to_add)
        fixed_count = count - roleset_roles[role]
        if fixed_count > 0:
            for pr in possible_rolesets:
                pr[role] += fixed_count
    var.ROLES[var.DEFAULT_ROLE].update(vils)
    for x in vils:
        var.MAIN_ROLES[x] = var.DEFAULT_ROLE
        var.ORIGINAL_MAIN_ROLES[x] = var.DEFAULT_ROLE
    if vils:
        for pr in possible_rolesets:
            pr[var.DEFAULT_ROLE] += len(vils)

    # Collapse possible_rolesets into var.ROLE_STATS
    # which is a FrozenSet[FrozenSet[Tuple[str, int]]]
    possible_rolesets_set = set()
    for pr in possible_rolesets:
        possible_rolesets_set.add(frozenset(pr.items()))
    var.ROLE_STATS = frozenset(possible_rolesets_set)

    # Now for the templates
    for template, restrictions in var.TEMPLATE_RESTRICTIONS.items():
        templ_count = len(var.ROLES[template])
        var.ROLES[template] = UserSet()
        if template in var.FORCE_ROLES:
            ps = var.FORCE_ROLES[template]
            var.ROLES[template].update(ps)
            templ_count -= len(ps)
        # sharpshooter gets applied specially
        # Don't do anything further if this template was forced on enough players already
        if template == "sharpshooter" or templ_count <= 0:
            continue
        possible = pl[:]
        for cannotbe in list_players(restrictions):
            if cannotbe in possible:
                possible.remove(cannotbe)
        if len(possible) < templ_count:
            cli.msg(chan, messages["not_enough_targets"].format(template))
            if var.ORIGINAL_SETTINGS:
                var.ROLES.clear()
                var.ROLES["person"] = UserSet(var.ALL_PLAYERS)
                reset_settings()
                cli.msg(chan, messages["default_reset"].format(botconfig.CMD_CHAR))
                var.PHASE = "join"
                return
            else:
                cli.msg(chan, messages["role_skipped"])
                continue

        var.ROLES[template].update([users._get(x) for x in random.sample(possible, templ_count)]) # FIXME

    # Handle gunner
    cannot_be_sharpshooter = get_players(var.TEMPLATE_RESTRICTIONS["sharpshooter"]) + list(var.FORCE_ROLES["gunner"])
    gunner_list = set(var.ROLES["gunner"]) # make a copy since we mutate var.ROLES["gunner"]
    num_sharpshooters = 0
    for gunner in gunner_list:
        if gunner in var.ROLES["village drunk"]:
            var.GUNNERS[gunner] = (var.DRUNK_SHOTS_MULTIPLIER * math.ceil(var.SHOTS_MULTIPLIER * len(pl)))
        elif num_sharpshooters < addroles["sharpshooter"] and gunner not in cannot_be_sharpshooter and random.random() <= var.SHARPSHOOTER_CHANCE:
            var.GUNNERS[gunner] = math.ceil(var.SHARPSHOOTER_MULTIPLIER * len(pl))
            var.ROLES["gunner"].remove(gunner)
            var.ROLES["sharpshooter"].add(gunner)
            num_sharpshooters += 1
        else:
            var.GUNNERS[gunner] = math.ceil(var.SHOTS_MULTIPLIER * len(pl))

    with var.WARNING_LOCK: # cancel timers
        for name in ("join", "join_pinger", "start_votes"):
            if name in var.TIMERS:
                var.TIMERS[name][0].cancel()
                del var.TIMERS[name]

    var.LAST_STATS = None
    var.LAST_TIME = None
    var.LAST_VOTES = None

    event = Event("role_assignment", {})
    event.dispatch(var, var.CURRENT_GAMEMODE.name, get_players())

    if not restart:
        gamemode = var.CURRENT_GAMEMODE.name
        if gamemode == "villagergame":
            gamemode = "default"

        # Alert the players to option changes they may not be aware of
        options = []
        if var.ORIGINAL_SETTINGS.get("ROLE_REVEAL") is not None:
            if var.ROLE_REVEAL == "on":
                options.append("role reveal")
            elif var.ROLE_REVEAL == "team":
                options.append("team reveal")
            elif var.ROLE_REVEAL == "off":
                options.append("no role reveal")
        if var.ORIGINAL_SETTINGS.get("STATS_TYPE") is not None:
            if var.STATS_TYPE == "disabled":
                options.append("no stats")
            else:
                options.append("{0} stats".format(var.STATS_TYPE))
        if var.ORIGINAL_SETTINGS.get("ABSTAIN_ENABLED") is not None or var.ORIGINAL_SETTINGS.get("LIMIT_ABSTAIN") is not None:
            if var.ABSTAIN_ENABLED and var.LIMIT_ABSTAIN:
                options.append("restricted abstaining")
            elif var.ABSTAIN_ENABLED:
                options.append("unrestricted abstaining")
            else:
                options.append("no abstaining")

        if len(options) > 2:
            options = " with {0}, and {1}".format(", ".join(options[:-1]), options[-1])
        elif len(options) == 2:
            options = " with {0} and {1}".format(options[0], options[1])
        elif len(options) == 1:
            options = " with {0}".format(options[0])
        else:
            options = ""

        cli.msg(chan, messages["welcome"].format(", ".join(pl), gamemode, options))
        cli.mode(chan, "+m")

    var.ORIGINAL_ROLES.clear()
    for role, players in var.ROLES.items():
        var.ORIGINAL_ROLES[role] = players.copy()

    # Handle doctor
    for doctor in var.ROLES["doctor"]:
        var.DOCTORS[doctor.nick] = math.ceil(var.DOCTOR_IMMUNIZATION_MULTIPLIER * len(pl)) # FIXME

    var.DAY_TIMEDELTA = timedelta(0)
    var.NIGHT_TIMEDELTA = timedelta(0)
    var.DAY_START_TIME = datetime.now()
    var.NIGHT_START_TIME = datetime.now()

    var.LAST_PING = None

    var.PLAYERS = {plr:dict(var.USERS[plr]) for plr in pl if plr in var.USERS}

    debuglog("ROLES:", " | ".join("{0}: {1}".format(role, ", ".join(p.nick for p in players))
        for role, players in sorted(var.ROLES.items()) if players and role not in var.TEMPLATE_RESTRICTIONS.keys()))
    templates = " | ".join("{0}: {1}".format(tmplt, ", ".join(p.nick for p in players))
        for tmplt, players in sorted(var.ROLES.items()) if players and tmplt in var.TEMPLATE_RESTRICTIONS.keys())
    if not templates:
        templates = "None"
    debuglog("TEMPLATES:", templates)

    if restart:
        var.PHASE = None # allow transition_* to run properly if game was restarted on first night
    var.FIRST_NIGHT = True
    if not var.START_WITH_DAY:
        var.GAMEPHASE = "night"
        transition_night()
    else:
        var.FIRST_DAY = True
        var.GAMEPHASE = "day"
        transition_day()

    decrement_stasis()

    if not botconfig.DEBUG_MODE or not var.DISABLE_DEBUG_MODE_REAPER:
        # DEATH TO IDLERS!
        reapertimer = threading.Thread(None, reaper, args=(cli,var.GAME_ID))
        reapertimer.daemon = True
        reapertimer.start()

@hook("error")
def on_error(cli, pfx, msg):
    if var.RESTARTING or msg.endswith("(Excess Flood)"):
        _restart_program()
    elif msg.startswith("Closing Link:"):
        raise SystemExit

@cmd("template", "ftemplate", flag="F", pm=True)
def ftemplate(cli, nick, chan, rest):
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

@cmd("fflags", flag="F", pm=True)
def fflags(cli, nick, chan, rest):
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


@cmd("wait", "w", playing=True, phases=("join",))
def wait(cli, nick, chan, rest):
    """Increases the wait time until !start can be used."""
    pl = list_players()

    if chan != botconfig.CHANNEL:
        return

    with var.WAIT_TB_LOCK:
        wait_check_time = time.time()
        var.WAIT_TB_TOKENS += (wait_check_time - var.WAIT_TB_LAST) / var.WAIT_TB_DELAY
        var.WAIT_TB_LAST = wait_check_time

        var.WAIT_TB_TOKENS = min(var.WAIT_TB_TOKENS, var.WAIT_TB_BURST)

        now = datetime.now()
        if ((var.LAST_WAIT and nick in var.LAST_WAIT and var.LAST_WAIT[nick] +
                timedelta(seconds=var.WAIT_RATE_LIMIT) > now)
                or var.WAIT_TB_TOKENS < 1):
            cli.notice(nick, messages["command_ratelimited"])
            return

        var.LAST_WAIT[nick] = now
        var.WAIT_TB_TOKENS -= 1
        if now > var.CAN_START_TIME:
            var.CAN_START_TIME = now + timedelta(seconds=var.EXTRA_WAIT)
        else:
            var.CAN_START_TIME += timedelta(seconds=var.EXTRA_WAIT)
        cli.msg(chan, messages["wait_time_increase"].format(nick, var.EXTRA_WAIT))


@cmd("fwait", flag="w", phases=("join",))
def fwait(cli, nick, chan, rest):
    """Forces an increase (or decrease) in wait time. Can be used with a number of seconds to wait."""

    pl = list_players()

    rest = re.split(" +", rest.strip(), 1)[0]

    if rest and (rest.isdigit() or (rest[0] == "-" and rest[1:].isdigit())):
        extra = int(rest)
    else:
        extra = var.EXTRA_WAIT

    now = datetime.now()
    extra = max(-900, min(900, extra))

    if now > var.CAN_START_TIME:
        var.CAN_START_TIME = now + timedelta(seconds=extra)
    else:
        var.CAN_START_TIME += timedelta(seconds=extra)

    if extra >= 0:
        cli.msg(chan, messages["forced_wait_time_increase"].format(nick, abs(extra), "s" if extra != 1 else ""))
    else:
        cli.msg(chan, messages["forced_wait_time_decrease"].format(nick, abs(extra), "s" if extra != -1 else ""))


@cmd("fstop", flag="S", phases=("join", "day", "night"))
def reset_game(cli, nick, chan, rest):
    """Forces the game to stop."""
    if nick == "<stderr>":
        cli.msg(botconfig.CHANNEL, messages["error_stop"])
    else:
        cli.msg(botconfig.CHANNEL, messages["fstop_success"].format(nick))
    if var.PHASE != "join":
        stop_game(var, log=False)
    else:
        pl = [p for p in list_players() if not is_fake_nick(p)]
        reset_modes_timers(var)
        reset()
        cli.msg(botconfig.CHANNEL, "PING! {0}".format(" ".join(pl)))

@cmd("rules", pm=True)
def show_rules(cli, nick, chan, rest):
    """Displays the rules."""

    if hasattr(botconfig, "RULES"):
        rules = botconfig.RULES

        # Backwards-compatibility
        pattern = re.compile(r"^\S+ channel rules: ")

        if pattern.search(rules):
            rules = pattern.sub("", rules)

        reply(cli, nick, chan, messages["channel_rules"].format(botconfig.CHANNEL, rules))
    else:
        reply(cli, nick, chan, messages["no_channel_rules"].format(botconfig.CHANNEL))

@cmd("help", raw_nick=True, pm=True)
def get_help(cli, rnick, chan, rest):
    """Gets help."""
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

@cmd("wiki", pm=True)
def wiki(cli, nick, chan, rest):
    """Prints information on roles from the wiki."""

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

@cmd("admins", "ops", pm=True)
def show_admins(cli, nick, chan, rest):
    """Pings the admins that are available."""

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
        coin = messages["coin_choices"][0]
    elif rnd < 0.88:
        coin = messages["coin_choices"][1]
    else:
        coin = messages["coin_choices"][2]
    wrapper.send(messages["coin_land"].format(coin))

@command("pony", "horse", pm=True)
def pony(var, wrapper, message):
    """Toss a magical pony into the air and see what happens!"""

    wrapper.send(messages["pony_toss"].format(wrapper.source))
    # 59/29/7/5 split
    rnd = random.random()
    if rnd < 0.59:
        pony = messages["pony_choices"][0]
    elif rnd < 0.88:
        pony = messages["pony_choices"][1]
    elif rnd < 0.95:
        pony = messages["pony_choices"][2].format(nick=wrapper.source)
    else:
        wrapper.send(messages["pony_fly"])
        return
    wrapper.send(messages["pony_land"].format(pony))

@command("cat", pm=True)
def cat(var, wrapper, message):
    """Toss a cat into the air and see what happens!"""
    wrapper.send(messages["cat_toss"].format(wrapper.source), messages["cat_land"], sep="\n")

@cmd("time", pm=True, phases=("join", "day", "night"))
def timeleft(cli, nick, chan, rest):
    """Returns the time left until the next day/night transition."""

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

@cmd("roles", pm=True)
def listroles(cli, nick, chan, rest):
    """Displays which roles are enabled at a certain number of players."""

    old = defaultdict(int)
    msg = []
    index = 0
    lpl = len(list_players()) + len(var.DEAD)
    roleindex = var.ROLE_INDEX
    roleguide = var.ROLE_GUIDE
    gamemode = var.CURRENT_GAMEMODE.name
    if gamemode == "villagergame":
        gamemode = "default"
        roleindex = var.CURRENT_GAMEMODE.fake_index
        roleguide = var.CURRENT_GAMEMODE.fake_guide

    rest = re.split(" +", rest.strip(), 1)

    #message if this game mode has been disabled
    if (not rest[0] or rest[0].isdigit()) and not hasattr(var.CURRENT_GAMEMODE, "ROLE_GUIDE"):
        msg.append("{0}: There {1} \u0002{2}\u0002 playing. {3}roles is disabled for the {4} game mode.".format(nick,
                   "is" if lpl == 1 else "are", lpl, botconfig.CMD_CHAR, gamemode))
        rest = []
        roleindex = {}
    #prepend player count if called without any arguments
    elif not rest[0] and lpl > 0:
        msg.append("{0}: There {1} \u0002{2}\u0002 playing.".format(nick, "is" if lpl == 1 else "are", lpl))
        if var.PHASE in var.GAME_PHASES:
            msg.append("Using the {0} game mode.".format(gamemode))
            rest = [str(lpl)]

    #read game mode to get roles for
    elif rest[0] and not rest[0].isdigit():
        gamemode = rest[0]
        validgamemodes = var.GAME_MODES.keys() - {"roles", "villagergame"} - var.DISABLED_GAMEMODES
        if gamemode not in validgamemodes:
            matches = complete_match(rest[0], validgamemodes)
            if len(matches) > 1:
                reply(cli, nick, chan, nick + ": " + messages["ambiguous_mode"].format(rest[0], ", ".join(matches)))
                return
            if len(matches) == 0:
                reply(cli, nick, chan, nick + ": " + messages["invalid_mode"].format(rest[0]))
                return
            gamemode = matches[0]

        if hasattr(var.GAME_MODES[gamemode][0](), "ROLE_GUIDE"):
            mode = var.GAME_MODES[gamemode][0]()
            if hasattr(mode, "ROLE_INDEX") and hasattr(mode, "ROLE_GUIDE"):
                roleindex = mode.ROLE_INDEX
                roleguide = mode.ROLE_GUIDE
            elif gamemode == "default" and "ROLE_INDEX" in var.ORIGINAL_SETTINGS and "ROLE_GUIDE" in var.ORIGINAL_SETTINGS:
                roleindex = var.ORIGINAL_SETTINGS["ROLE_INDEX"]
                roleguide = var.ORIGINAL_SETTINGS["ROLE_GUIDE"]
            rest.pop(0)
        else:
            msg.append("{0}: {1}roles is disabled for the {2} game mode.".format(nick, botconfig.CMD_CHAR, gamemode))
            rest = []
            roleindex = {}

    #number of players to print the game mode for
    if rest and rest[0].isdigit():
        index = int(rest[0])
        for i in range(len(roleindex)-1, -1, -1):
            if roleindex[i] <= index:
                index = roleindex[i]
                break

    #special ordering
    roleguide = [(role, roleguide[role]) for role in role_order()]
    for i, num in enumerate(roleindex):
        #getting the roles at a specific player count
        if index:
            if num < index:
                continue
            if num > index:
                break
        msg.append("{0}[{1}]{0}".format("\u0002" if num <= lpl else "", str(num)))
        roles = []
        for role, amount in roleguide:
            direction = 1 if amount[i] > old[role] else -1
            for j in range(old[role], amount[i], direction):
                temp = "{0}{1}".format("-" if direction == -1 else "", role)
                if direction == 1 and j+1 > 1:
                    temp += "({0})".format(j+1)
                elif j > 1:
                    temp += "({0})".format(j)
                roles.append(temp)
            old[role] = amount[i]
        msg.append(", ".join(roles))

    if not msg:
        msg = ["No roles are defined for {0}p games.".format(index)]

    reply(cli, nick, chan, " ".join(msg))

@command("myrole", pm=True, phases=("day", "night"))
def myrole(var, wrapper, message): # FIXME: Need to fix !swap once this gets converted
    """Reminds you of your current role."""

    ps = get_participants()
    if wrapper.source not in ps:
        return

    role = get_main_role(wrapper.source)
    if role in var.HIDDEN_VILLAGERS:
        role = "villager"
    elif role in var.HIDDEN_ROLES:
        role = var.DEFAULT_ROLE

    evt = Event("myrole", {"role": role, "messages": []})
    if not evt.dispatch(var, wrapper.source):
        return
    role = evt.data["role"]

    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
    wrapper.pm(messages["show_role"].format(an, role))

    for msg in evt.data["messages"]:
        wrapper.pm(msg)

    # Remind clone who they have cloned
    if role == "clone" and wrapper.source.nick in var.CLONED:
        wrapper.pm(messages["clone_target"].format(var.CLONED[wrapper.source.nick]))

    # Remind turncoats of their side
    if role == "turncoat":
        wrapper.pm(messages["turncoat_side"].format(var.TURNCOATS.get(wrapper.source.nick, "none")[0]))

    # Check for gun/bullets
    if wrapper.source not in var.ROLES["amnesiac"] and wrapper.source in var.GUNNERS and var.GUNNERS[wrapper.source]:
        role = "gunner"
        if wrapper.source in var.ROLES["sharpshooter"]:
            role = "sharpshooter"
        wrapper.pm(messages["gunner_simple"].format(role, var.GUNNERS[wrapper.source], "" if var.GUNNERS[wrapper.source] == 1 else "s"))

    # Remind prophet of their role, in sleepy mode only where it is hacked into a template instead of a role
    if "prophet" in var.TEMPLATE_RESTRICTIONS and wrapper.source in var.ROLES["prophet"]:
        wrapper.pm(messages["prophet_simple"])

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
                fn.caller(wrapper.source.client, wrapper.source.rawnick, channels.Main.name if fn.chan else users.Bot.nick, " ".join(args))
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

def _command_disabled_oldapi(cli, nick, chan, rest):
    # FIXME: kill this off when the old @cmd API is completely killed off
    reply(cli, nick, chan, messages["command_disabled_admin"])

@command("lastgame", "flastgame", flag="D", pm=True)
def flastgame(var, wrapper, message):
    """Disables starting or joining a game, and optionally schedules a command to run after the current game ends."""
    for cmdcls in (COMMANDS["join"] + COMMANDS["start"]):
        if isinstance(cmdcls, command):
            cmdcls.func = _command_disabled
        else:
            # FIXME: kill this off when the old @cmd API is completely killed off
            cmdcls.func = _command_disabled_oldapi

    channels.Main.send(messages["disable_new_games"].format(wrapper.source))
    var.ADMIN_TO_PING = wrapper.source

    if message.strip():
        aftergame.func(var, wrapper, message)

@cmd("gamestats", "gstats", pm=True)
def game_stats(cli, nick, chan, rest):
    """Gets the game stats for a given game size or lists game totals for all game sizes if no game size is given."""
    if (chan != nick and var.LAST_GSTATS and var.GSTATS_RATE_LIMIT and
            var.LAST_GSTATS + timedelta(seconds=var.GSTATS_RATE_LIMIT) >
            datetime.now()):
        cli.notice(nick, messages["command_ratelimited"])
        return

    if chan != nick:
        var.LAST_GSTATS = datetime.now()
        if var.PHASE not in ("none", "join") and chan == botconfig.CHANNEL:
            cli.notice(nick, messages["stats_wait_for_game_end"])
            return

    gamemode = "all"
    gamesize = None
    rest = rest.split()
    # Check for gamemode
    if len(rest) and not rest[0].isdigit():
        gamemode = rest[0]
        if gamemode != "all" and gamemode not in var.GAME_MODES.keys():
            matches = complete_match(gamemode, var.GAME_MODES.keys())
            if len(matches) == 1:
                gamemode = matches[0]
            if not matches:
                cli.notice(nick, messages["invalid_mode"].format(rest[0]))
                return
            if len(matches) > 1:
                cli.notice(nick, messages["ambiguous_mode"].format(rest[0], ", ".join(matches)))
                return
        rest.pop(0)
    # Check for invalid input
    if len(rest) and rest[0].isdigit():
        gamesize = int(rest[0])
        if gamemode != "all" and (gamesize > var.GAME_MODES[gamemode][2] or gamesize < var.GAME_MODES[gamemode][1]):
            cli.notice(nick, messages["integer_range"].format(var.GAME_MODES[gamemode][1], var.GAME_MODES[gamemode][2]))
            return

    # List all games sizes and totals if no size is given
    if not gamesize:
        reply(cli, nick, chan, db.get_game_totals(gamemode))
    else:
        # Attempt to find game stats for the given game size
        reply(cli, nick, chan, db.get_game_stats(gamemode, gamesize))

@cmd("playerstats", "pstats", "player", "p", pm=True) # XXX: mystats (just after this) needs updating along this one
def player_stats(cli, nick, chan, rest):
    """Gets the stats for the given player and role or a list of role totals if no role is given."""
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
        if role not in var.ROLE_GUIDE.keys():
            special_keys = {"lover"}
            evt = Event("get_role_metadata", {})
            evt.dispatch(var, "special_keys")
            special_keys = functools.reduce(lambda x, y: x | y, evt.data.values(), special_keys)
            if role.lower() in var.ROLE_ALIASES:
                matches = (var.ROLE_ALIASES[role.lower()],)
            else:
                matches = complete_match(role, var.ROLE_GUIDE.keys() | special_keys)
            if not matches:
                reply(cli, nick, chan, messages["no_such_role"].format(role))
                return
            if len(matches) > 1:
                reply(cli, nick, chan, messages["ambiguous_role"].format(", ".join(matches)))
                return
            role = matches[0]
        # Attempt to find the player's stats
        reply(cli, nick, chan, db.get_player_stats(acc, hostmask, role))

@cmd("mystats", "m", pm=True)
def my_stats(cli, nick, chan, rest):
    """Get your own stats."""
    rest = rest.split()
    player_stats.func(cli, nick, chan, " ".join([nick] + rest))

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
                wrapper.pm(messages["ambiguous_mode"].format(gamemode, ", ".join(matches)))
            return
        if len(matches) == 1:
            gamemode = matches[0]

    if gamemode != "roles" and gamemode != "villagergame" and gamemode not in var.DISABLED_GAMEMODES:
        if var.GAMEMODE_VOTES.get(wrapper.source.nick) == gamemode:
            wrapper.pm(messages["already_voted_game"].format(gamemode))
        else:
            var.GAMEMODE_VOTES[wrapper.source.nick] = gamemode
            wrapper.send(messages["vote_game_mode"].format(wrapper.source.nick, gamemode))
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


@cmd("vote", "v", pm=True, phases=("join", "day"))
def vote(cli, nick, chan, rest):
    """Vote for a game mode if no game is running, or for a player to be lynched."""
    if rest:
        if var.PHASE == "join" and chan != nick:
            return game.caller(cli, nick, chan, rest)
        else:
            return lynch.caller(cli, nick, chan, rest)
    else:
        return show_votes.caller(cli, nick, chan, rest)

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
                special_case = []
                if role == "clone" and user.nick in var.CLONED:
                    special_case.append("cloning {0}".format(var.CLONED[user.nick]))
                # print how many bullets normal gunners have
                elif (role == "gunner" or role == "sharpshooter") and user in var.GUNNERS:
                    special_case.append("{0} bullet{1}".format(var.GUNNERS[user], "" if var.GUNNERS[user] == 1 else "s"))
                elif role == "turncoat" and user.nick in var.TURNCOATS:
                    special_case.append("currently with \u0002{0}\u0002".format(var.TURNCOATS[user.nick][0])
                                        if var.TURNCOATS[user.nick][0] != "none" else "not currently on any side")

                evt = Event("revealroles_role", {"special_case": special_case})
                evt.dispatch(var, user, role)
                special_case = evt.data["special_case"]

                if not evt.prevent_default and user not in var.ORIGINAL_ROLES[role] and role not in var.TEMPLATE_RESTRICTIONS:
                    for old_role in role_order(): # order doesn't matter here, but oh well
                        if user in var.ORIGINAL_ROLES[old_role] and user not in var.ROLES[old_role]:
                            special_case.append("was {0}".format(old_role))
                            break
                if special_case:
                    out.append("".join((user.nick, " (", ", ".join(special_case), ")")))
                else:
                    out.append(user.nick)

            output.append("\u0002{0}\u0002: {1}".format(role, ", ".join(out)))

    #show who got immunized
    if var.IMMUNIZED:
        output.append("\u0002immunized\u0002: {0}".format(", ".join(var.IMMUNIZED)))

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

@command("frole", flag="d", phases=("join",))
def frole(var, wrapper, message):
    """Force a player into a certain role."""
    pl = get_players()

    parts = message.strip().lower().replace("=", " ").split(",")
    for part in parts:
        try:
            (name, role) = part.strip().split(" ", 1)
        except ValueError:
            wrapper.send(messages["frole_incorrect"].format(botconfig.CMD_CHAR, part))
            return
        user, _ = users.complete_match(name, pl)
        role = role.replace("_", " ")
        if role in var.ROLE_ALIASES:
            role = var.ROLE_ALIASES[role]
        if user is None or role not in var.ROLE_GUIDE or role == var.DEFAULT_ROLE:
            wrapper.send(messages["frole_incorrect"].format(botconfig.CMD_CHAR, part))
            return
        var.FORCE_ROLES[role].add(user)

    wrapper.send(messages["operation_successful"])

def fgame_help(args=""):
    args = args.strip()

    if not args:
        return messages["available_mode_setters"] + ", ".join(var.GAME_MODES.keys() - var.DISABLED_GAMEMODES)
    elif args in var.GAME_MODES.keys() and args not in var.DISABLED_GAMEMODES:
        return var.GAME_MODES[args][0].__doc__ or messages["setter_no_doc"].format(args)
    else:
        return messages["setter_not_found"].format(args)


fgame.__doc__ = fgame_help

if botconfig.DEBUG_MODE:

    @command("eval", owner_only=True, pm=True)
    def pyeval(var, wrapper, message):
        """Evaluate a Python expression."""
        try:
            wrapper.send(str(eval(message))[:500])
        except Exception as e:
            wrapper.send("{e.__class__.__name__}: {e}".format(e=e))

    @command("exec", owner_only=True, pm=True)
    def py(var, wrapper, message):
        """Execute arbitrary Python code."""
        try:
            exec(message)
        except Exception as e:
            wrapper.send("{e.__class__.__name__}: {e}".format(e=e))

    # DO NOT MAKE THIS A PMCOMMAND ALSO
    @cmd("force", flag="d")
    def force(cli, nick, chan, rest):
        """Force a certain player to use a specific command."""
        rst = re.split(" +",rest)
        if len(rst) < 2:
            cli.msg(chan, messages["incorrect_syntax"])
            return
        who = rst.pop(0).strip()
        if not who or who == users.Bot.nick:
            cli.msg(chan, messages["invalid_target"])
            return
        if who == "*":
            who = list_players()
        else:
            if not is_fake_nick(who):
                ul = list(var.USERS.keys()) # ark
                ull = [u.lower() for u in ul]
                if who.lower() not in ull:
                    cli.msg(chan, messages["invalid_target"])
                    return
                else:
                    who = [ul[ull.index(who.lower())]]
            else:
                who = [who]
        comm = rst.pop(0).lower().replace(botconfig.CMD_CHAR, "", 1)
        if comm in COMMANDS and not COMMANDS[comm][0].owner_only:
            for fn in COMMANDS[comm]:
                if fn.owner_only:
                    continue
                if fn.flag and users.exists(nick) and not is_admin(nick):
                    # Not a full admin
                    cli.notice(nick, messages["admin_only_force"])
                    continue
                for user in who:
                    if fn.chan:
                        fn.caller(cli, user, chan, " ".join(rst))
                    else:
                        fn.caller(cli, user, users.Bot.nick, " ".join(rst))
            cli.msg(chan, messages["operation_successful"])
        else:
            cli.msg(chan, messages["command_not_found"])


    @cmd("rforce", flag="d")
    def rforce(cli, nick, chan, rest):
        """Force all players of a given role to perform a certain action."""
        rst = re.split(" +",rest)
        if len(rst) < 2:
            cli.msg(chan, messages["incorrect_syntax"])
            return
        who = rst.pop(0).strip().lower()
        who = who.replace("_", " ")

        if who == "*": # wildcard match
            tgt = get_players()
        elif (who not in var.ROLES or not var.ROLES[who]) and (who != "gunner"
            or var.PHASE in ("none", "join")):
            cli.msg(chan, nick+": invalid role")
            return
        elif who == "gunner":
            tgt = set(var.GUNNERS)
        else:
            tgt = set(var.ROLES[who])

        comm = rst.pop(0).lower().replace(botconfig.CMD_CHAR, "", 1)
        if comm in COMMANDS and not COMMANDS[comm][0].owner_only:
            for fn in COMMANDS[comm]:
                if fn.owner_only:
                    continue
                if fn.flag and users.exists(nick) and not is_admin(nick):
                    # Not a full admin
                    cli.notice(nick, messages["admin_only_force"])
                    continue
                for user in tgt:
                    # FIXME: old command API
                    if fn.chan:
                        fn.caller(cli, user.nick, chan, " ".join(rst))
                    else:
                        fn.caller(cli, user.nick, users.Bot.nick, " ".join(rst))
            cli.msg(chan, messages["operation_successful"])
        else:
            cli.msg(chan, messages["command_not_found"])

# vim: set sw=4 expandtab:
