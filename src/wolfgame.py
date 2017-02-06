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
from src import db, events, dispatcher, channels, users, hooks, logger, proxy, debuglog, errlog, plog
from src.decorators import command, cmd, hook, handle_error, event_listener, COMMANDS
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

var.USERS = {}

var.ADMIN_PINGING = False
var.SPECIAL_ROLES = {}
var.ORIGINAL_ROLES = {}
var.PLAYERS = {}
var.DCED_PLAYERS = {}
var.ADMIN_TO_PING = None
var.AFTER_FLASTGAME = None
var.PINGING_IFS = False
var.TIMERS = {}

var.ORIGINAL_SETTINGS = {}
var.CURRENT_GAMEMODE = var.GAME_MODES["default"][0]()

var.LAST_SAID_TIME = {}

var.GAME_START_TIME = datetime.now()  # for idle checker only
var.CAN_START_TIME = 0
var.STARTED_DAY_PLAYERS = 0

var.DISCONNECTED = {}  # players who got disconnected

var.RESTARTING = False

#var.OPPED = False  # Keeps track of whether the bot is opped

var.BITTEN_ROLES = {}
var.LYCAN_ROLES = {}
var.CHARMED = set()
var.START_VOTES = set()

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
                    plog("IRCd does not support accounts, disabling account-related features.")
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
    if target and target != [botconfig.NICK]:
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
    # Only sync modes if a server changed modes because
    # 1) human ops probably know better
    # 2) other bots might start a fight over modes
    # 3) recursion; we see our own mode changes.
    if "!" not in rnick:
        sync_modes(var)

def reset_settings():
    var.CURRENT_GAMEMODE.teardown()
    var.CURRENT_GAMEMODE = var.GAME_MODES["default"][0]()
    for attr in list(var.ORIGINAL_SETTINGS.keys()):
        setattr(var, attr, var.ORIGINAL_SETTINGS[attr])
    var.ORIGINAL_SETTINGS.clear()

def reset_modes_timers(cli):
    # Reset game timers
    with var.WARNING_LOCK: # make sure it isn't being used by the ping join handler
        for x, timr in var.TIMERS.items():
            timr[0].cancel()
        var.TIMERS = {}

    # Reset modes
    cmodes = []
    for plr in list_players():
        cmodes.append(("-v", plr))
    if var.AUTO_TOGGLE_MODES:
        for plr in var.USERS:
            if not "moded" in var.USERS[plr]:
                continue
            for mode in var.USERS[plr]["moded"]:
                cmodes.append(("+"+mode, plr))
            users.get(plr).modes.update(users.get(plr).moded)
            users.get(plr).moded = set()
    if var.QUIET_DEAD_PLAYERS:
        for deadguy in var.DEAD:
            if not is_fake_nick(deadguy):
                cmodes.append(("-{0}".format(var.QUIET_MODE), var.QUIET_PREFIX+deadguy+"!*@*"))
    mass_mode(cli, cmodes, ["-m"])

def reset():
    var.PHASE = "none" # "join", "day", or "night"
    var.GAME_ID = 0
    var.RESTART_TRIES = 0
    var.DEAD = set()
    var.ROLES = {"person" : set()}
    var.ALL_PLAYERS = []
    var.JOINED_THIS_GAME = set() # keeps track of who already joined this game at least once (hostmasks)
    var.JOINED_THIS_GAME_ACCS = set() # same, except accounts
    var.PINGED_ALREADY = set()
    var.PINGED_ALREADY_ACCS = set()
    var.NO_LYNCH = set()
    var.FGAMED = False
    var.GAMEMODE_VOTES = {} #list of players who have used !game
    var.START_VOTES.clear() # list of players who have voted to !start
    var.LOVERS = {} # need to be here for purposes of random
    var.ROLE_STATS = frozenset() # type: FrozenSet[FrozenSet[Tuple[str, int]]]
    var.ROLE_SETS = [] # type: List[Tuple[Counter[str], int]]

    reset_settings()

    var.LAST_SAID_TIME.clear()
    var.PLAYERS.clear()
    var.DCED_PLAYERS.clear()
    var.DISCONNECTED.clear()
    var.SPECTATING_WOLFCHAT = set()
    var.SPECTATING_DEADCHAT = set()

    evt = Event("reset", {})
    evt.dispatch(var)

reset()

@command("sync", "fsync", flag="m", pm=True)
def fsync(var, wrapper, message):
    """Makes the bot apply the currently appropriate channel modes."""
    sync_modes(var)

def sync_modes(var):
    voices = [None]
    mode = hooks.Features["PREFIX"]["+"]
    pl = list_players()

    for user in channels.Main.users:
        if var.DEVOICE_DURING_NIGHT and var.PHASE == "night":
            if mode in user.channels[channels.Main]:
                voices.append(("-" + mode, user))
            elif user.nick in pl and mode not in user.channels[channels.Main]: # FIXME: Need to fix for when list_players() returns User instances
                voices.append(("+" + mode, user))
            elif user.nick not in pl and mode in user.channels[channels.Main]: # FIXME: See above comment
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

@command("fdie", "fbye", flag="D", pm=True)
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
            stop_game(wrapper.client, log=False)
        else:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(
                what="stop", cmd="fdie", prefix=botconfig.CMD_CHAR))
            return

    reset_modes_timers(wrapper.client)
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
            stop_game(wrapper.client, log=False)
        else:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(
                what="restart", cmd="frestart", prefix=botconfig.CMD_CHAR))
            return

    reset_modes_timers(wrapper.client)
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

    simple = wr