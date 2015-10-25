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
import random
import re
import signal
import socket
import sqlite3
import string
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

from oyoyo.parse import parse_nick

import botconfig
import src.settings as var
from src import decorators, events, logger

# done this way so that events is accessible in !eval (useful for debugging)
Event = events.Event

debuglog = logger("debug.log", write=False, display=False) # will be True if in debug mode
errlog = logger("errors.log")
plog = logger(None) #use this instead of print so that logs have timestamps

is_admin = var.is_admin
is_owner = var.is_owner

cmd = decorators.cmd
hook = decorators.hook
COMMANDS = decorators.COMMANDS

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
var.GRAVEYARD_LOCK = threading.RLock()
var.WARNING_LOCK = threading.RLock()
var.WAIT_TB_LOCK = threading.RLock()
var.STARTED_DAY_PLAYERS = 0

var.DISCONNECTED = {}  # players who got disconnected

var.RESTARTING = False

var.OPPED = False  # Keeps track of whether the bot is opped

var.BITTEN = {}
var.BITTEN_ROLES = {}
var.LYCAN_ROLES = {}
var.VENGEFUL_GHOSTS = {}
var.CHARMED = set()

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
    var.LEAVE_STASIS_PENALTY = 0
    var.IDLE_STASIS_PENALTY = 0
    var.PART_STASIS_PENALTY = 0
    var.ACC_STASIS_PENALTY = 0

if botconfig.DEBUG_MODE and var.DISABLE_DEBUG_MODE_TIME_LORD:
    var.TIME_LORD_DAY_LIMIT = 0 # 60
    var.TIME_LORD_DAY_WARN = 0 # 45
    var.TIME_LORD_NIGHT_LIMIT = 0 # 30
    var.TIME_LORD_NIGHT_WARN = 0 # 20

plog("Loading Werewolf IRC bot")

def connect_callback(cli):
    SIGUSR1 = getattr(signal, "SIGUSR1", None)
    SIGUSR2 = getattr(signal, "SIGUSR2", None)

    def sighandler(signum, frame):
        if signum == signal.SIGINT:
            # Exit immediately if Ctrl-C is pressed twice
            signal.signal(signal.SIGINT, signal.SIG_DFL)

        if signum in (signal.SIGINT, signal.SIGTERM):
            forced_exit.func(cli, "<console>", botconfig.CHANNEL, "")
        elif signum == SIGUSR1:
            restart_program.func(cli, "<console>", botconfig.CHANNEL, "")
        elif signum == SIGUSR2:
            plog("Scheduling aftergame restart")
            aftergame.func(cli, "<console>", botconfig.CHANNEL, "frestart")

    signal.signal(signal.SIGINT, sighandler)
    signal.signal(signal.SIGTERM, sighandler)

    if SIGUSR1:
        signal.signal(SIGUSR1, sighandler)

    if SIGUSR2:
        signal.signal(SIGUSR2, sighandler)

    to_be_devoiced = []
    cmodes = []

    @hook("quietlist", hookid=294)
    def on_quietlist(cli, server, botnick, channel, q, quieted, by, something):
        if re.search(r"^{0}.+\!\*@\*$".format(var.QUIET_PREFIX), quieted):  # only unquiet people quieted by bot
            cmodes.append(("-{0}".format(var.QUIET_MODE), quieted))

    @hook("banlist", hookid=294)
    def on_banlist(cli, server, botnick, channel, ban, by, timestamp):
        if re.search(r"^{0}.+\!\*@\*$".format(var.QUIET_PREFIX), ban):
            cmodes.append(("-{0}".format(var.QUIET_MODE), ban))

    @hook("whoreply", hookid=295)
    def on_whoreply(cli, svr, botnick, chan, user, host, server, nick, status, rest):
        if not var.DISABLE_ACCOUNTS:
            plog("IRCd does not support accounts, disabling account-related features.")
        var.DISABLE_ACCOUNTS = True
        var.ACCOUNTS_ONLY = False

        if nick in var.USERS:
            return

        if nick == botconfig.NICK:
            cli.nickname = nick
            cli.ident = user
            cli.hostmask = host

        if "+" in status:
            to_be_devoiced.append(user)
        newstat = ""
        for stat in status:
            if not stat in var.MODES_PREFIXES:
                continue
            newstat += var.MODES_PREFIXES[stat]
        var.USERS[nick] = dict(ident=user,host=host,account="*",inchan=True,modes=set(newstat),moded=set())

    @hook("whospcrpl", hookid=295)
    def on_whoreply(cli, server, nick, ident, host, _, user, status, acc):
        if user in var.USERS: return  # Don't add someone who is already there
        if user == botconfig.NICK:
            cli.nickname = user
            cli.ident = ident
            cli.hostmask = host
        if acc == "0":
            acc = "*"
        if "+" in status:
            to_be_devoiced.append(user)
        newstat = ""
        for stat in status:
            if not stat in var.MODES_PREFIXES:
                continue
            newstat += var.MODES_PREFIXES[stat]
        var.USERS[user] = dict(ident=ident,host=host,account=acc,inchan=True,modes=set(newstat),moded=set())

    @hook("endofwho", hookid=295)
    def afterwho(*args):
        # Devoice all on connect
        for nick in to_be_devoiced:
            cmodes.append(("-v", nick))

        try:
            # If the bot was restarted in the middle of the join phase, ping players that were joined.
            with sqlite3.connect("data.sqlite3", check_same_thread=False) as conn:
                c = conn.cursor()
                c.execute("SELECT players FROM pre_restart_state")
                players = c.fetchone()[0]
                if players:
                    msg = "PING! " + var.break_long_message(players.split()).replace("\n", "\nPING! ")
                    cli.msg(botconfig.CHANNEL, msg)
                    c.execute("UPDATE pre_restart_state SET players = NULL")
        except Exception:
            notify_error(cli, botconfig.CHANNEL, errlog)

        # Unhook the WHO hooks
        hook.unhook(295)


    #bot can be tricked into thinking it's still opped by doing multiple modes at once
    @hook("mode", hookid=296)
    def on_give_me_ops(cli, nick, chan, modeaction, target="", *other):
        if chan != botconfig.CHANNEL:
            return
        if modeaction == "+o" and target == botconfig.NICK:
            var.OPPED = True
            if botconfig.NICK in var.USERS:
                var.USERS[botconfig.NICK]["modes"].add("o")

            if var.PHASE == "none":
                @hook("quietlistend", hookid=297)
                def on_quietlist_end(cli, svr, nick, chan, *etc):
                    if chan == botconfig.CHANNEL:
                        mass_mode(cli, cmodes, ["-m"])
                @hook("endofbanlist", hookid=297)
                def on_banlist_end(cli, svr, nick, chan, *etc):
                    if chan == botconfig.CHANNEL:
                        mass_mode(cli, cmodes, ["-m"])

                cli.mode(botconfig.CHANNEL, var.QUIET_MODE)  # unquiet all
        elif modeaction == "-o" and target == botconfig.NICK:
            var.OPPED = False
            cli.msg("ChanServ", "op " + botconfig.CHANNEL)


    if var.DISABLE_ACCOUNTS:
        cli.who(botconfig.CHANNEL)
    else:
        cli.who(botconfig.CHANNEL, "%uhsnfa")

@hook("mode")
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
        sync_modes(cli)

#completes a partial nickname or string from a list
def complete_match(string, matches):
    num_matches = 0
    bestmatch = string
    for possible in matches:
        if string == possible:
            return string, 1
        if possible.startswith(string) or possible.lstrip("[{\\^_`|}]").startswith(string):
            bestmatch = possible
            num_matches += 1
    if num_matches != 1:
        return None, num_matches
    else:
        return bestmatch, 1

#wrapper around complete_match() used for roles
def get_victim(cli, nick, victim, in_chan, self_in_list = False):
    if not victim:
        if in_chan:
            cli.notice(nick, "Not enough parameters.")
        else:
            pm(cli, nick, "Not enough parameters")
        return
    pl = [x for x in var.list_players() if x != nick or self_in_list]
    pll = [x.lower() for x in pl]

    tempvictim, num_matches = complete_match(victim.lower(), pll)
    if not tempvictim:
        #ensure messages about not being able to act on yourself work
        if num_matches == 0 and nick.lower().startswith(victim.lower()):
            return nick
        if in_chan:
            cli.notice(nick, "\u0002{0}\u0002 is not currently playing.".format(victim))
        else:
            pm(cli, nick, "\u0002{0}\u0002 is not currently playing.".format(victim))
        return
    return pl[pll.index(tempvictim)] #convert back to normal casing

def get_roles(*roles):
    all_roles = []
    for role in roles:
        all_roles.append(var.ROLES[role])
    return list(itertools.chain(*all_roles))

def mass_mode(cli, md_param, md_plain):
    """ Example: mass_mode(cli, [('+v', 'asdf'), ('-v','wobosd')], ['-m']) """
    lmd = len(md_param)  # store how many mode changes to do
    if md_param:
        for start_i in range(0, lmd, var.MODELIMIT):  # 4 mode-changes at a time
            if start_i + var.MODELIMIT > lmd:  # If this is a remainder (mode-changes < 4)
                z = list(zip(*md_param[start_i:]))  # zip this remainder
                ei = lmd % var.MODELIMIT  # len(z)
            else:
                z = list(zip(*md_param[start_i:start_i+var.MODELIMIT])) # zip four
                ei = var.MODELIMIT # len(z)
            # Now z equal something like [('+v', '-v'), ('asdf', 'wobosd')]
            arg1 = "".join(md_plain) + "".join(z[0])
            arg2 = " ".join(z[1])  # + " " + " ".join([x+"!*@*" for x in z[1]])
            cli.mode(botconfig.CHANNEL, arg1, arg2)
    else:
            cli.mode(botconfig.CHANNEL, "".join(md_plain))

def pm(cli, target, message):  # message either privmsg or notice, depending on user settings
    if is_fake_nick(target) and botconfig.DEBUG_MODE:
        debuglog("Would message fake nick {0}: {1!r}".format(target, message))
        return

    if is_user_notice(target):
        cli.notice(target, message)
        return

    cli.msg(target, message)

decorators.pm = pm

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
    for plr in var.list_players():
        cmodes.append(("-v", plr))
    if var.AUTO_TOGGLE_MODES:
        for plr in var.USERS:
            if not "moded" in var.USERS[plr]:
                continue
            for mode in var.USERS[plr]["moded"]:
                cmodes.append(("+"+mode, plr))
            var.USERS[plr]["modes"].update(var.USERS[plr]["moded"])
            var.USERS[plr]["moded"] = set()
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
    var.START_VOTES = set() # list of players who have voted to !start
    var.LOVERS = {} # need to be here for purposes of random

    reset_settings()

    var.LAST_SAID_TIME.clear()
    var.PLAYERS.clear()
    var.DCED_PLAYERS.clear()
    var.DISCONNECTED.clear()

reset()

def make_stasis(nick, penalty):
    if nick in var.USERS:
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        acc = var.USERS[nick]["account"]
    else:
        return # Can't do it
    if not acc or acc == "*":
        acc = None
    if not host and not acc:
        return # Can't do it, either
    if acc:
        if penalty == 0:
            if acc in var.STASISED_ACCS:
                del var.STASISED_ACCS[acc]
                var.set_stasis_acc(acc, 0)
        else:
            var.STASISED_ACCS[acc] += penalty
            var.set_stasis_acc(acc, var.STASISED_ACCS[acc])
    if (not var.ACCOUNTS_ONLY or not acc) and host:
        hostmask = ident + "@" + host
        if penalty == 0:
            if hostmask in var.STASISED:
                del var.STASISED[hostmask]
                var.set_stasis(hostmask, 0)
        else:
            var.STASISED[hostmask] += penalty
            var.set_stasis(hostmask, var.STASISED[hostmask])

@cmd("fsync", admin_only=True, pm=True)
def fsync(cli, nick, chan, rest):
    """Makes the bot apply the currently appropriate channel modes."""
    sync_modes(cli)

def sync_modes(cli):
    voices = []
    pl = var.list_players()
    for nick, u in var.USERS.items():
        if nick in pl and "v" not in u.get("modes", set()):
            voices.append(("+v", nick))
        elif nick not in pl and "v" in u.get("modes", set()):
            voices.append(("-v", nick))
    if var.PHASE in ("day", "night"):
        other = ["+m"]
    else:
        other = ["-m"]

    mass_mode(cli, voices, other)


@cmd("fdie", "fbye", admin_only=True, pm=True)
def forced_exit(cli, nick, chan, rest):
    """Forces the bot to close."""

    if var.PHASE in ("day", "night"):
        try:
            stop_game(cli)
        except Exception:
            traceback.print_exc()

    try:
        reset_modes_timers(cli)
    except Exception:
        traceback.print_exc()

    try:
        reset()
    except Exception:
        traceback.print_exc()

    msg = "{0} quit from {1}"

    if rest.strip():
        msg += " ({2})"

    try:
        cli.quit(msg.format("Scheduled" if forced_exit.aftergame else "Forced",
                            nick,
                            rest.strip()))
    except Exception:
        traceback.print_exc()
        sys.exit()
    finally:
        cli.socket.close() # in case it didn't close, force it to


def _restart_program(cli, mode=None):
    plog("RESTARTING")

    python = sys.executable

    if mode:
        assert mode in ("normal", "verbose", "debug")
        os.execl(python, python, sys.argv[0], "--{0}".format(mode))
    else:
        os.execl(python, python, *sys.argv)


@cmd("frestart", admin_only=True, pm=True)
def restart_program(cli, nick, chan, rest):
    """Restarts the bot."""

    if var.PHASE in ("day", "night"):
        try:
            stop_game(cli)
        except Exception:
            traceback.print_exc()

    try:
        reset_modes_timers(cli)
    except Exception:
        traceback.print_exc()

    try:
        with sqlite3.connect("data.sqlite3", check_same_thread=False) as conn:
            c = conn.cursor()
            players = var.list_players()
            if players:
                c.execute("UPDATE pre_restart_state SET players = ?", (" ".join(players),))
    except Exception:
        traceback.print_exc()

    try:
        reset()
    except Exception:
        traceback.print_exc()

    msg = "{0} restart from {1}".format(
        "Scheduled" if restart_program.aftergame else "Forced", nick)

    rest = rest.strip()
    mode = None

    if rest:
        args = rest.split()
        first_arg = args[0].lower()

        if first_arg.endswith("mode") and first_arg != "mode":
            mode = first_arg.replace("mode", "")

            VALID_MODES = ("normal", "verbose", "debug")

            if mode not in VALID_MODES:
                err_msg = ("\u0002{0}\u0002 is not a valid mode. Valid "
                           "modes are: {1}").format(mode, ", ".join(VALID_MODES))

                if chan == nick:
                    pm(cli, nick, err_msg)
                else:
                    cli.notice(nick, err_msg)

                return

            msg += " in {0} mode".format(mode)
            rest = " ".join(args[1:])

    if rest:
        msg += " ({0})".format(rest)

    try:
        cli.quit(msg.format(nick, rest.strip()))
    except Exception:
        traceback.print_exc()

    @hook("quit")
    def restart_buffer(cli, raw_nick, reason):
        nick, _, __, host = parse_nick(raw_nick)
        # restart the bot once our quit message goes though to ensure entire IRC queue is sent
        # if the bot is using a nick that isn't botconfig.NICK, then stop breaking things and fdie
        try:
            if nick == botconfig.NICK:
                _restart_program(cli, mode)
        finally:
            cli.socket.close()

    # This is checked in the on_error handler. Some IRCds, such as InspIRCd, don't send the bot
    # its own QUIT message, so we need to use ERROR. Ideally, we shouldn't even need the above
    # handler now, but I'm keeping it for now just in case.
    var.RESTARTING = True


@cmd("ping", pm=True)
def pinger(cli, nick, chan, rest):
    """Check if you or the bot is still connected."""
    message = random.choice(var.PING_MESSAGES).format(nick=nick)

    if chan == nick:
        pm(cli, nick, message)
    else:
        cli.msg(chan, message)

@cmd("simple", raw_nick=True, pm=True)
def mark_simple_notify(cli, nick, chan, rest):
    """Makes the bot give you simple role instructions, in case you are familiar with the roles."""

    nick, _, ident, host = parse_nick(nick)
    if nick in var.USERS:
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        acc = var.USERS[nick]["account"]
    else:
        acc = None
    if not acc or acc == "*":
        acc = None

    if acc: # Prioritize account
        if acc in var.SIMPLE_NOTIFY_ACCS:
            var.SIMPLE_NOTIFY_ACCS.remove(acc)
            var.remove_simple_rolemsg_acc(acc)
            if host in var.SIMPLE_NOTIFY:
                var.SIMPLE_NOTIFY.remove(host)
                var.remove_simple_rolemsg(host)
            fullmask = ident + "@" + host
            if fullmask in var.SIMPLE_NOTIFY:
                var.SIMPLE_NOTIFY.remove(fullmask)
                var.remove_simple_rolemsg(fullmask)

            cli.notice(nick, "You now no longer receive simple role instructions.")
            return

        var.SIMPLE_NOTIFY_ACCS.add(acc)
        var.add_simple_rolemsg_acc(acc)
    elif var.ACCOUNTS_ONLY:
        cli.notice(nick, "You are not logged in to NickServ.")
        return

    else: # Not logged in, fall back to ident@hostmask
        if host in var.SIMPLE_NOTIFY:
            var.SIMPLE_NOTIFY.remove(host)
            var.remove_simple_rolemsg(host)
        
            cli.notice(nick, "You now no longer receive simple role instructions.")
            return
      
        fullmask = ident + "@" + host
        if fullmask in var.SIMPLE_NOTIFY:
            var.SIMPLE_NOTIFY.remove(fullmask)
            var.remove_simple_rolemsg(fullmask)

            cli.notice(nick, "You now no longer receive simple role instructions.")
            return

        var.SIMPLE_NOTIFY.add(fullmask)
        var.add_simple_rolemsg(fullmask)

    cli.notice(nick, "You now receive simple role instructions.")

def is_user_simple(nick):
    if nick in var.USERS:
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        acc = var.USERS[nick]["account"]
    else:
        return False
    if acc and acc != "*" and not var.DISABLE_ACCOUNTS:
        if acc in var.SIMPLE_NOTIFY_ACCS:
            return True
        return False
    elif not var.ACCOUNTS_ONLY:
        for hostmask in var.SIMPLE_NOTIFY:
            if var.match_hostmask(hostmask, nick, ident, host):
                return True
    return False

@cmd("notice", raw_nick=True, pm=True)
def mark_prefer_notice(cli, nick, chan, rest):
    """Makes the bot NOTICE you for every interaction."""

    nick, _, ident, host = parse_nick(nick)
    if nick in var.USERS:
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        acc = var.USERS[nick]["account"]
    else:
        acc = None
    if not acc or acc == "*":
        acc = None

    if acc and not var.DISABLE_ACCOUNTS: # Do things by account if logged in
        if acc in var.PREFER_NOTICE_ACCS:
            var.PREFER_NOTICE_ACCS.remove(acc)
            var.remove_prefer_notice_acc(acc)
            if host in var.PREFER_NOTICE:
                var.PREFER_NOTICE.remove(host)
                var.remove_prefer_notice(host)
            fullmask = ident + "@" + host
            if fullmask in var.PREFER_NOTICE:
                var.PREFER_NOTICE.remove(fullmask)
                var.remove_prefer_notice(fullmask)

            cli.notice(nick, "Gameplay interactions will now use PRIVMSG for you.")
            return

        var.PREFER_NOTICE_ACCS.add(acc)
        var.add_prefer_notice_acc(acc)
    elif var.ACCOUNTS_ONLY:
        cli.notice(nick, "You are not logged in to NickServ.")
        return

    else: # Not logged in
        if host in var.PREFER_NOTICE:
            var.PREFER_NOTICE.remove(host)
            var.remove_prefer_notice(host)

            cli.notice(nick, "Gameplay interactions will now use PRIVMSG for you.")
            return
        fullmask = ident + "@" + host
        if fullmask in var.PREFER_NOTICE:
            var.PREFER_NOTICE.remove(fullmask)
            var.remove_prefer_notice(fullmask)

            cli.notice(nick, "Gameplay interactions will now use PRIVMSG for you.")
            return

        var.PREFER_NOTICE.add(fullmask)
        var.add_prefer_notice(fullmask)

    cli.notice(nick, "The bot will now always NOTICE you.")

def is_user_notice(nick):
    if nick in var.USERS and var.USERS[nick]["account"] and var.USERS[nick]["account"] != "*" and not var.DISABLE_ACCOUNTS:
        if var.USERS[nick]["account"] in var.PREFER_NOTICE_ACCS:
            return True
    if nick in var.USERS and not var.ACCOUNTS_ONLY:
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        for hostmask in var.PREFER_NOTICE:
            if var.match_hostmask(hostmask, nick, ident, host):
                return True
    return False

@cmd("swap", "replace", pm=True, phases=("join", "day", "night"))
def replace(cli, nick, chan, rest):
    """Swap out a player logged in to your account."""
    if nick not in var.USERS or not var.USERS[nick]["inchan"]:
        pm(cli, nick, "You need to be in {0} to use that command.".format(botconfig.CHANNEL))
        return

    if nick in var.list_players():
        if chan == nick:
            pm(cli, nick, "You're already playing!")
        else:
            cli.notice(nick, "You're already playing!")
        return

    account = var.USERS[nick]["account"]

    if not account or account == "*":
        if chan == nick:
            pm(cli, nick, "You are not logged in to NickServ.")
        else:
            cli.notice(nick, "You are not logged in to NickServ.")
        return

    rest = rest.split()

    if not rest: # bare call
        target = None

        for user in var.USERS:
            if var.USERS[user]["account"] == account:
                if user == nick or (user not in var.list_players() and user not in var.VENGEFUL_GHOSTS):
                    pass
                elif target is None:
                    target = user
                else:
                    if chan == nick:
                        pm(cli, nick, "More than one player is logged in to your account. Use 'swap <nick>' to swap.")
                    else:
                        cli.notice(nick, "More than one player is logged in to your account. Use '{0}swap <nick>' to swap.".format(botconfig.CMD_CHAR))
                    return

        if target is None:
            msg = "You do not appear to be playing. Make sure you are identified to the same account."
            if chan == nick:
                pm(cli, nick, msg)
            else:
                cli.notice(nick, msg)
            return
    else:
        target, _ = complete_match(rest[0], var.list_players() + list(var.VENGEFUL_GHOSTS.keys()))

        if target not in var.list_players() and target not in var.VENGEFUL_GHOSTS:
            msg = "That person is no{0} playing.".format(" longer" if target in var.DEAD else "t")
            if chan == nick:
                pm(cli, nick, msg)
            else:
                cli.notice(nick, msg)
            return

        if target in var.USERS:
            if var.USERS[target]["account"] == "*":
                if chan == nick:
                    pm(cli, nick, "That person is not logged in to NickServ.")
                else:
                    cli.notice(nick, "That person is not logged in to NickServ.")
                return

    if var.USERS[target]["account"] == account and nick != target:
        rename_player(cli, target, nick)
        # Make sure to remove player from var.DISCONNECTED if they were in there
        if var.PHASE in ("day", "night"):
            return_to_village(cli, chan, target, False)

        mass_mode(cli, [("-v", target), ("+v", nick)], [])

        cli.msg(botconfig.CHANNEL, "\u0002{0}\u0002 has swapped places with \u0002{1}\u0002.".format(nick, target))
        myrole.caller(cli, nick, chan, "")

@cmd("pingif", "pingme", "pingat", "pingpref", pm=True)
def altpinger(cli, nick, chan, rest):
    """Pings you when the number of players reaches your preference. Usage: "pingif <players>". https://github.com/lykoss/lykos/wiki/Pingif"""
    players = is_user_altpinged(nick)
    rest = rest.split()
    if nick in var.USERS:
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        acc = var.USERS[nick]["account"]
    else:
        if chan == nick:
            pm(cli, nick, "You need to be in {0} to use that command.".format(botconfig.CHANNEL))
        else: # former message: "You won the lottery! This is a bug though, so report it to the admins."
            cli.notice(nick, "You need to be in {0} to use that command.".format(botconfig.CHANNEL))
        return

    if (not acc or acc == "*") and var.ACCOUNTS_ONLY:
        if chan == nick:
            pm(cli, nick, "You are not logged in to NickServ.")
        else:
            cli.notice(nick, "You are not logged in to NickServ.")
        return

    msg = []

    if not rest:
        if players:
            msg.append("You will be pinged when there are at least {0} players joined.".format(players))
        else:
            msg.append("You do not have any ping preferences currently set.")

    elif any((rest[0] in ("off", "never"),
              rest[0].isdigit() and int(rest[0]) == 0,
              len(rest) > 1 and rest[1].isdigit() and int(rest[1]) == 0)):
        if players:
            msg.append("Your ping preferences have been removed (was {0}).".format(players))
            toggle_altpinged_status(nick, 0, players)
        else:
            msg.append("You do not have any preferences set.")

    elif rest[0].isdigit() or (len(rest) > 1 and rest[1].isdigit()):
        if rest[0].isdigit():
            num = int(rest[0])
        else:
            num = int(rest[1])
        if num > 999:
            msg.append("That number is too large.")
        elif players == num:
            msg.append("Your ping preferences are already set to {0}.".format(num))
        elif players:
            msg.append("Your ping preferences have been changed from {0} to {1}.".format(players, num))
            toggle_altpinged_status(nick, num, players)
        else:
            msg.append("Your ping preferences have been set to {0}.".format(num))
            toggle_altpinged_status(nick, num)

    else:
        msg.append("Invalid parameter. Please enter a non-negative integer or a valid preference.")

    if chan == nick:
        pm(cli, nick, "\n".join(msg))
    else:
        cli.notice(nick, "\n".join(msg))

def is_user_altpinged(nick):
    if nick in var.USERS.keys():
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        acc = var.USERS[nick]["account"]
    else:
        return 0
    if not var.DISABLE_ACCOUNTS and acc and acc != "*":
        if acc in var.PING_IF_PREFS_ACCS.keys():
            return var.PING_IF_PREFS_ACCS[acc]
    elif not var.ACCOUNTS_ONLY:
        for hostmask, pref in var.PING_IF_PREFS.items():
            if var.match_hostmask(hostmask, nick, ident, host):
                return pref
    return 0

def toggle_altpinged_status(nick, value, old=None):
    # nick should be in var.USERS if not fake; if not, let the error propagate
    ident = var.USERS[nick]["ident"]
    host = var.USERS[nick]["host"]
    acc = var.USERS[nick]["account"]
    if value == 0:
        if not var.DISABLE_ACCOUNTS and acc and acc != "*":
            if acc in var.PING_IF_PREFS_ACCS:
                del var.PING_IF_PREFS_ACCS[acc]
                var.set_pingif_status(acc, True, 0)
                if old is not None:
                    with var.WARNING_LOCK:
                        if old in var.PING_IF_NUMS_ACCS:
                            var.PING_IF_NUMS_ACCS[old].discard(acc)
        if not var.ACCOUNTS_ONLY:
            for hostmask in list(var.PING_IF_PREFS.keys()):
                if var.match_hostmask(hostmask, nick, ident, host):
                    del var.PING_IF_PREFS[hostmask]
                    var.set_pingif_status(hostmask, False, 0)
                    if old is not None:
                        with var.WARNING_LOCK:
                            if old in var.PING_IF_NUMS.keys():
                                var.PING_IF_NUMS[old].discard(host)
                                var.PING_IF_NUMS[old].discard(hostmask)
    else:
        if not var.DISABLE_ACCOUNTS and acc and acc != "*":
            var.PING_IF_PREFS_ACCS[acc] = value
            var.set_pingif_status(acc, True, value)
            with var.WARNING_LOCK:
                if value not in var.PING_IF_NUMS_ACCS:
                    var.PING_IF_NUMS_ACCS[value] = set()
                var.PING_IF_NUMS_ACCS[value].add(acc)
                if old is not None:
                    if old in var.PING_IF_NUMS_ACCS:
                        var.PING_IF_NUMS_ACCS[old].discard(acc)
        elif not var.ACCOUNTS_ONLY:
            hostmask = ident + "@" + host
            var.PING_IF_PREFS[hostmask] = value
            var.set_pingif_status(hostmask, False, value)
            with var.WARNING_LOCK:
                if value not in var.PING_IF_NUMS.keys():
                    var.PING_IF_NUMS[value] = set()
                var.PING_IF_NUMS[value].add(hostmask)
                if old is not None:
                    if old in var.PING_IF_NUMS.keys():
                        var.PING_IF_NUMS[old].discard(host)
                        var.PING_IF_NUMS[old].discard(hostmask)

def join_timer_handler(cli):
    with var.WARNING_LOCK:
        var.PINGING_IFS = True
        to_ping = []
        pl = var.list_players()

        checker = set()
        chk_acc = set()

        # Add accounts/hosts to the list of possible players to ping
        if not var.DISABLE_ACCOUNTS:
            for num in var.PING_IF_NUMS_ACCS:
                if num <= len(pl):
                    chk_acc.update(var.PING_IF_NUMS_ACCS[num])

        if not var.ACCOUNTS_ONLY:
            for num in var.PING_IF_NUMS:
                if num <= len(pl):
                    checker.update(var.PING_IF_NUMS[num])

        # Don't ping alt connections of users that have already joined
        if not var.DISABLE_ACCOUNTS:
            for acc in (var.USERS[player]["account"] for player in pl if player in var.USERS):
                var.PINGED_ALREADY_ACCS.add(acc)

        # Remove players who have already been pinged from the list of possible players to ping
        for acc in frozenset(chk_acc):
            if acc in var.PINGED_ALREADY_ACCS:
                chk_acc.remove(acc)

        for hostmask in frozenset(checker):
            if hostmask in var.PINGED_ALREADY:
                checker.remove(hostmask)

        # If there is nobody to ping, do nothing
        if not chk_acc and not checker:
            var.PINGING_IFS = False
            return

        @hook("whoreply", hookid=387)
        def ping_altpingers_noacc(cli, svr, botnick, chan, ident, host, server, nick, status, rest):
            if ("G" in status or is_user_stasised(nick) or not var.PINGING_IFS or
                    nick == botnick or nick in pl):
                return

            hostmask = ident + "@" + host
            if hostmask in checker:
                to_ping.append(nick)
                var.PINGED_ALREADY.add(hostmask)

        @hook("whospcrpl", hookid=387)
        def ping_altpingers(cli, server, nick, ident, host, _, user, status, acc):
            if ("G" in status or is_user_stasised(user) or not var.PINGING_IFS or
                user == botconfig.NICK or user in pl):

                return

            # Create list of players to ping
            if acc and acc != "*":
                if acc in chk_acc:
                    to_ping.append(user)
                    var.PINGED_ALREADY_ACCS.add(acc)

            elif not var.ACCOUNTS_ONLY:
                hostmask = ident + "@" + host
                to_ping.append(user)
                var.PINGED_ALREADY.add(hostmask)

        @hook("endofwho", hookid=387)
        def fetch_altpingers(*stuff):
            # fun fact: if someone joined 10 seconds after someone else, the bot would break.
            # effectively, the join would delete join_pinger from var.TIMERS and this function
            # here would be reached before it was created again, thus erroring and crashing.
            # this is one of the multiple reasons we need unit testing
            # I was lucky to catch this in testing, as it requires precise timing
            # it only failed if a join happened while this outer func had started
            var.PINGING_IFS = False
            hook.unhook(387)
            if to_ping:
                to_ping.sort(key=lambda x: x.lower())

                msg_prefix = "PING! {0} player{1}! ".format(len(pl), "" if len(pl) == 1 else "s")
                msg = msg_prefix + var.break_long_message(to_ping).replace("\n", "\n" + msg_prefix)

                cli.msg(botconfig.CHANNEL, msg)

        if not var.DISABLE_ACCOUNTS:
            cli.who(botconfig.CHANNEL, "%uhsnfa")
        else:
            cli.who(botconfig.CHANNEL)

@cmd("join", "j", phases=("none", "join"))
def join(cli, nick, chan, rest):
    """Either starts a new game of Werewolf or joins an existing game that has not started yet."""
    if var.ACCOUNTS_ONLY:
        if nick in var.USERS and (not var.USERS[nick]["account"] or var.USERS[nick]["account"] == "*"):
            cli.notice(nick, "You are not logged in to NickServ.")
            return
    if join_player(cli, nick, chan) and rest and not var.FGAMED:
        gamemode = rest.lower().split()[0]
        if gamemode not in var.GAME_MODES.keys():
            match, _ = complete_match(gamemode, var.GAME_MODES.keys() - {"roles"})
            if not match:
                return
            gamemode = match
        if gamemode != "roles":
            var.GAMEMODE_VOTES[nick] = gamemode
            cli.msg(chan, "\u0002{0}\u0002 votes for the \u0002{1}\u0002 game mode.".format(nick, gamemode))

def join_player(cli, player, chan, who = None, forced = False):
    if who is None:
        who = player

    pl = var.list_players()
    if chan != botconfig.CHANNEL:
        return

    if not var.OPPED:
        cli.notice(who, "Sorry, I'm not opped in {0}.".format(chan))
        cli.msg("ChanServ", "op " + botconfig.CHANNEL)
        return

    if player in var.USERS:
        ident = var.USERS[player]["ident"]
        host = var.USERS[player]["host"]
        acc = var.USERS[player]["account"]
    elif is_fake_nick(player) and botconfig.DEBUG_MODE:
        # fakenick
        ident = None
        host = None
        acc = None
    else:
        return # Not normal
    if not acc or acc == "*" or var.DISABLE_ACCOUNTS:
        acc = None

    stasis = is_user_stasised(player)

    if stasis:
        if forced and stasis == 1:
            for hostmask in list(var.STASISED.keys()):
                if var.match_hostmask(hostmask, player, ident, host):
                    var.set_stasis(hostmask, 0)
                    del var.STASISED[hostmask]
            if not var.DISABLE_ACCOUNTS and acc in var.STASISED_ACCS:
                var.set_stasis_acc(acc, 0)
                del var.STASISED_ACCS[acc]
        else:
            cli.notice(who, "Sorry, but {0} in stasis for {1} game{2}.".format(
                "you are" if player == who else player + " is", stasis,
                "s" if stasis != 1 else ""))
            return

    cmodes = [("+v", player)]
    if var.PHASE == "none":

        if var.AUTO_TOGGLE_MODES and player in var.USERS and var.USERS[player]["modes"]:
            for mode in var.USERS[player]["modes"]:
                cmodes.append(("-"+mode, player))
            var.USERS[player]["moded"].update(var.USERS[player]["modes"])
            var.USERS[player]["modes"] = set()
        mass_mode(cli, cmodes, [])
        var.ROLES["person"].add(player)
        var.ALL_PLAYERS.append(player)
        var.PHASE = "join"
        with var.WAIT_TB_LOCK:
            var.WAIT_TB_TOKENS = var.WAIT_TB_INIT
            var.WAIT_TB_LAST   = time.time()
        var.GAME_ID = time.time()
        var.PINGED_ALREADY_ACCS = set()
        var.PINGED_ALREADY = set()
        if host:
            var.JOINED_THIS_GAME.add(ident + "@" + host)
        if acc:
            var.JOINED_THIS_GAME_ACCS.add(acc)
        var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.MINIMUM_WAIT)
        cli.msg(chan, ('\u0002{0}\u0002 has started a game of Werewolf. '+
                      'Type "{1}join" to join. Type "{1}start" to vote to start the game. '+
                      'Type "{1}wait" to increase the start wait time.').format(player, botconfig.CMD_CHAR))

        # Set join timer
        if var.JOIN_TIME_LIMIT > 0:
            t = threading.Timer(var.JOIN_TIME_LIMIT, kill_join, [cli, chan])
            var.TIMERS["join"] = (t, time.time(), var.JOIN_TIME_LIMIT)
            t.daemon = True
            t.start()

    elif player in pl:
        cli.notice(who, "{0}'re already playing!".format("You" if who == player else "They"))
        return True
    elif len(pl) >= var.MAX_PLAYERS:
        cli.notice(who, "Too many players! Try again next time.")
        return
    elif var.PHASE != "join":
        cli.notice(who, "Sorry, but the game is already running. Try again next time.")
        return
    else:
        if acc is not None and not botconfig.DEBUG_MODE:
            for user in pl:
                if var.USERS[user]["account"] == acc:
                    msg = "Sorry, but \u0002{0}\u0002 is already joined under {1} account.{2}"
                    if who == player:
                        cli.notice(who, msg.format(user, "your", " Please use '{0}swap' to join instead.".format(botconfig.CMD_CHAR)))
                    else:
                        cli.notice(who, msg.format(user, "their", ""))
                    return

        var.ROLES["person"].add(player)
        var.ALL_PLAYERS.append(player)
        if not is_fake_nick(player) or not botconfig.DEBUG_MODE:
            if var.AUTO_TOGGLE_MODES and var.USERS[player]["modes"]:
                for mode in var.USERS[player]["modes"]:
                    cmodes.append(("-"+mode, player))
                var.USERS[player]["moded"].update(var.USERS[player]["modes"])
                var.USERS[player]["modes"] = set()
            mass_mode(cli, cmodes, [])
            cli.msg(chan, "\u0002{0}\u0002 has joined the game and raised the number of players to \u0002{1}\u0002.".format(player, len(pl) + 1))
        if not is_fake_nick(player):
            hostmask = ident + "@" + host
            if hostmask not in var.JOINED_THIS_GAME and (not acc or acc not in var.JOINED_THIS_GAME_ACCS):
                # make sure this only happens once
                var.JOINED_THIS_GAME.add(hostmask)
                if acc:
                    var.JOINED_THIS_GAME_ACCS.add(acc)
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

        t = threading.Timer(10, join_timer_handler, (cli,))
        var.TIMERS["join_pinger"] = (t, time.time(), 10)
        t.daemon = True
        t.start()

    return True

def kill_join(cli, chan):
    pl = var.list_players()
    pl.sort(key=lambda x: x.lower())
    msg = "PING! " + var.break_long_message(pl).replace("\n", "\nPING! ")
    reset_modes_timers(cli)
    reset()
    cli.msg(chan, msg)
    cli.msg(chan, "The current game took too long to start and " +
                  "has been canceled. If you are still active, " +
                  "please join again to start a new game.")
    if var.AFTER_FLASTGAME is not None:
        var.AFTER_FLASTGAME()
        var.AFTER_FLASTGAME = None


@cmd("fjoin", admin_only=True, phases=("none", "join"))
def fjoin(cli, nick, chan, rest):
    """Forces someone to join a game."""
    noticed = False
    fake = False
    if not var.OPPED:
        cli.notice(nick, "Sorry, I'm not opped in {0}.".format(chan))
        cli.msg("ChanServ", "op " + botconfig.CHANNEL)
        return
    if not rest.strip():
        join_player(cli, nick, chan, forced=True)

    for tojoin in re.split(" +",rest):
        tojoin = tojoin.strip()
        if "-" in tojoin:
            first, hyphen, last = tojoin.partition("-")
            if first.isdigit() and last.isdigit():
                if int(last)+1 - int(first) > var.MAX_PLAYERS - len(var.list_players()):
                    cli.msg(chan, "{0}: Too many players to join.".format(nick))
                    break
                fake = True
                for i in range(int(first), int(last)+1):
                    join_player(cli, str(i), chan, forced=True, who=nick)
                continue
        if not tojoin:
            continue
        ul = list(var.USERS.keys())
        ull = [u.lower() for u in ul]
        if tojoin.lower() not in ull or not var.USERS[ul[ull.index(tojoin.lower())]]["inchan"]:
            if not is_fake_nick(tojoin) or not botconfig.DEBUG_MODE:
                if not noticed:  # important
                    cli.msg(chan, nick+(": You may only fjoin "+
                                        "people who are in this channel."))
                    noticed = True
                continue
        if not is_fake_nick(tojoin):
            tojoin = ul[ull.index(tojoin.lower())].strip()
            if not botconfig.DEBUG_MODE and var.ACCOUNTS_ONLY:
                if not var.USERS[tojoin]["account"] or var.USERS[tojoin]["account"] == "*":
                    cli.notice(nick, "{0} is not logged in to NickServ.".format(tojoin))
                    return
        elif botconfig.DEBUG_MODE:
            fake = True
        if tojoin != botconfig.NICK:
            join_player(cli, tojoin, chan, forced=True, who=nick)
        else:
            cli.notice(nick, "No, that won't be allowed.")
    if fake:
        cli.msg(chan, "\u0002{0}\u0002 used fjoin and raised the number of players to \u0002{1}\u0002.".format(nick, len(var.list_players())))

@cmd("fleave", "fquit", admin_only=True, phases=("join", "day", "night"))
def fleave(cli, nick, chan, rest):
    """Forces someone to leave the game."""
    if chan != botconfig.CHANNEL:
        return

    for a in re.split(" +",rest):
        a = a.strip()
        if not a:
            continue
        pl = var.list_players()
        pll = [x.lower() for x in pl]
        if a.lower() in pll:
            a = pl[pll.index(a.lower())]
        else:
            cli.msg(chan, nick+": That person is not playing.")
            return

        message = "\u0002{0}\u0002 is forcing \u0002{1}\u0002 to leave.".format(nick, a)
        if var.get_role(a) != "person" and var.ROLE_REVEAL:
            message += " Say goodbye to the \u0002{0}\u0002.".format(var.get_reveal_role(a))
        if var.PHASE == "join":
            lpl = len(var.list_players()) - 1
            if lpl == 0:
                message += " No more players remaining."
            else:
                message += " New player count: \u0002{0}\u0002".format(lpl)
        cli.msg(chan, message)

        del_player(cli, a, death_triggers=False)


@cmd("fstart", admin_only=True, phases=("join",))
def fstart(cli, nick, chan, rest):
    """Forces the game to start immediately."""
    cli.msg(botconfig.CHANNEL, "\u0002{0}\u0002 has forced the game to start.".format(nick))
    start(cli, nick, botconfig.CHANNEL, forced = True)

@hook("kick")
def on_kicked(cli, nick, chan, victim, reason):
    if victim == botconfig.NICK:
        cli.join(chan)
        if chan == botconfig.CHANNEL:
            cli.msg("ChanServ", "op "+botconfig.CHANNEL)
    if var.AUTO_TOGGLE_MODES and victim in var.USERS:
        var.USERS[victim]["modes"] = set()
        var.USERS[victim]["moded"] = set()

@hook("account")
def on_account(cli, rnick, acc):
    nick, _, ident, host = parse_nick(rnick)
    hostmask = ident + "@" + host
    chan = botconfig.CHANNEL
    if acc == "*" and var.ACCOUNTS_ONLY and nick in var.list_players():
        leave(cli, "account", nick)
        if var.PHASE not in "join":
            cli.mode(chan, "-v", nick)
            cli.notice(nick, "Please reidentify to the account \u0002{0}\u0002".format(var.USERS[nick]["account"]))
        else:
            cli.notice(nick, "Please do not change accounts midgame")
    if nick in var.USERS.keys():
        var.USERS[nick]["ident"] = ident
        var.USERS[nick]["host"] = host
        var.USERS[nick]["account"] = acc
    if nick in var.DISCONNECTED.keys():
        if acc == var.DISCONNECTED[nick][0]:
            if nick in var.USERS and var.USERS[nick]["inchan"]:
                with var.GRAVEYARD_LOCK:
                    hm = var.DISCONNECTED[nick][1]
                    act = var.DISCONNECTED[nick][0]
                    if (acc == act and not var.DISABLE_ACCOUNTS) or (hostmask == hm and not var.ACCOUNTS_ONLY):
                        cli.mode(chan, "+v", nick, nick+"!*@*")
                        del var.DISCONNECTED[nick]
                        var.LAST_SAID_TIME[nick] = datetime.now()
                        cli.msg(chan, "\u0002{0}\u0002 has returned to the village.".format(nick))
                        for r,rset in var.ORIGINAL_ROLES.items():
                            if "(dced)"+nick in rset:
                                rset.remove("(dced)"+nick)
                                rset.add(nick)
                                break
                        if nick in var.DCED_PLAYERS.keys():
                            var.PLAYERS[nick] = var.DCED_PLAYERS.pop(nick)

@cmd("stats", "players", pm=True, phases=("join", "day", "night"))
def stats(cli, nick, chan, rest):
    """Displays the player statistics."""

    pl = var.list_players()

    if nick != chan and (nick in pl or var.PHASE == "join"):
        # only do this rate-limiting stuff if the person is in game
        if (var.LAST_STATS and
            var.LAST_STATS + timedelta(seconds=var.STATS_RATE_LIMIT) > datetime.now()):
            cli.notice(nick, ("This command is rate-limited. " +
                              "Please wait a while before using it again."))
            return

        var.LAST_STATS = datetime.now()

    _nick = nick + ": "
    if nick == chan:
        _nick = ""

    if chan == nick and nick in pl and var.get_role(nick) in var.WOLFCHAT_ROLES:
        ps = pl[:]
        random.shuffle(ps)
        for i, player in enumerate(ps):
            prole = var.get_role(player)
            if prole in var.WOLFCHAT_ROLES:
                cursed = ""
                if player in var.ROLES["cursed villager"]:
                    cursed = "cursed "
                ps[i] = "\u0002{0}\u0002 ({1}{2})".format(player, cursed, prole)
            elif player in var.ROLES["cursed villager"]:
                ps[i] = player + " (cursed)"
        msg = "\u0002{0}\u0002 players: {1}".format(len(pl), ", ".join(ps))

    elif len(pl) > 1:
        msg = "{0}\u0002{1}\u0002 players: {2}".format(_nick,
            len(pl), ", ".join(pl))
    else:
        msg = "{0}\u00021\u0002 player: {1}".format(_nick, pl[0])

    if nick == chan:
        pm(cli, nick, msg)
    else:
        if nick in pl or var.PHASE == "join":
            cli.msg(chan, msg)
        else:
            cli.notice(nick, msg)

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
                if p.startswith("(dced)"):
                    p = p[6:]
                orig_roles[p] = r

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
                if pr == "clone":
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
        order = [r for r in var.role_order() if r in rolecounts]
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
                    message.append("\u0002{0}\u0002 {1}".format(count[0] if count[0] else "\u0002no\u0002", var.plural(role)))
                else:
                    message.append("\u0002{0}\u0002 {1}".format(count[0], role))
            else:
                message.append("\u0002{0}-{1}\u0002 {2}".format(count[0], count[1], var.plural(role)))


    # Show everything mostly as-is; the only hidden information is which
    # role was turned into wolf due to alpha bite or lycanthropy totem.
    # Amnesiac and clone show which roles they turned into. Time lords
    # and VGs show individually instead of being lumped in the default role,
    # and traitor is still based on var.HIDDEN_TRAITOR.
    elif var.STATS_TYPE == "accurate":
        l1 = [k for k in var.ROLES.keys() if var.ROLES[k]]
        l2 = [k for k in var.ORIGINAL_ROLES.keys() if var.ORIGINAL_ROLES[k]]
        rs = set(l1+l2)
        rs = [role for role in var.role_order() if role in rs]

        # picky ordering: villager always last
        if var.DEFAULT_ROLE in rs:
            rs.remove(var.DEFAULT_ROLE)
        rs.append(var.DEFAULT_ROLE)

        bitten_roles = defaultdict(int)
        lycan_roles = defaultdict(int)
        for role in var.BITTEN_ROLES.values():
            bitten_roles[role] += 1

        for role in var.LYCAN_ROLES.values():
            lycan_roles[role] += 1

        vb = "are"
        for role in rs:
            # only show actual roles
            if role in var.TEMPLATE_RESTRICTIONS.keys():
                continue
            count = len(var.ROLES[role])
            if role == "traitor" and var.HIDDEN_TRAITOR:
                continue
            elif role == var.DEFAULT_ROLE:
                if var.HIDDEN_TRAITOR:
                    count += len(var.ROLES["traitor"])
                    count += bitten_roles["traitor"]
                    count += lycan_roles["traitor"]
                count += bitten_roles[var.DEFAULT_ROLE]
                count += lycan_roles[var.DEFAULT_ROLE]
            elif role == "wolf":
                count -= sum(bitten_roles.values())
                count -= sum(lycan_roles.values())
                # GAs turn into FAs, not wolves for bitten_roles
                # (but turn into wolves for lycan_roles)
                count += bitten_roles["guardian angel"]
            elif role == "fallen angel":
                count -= bitten_roles["guardian angel"]
                count += bitten_roles["fallen angel"]
                count += lycan_roles["fallen angel"]
            else:
                count += bitten_roles[role]
                count += lycan_roles[role]

            if role == rs[0]:
                if count == 1:
                    vb = "is"
                else:
                    vb = "are"

            if count != 1:
                if count == 0 and len(var.ORIGINAL_ROLES[role]) == 0:
                    continue
                message.append("\u0002{0}\u0002 {1}".format(count if count else "\u0002no\u0002", var.plural(role)))
            else:
                message.append("\u0002{0}\u0002 {1}".format(count, role))

    # Only show team affiliation, this may be different than what mystics
    # and wolf mystics are told since neutrals are split off. Determination
    # of what numbers are shown is the same as summing up counts in "accurate"
    elif var.STATS_TYPE == "team":
        wolfteam = 0
        villagers = 0
        neutral = 0

        for role, players in var.ROLES.items():
            if role in var.TEMPLATE_RESTRICTIONS.keys():
                continue
            elif role in var.WOLFTEAM_ROLES:
                if role == "traitor" and var.HIDDEN_TRAITOR:
                    villagers += len(players)
                else:
                    wolfteam += len(players)
            elif role in var.TRUE_NEUTRAL_ROLES:
                neutral += len(players)
            else:
                villagers += len(players)

        for role in list(var.BITTEN_ROLES.values()) + list(var.LYCAN_ROLES.values()):
            wolfteam -= 1
            if role in var.WOLFTEAM_ROLES:
                if role == "traitor" and var.HIDDEN_TRAITOR:
                    villagers += 1
                else:
                    wolfteam += 1
            elif role in var.TRUE_NEUTRAL_ROLES:
                neutral += 1
            else:
                villagers += 1

        message.append("\u0002{0}\u0002 {1}".format(wolfteam if wolfteam else "\u0002no\u0002", "wolf" if wolfteam == 1 else "wolves"))
        message.append("\u0002{0}\u0002 {1}".format(villagers if villagers else "\u0002no\u0002", "villager" if villagers == 1 else "villagers"))
        message.append("\u0002{0}\u0002 {1}".format(neutral if neutral else "\u0002no\u0002", "neutral player" if neutral == 1 else "neutral players"))
        vb = "is" if wolfteam == 1 else "are"

    stats_mssg =  "{0}It is currently {4}. There {3} {1}, and {2}.".format(_nick,
                                                        ", ".join(message[0:-1]),
                                                        message[-1],
                                                        vb,
                                                        var.PHASE)
    if nick == chan:
        pm(cli, nick, stats_mssg)
    else:
        if nick in pl or var.PHASE == "join":
            cli.msg(chan, stats_mssg)
        else:
            cli.notice(nick, stats_mssg)

def hurry_up(cli, gameid, change):
    if var.PHASE != "day": return
    if gameid:
        if gameid != var.DAY_ID:
            return

    chan = botconfig.CHANNEL

    if not change:
        cli.msg(chan, ("\u0002As the sun sinks inexorably toward the horizon, turning the lanky pine " +
                      "trees into fire-edged silhouettes, the villagers are reminded that very little " +
                      "time remains for them to reach a decision; if darkness falls before they have done " +
                      "so, the majority will win the vote. No one will be lynched if there " +
                      "are no votes or an even split.\u0002"))
        return


    var.DAY_ID = 0

    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED) - len(var.ASLEEP)
    votesneeded = avail // 2 + 1
    not_lynching = len(var.NO_LYNCH)

    found_dup = False
    maxfound = (0, "")
    votelist = copy.deepcopy(var.VOTES)
    for votee, voters in votelist.items():
        numvotes = 0
        for v in var.IMPATIENT:
            if v in pl and v not in voters and v != votee:
                voters.append(v)
        for v in voters:
            weight = 1
            imp_count = var.IMPATIENT.count(v)
            pac_count = var.PACIFISTS.count(v)
            if pac_count > imp_count:
                weight = 0 # more pacifists than impatience totems
            elif imp_count == pac_count and v not in var.VOTES[votee]:
                weight = 0 # impatience and pacifist cancel each other out, so don't count impatience
            if v in var.ROLES["bureaucrat"] or v in var.INFLUENTIAL: # the two do not stack
                weight *= 2
            numvotes += weight
        if numvotes > maxfound[0]:
            maxfound = (numvotes, votee)
            found_dup = False
        elif numvotes == maxfound[0]:
            found_dup = True
    if maxfound[0] > 0 and not found_dup:
        cli.msg(chan, "The sun sets.")
        chk_decision(cli, force = maxfound[1])  # Induce a lynch
    else:
        cli.msg(chan, ("As the sun sets, the villagers agree to "+
                      "retire to their beds and wait for morning."))
        transition_night(cli)




@cmd("fnight", admin_only=True)
def fnight(cli, nick, chan, rest):
    """Forces the day to end and night to begin."""
    if var.PHASE != "day":
        cli.notice(nick, "It is not daytime.")
    else:
        hurry_up(cli, 0, True)


@cmd("fday", admin_only=True)
def fday(cli, nick, chan, rest):
    """Forces the night to end and the next day to begin."""
    if var.PHASE != "night":
        cli.notice(nick, "It is not nighttime.")
    else:
        transition_day(cli)

# Specify force = "nick" to force nick to be lynched
def chk_decision(cli, force = ""):
    with var.GRAVEYARD_LOCK:
        if var.PHASE != "day":
            return
        chan = botconfig.CHANNEL
        pl = var.list_players()
        avail = len(pl) - len(var.WOUNDED) - len(var.ASLEEP)
        votesneeded = avail // 2 + 1
        not_lynching = list(var.NO_LYNCH)
        for p in var.PACIFISTS:
            if p in pl and p not in var.WOUNDED and p not in var.ASLEEP:
                not_lynching.append(p)

        # .remove() will only remove the first instance, which means this plays nicely with pacifism countering this
        for p in var.IMPATIENT:
            if p in not_lynching:
                not_lynching.remove(p)

        # remove duplicates
        not_lynching = set(not_lynching)

        # we only need 50%+ to not lynch, instead of an actual majority, because a tie would time out day anyway
        # don't check for ABSTAIN_ENABLED here since we may have a case where the majority of people have pacifism totems or something
        if len(not_lynching) >= math.ceil(avail / 2):
            for p in not_lynching:
                if p not in var.NO_LYNCH:
                    cli.msg(botconfig.CHANNEL, "\u0002{0}\u0002 meekly votes not to lynch anyone today.".format(p))
            cli.msg(botconfig.CHANNEL, "The villagers have agreed not to lynch anybody today.")
            var.ABSTAINED = True
            transition_night(cli)
            return
        aftermessage = None
        votelist = copy.deepcopy(var.VOTES)
        for votee, voters in votelist.items():
            impatient_voters = []
            numvotes = 0
            random.shuffle(var.IMPATIENT)
            for v in var.IMPATIENT:
                if v in pl and v not in voters and v != votee and v not in var.WOUNDED and v not in var.ASLEEP:
                    # don't add them in if they have the same number or more of pacifism totems
                    # this matters for desperation totem on the votee
                    imp_count = var.IMPATIENT.count(v)
                    pac_count = var.PACIFISTS.count(v)
                    if pac_count >= imp_count:
                        continue

                    # yes, this means that one of the impatient people will get desperation totem'ed if they didn't
                    # already !vote earlier. sucks to suck. >:)
                    voters.append(v)
                    impatient_voters.append(v)
            for v in voters:
                weight = 1
                imp_count = var.IMPATIENT.count(v)
                pac_count = var.PACIFISTS.count(v)
                if pac_count > imp_count:
                    weight = 0 # more pacifists than impatience totems
                elif imp_count == pac_count and v not in var.VOTES[votee]:
                    weight = 0 # impatience and pacifist cancel each other out, so don't count impatience
                if v in var.ROLES["bureaucrat"] | var.INFLUENTIAL: # the two do not stack
                    weight *= 2
                numvotes += weight

            if numvotes >= votesneeded or votee == force:
                for p in impatient_voters:
                    cli.msg(botconfig.CHANNEL, "\u0002{0}\u0002 impatiently votes for \u0002{1}\u0002.".format(p, votee))

                # roles that prevent any lynch from happening
                if votee in var.ROLES["mayor"] and votee not in var.REVEALED_MAYORS:
                    lmsg = ("While being dragged to the gallows, \u0002{0}\u0002 reveals that they " +
                            "are the \u0002mayor\u0002. The village agrees to let them live for now.").format(votee)
                    var.REVEALED_MAYORS.add(votee)
                    votee = None
                elif votee in var.REVEALED:
                    role = var.get_role(votee)
                    if role == "amnesiac":
                        var.ROLES["amnesiac"].remove(votee)
                        role = var.AMNESIAC_ROLES[votee]
                        var.ROLES[role].add(votee)
                        var.AMNESIACS.add(votee)
                        var.FINAL_ROLES[votee] = role
                        pm(cli, votee, "Your totem clears your amnesia and you now fully remember who you are!")
                        # If wolfteam, don't bother giving list of wolves since night is about to start anyway
                        # Existing wolves also know that someone just joined their team because revealing totem says what they are
                        # If turncoat, set their initial starting side to "none" just in case game ends before they can set it themselves
                        if role == "turncoat":
                            var.TURNCOATS[votee] = ("none", -1)

                    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                    lmsg = ("Before the rope is pulled, \u0002{0}\u0002's totem emits a brilliant flash of light. " +
                            "When the villagers are able to see again, they discover that {0} has escaped! " +
                            "The left-behind totem seems to have taken on the shape of a{1} \u0002{2}\u0002.").format(votee, an, role)
                    votee = None

                else:
                    # roles that end the game upon being lynched
                    if votee in var.ROLES["fool"]:
                        # ends game immediately, with fool as only winner
                        lmsg = random.choice(var.LYNCH_MESSAGES).format(votee, "", var.get_reveal_role(votee))
                        cli.msg(botconfig.CHANNEL, lmsg)
                        if chk_win(cli, winner="@" + votee):
                            return
                    # roles that eliminate other players upon being lynched
                    # note that lovers, assassin, clone, and vengeful ghost are handled in del_player() since they trigger on more than just lynch
                    if votee in var.DESPERATE:
                        # Also kill the very last person to vote them, unless they voted themselves last in which case nobody else dies
                        target = voters[-1]
                        if target != votee:
                            if var.ROLE_REVEAL in ("on", "team"):
                                r1 = var.get_reveal_role(target)
                                an1 = "n" if r1.startswith(("a", "e", "i", "o", "u")) else ""
                                tmsg = ("As the noose is being fitted, \u0002{0}\u0002's totem emits a brilliant flash of light. " +
                                        "When the villagers are able to see again, they discover that \u0002{1}\u0002, " +
                                        "a{2} \u0002{3}\u0002, has fallen over dead.").format(votee, target, an1, r1)
                            else:
                                tmsg = ("As the noose is being fitted, \u0002{0}\u0002's totem emits a brilliant flash of light. " +
                                        "When the villagers are able to see again, they discover that \u0002{1}\u0002 " +
                                        "has fallen over dead.").format(votee, target)
                            cli.msg(botconfig.CHANNEL, tmsg)
                            # we lie to this function so it doesn't devoice the player yet. instead, we'll let the call further down do it
                            del_player(cli, target, True, end_game=False, killer_role="shaman", ismain=False) # do not end game just yet, we have more killin's to do!
                    # Other
                    if votee in var.ROLES["jester"]:
                        var.JESTERS.add(votee)

                    if var.ROLE_REVEAL in ("on", "team"):
                        rrole = var.get_reveal_role(votee)
                        an = "n" if rrole.startswith(("a", "e", "i", "o", "u")) else ""
                        lmsg = random.choice(var.LYNCH_MESSAGES).format(votee, an, rrole)
                    else:
                        lmsg = random.choice(var.LYNCH_MESSAGES_NO_REVEAL).format(votee)
                cli.msg(botconfig.CHANNEL, lmsg)
                if aftermessage != None:
                    cli.msg(botconfig.CHANNEL, aftermessage)
                if del_player(cli, votee, True, killer_role="villager"):
                    transition_night(cli)
                break

@cmd("votes", pm=True, phases=("join", "day", "night"))
def show_votes(cli, nick, chan, rest):
    """Displays the voting statistics."""

    pl = var.list_players()
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
            the_message += "{0}Votes needed for a majority: {1}".format("; " if votelist else "", int(math.ceil(len(pl)/2)))

        with var.WARNING_LOCK:
            if var.START_VOTES:
                the_message += "; Votes to start the game: {} ({})".format(len(var.START_VOTES), ', '.join(var.START_VOTES))

    elif var.PHASE == "night":
        cli.notice(nick, "Voting is only during the day.")
        return
    else:
        if (chan != nick and var.LAST_VOTES and var.VOTES_RATE_LIMIT and
                var.LAST_VOTES + timedelta(seconds=var.VOTES_RATE_LIMIT) >
                datetime.now()):
            cli.notice(nick, "This command is rate-limited. Please wait a while "
                             "before using it again.")
            return

        _nick = nick + ": "
        if chan == nick:
            _nick = ""

        if chan != nick and nick in pl:
            var.LAST_VOTES = datetime.now()

        if not var.VOTES.values():
            msg = _nick + "No votes yet."

            if nick in pl:
                var.LAST_VOTES = None  # reset
        else:
            votelist = ["{0}: {1} ({2})".format(votee,
                                             len(var.VOTES[votee]),
                                             " ".join(var.VOTES[votee]))
                        for votee in var.VOTES.keys()]
            msg = "{0}{1}".format(_nick, ", ".join(votelist))

        if chan == nick:
            pm(cli, nick, msg)
        elif nick not in pl and var.PHASE not in ("none", "join"):
            cli.notice(nick, msg)
        else:
            cli.msg(chan, msg)

        pl = var.list_players()
        avail = len(pl) - len(var.WOUNDED) - len(var.ASLEEP)
        votesneeded = avail // 2 + 1
        not_voting = len(var.NO_LYNCH)
        if not_voting == 1:
            plural = " has"
        else:
            plural = "s have"
        the_message = ("{0}\u0002{1}\u0002 players, \u0002{2}\u0002 votes "
                       "required to lynch, \u0002{3}\u0002 players available to "
                       "vote.").format(_nick, len(pl), votesneeded, avail)
        if var.ABSTAIN_ENABLED:
            the_message += " \u0002{0}\u0002 player{1} refrained from voting.".format(not_voting, plural)

    if chan == nick:
        pm(cli, nick, the_message)
    elif nick not in pl and var.PHASE != "join":
        cli.notice(nick, the_message)
    else:
        cli.msg(chan, the_message)

def chk_traitor(cli):
    realwolves = var.WOLF_ROLES - {"wolf cub"}
    if len(var.list_players(realwolves)) > 0:
        return # actual wolves still alive

    wcl = copy.copy(var.ROLES["wolf cub"])
    ttl = copy.copy(var.ROLES["traitor"])

    event = Event("chk_traitor", {})
    if event.dispatch(cli, var, wcl, ttl):
        for wc in wcl:
            var.ROLES["wolf"].add(wc)
            var.ROLES["wolf cub"].remove(wc)
            var.FINAL_ROLES[wc] = "wolf"
            pm(cli, wc, "You have grown up into a wolf and vowed to take revenge for your dead parents!")
            debuglog(wc, "(wolf cub) GROW UP")

        if len(var.ROLES["wolf"]) == 0:
            for tt in ttl:
                var.ROLES["wolf"].add(tt)
                var.ROLES["traitor"].remove(tt)
                var.FINAL_ROLES[tt] = "wolf"
                var.ROLES["cursed villager"].discard(tt)
                pm(cli, tt, "HOOOOOOOOOWL. You have become... a wolf!\n"+
                            "It is up to you to avenge your fallen leaders!")
                debuglog(tt, "(traitor) TURNING")

            if len(var.ROLES["wolf"]) > 0:
                var.TRAITOR_TURNED = True
                cli.msg(botconfig.CHANNEL, "\u0002The villagers, during their celebrations, are "+
                                           "frightened as they hear a loud howl. The wolves are "+
                                           "not gone!\u0002")

def stop_game(cli, winner = "", abort = False, additional_winners = None):
    chan = botconfig.CHANNEL
    if abort:
        cli.msg(chan, "The role attribution failed 3 times. Game was canceled.")
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
    gameend_msg = ("Game lasted \u0002{0:0>2}:{1:0>2}\u0002. " +
                   "\u0002{2:0>2}:{3:0>2}\u0002 was day. " +
                   "\u0002{4:0>2}:{5:0>2}\u0002 was night. ").format(tmin, tsec,
                                                                     daymin, daysec,
                                                                     nitemin, nitesec)

    if not abort:
        cli.msg(chan, gameend_msg)

    roles_msg = []

    origroles = {} #nick based list of original roles
    rolelist = copy.deepcopy(var.ORIGINAL_ROLES)
    for role, playerlist in var.ORIGINAL_ROLES.items():
        if role in var.TEMPLATE_RESTRICTIONS.keys():
            continue
        for p in playerlist:
            player = p #with (dced) still in
            if p.startswith("(dced)"):
                p = p[6:]
            # Show cubs and traitors as themselves even if they turned into wolf
            if p in var.FINAL_ROLES and var.FINAL_ROLES[p] != role and (var.FINAL_ROLES[p] != "wolf" or role not in ("wolf cub", "traitor")):
                origroles[p] = role
                rolelist[role].remove(player)
                rolelist[var.FINAL_ROLES[p]].add(p)
    prev = False
    for role in var.role_order():
        if len(rolelist[role]) == 0:
            continue
        playersformatted = []
        for p in rolelist[role]:
            if p.startswith("(dced)"):
                p = p[6:]
            if p in origroles and role not in var.TEMPLATE_RESTRICTIONS.keys():
                playersformatted.append("\u0002{0}\u0002 ({1}{2})".format(p,
                                        "" if prev else "was ", origroles[p]))
                prev = True
            elif role == "amnesiac":
                playersformatted.append("\u0002{0}\u0002 (would be {1})".format(p,
                                        var.AMNESIAC_ROLES[p]))
            else:
                playersformatted.append("\u0002{0}\u0002".format(p))
        if len(rolelist[role]) == 2:
            msg = "The {1} were {0[0]} and {0[1]}."
            roles_msg.append(msg.format(playersformatted, var.plural(role)))
        elif len(rolelist[role]) == 1:
            roles_msg.append("The {1} was {0[0]}.".format(playersformatted, role))
        else:
            msg = "The {2} were {0}, and {1}."
            roles_msg.append(msg.format(", ".join(playersformatted[0:-1]),
                                                  playersformatted[-1],
                                                  var.plural(role)))
    message = ""
    count = 0
    if not abort:
        done = {}
        lovers = []
        for lover1, llist in var.ORIGINAL_LOVERS.items():
            for lover2 in llist:
                # check if already said the pairing
                if (lover1 in done and lover2 in done[lover1]) or (lover2 in done and lover1 in done[lover2]):
                    continue
                lovers.append("\u0002{0}\u0002/\u0002{1}\u0002".format(lover1, lover2))
                if lover1 in done:
                    done[lover1].append(lover2)
                else:
                    done[lover1] = [lover2]
        if len(lovers) == 1 or len(lovers) == 2:
            roles_msg.append("The lovers were {0}.".format(" and ".join(lovers)))
        elif len(lovers) > 2:
            roles_msg.append("The lovers were {0}, and {1}".format(", ".join(lovers[0:-1]), lovers[-1]))

        cli.msg(chan, var.break_long_message(roles_msg))

    # Only update if someone actually won, "" indicates everyone died or abnormal game stop
    if winner != "":
        plrl = {}
        winners = []
        if additional_winners is not None:
            winners.extend(additional_winners)
        for role,ppl in var.ORIGINAL_ROLES.items():
            if role in var.TEMPLATE_RESTRICTIONS.keys():
                continue
            for x in ppl:
                if x != None:
                    if x in var.FINAL_ROLES:
                        plrl[x] = var.FINAL_ROLES[x]
                    else:
                        plrl[x] = role
        for plr, rol in plrl.items():
            orol = rol # original role, since we overwrite rol in case of clone
            splr = plr # plr stripped of the (dced) bit at the front, since other dicts don't have that
            # TODO: figure out how player stats should work when var.DISABLE_ACCOUNTS is True; likely track by nick
            if plr.startswith("(dced)") and plr[6:] in var.DCED_PLAYERS.keys():
                splr = plr[6:]
                if var.DISABLE_ACCOUNTS:
                    acc = splr
                else:
                    acc = var.DCED_PLAYERS[plr[6:]]["account"]
            elif plr in var.PLAYERS.keys():
                if var.DISABLE_ACCOUNTS:
                    acc = plr
                else:
                    acc = var.PLAYERS[plr]["account"]
            else:
                acc = "*"  #probably fjoin'd fake

            won = False
            iwon = False
            # determine if this player's team won
            if rol in var.WOLFTEAM_ROLES:  # the player was wolf-aligned
                if winner == "wolves":
                    won = True
            elif rol in var.TRUE_NEUTRAL_ROLES:
                # most true neutral roles never have a team win, only individual wins
                if winner == "monsters" and rol == "monster":
                    won = True
                if winner == "pipers" and rol == "piper":
                    won = True
                if rol == "turncoat" and splr in var.TURNCOATS and var.TURNCOATS[splr][0] != "none":
                    won = (winner == var.TURNCOATS[splr][0])
            elif rol in ("amnesiac", "vengeful ghost") and splr not in var.VENGEFUL_GHOSTS:
                if var.DEFAULT_ROLE == "villager" and winner == "villagers":
                    won = True
                elif var.DEFAULT_ROLE == "cultist" and winner == "wolves":
                    won = True
            elif winner == "villagers":
                won = True

            survived = var.list_players()
            if plr.startswith("(dced)"):
                # You get NOTHING! You LOSE! Good DAY, sir!
                won = False
                iwon = False
            elif rol == "fool" and "@" + splr == winner:
                iwon = True
            elif winner != "lovers" and splr in var.LOVERS and splr in survived and len([x for x in var.LOVERS[splr] if x in survived]) > 0:
                for lvr in var.LOVERS[splr]:
                    if lvr not in survived:
                        # cannot win with dead lover (if splr in survived and lvr is not, that means lvr idled out)
                        continue

                    lvrrol = "" #somehow lvrrol wasn't set and caused a crash once
                    if lvr in plrl:
                        lvrrol = plrl[lvr]

                    if not winner.startswith("@") and winner not in ("monsters", "pipers"):
                        iwon = True
                        break
                    elif winner.startswith("@") and winner == "@" + lvr and var.LOVER_WINS_WITH_FOOL:
                        iwon = True
                        break
                    elif winner == "monsters" and lvrrol == "monster":
                        iwon = True
                        break
                    elif winner == "pipers" and lvrrol == "piper":
                        iwon = True
                        break
            elif rol == "monster" and splr in survived and winner == "monsters":
                iwon = True
            elif rol == "piper" and splr in survived and winner == "pipers":
                iwon = True
            elif rol == "crazed shaman" or rol == "clone":
                # For clone, this means they ended game while being clone and not some other role
                if splr in survived and not winner.startswith("@") and winner not in ("monsters", "pipers"):
                    iwon = True
            elif rol == "vengeful ghost":
                if not winner.startswith("@") and winner not in ("monsters", "pipers"):
                    if won and splr in survived:
                        iwon = True
                    elif splr in var.VENGEFUL_GHOSTS and var.VENGEFUL_GHOSTS[splr] == "villagers" and winner == "wolves":
                        won = True
                        iwon = True
                    elif splr in var.VENGEFUL_GHOSTS and var.VENGEFUL_GHOSTS[splr] == "!villagers" and winner == "wolves":
                        # Starts with ! if they were driven off by retribution totem
                        won = True
                        iwon = False
                    elif splr in var.VENGEFUL_GHOSTS and var.VENGEFUL_GHOSTS[splr] == "wolves" and winner == "villagers":
                        won = True
                        iwon = True
                    elif splr in var.VENGEFUL_GHOSTS and var.VENGEFUL_GHOSTS[splr] == "!wolves" and winner == "villagers":
                        won = True
                        iwon = False
                    else:
                        won = False
                        iwon = False
            elif rol == "jester" and splr in var.JESTERS:
                iwon = True
            elif not iwon:
                iwon = won and splr in survived  # survived, team won = individual win

            if acc != "*":
                var.update_role_stats(acc, orol, won, iwon)
                for role in var.TEMPLATE_RESTRICTIONS.keys():
                    if plr in var.ORIGINAL_ROLES[role]:
                        var.update_role_stats(acc, role, won, iwon)
                if splr in var.LOVERS:
                    var.update_role_stats(acc, "lover", won, iwon)

            if won or iwon:
                winners.append(splr)

        var.update_game_stats(var.CURRENT_GAMEMODE.name, len(survived) + len(var.DEAD), winner)

        # spit out the list of winners
        winners.sort()
        if len(winners) == 1:
            cli.msg(chan, "The winner is \u0002{0}\u0002.".format(winners[0]))
        elif len(winners) == 2:
            cli.msg(chan, "The winners are \u0002{0}\u0002 and \u0002{1}\u0002.".format(winners[0], winners[1]))
        elif len(winners) > 2:
            nicklist = ("\u0002" + x + "\u0002" for x in winners[0:-1])
            cli.msg(chan, "The winners are {0}, and \u0002{1}\u0002.".format(", ".join(nicklist), winners[-1]))

    reset_modes_timers(cli)

    reset()

    # This must be after reset()
    if var.AFTER_FLASTGAME is not None:
        var.AFTER_FLASTGAME()
        var.AFTER_FLASTGAME = None
    if var.ADMIN_TO_PING:  # It was an flastgame
        cli.msg(chan, "PING! " + var.ADMIN_TO_PING)
        var.ADMIN_TO_PING = None

    return True

def chk_win(cli, end_game=True, winner=None):
    """ Returns True if someone won """
    chan = botconfig.CHANNEL
    lpl = len(var.list_players())

    if var.PHASE == "join":
        if lpl == 0:
            reset_modes_timers(cli)

            reset()

            # This must be after reset()
            if var.AFTER_FLASTGAME is not None:
                var.AFTER_FLASTGAME()
                var.AFTER_FLASTGAME = None
            if var.ADMIN_TO_PING:  # It was an flastgame
                cli.msg(chan, "PING! " + var.ADMIN_TO_PING)
                var.ADMIN_TO_PING = None

            return True

        return False

    with var.GRAVEYARD_LOCK:
        if var.PHASE not in ("day", "night"):
            return False #some other thread already ended game probably

        lwolves = len(var.list_players(var.WOLFCHAT_ROLES))
        lcubs = len(var.ROLES.get("wolf cub", ()))
        lrealwolves = len(var.list_players(var.WOLF_ROLES - {"wolf cub"}))
        lmonsters = len(var.ROLES.get("monster", ()))
        ltraitors = len(var.ROLES.get("traitor", ()))
        lpipers = len(var.ROLES.get("piper", ()))
        if var.PHASE == "day":
            for p in var.WOUNDED | var.ASLEEP:
                try:
                    role = var.get_role(p)
                    if role in var.WOLFCHAT_ROLES:
                        lwolves -= 1
                    else:
                        lpl -= 1
                except KeyError:
                    pass

        return chk_win_conditions(lpl, lwolves, lcubs, lrealwolves, lmonsters, ltraitors, lpipers, cli, end_game, winner)

def chk_win_conditions(lpl, lwolves, lcubs, lrealwolves, lmonsters, ltraitors, lpipers, cli, end_game=True, winner=None):
    """Internal handler for the chk_win function."""
    chan = botconfig.CHANNEL
    with var.GRAVEYARD_LOCK:
        message = ""
        # fool won, chk_win was called from !lynch
        if winner and winner.startswith("@"):
            message = "Game over! The fool has been lynched, causing them to win."
        elif lpl < 1:
            message = "Game over! There are no players remaining. Nobody wins."
            winner = "none"
        elif var.PHASE == "day" and lpipers and len(var.list_players()) - lpipers == len(var.CHARMED - var.ROLES["piper"]):
            winner = "pipers"
            message = ("Game over! Everyone has fallen victim to the charms of the " +
                       "piper{0}. The piper{0} lead{1} the villagers away from the village, " +
                       "never to return...").format("s" if lpipers > 1 else "", "s" if lpipers == 1 else "")
        elif lrealwolves == 0 and ltraitors == 0 and lcubs == 0:
            if lmonsters > 0:
                plural = "s" if lmonsters > 1 else ""
                message = ("Game over! All the wolves are dead! As the villagers start preparing the BBQ, " +
                           "the monster{0} quickly kill{1} the remaining villagers, " +
                           "causing the monster{0} to win.").format(plural, "" if plural else "s")
                winner = "monsters"
            else:
                message = ("Game over! All the wolves are dead! The villagers " +
                          "chop them up, BBQ them, and have a hearty meal.")
                winner = "villagers"
        elif lwolves == lpl / 2:
            if lmonsters > 0:
                plural = "s" if lmonsters > 1 else ""
                message = ("Game over! There are the same number of wolves as uninjured villagers. " +
                           "The wolves overpower the villagers but then get destroyed by the monster{0}, " +
                           "causing the monster{0} to win.").format(plural)
                winner = "monsters"
            else:
                message = ("Game over! There are the same number of wolves as " +
                          "uninjured villagers. The wolves overpower the villagers and win.")
                winner = "wolves"
        elif lwolves > lpl / 2:
            if lmonsters > 0:
                plural = "s" if lmonsters > 1 else ""
                message = ("Game over! There are more wolves than uninjured villagers. " +
                           "The wolves overpower the villagers but then get destroyed by the monster{0}, " +
                           "causing the monster{0} to win.").format(plural)
                winner = "monsters"
            else:
                message = ("Game over! There are more wolves than "+
                          "uninjured villagers. The wolves overpower the villagers and win.")
                winner = "wolves"
        elif lrealwolves == 0:
            chk_traitor(cli)
            # update variables for recursive call (this shouldn't happen when checking 'random' role attribution, where it would probably fail)
            lwolves = len(var.list_players(var.WOLFCHAT_ROLES))
            lcubs = len(var.ROLES.get("wolf cub", ()))
            lrealwolves = len(var.list_players(var.WOLF_ROLES - {"wolf cub"}))
            ltraitors = len(var.ROLES.get("traitor", ()))
            return chk_win_conditions(lpl, lwolves, lcubs, lrealwolves, lmonsters, ltraitors, lpipers, cli, end_game)

        event = Event("chk_win", {"winner": winner, "message": message, "additional_winners": None})
        event.dispatch(var, lpl, lwolves, lrealwolves)
        winner = event.data["winner"]
        message = event.data["message"]

        if winner is None:
            return False

        if end_game:
            if event.data["additional_winners"] is None:
                players = []
            else:
                players = ["{0} ({1})".format(x, var.get_role(x)) for x in event.data["additional_winners"]]
            if winner == "monsters":
                for plr in var.ROLES["monster"]:
                    players.append("{0} ({1})".format(plr, var.get_role(plr)))
            elif winner == "wolves":
                for plr in var.list_players(var.WOLFTEAM_ROLES):
                    players.append("{0} ({1})".format(plr, var.get_role(plr)))
            elif winner == "villagers":
                vroles = (role for role in var.ROLES.keys() if var.ROLES[role] and role not in (var.WOLFTEAM_ROLES | var.TRUE_NEUTRAL_ROLES | var.TEMPLATE_RESTRICTIONS.keys()))
                for plr in var.list_players(vroles):
                    players.append("{0} ({1})".format(plr, var.get_role(plr)))
            elif winner == "pipers":
                for plr in var.ROLES["piper"]:
                    players.append("{0} ({1})".format(plr, var.get_role(plr)))
            debuglog("WIN:", winner)
            debuglog("PLAYERS:", ", ".join(players))
            cli.msg(chan, message)
            stop_game(cli, winner, additional_winners=event.data["additional_winners"])
        return True

def del_player(cli, nick, forced_death = False, devoice = True, end_game = True, death_triggers = True, killer_role = "", deadlist = [], original = "", cmode = [], ismain = True):
    """
    Returns: False if one side won.
    arg: forced_death = True when lynched or when the seer/wolf both don't act
    """

    def refresh_pl(old_pl):
        return [p for p in var.list_players() if p in old_pl]

    t = time.time()  #  time

    var.LAST_STATS = None # reset
    var.LAST_VOTES = None

    with var.GRAVEYARD_LOCK:
        if not var.GAME_ID or var.GAME_ID > t:
            #  either game ended, or a new game has started.
            return False
        ret = True
        pl = var.list_players()
        for dead in deadlist:
            if dead in pl:
                pl.remove(dead)
        if nick != None and (nick == original or nick in pl):
            nickrole = var.get_role(nick)
            nicktpls = var.get_templates(nick)
            var.del_player(nick)
            if nick in pl:
                pl.remove(nick)
            # handle roles that trigger on death
            # clone happens regardless of death_triggers being true or not
            if var.PHASE in ("night", "day"):
                clones = copy.copy(var.ROLES["clone"])
                for clone in clones:
                    if clone in var.CLONED:
                        target = var.CLONED[clone]
                        if nick == target and clone in var.CLONED:
                            # clone is cloning nick, so clone becomes nick's role
                            # clone does NOT get any of nick's templates (gunner/assassin/etc.)
                            del var.CLONED[clone]
                            var.ROLES["clone"].remove(clone)
                            if nickrole == "amnesiac":
                                # clone gets the amnesiac's real role
                                sayrole = var.AMNESIAC_ROLES[nick]
                                var.FINAL_ROLES[clone] = sayrole
                                var.ROLES[sayrole].add(clone)
                            else:
                                var.ROLES[nickrole].add(clone)
                                var.FINAL_ROLES[clone] = nickrole
                                sayrole = nickrole
                            debuglog("{0} (clone) CLONE DEAD PLAYER: {1} ({2})".format(clone, target, sayrole))
                            # if cloning time lord or vengeful ghost, say they are villager instead
                            if sayrole == "time lord":
                                sayrole = "villager"
                            elif sayrole == "vengeful ghost":
                                sayrole = var.DEFAULT_ROLE
                            an = "n" if sayrole.startswith(("a", "e", "i", "o", "u")) else ""
                            pm(cli, clone, "You are now a{0} \u0002{1}\u0002.".format(an, sayrole))
                            # if a clone is cloning a clone, clone who the old clone cloned
                            if nickrole == "clone" and nick in var.CLONED:
                                if var.CLONED[nick] == clone:
                                    pm(cli, clone, "It appears that \u0002{0}\u0002 was cloning you, so you are now stuck as a clone forever. How sad.".format(nick))
                                else:
                                    var.CLONED[clone] = var.CLONED[nick]
                                    pm(cli, clone, "You will now be cloning \u0002{0}\u0002 if they die.".format(var.CLONED[clone]))
                                    debuglog("{0} (clone) CLONE: {1} ({2})".format(clone, var.CLONED[clone], var.get_role(var.CLONED[clone])))
                            elif nickrole in var.WOLFCHAT_ROLES:
                                wolves = var.list_players(var.WOLFCHAT_ROLES)
                                wolves.remove(clone) # remove self from list
                                for wolf in wolves:
                                    pm(cli, wolf, "\u0002{0}\u0002 cloned \u0002{1}\u0002 and has now become a wolf!".format(clone, nick))
                                if var.PHASE == "day":
                                    random.shuffle(wolves)
                                    for i, wolf in enumerate(wolves):
                                        wolfrole = var.get_role(wolf)
                                        cursed = ""
                                        if wolf in var.ROLES["cursed villager"]:
                                            cursed = "cursed "
                                        wolves[i] = "\u0002{0}\u0002 ({1}{2})".format(wolf, cursed, wolfrole)

                                    if len(wolves):
                                        pm(cli, clone, "Wolves: " + ", ".join(wolves))
                                    else:
                                        pm(cli, clone, "There are no other wolves")
                            elif nickrole == "turncoat":
                                var.TURNCOATS[clone] = ("none", -1)

                if nickrole == "clone" and nick in var.CLONED:
                    del var.CLONED[nick]

            if death_triggers and var.PHASE in ("night", "day"):
                if nick in var.LOVERS:
                    others = var.LOVERS[nick].copy()
                    var.LOVERS[nick].clear()
                    for other in others:
                        if other not in pl:
                            continue # already died somehow
                        if nick not in var.LOVERS[other]:
                            continue
                        var.LOVERS[other].remove(nick)
                        if var.ROLE_REVEAL in ("on", "team"):
                            role = var.get_reveal_role(other)
                            an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                            message = ("Saddened by the loss of their lover, \u0002{0}\u0002, " +
                                       "a{1} \u0002{2}\u0002, commits suicide.").format(other, an, role)
                        else:
                            message = "Saddened by the loss of their lover, \u0002{0}\u0002 commits suicide.".format(other)
                        cli.msg(botconfig.CHANNEL, message)
                        debuglog("{0} ({1}) LOVE SUICIDE: {2} ({3})".format(other, var.get_role(other), nick, nickrole))
                        del_player(cli, other, True, end_game = False, killer_role = killer_role, deadlist = deadlist, original = original, ismain = False)
                        pl = refresh_pl(pl)
                if "assassin" in nicktpls:
                    if nick in var.TARGETED:
                        target = var.TARGETED[nick]
                        del var.TARGETED[nick]
                        if target != None and target in pl:
                            if "totem" in var.ACTIVE_PROTECTIONS[target] and nickrole != "fallen angel":
                                var.ACTIVE_PROTECTIONS[target].remove("totem")
                                message = ("Before dying, \u0002{0}\u0002 quickly attempts to slit \u0002{1}\u0002's throat; " +
                                           "however, {1}'s totem emits a brilliant flash of light, causing the attempt to miss.").format(nick, target)
                                cli.msg(botconfig.CHANNEL, message)
                            elif "angel" in var.ACTIVE_PROTECTIONS[target] and nickrole != "fallen angel":
                                var.ACTIVE_PROTECTIONS[target].remove("angel")
                                message = ("Before dying, \u0002{0}\u0002 quickly attempts to slit \u0002{1}\u0002's throat; " +
                                           "however, a guardian angel was on duty and able to foil the attempt.").format(nick, target)
                                cli.msg(botconfig.CHANNEL, message)
                            elif "bodyguard" in var.ACTIVE_PROTECTIONS[target] and nickrole != "fallen angel":
                                var.ACTIVE_PROTECTIONS[target].remove("bodyguard")
                                for ga in var.ROLES["bodyguard"]:
                                    if var.GUARDED.get(ga) == target:
                                        message = ("Before dying, \u0002{0}\u0002 quickly attempts to slit \u0002{1}\u0002's throat; " +
                                                   "however, \u0002{2}\u0002, a bodyguard, sacrificed their life to protect them.").format(nick, target, ga)
                                        cli.msg(botconfig.CHANNEL, message)
                                        del_player(cli, ga, True, end_game = False, killer_role = nickrole, deadlist = deadlist, original = original, ismain = False)
                                        pl.remove(ga)
                                        break
                            else:
                                if var.ROLE_REVEAL in ("on", "team"):
                                    role = var.get_reveal_role(target)
                                    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                                    message = ("Before dying, \u0002{0}\u0002 quickly slits \u0002{1}\u0002's throat. " +
                                               "The village mourns the loss of a{2} \u0002{3}\u0002.").format(nick, target, an, role)
                                else:
                                    message = "Before dying, \u0002{0}\u0002 quickly slits \u0002{1}\u0002's throat.".format(nick, target)
                                cli.msg(botconfig.CHANNEL, message)
                                debuglog("{0} ({1}) ASSASSINATE: {2} ({3})".format(nick, nickrole, target, var.get_role(target)))
                                del_player(cli, target, True, end_game = False, killer_role = nickrole, deadlist = deadlist, original = original, ismain = False)
                                pl = refresh_pl(pl)

                if nickrole == "time lord":
                    if "DAY_TIME_LIMIT" not in var.ORIGINAL_SETTINGS:
                        var.ORIGINAL_SETTINGS["DAY_TIME_LIMIT"] = var.DAY_TIME_LIMIT
                    if "DAY_TIME_WARN" not in var.ORIGINAL_SETTINGS:
                        var.ORIGINAL_SETTINGS["DAY_TIME_WARN"] = var.DAY_TIME_WARN
                    if "SHORT_DAY_LIMIT" not in var.ORIGINAL_SETTINGS:
                        var.ORIGINAL_SETTINGS["SHORT_DAY_LIMIT"] = var.SHORT_DAY_LIMIT
                    if "SHORT_DAY_WARN" not in var.ORIGINAL_SETTINGS:
                        var.ORIGINAL_SETTINGS["SHORT_DAY_WARN"] = var.SHORT_DAY_WARN
                    if "NIGHT_TIME_LIMIT" not in var.ORIGINAL_SETTINGS:
                        var.ORIGINAL_SETTINGS["NIGHT_TIME_LIMIT"] = var.NIGHT_TIME_LIMIT
                    if "NIGHT_TIME_WARN" not in var.ORIGINAL_SETTINGS:
                        var.ORIGINAL_SETTINGS["NIGHT_TIME_WARN"] = var.NIGHT_TIME_WARN
                    var.DAY_TIME_LIMIT = var.TIME_LORD_DAY_LIMIT
                    var.DAY_TIME_WARN = var.TIME_LORD_DAY_WARN
                    var.SHORT_DAY_LIMIT = var.TIME_LORD_DAY_LIMIT
                    var.SHORT_DAY_WARN = var.TIME_LORD_DAY_WARN
                    var.NIGHT_TIME_LIMIT = var.TIME_LORD_NIGHT_LIMIT
                    var.NIGHT_TIME_WARN = var.TIME_LORD_NIGHT_WARN
                    cli.msg(botconfig.CHANNEL, ("Tick tock! Since the time lord has died, " +
                                                "day will now only last {0} seconds and night will now only " +
                                                "last {1} seconds!").format(var.TIME_LORD_DAY_LIMIT, var.TIME_LORD_NIGHT_LIMIT))
                    if var.GAMEPHASE == "day" and timeleft_internal("day") > var.DAY_TIME_LIMIT and var.DAY_TIME_LIMIT > 0:
                        if "day" in var.TIMERS:
                            var.TIMERS["day"][0].cancel()
                        t = threading.Timer(var.DAY_TIME_LIMIT, hurry_up, [cli, var.DAY_ID, True])
                        var.TIMERS["day"] = (t, time.time(), var.DAY_TIME_LIMIT)
                        t.daemon = True
                        t.start()
                        # Don't duplicate warnings, e.g. only set the warn timer if a warning was not already given
                        if "day_warn" in var.TIMERS and var.TIMERS["day_warn"][0].isAlive():
                            var.TIMERS["day_warn"][0].cancel()
                            t = threading.Timer(var.DAY_TIME_WARN, hurry_up, [cli, var.DAY_ID, False])
                            var.TIMERS["day_warn"] = (t, time.time(), var.DAY_TIME_WARN)
                            t.daemon = True
                            t.start()
                    elif var.GAMEPHASE == "night" and timeleft_internal("night") > var.NIGHT_TIME_LIMIT and var.NIGHT_TIME_LIMIT > 0:
                        if "night" in var.TIMERS:
                            var.TIMERS["night"][0].cancel()
                        t = threading.Timer(var.NIGHT_TIME_LIMIT, hurry_up, [cli, var.NIGHT_ID, True])
                        var.TIMERS["night"] = (t, time.time(), var.NIGHT_TIME_LIMIT)
                        t.daemon = True
                        t.start()
                        # Don't duplicate warnings, e.g. only set the warn timer if a warning was not already given
                        if "night_warn" in var.TIMERS and var.TIMERS["night_warn"][0].isAlive():
                            var.TIMERS["night_warn"][0].cancel()
                            t = threading.Timer(var.NIGHT_TIME_WARN, hurry_up, [cli, var.NIGHT_ID, False])
                            var.TIMERS["night_warn"] = (t, time.time(), var.NIGHT_TIME_WARN)
                            t.daemon = True
                            t.start()

                    debuglog(nick, "(time lord) TRIGGER")
                if nickrole == "vengeful ghost":
                    if killer_role in var.WOLFTEAM_ROLES:
                        var.VENGEFUL_GHOSTS[nick] = "wolves"
                    else:
                        var.VENGEFUL_GHOSTS[nick] = "villagers"
                    pm(cli, nick, ("OOOooooOOOOooo! You are the \u0002vengeful ghost\u0002. It is now your job " +
                                   "to exact your revenge on the \u0002{0}\u0002 that killed you.").format(var.VENGEFUL_GHOSTS[nick]))
                    debuglog(nick, "(vengeful ghost) TRIGGER", var.VENGEFUL_GHOSTS[nick])
                if nickrole == "wolf cub":
                    var.ANGRY_WOLVES = True
                if nickrole in var.WOLF_ROLES:
                    if var.GAMEPHASE == "day":
                        var.ALPHA_ENABLED = True
                    for bitten, days in var.BITTEN.items():
                        brole = var.get_role(bitten)
                        if brole not in var.WOLF_ROLES and days > 0:
                            var.BITTEN[bitten] -= 1
                            pm(cli, bitten, ("Upon gazing at {0}'s lifeless body, you feel a sharp pang of regret and vengeance. " +
                                             "You quickly look away and the feelings subside...").format(nick))

                if nickrole == "mad scientist":
                    # kills the 2 players adjacent to them in the original players listing (in order of !joining)
                    # if those players are already dead, nothing happens
                    index = var.ALL_PLAYERS.index(nick)
                    targets = []
                    target1 = var.ALL_PLAYERS[index - 1]
                    target2 = var.ALL_PLAYERS[index + 1 if index < len(var.ALL_PLAYERS) - 1 else 0]
                    if len(var.ALL_PLAYERS) >= var.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS:
                        # determine left player
                        i = index
                        while True:
                            i -= 1
                            if i < 0:
                                i = len(var.ALL_PLAYERS) - 1
                            if var.ALL_PLAYERS[i] in pl or var.ALL_PLAYERS[i] == nick:
                                target1 = var.ALL_PLAYERS[i]
                                break
                        # determine right player
                        i = index
                        while True:
                            i += 1
                            if i >= len(var.ALL_PLAYERS):
                                i = 0
                            if var.ALL_PLAYERS[i] in pl or var.ALL_PLAYERS[i] == nick:
                                target2 = var.ALL_PLAYERS[i]
                                break

                    if target1 in pl:
                        if target2 in pl and target1 != target2:
                            if var.ROLE_REVEAL in ("on", "team"):
                                r1 = var.get_reveal_role(target1)
                                an1 = "n" if r1.startswith(("a", "e", "i", "o", "u")) else ""
                                r2 = var.get_reveal_role(target2)
                                an2 = "n" if r2.startswith(("a", "e", "i", "o", "u")) else ""
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002, " +
                                        "a{2} \u0002{3}\u0002, and \u0002{4}\u0002, a{5} \u0002{6}\u0002, " +
                                        "get hit by the chemicals and die.").format(nick, target1, an1, r1, target2, an2, r2)
                            else:
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002 " +
                                        "and \u0002{2}\u0002 get hit by the chemicals and die.").format(nick, target1, target2)
                            cli.msg(botconfig.CHANNEL, tmsg)
                            debuglog(nick, "(mad scientist) KILL: {0} ({1}) - {2} ({3})".format(target1, var.get_role(target1), target2, var.get_role(target2)))
                            deadlist1 = copy.copy(deadlist)
                            deadlist1.append(target2)
                            deadlist2 = copy.copy(deadlist)
                            deadlist2.append(target1)
                            del_player(cli, target1, True, end_game = False, killer_role = "mad scientist", deadlist = deadlist1, original = original, ismain = False)
                            del_player(cli, target2, True, end_game = False, killer_role = "mad scientist", deadlist = deadlist2, original = original, ismain = False)
                            pl = refresh_pl(pl)
                        else:
                            if var.ROLE_REVEAL in ("on", "team"):
                                r1 = var.get_reveal_role(target1)
                                an1 = "n" if r1.startswith(("a", "e", "i", "o", "u")) else ""
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002, " +
                                        "a{2} \u0002{3}\u0002, gets hit by the chemicals and dies.").format(nick, target1, an1, r1)
                            else:
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002 " +
                                        "gets hit by the chemicals and dies.").format(nick, target1)
                            cli.msg(botconfig.CHANNEL, tmsg)
                            debuglog(nick, "(mad scientist) KILL: {0} ({1})".format(target1, var.get_role(target1)))
                            del_player(cli, target1, True, end_game = False, killer_role = "mad scientist", deadlist = deadlist, original = original, ismain = False)
                            pl = refresh_pl(pl)
                    else:
                        if target2 in pl:
                            if var.ROLE_REVEAL in ("on", "team"):
                                r2 = var.get_reveal_role(target2)
                                an2 = "n" if r2.startswith(("a", "e", "i", "o", "u")) else ""
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002, " +
                                        "a{2} \u0002{3}\u0002, gets hit by the chemicals and dies.").format(nick, target2, an2, r2)
                            else:
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002 " +
                                        "gets hit by the chemicals and dies.").format(nick, target2)
                            cli.msg(botconfig.CHANNEL, tmsg)
                            debuglog(nick, "(mad scientist) KILL: {0} ({1})".format(target2, var.get_role(target2)))
                            del_player(cli, target2, True, end_game = False, killer_role = "mad scientist", deadlist = deadlist, original = original, ismain = False)
                            pl = refresh_pl(pl)
                        else:
                            tmsg = ("\u0002{0}\u0002 throws " +
                                    "a potent chemical concoction into the crowd. Thankfully, " +
                                    "nobody seems to have gotten hit.").format(nick)
                            cli.msg(botconfig.CHANNEL, tmsg)
                            debuglog(nick, "(mad scientist) KILL FAIL")

            if devoice and (var.PHASE != "night" or not var.DEVOICE_DURING_NIGHT):
                cmode.append(("-v", nick))
            # devoice all players that died as a result, if we are in the original del_player
            if ismain:
                mass_mode(cli, cmode, [])
                del cmode[:]
            if var.PHASE == "join":
                if nick in var.GAMEMODE_VOTES:
                    del var.GAMEMODE_VOTES[nick]

                with var.WARNING_LOCK:
                    var.START_VOTES.discard(nick)

                # Died during the joining process as a person
                if var.AUTO_TOGGLE_MODES and nick in var.USERS and var.USERS[nick]["moded"]:
                    for newmode in var.USERS[nick]["moded"]:
                        cmode.append(("+"+newmode, nick))
                    var.USERS[nick]["modes"].update(var.USERS[nick]["moded"])
                    var.USERS[nick]["moded"] = set()
                var.ALL_PLAYERS.remove(nick)
                ret = not chk_win(cli)
            else:
                # Died during the game, so quiet!
                if var.QUIET_DEAD_PLAYERS and not is_fake_nick(nick):
                    cmode.append(("+{0}".format(var.QUIET_MODE), var.QUIET_PREFIX+nick+"!*@*"))
                var.DEAD.add(nick)
                ret = not chk_win(cli, end_game)
            if var.PHASE in ("night", "day") and ret:
                # remove the player from variables if they're in there
                for a,b in list(var.KILLS.items()):
                    for n in b: #var.KILLS can have 2 kills in a list
                        if n == nick:
                            var.KILLS[a].remove(nick)
                    if a == nick or len(var.KILLS[a]) == 0:
                        del var.KILLS[a]
                for x in (var.OBSERVED, var.HVISITED, var.GUARDED, var.TARGETED, var.LASTGUARDED, var.LASTGIVEN, var.LASTHEXED):
                    for k in list(x):
                        if nick in (k, x[k]):
                            del x[k]
                for x in (var.SHAMANS,):
                    for k in list(x):
                        if nick in (k, x[k][0]):
                            del x[k]
                for k in list(var.OTHER_KILLS):
                    if var.OTHER_KILLS[k] == nick:
                        var.HUNTERS.discard(k)
                        pm(cli, k, "Your target has died, so you may now pick a new one.")
                        del var.OTHER_KILLS[k]
                    elif nick == k:
                        del var.OTHER_KILLS[k]
                if nick in var.DISCONNECTED:
                    del var.DISCONNECTED[nick]
            if var.PHASE == "night":
                # remove players from night variables
                # the dicts are handled above, these are the lists of who has acted which is used to determine whether night should end
                # if these aren't cleared properly night may end prematurely
                for x in (var.SEEN, var.PASSED, var.HUNTERS, var.HEXED, var.MATCHMAKERS, var.CURSED, var.CHARMERS):
                    x.discard(nick)
            if var.PHASE == "day" and not forced_death and ret:  # didn't die from lynching
                var.VOTES.pop(nick, None)  #  Delete other people's votes on the player
                for k in list(var.VOTES.keys()):
                    if nick in var.VOTES[k]:
                        var.VOTES[k].remove(nick)
                        if not var.VOTES[k]:  # no more votes on that person
                            del var.VOTES[k]
                        break # can only vote once

                var.NO_LYNCH.discard(nick)
                var.WOUNDED.discard(nick)
                var.ASLEEP.discard(nick)
                chk_decision(cli)
            elif var.PHASE == "night" and ret:
                chk_nightdone(cli)

        return ret


def reaper(cli, gameid):
    # check to see if idlers need to be killed.
    var.IDLE_WARNED    = set()
    var.IDLE_WARNED_PM = set()
    chan = botconfig.CHANNEL

    while gameid == var.GAME_ID:
        with var.GRAVEYARD_LOCK:
            # Terminate reaper when game ends
            if var.PHASE not in ("day", "night"):
                return
            if var.WARN_IDLE_TIME or var.PM_WARN_IDLE_TIME or var.KILL_IDLE_TIME:  # only if enabled
                to_warn    = []
                to_warn_pm = []
                to_kill    = []
                for nick in var.list_players():
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
                    if nck not in var.list_players():
                        continue
                    if var.ROLE_REVEAL in ("on", "team"):
                        cli.msg(chan, ("\u0002{0}\u0002 didn't get out of bed for a very long "+
                                       "time and has been found dead. The survivors bury "+
                                       "the \u0002{1}\u0002's body.").format(nck, var.get_reveal_role(nck)))
                    else:
                        cli.msg(chan, ("\u0002{0}\u0002 didn't get out of bed for a very long " +
                                       "time and has been found dead.").format(nck))
                    for r,rlist in var.ORIGINAL_ROLES.items():
                        if nck in rlist:
                            var.ORIGINAL_ROLES[r].remove(nck)
                            var.ORIGINAL_ROLES[r].add("(dced)"+nck)
                    make_stasis(nck, var.IDLE_STASIS_PENALTY)
                    del_player(cli, nck, end_game = False, death_triggers = False)
                chk_win(cli)
                pl = var.list_players()
                x = [a for a in to_warn if a in pl]
                if x:
                    cli.msg(chan, ("{0}: \u0002You have been idling for a while. "+
                                   "Please say something soon or you "+
                                   "might be declared dead.\u0002").format(", ".join(x)))
                msg_targets = [p for p in to_warn_pm if p in pl]
                mass_privmsg(cli, msg_targets, ("\u0002You have been idling in {0} for a while. Please say something in {0} "+
                                                "or you will be declared dead.\u0002").format(chan), privmsg=True)
            for dcedplayer in list(var.DISCONNECTED.keys()):
                acc, hostmask, timeofdc, what = var.DISCONNECTED[dcedplayer]
                if what in ("quit", "badnick") and (datetime.now() - timeofdc) > timedelta(seconds=var.QUIT_GRACE_TIME):
                    if var.get_role(dcedplayer) != "person" and var.ROLE_REVEAL in ("on", "team"):
                        cli.msg(chan, ("\u0002{0}\u0002 was mauled by wild animals and has died. It seems that "+
                                       "\u0002{1}\u0002 meat is tasty.").format(dcedplayer, var.get_reveal_role(dcedplayer)))
                    else:
                        cli.msg(chan, ("\u0002{0}\u0002 was mauled by wild animals and has died.").format(dcedplayer))
                    if var.PHASE != "join":
                        make_stasis(dcedplayer, var.PART_STASIS_PENALTY)
                    if not del_player(cli, dcedplayer, devoice = False, death_triggers = False):
                        return
                elif what == "part" and (datetime.now() - timeofdc) > timedelta(seconds=var.PART_GRACE_TIME):
                    if var.get_role(dcedplayer) != "person" and var.ROLE_REVEAL in ("on", "team"):
                        cli.msg(chan, ("\u0002{0}\u0002, a \u0002{1}\u0002, ate some poisonous berries "+
                                       "and has died.").format(dcedplayer, var.get_reveal_role(dcedplayer)))
                    else:
                        cli.msg(chan, ("\u0002{0}\u0002 ate some poisonous berries and has died.").format(dcedplayer))
                    if var.PHASE != "join":
                        make_stasis(dcedplayer, var.PART_STASIS_PENALTY)
                    if not del_player(cli, dcedplayer, devoice = False, death_triggers = False):
                        return
                elif what == "account" and (datetime.now() - timeofdc) > timedelta(seconds=var.ACC_GRACE_TIME):
                    if var.get_role(dcedplayer) != "person" and var.ROLE_REVEAL in ("on", "team"):
                        cli.msg(chan, ("\u0002{0}\u0002 has died of a heart attack. The villagers "+
                                       "couldn't save the \u0002{1}\u0002.").format(dcedplayer, var.get_reveal_role(dcedplayer)))
                    else:
                        cli.msg(chan, ("\u0002{0}\u0002 has died of a heart attack.").format(dcedplayer))
                    if var.PHASE != "join":
                        make_stasis(dcedplayer, var.ACC_STASIS_PENALTY)
                    if not del_player(cli, dcedplayer, devoice = False, death_triggers = False):
                        return
        time.sleep(10)



@cmd("")  # update last said
def update_last_said(cli, nick, chan, rest):
    if chan != botconfig.CHANNEL:
        return

    if var.PHASE not in ("join", "none"):
        var.LAST_SAID_TIME[nick] = datetime.now()

    fullstring = "".join(rest)
    if var.CARE_BOLD and BOLD in fullstring:
        if var.KILL_BOLD:
            cli.send("KICK {0} {1} :Using bold is not allowed".format(botconfig.CHANNEL, nick))
        else:
            cli.notice(nick, "Using bold in the channel is not allowed.")
    if var.CARE_COLOR and any(code in fullstring for code in ["\u0003", "\u0016", "\u001f" ]):
        if var.KILL_COLOR:
            cli.send("KICK {0} {1} :Using color is not allowed".format(botconfig.CHANNEL, nick))
        else:
            cli.notice(nick, "Using color in the channel is not allowed.")

@hook("join")
def on_join(cli, raw_nick, chan, acc="*", rname=""):
    nick, _, ident, host = parse_nick(raw_nick)
    if nick != botconfig.NICK:
        if nick not in var.USERS.keys():
            var.USERS[nick] = dict(ident=ident,host=host,account=acc,inchan=chan == botconfig.CHANNEL,modes=set(),moded=set())
        else:
            var.USERS[nick]["ident"] = ident
            var.USERS[nick]["host"] = host
            var.USERS[nick]["account"] = acc
            if not var.USERS[nick]["inchan"]:
                # Will be True if the user joined the main channel, else False
                var.USERS[nick]["inchan"] = (chan == botconfig.CHANNEL)
    if chan != botconfig.CHANNEL:
        return
    with var.GRAVEYARD_LOCK:
        hostmask = ident + "@" + host
        if nick in var.DISCONNECTED.keys():
            hm = var.DISCONNECTED[nick][1]
            act = var.DISCONNECTED[nick][0]
            if (acc == act and not var.DISABLE_ACCOUNTS) or (hostmask == hm and not var.ACCOUNTS_ONLY):
                cli.mode(chan, "+v", nick, nick+"!*@*")
                del var.DISCONNECTED[nick]
                var.LAST_SAID_TIME[nick] = datetime.now()
                cli.msg(chan, "\u0002{0}\u0002 has returned to the village.".format(nick))
                for r,rlist in var.ORIGINAL_ROLES.items():
                    if "(dced)"+nick in rlist:
                        rlist.remove("(dced)"+nick)
                        rlist.add(nick)
                        break
                if nick in var.DCED_PLAYERS.keys():
                    var.PLAYERS[nick] = var.DCED_PLAYERS.pop(nick)
    if nick == botconfig.NICK:
        var.OPPED = False
    if nick == "ChanServ" and not var.OPPED:
        cli.msg("ChanServ", "op " + chan)


@cmd("goat", playing=True, phases=("day",))
def goat(cli, nick, chan, rest):
    """Use a goat to interact with anyone in the channel during the day."""

    if var.GOATED and nick not in var.SPECIAL_ROLES["goat herder"]:
        cli.notice(nick, "This can only be done once per day.")
        return

    ul = list(var.USERS.keys())
    ull = [x.lower() for x in ul]

    rest = re.split(" +",rest)[0]
    if not rest:
        cli.notice(nick, "Not enough parameters.")

    victim, _ = complete_match(rest.lower(), ull)
    if not victim:
        cli.notice(nick, "\u0002{0}\u0002 is not in this channel.".format(rest))
        return
    victim = ul[ull.index(victim)]

    goatact = random.choice(("kicks", "headbutts"))

    cli.msg(chan, "\u0002{0}\u0002's goat walks by and {1} \u0002{2}\u0002.".format(
        nick, goatact, victim))

    var.GOATED = True

@cmd("fgoat", admin_only=True)
def fgoat(cli, nick, chan, rest):
    """Forces a goat to interact with anyone or anything, without limitations."""
    nick_ = rest.split(' ')[0].strip()
    ul = list(var.USERS.keys())
    if nick_.lower() in (x.lower() for x in ul):
        togoat = nick_
    else:
        togoat = rest
    goatact = random.choice(("kicks", "headbutts"))

    cli.msg(chan, "\u0002{0}\u0002's goat walks by and {1} \u0002{2}\u0002.".format(nick, goatact, togoat))

def return_to_village(cli, chan, nick, show_message):
    with var.GRAVEYARD_LOCK:
        if nick in var.DISCONNECTED.keys():
            hm = var.DISCONNECTED[nick][1]
            act = var.DISCONNECTED[nick][0]
            if nick in var.USERS:
                ident = var.USERS[nick]["ident"]
                host = var.USERS[nick]["host"]
                acc = var.USERS[nick]["account"]
            else:
                acc = None
            if not acc or acc == "*":
                acc = None
            hostmask = ident + "@" + host
            if (acc and acc == act) or (hostmask == hm and not var.ACCOUNTS_ONLY):
                del var.DISCONNECTED[nick]
                var.LAST_SAID_TIME[nick] = datetime.now()
                for r,rset in var.ORIGINAL_ROLES.items():
                    if "(dced)"+nick in rset:
                        rset.remove("(dced)"+nick)
                        rset.add(nick)
                if nick in var.DCED_PLAYERS.keys():
                    var.PLAYERS[nick] = var.DCED_PLAYERS.pop(nick)
                if show_message:
                    cli.mode(chan, "+v", nick, nick+"!*@*")
                    cli.msg(chan, "\u0002{0}\u0002 has returned to the village.".format(nick))

def rename_player(cli, prefix, nick):
    chan = botconfig.CHANNEL

    if prefix in var.list_players():
        r = var.ROLES[var.get_role(prefix)]
        r.add(nick)
        r.remove(prefix)
        tpls = var.get_templates(prefix)
        for t in tpls:
            var.ROLES[t].add(nick)
            var.ROLES[t].remove(prefix)

        if prefix in var.ALL_PLAYERS:
            # ALL_PLAYERS needs to keep its ordering for purposes of mad scientist
            var.ALL_PLAYERS[var.ALL_PLAYERS.index(prefix)] = nick

        if var.PHASE in ("night", "day"):
            for k,v in var.ORIGINAL_ROLES.items():
                if prefix in v:
                    var.ORIGINAL_ROLES[k].remove(prefix)
                    var.ORIGINAL_ROLES[k].add(nick)
                if "(dced)"+prefix in v:
                    var.ORIGINAL_ROLES[k].remove("(dced)"+prefix)
                    var.ORIGINAL_ROLES[k].add(nick)
            for k,v in list(var.PLAYERS.items()):
                if prefix == k:
                    var.PLAYERS[nick] = var.PLAYERS.pop(k)
            for dictvar in (var.HVISITED, var.OBSERVED, var.GUARDED, var.OTHER_KILLS, var.TARGETED,
                            var.CLONED, var.LASTGUARDED, var.LASTGIVEN, var.LASTHEXED,
                            var.BITE_PREFERENCES):
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
            for dictvar in (var.SHAMANS,):
                kvp = []
                for a,(b,c) in dictvar.items():
                    if a == prefix:
                        a = nick
                    if b == prefix:
                        b = nick
                    if c == prefix:
                        c = nick
                    kvp.append((a,(b,c)))
                dictvar.update(kvp)
                if prefix in dictvar.keys():
                    del dictvar[prefix]
            for dictvar in (var.VENGEFUL_GHOSTS, var.TOTEMS, var.FINAL_ROLES, var.BITTEN, var.GUNNERS, var.TURNCOATS,
                            var.DOCTORS, var.BITTEN_ROLES, var.LYCAN_ROLES, var.AMNESIAC_ROLES):
                if prefix in dictvar.keys():
                    dictvar[nick] = dictvar.pop(prefix)
            # Looks like {'jacob2': ['5'], '7': ['3']}
            for dictvar in (var.KILLS,):
                kvp = []
                for a,b in dictvar.items():
                    nl = []
                    for n in b:
                        if n == prefix:
                            n = nick
                        nl.append(n)
                    if a == prefix:
                        a = nick
                    kvp.append((a,nl))
                dictvar.update(kvp)
                if prefix in dictvar.keys():
                    del dictvar[prefix]
            # Looks like {'6': {'jacob3'}, 'jacob3': {'6'}}
            for dictvar in (var.LOVERS, var.ORIGINAL_LOVERS):
                kvp = []
                for a,b in dictvar.items():
                    nl = set()
                    for n in b:
                        if n == prefix:
                            n = nick
                        nl.add(n)
                    if a == prefix:
                        a = nick
                    kvp.append((a,nl))
                dictvar.update(kvp)
                if prefix in dictvar.keys():
                    del dictvar[prefix]
            for idx, tup in enumerate(var.EXCHANGED_ROLES):
                a, b = tup
                if a == prefix:
                    a = nick
                if b == prefix:
                    b = nick
                var.EXCHANGED_ROLES[idx] = (a, b)
            if prefix in var.SEEN:
                var.SEEN.remove(prefix)
                var.SEEN.add(nick)
            if prefix in var.HEXED:
                var.HEXED.remove(prefix)
                var.HEXED.add(nick)
            if prefix in var.ASLEEP:
                var.ASLEEP.remove(prefix)
                var.ASLEEP.add(nick)
            if prefix in var.DESPERATE:
                var.DESPERATE.remove(prefix)
                var.DESPERATE.add(nick)
            for k, d in list(var.DEATH_TOTEM):
                if k == prefix or d == prefix:
                    var.DEATH_TOTEM.remove((k, d))
                    nk = nick if k == prefix else k
                    nd = nick if d == prefix else d
                    var.DEATH_TOTEM.append((nk, nd))
            while prefix in var.PROTECTED:
                var.PROTECTED.remove(prefix)
                var.PROTECTED.append(nick)
            if prefix in var.REVEALED:
                var.REVEALED.remove(prefix)
                var.REVEALED.add(nick)
            if prefix in var.SILENCED:
                var.SILENCED.remove(prefix)
                var.SILENCED.add(nick)
            if prefix in var.TOBESILENCED:
                var.TOBESILENCED.remove(prefix)
                var.TOBESILENCED.add(nick)
            if prefix in var.REVEALED_MAYORS:
                var.REVEALED_MAYORS.remove(prefix)
                var.REVEALED_MAYORS.add(nick)
            if prefix in var.MATCHMAKERS:
                var.MATCHMAKERS.remove(prefix)
                var.MATCHMAKERS.add(nick)
            if prefix in var.HUNTERS:
                var.HUNTERS.remove(prefix)
                var.HUNTERS.add(nick)
            if prefix in var.PASSED:
                var.PASSED.remove(prefix)
                var.PASSED.add(nick)
            if prefix in var.JESTERS:
                var.JESTERS.remove(prefix)
                var.JESTERS.add(nick)
            if prefix in var.AMNESIACS:
                var.AMNESIACS.remove(prefix)
                var.AMNESIACS.add(nick)
            while prefix in var.IMPATIENT:
                var.IMPATIENT.remove(prefix)
                var.IMPATIENT.append(nick)
            while prefix in var.PACIFISTS:
                var.PACIFISTS.remove(prefix)
                var.PACIFISTS.append(nick)
            if prefix in var.INFLUENTIAL:
                var.INFLUENTIAL.remove(prefix)
                var.INFLUENTIAL.add(nick)
            if prefix in var.LYCANTHROPES:
                var.LYCANTHROPES.remove(prefix)
                var.LYCANTHROPES.add(nick)
            if prefix in var.TOBELYCANTHROPES:
                var.TOBELYCANTHROPES.remove(prefix)
                var.TOBELYCANTHROPES.add(nick)
            if prefix in var.LUCKY:
                var.LUCKY.remove(prefix)
                var.LUCKY.add(nick)
            if prefix in var.TOBELUCKY:
                var.TOBELUCKY.remove(prefix)
                var.TOBELUCKY.add(nick)
            if prefix in var.DISEASED:
                var.DISEASED.remove(prefix)
                var.DISEASED.add(nick)
            if prefix in var.TOBEDISEASED:
                var.TOBEDISEASED.remove(prefix)
                var.TOBEDISEASED.add(nick)
            if prefix in var.RETRIBUTION:
                var.RETRIBUTION.remove(prefix)
                var.RETRIBUTION.add(nick)
            if prefix in var.MISDIRECTED:
                var.MISDIRECTED.remove(prefix)
                var.MISDIRECTED.add(nick)
            if prefix in var.TOBEMISDIRECTED:
                var.TOBEMISDIRECTED.remove(prefix)
                var.TOBEMISDIRECTED.add(nick)
            if prefix in var.EXCHANGED:
                var.EXCHANGED.remove(prefix)
                var.EXCHANGED.add(nick)
            if prefix in var.IMMUNIZED:
                var.IMMUNIZED.remove(prefix)
                var.IMMUNIZED.add(nick)
            if prefix in var.CURED_LYCANS:
                var.CURED_LYCANS.remove(prefix)
                var.CURED_LYCANS.add(nick)
            if prefix in var.ALPHA_WOLVES:
                var.ALPHA_WOLVES.remove(prefix)
                var.ALPHA_WOLVES.add(nick)
            if prefix in var.CURSED:
                var.CURSED.remove(prefix)
                var.CURSED.add(nick)
            if prefix in var.CHARMERS:
                var.CHARMERS.remove(prefix)
                var.CHARMERS.add(nick)
            if prefix in var.CHARMED:
                var.CHARMED.remove(prefix)
                var.CHARMED.add(nick)
            if prefix in var.TOBECHARMED:
                var.TOBECHARMED.remove(prefix)
                var.TOBECHARMED.add(nick)
            with var.GRAVEYARD_LOCK:  # to be safe
                if prefix in var.LAST_SAID_TIME.keys():
                    var.LAST_SAID_TIME[nick] = var.LAST_SAID_TIME.pop(prefix)
                if prefix in getattr(var, "IDLE_WARNED", ()):
                    var.IDLE_WARNED.remove(prefix)
                    var.IDLE_WARNED.add(nick)
                if prefix in getattr(var, "IDLE_WARNED_PM", ()):
                    var.IDLE_WARNED_PM.remove(prefix)
                    var.IDLE_WARNED_PM.add(nick)

        if var.PHASE == "day":
            if prefix in var.WOUNDED:
                var.WOUNDED.remove(prefix)
                var.WOUNDED.add(nick)
            if prefix in var.INVESTIGATED:
                var.INVESTIGATED.remove(prefix)
                var.INVESTIGATED.add(nick)
            if prefix in var.VOTES:
                var.VOTES[nick] = var.VOTES.pop(prefix)
            for v in var.VOTES.values():
                if prefix in v:
                    v.remove(prefix)
                    v.append(nick)

        if var.PHASE == "join":
            if prefix in var.GAMEMODE_VOTES:
                var.GAMEMODE_VOTES[nick] = var.GAMEMODE_VOTES.pop(prefix)
            with var.WARNING_LOCK:
                if prefix in var.START_VOTES:
                    var.START_VOTES.discard(prefix)
                    var.START_VOTES.add(nick)

    # Check if player was disconnected
    if var.PHASE in ("night", "day"):
        return_to_village(cli, chan, nick, True)

    if prefix in var.NO_LYNCH:
        var.NO_LYNCH.remove(prefix)
        var.NO_LYNCH.add(nick)

@hook("nick")
def on_nick(cli, oldnick, nick):
    prefix, _, ident, host = parse_nick(oldnick)
    chan = botconfig.CHANNEL

    if (nick.startswith("Guest") or nick[0].isdigit() or (nick != "away" and "away" in nick.lower())) and nick not in var.DISCONNECTED.keys() and prefix in var.list_players():
        if var.PHASE != "join":
            cli.mode(chan, "-v", nick)
        leave(cli, "badnick", oldnick)
        # update var.USERS after so that leave() can keep track of new nick to use properly
        # return after doing this so that none of the game vars are updated with the bad nickname
        if prefix in var.USERS:
            var.USERS[nick] = var.USERS.pop(prefix)
        return

    if prefix in var.USERS:
        var.USERS[nick] = var.USERS.pop(prefix)
        if not var.USERS[nick]["inchan"]:
            return

    if prefix == var.ADMIN_TO_PING:
        var.ADMIN_TO_PING = nick

    if prefix not in var.DISCONNECTED.keys():
        rename_player(cli, prefix, nick)

def leave(cli, what, nick, why=""):
    nick, _, ident, host = parse_nick(nick)
    if nick in var.USERS:
        acc = var.USERS[nick]["account"]
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        if what == "quit" or (not what in ("account",) and why == botconfig.CHANNEL):
            var.USERS[nick]["inchan"] = False
    else:
        acc = None
    if not acc or acc == "*":
        acc = None

    if what in ("part", "kick") and why != botconfig.CHANNEL: return

    if why and why == botconfig.CHANGING_HOST_QUIT_MESSAGE:
        return
    if var.PHASE == "none":
        return
    # only mark living players as dced, unless they were kicked
    if nick in var.PLAYERS and (what == "kick" or nick in var.list_players()):
        # must prevent double entry in var.ORIGINAL_ROLES
        for r,rset in var.ORIGINAL_ROLES.items():
            if nick in rset:
                var.ORIGINAL_ROLES[r].remove(nick)
                var.ORIGINAL_ROLES[r].add("(dced)"+nick)
                break
        var.DCED_PLAYERS[nick] = var.PLAYERS.pop(nick)
    if nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        return

    #  the player who just quit was in the game
    killplayer = True

    population = ""

    if var.PHASE == "join":
        lpl = len(var.list_players()) - 1

        if lpl < var.MIN_PLAYERS:
            with var.WARNING_LOCK:
                var.START_VOTES = set()

        if lpl == 0:
            population = (" No more players remaining.")
        else:
            population = (" New player count: \u0002{0}\u0002").format(lpl)

    if what == "part" and (not var.PART_GRACE_TIME or var.PHASE == "join"):
        if var.get_role(nick) != "person" and var.ROLE_REVEAL in ("on", "team"):
            msg = ("\u0002{0}\u0002, a \u0002{1}\u0002, ate some poisonous berries and has "+
                   "died.{2}").format(nick, var.get_reveal_role(nick), population)
        else:
            msg = ("\u0002{0}\u0002 ate some poisonous berries and has died.{1}").format(nick, population)
    elif what in ("quit", "badnick") and (not var.QUIT_GRACE_TIME or var.PHASE == "join"):
        if var.get_role(nick) != "person" and var.ROLE_REVEAL in ("on", "team"):
            msg = ("\u0002{0}\u0002 was mauled by wild animals and has died. It seems that "+
                   "\u0002{1}\u0002 meat is tasty.{2}").format(nick, var.get_reveal_role(nick), population)
        else:
            msg = ("\u0002{0}\u0002 was mauled by wild animals and has died.{1}").format(nick, population)
    elif what == "account" and (not var.ACC_GRACE_TIME or var.PHASE == "join"):
        if var.get_role(nick) != "person" and var.ROLE_REVEAL in ("on", "team"):
            msg = ("\u0002{0}\u0002 fell into a river and was swept away. The villagers couldn't "+
                   "save the \u0002{1}\u0002.{2}").format(nick, var.get_reveal_role(nick), population)
        else:
            msg = ("\u0002{0}\u0002 fell into a river and was swept away.{1}").format(nick, population)
    elif what != "kick":
        msg = "\u0002{0}\u0002 has gone missing.".format(nick)
        killplayer = False
    else:
        if var.get_role(nick) != "person" and var.ROLE_REVEAL in ("on", "team"):
            msg = ("\u0002{0}\u0002 died due to falling off a cliff. The "+
                   "\u0002{1}\u0002 is lost to the ravine forever.{2}").format(nick, var.get_reveal_role(nick), population)
        else:
            msg = ("\u0002{0}\u0002 died due to falling off a cliff.{1}").format(nick, population)
        make_stasis(nick, var.LEAVE_STASIS_PENALTY)
    cli.msg(botconfig.CHANNEL, msg)
    if what not in ("badnick", "account") and nick in var.USERS:
        var.USERS[nick]["modes"] = set()
        var.USERS[nick]["moded"] = set()
    if killplayer:
        del_player(cli, nick, death_triggers = False)
    else:
        var.DISCONNECTED[nick] = (acc, ident + "@" + host, datetime.now(), what)

#Functions decorated with hook do not parse the nick by default
hook("part")(lambda cli, nick, *rest: leave(cli, "part", nick, rest[0]))
hook("quit")(lambda cli, nick, *rest: leave(cli, "quit", nick, rest[0]))
hook("kick")(lambda cli, nick, *rest: leave(cli, "kick", rest[1], rest[0]))


@cmd("quit", "leave", playing=True, phases=("join", "day", "night"))
def leave_game(cli, nick, chan, rest):
    """Quits the game."""
    if var.PHASE == "join":
        lpl = len(var.list_players()) - 1

        if lpl == 0:
            population = (" No more players remaining.")
        else:
            population = (" New player count: \u0002{0}\u0002").format(lpl)
    else:
        dur = int(var.START_QUIT_DELAY - (datetime.now() - var.GAME_START_TIME).total_seconds())
        if var.START_QUIT_DELAY and dur > 0:
            cli.notice(nick, "The game already started! If you still want to quit, try again in {0} second{1}.".format(dur, "" if dur == 1 else "s"))
            return
        population = ""
    if var.get_role(nick) != "person" and var.ROLE_REVEAL in ("on", "team"):
        role = var.get_reveal_role(nick)
        an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
        if var.DYNQUIT_DURING_GAME:
            lmsg = random.choice(var.QUIT_MESSAGES).format(nick, an, role)
            cli.msg(botconfig.CHANNEL, lmsg)
        else:
            cli.msg(botconfig.CHANNEL, ("\u0002{0}\u0002, a \u0002{1}\u0002, has died of an unknown disease.{2}").format(nick, role, population))
    else:
        # DYNQUIT_DURING_GAME should not have any effect during the join phase, so only check if we aren't in that
        if var.PHASE != "join" and not var.DYNQUIT_DURING_GAME:
            cli.msg(botconfig.CHANNEL, ("\u0002{0}\u0002 has died of an unknown disease.{1}").format(nick, population))
        else:
            lmsg = random.choice(var.QUIT_MESSAGES_NO_REVEAL).format(nick) + population
            cli.msg(botconfig.CHANNEL, lmsg)
    if var.PHASE != "join":
        for r, rset in var.ORIGINAL_ROLES.items():
            if nick in rset:
                var.ORIGINAL_ROLES[r].remove(nick)
                var.ORIGINAL_ROLES[r].add("(dced)"+nick)
        make_stasis(nick, var.LEAVE_STASIS_PENALTY)
        if nick in var.PLAYERS:
            var.DCED_PLAYERS[nick] = var.PLAYERS.pop(nick)

    del_player(cli, nick, death_triggers = False)

def begin_day(cli):
    chan = botconfig.CHANNEL

    # Reset nighttime variables
    var.GAMEPHASE = "day"
    var.KILLS = {}  # nicknames of kill victims (wolves only)
    var.OTHER_KILLS = {} # other kill victims (hunter/vengeful ghost)
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = set()  # set of seers/oracles/augurs that have had visions
    var.HEXED = set() # set of hags that have silenced others
    var.SHAMANS = {} # dict of shamans/crazed shamans that have acted and who got totems
    var.OBSERVED = {}  # those whom werecrows/sorcerers have observed
    var.HVISITED = {} # those whom harlots have visited
    var.GUARDED = {}  # this whom bodyguards/guardian angels have guarded
    var.PASSED = set() # set of certain roles that have opted not to act
    var.STARTED_DAY_PLAYERS = len(var.list_players())
    var.SILENCED = copy.copy(var.TOBESILENCED)
    var.LYCANTHROPES = copy.copy(var.TOBELYCANTHROPES)
    var.LUCKY = copy.copy(var.TOBELUCKY)
    var.DISEASED = copy.copy(var.TOBEDISEASED)
    var.MISDIRECTED = copy.copy(var.TOBEMISDIRECTED)
    var.ACTIVE_PROTECTIONS = defaultdict(list)

    msg = ('The villagers must now vote for whom to lynch. '+
           'Use "{0}lynch <nick>" to cast your vote. {1} votes '+
           'are required to lynch.').format(botconfig.CMD_CHAR, len(var.list_players()) // 2 + 1)
    cli.msg(chan, msg)

    var.DAY_ID = time.time()
    if var.DAY_TIME_WARN > 0:
        if var.STARTED_DAY_PLAYERS <= var.SHORT_DAY_PLAYERS:
            t1 = threading.Timer(var.SHORT_DAY_WARN, hurry_up, [cli, var.DAY_ID, False])
            l = var.SHORT_DAY_WARN
        else:
            t1 = threading.Timer(var.DAY_TIME_WARN, hurry_up, [cli, var.DAY_ID, False])
            l = var.DAY_TIME_WARN
        var.TIMERS["day_warn"] = (t1, var.DAY_ID, l)
        t1.daemon = True
        t1.start()

    if var.DAY_TIME_LIMIT > 0:  # Time limit enabled
        if var.STARTED_DAY_PLAYERS <= var.SHORT_DAY_PLAYERS:
            t2 = threading.Timer(var.SHORT_DAY_LIMIT, hurry_up, [cli, var.DAY_ID, True])
            l = var.SHORT_DAY_LIMIT
        else:
            t2 = threading.Timer(var.DAY_TIME_LIMIT, hurry_up, [cli, var.DAY_ID, True])
            l = var.DAY_TIME_LIMIT
        var.TIMERS["day"] = (t2, var.DAY_ID, l)
        t2.daemon = True
        t2.start()

    if var.DEVOICE_DURING_NIGHT:
        modes = []
        for player in var.list_players():
            modes.append(("+v", player))
        mass_mode(cli, modes, [])

def night_warn(cli, gameid):
    if gameid != var.NIGHT_ID:
        return

    if var.PHASE == "day":
        return

    cli.msg(botconfig.CHANNEL, ("\u0002A few villagers awake early and notice it " +
                                "is still dark outside. " +
                                "The night is almost over and there are " +
                                "still whispers heard in the village.\u0002"))

def transition_day(cli, gameid=0):
    if gameid:
        if gameid != var.NIGHT_ID:
            return
    var.NIGHT_ID = 0

    if var.PHASE == "day":
        return

    var.PHASE = "day"
    var.GOATED = False
    chan = botconfig.CHANNEL
    pl = var.list_players()

    if not var.START_WITH_DAY or not var.FIRST_DAY:
        # bodyguard doesn't have restrictions, but being checked anyway since both GA and bodyguard use var.GUARDED
        if len(var.GUARDED.keys()) < len(var.ROLES["bodyguard"] | var.ROLES["guardian angel"]):
            for gangel in var.ROLES["guardian angel"]:
                if gangel not in var.GUARDED or var.GUARDED[gangel] is None:
                    var.LASTGUARDED[gangel] = None

        if len(var.HEXED) < len(var.ROLES["hag"]):
            for hag in var.ROLES["hag"]:
                if hag not in var.HEXED:
                    var.LASTHEXED[hag] = None

        # NOTE: Random assassin selection is further down, since if we're choosing at random we pick someone
        # that isn't going to be dying today, meaning we need to know who is dying first :)

        # Select a random target for vengeful ghost if they didn't kill
        wolves = var.list_players(var.WOLFTEAM_ROLES)
        villagers = var.list_players()
        for wolf in wolves:
            villagers.remove(wolf)
        for ghost, target in var.VENGEFUL_GHOSTS.items():
            if target[0] == "!" or ghost in var.SILENCED:
                continue
            if ghost not in var.OTHER_KILLS:
                if target == "wolves":
                    var.OTHER_KILLS[ghost] = random.choice(wolves)
                else:
                    var.OTHER_KILLS[ghost] = random.choice(villagers)

        # Select random totem recipients if shamans didn't act
        shamans = var.list_players(var.TOTEM_ORDER)
        for shaman in shamans:
            if shaman not in var.SHAMANS and shaman not in var.SILENCED:
                ps = pl[:]
                if var.LASTGIVEN.get(shaman) in ps:
                    ps.remove(var.LASTGIVEN.get(shaman))
                totem.func(cli, shaman, shaman, random.choice(ps), prefix="Because you forgot to give out your totem at night, you")
            else:
                var.LASTGIVEN[shaman] = None

        if var.FIRST_NIGHT:
            # Select a random target for clone if they didn't choose someone
            for clone in var.ROLES["clone"]:
                if clone not in var.CLONED:
                    ps = pl[:]
                    ps.remove(clone)
                    if len(ps) > 0:
                        target = random.choice(ps)
                        var.CLONED[clone] = target
                        pm(cli, clone, "Because you forgot to select someone to clone at night, you are now cloning \u0002{0}\u0002.".format(target))

            for mm in var.ROLES["matchmaker"]:
                if mm not in var.MATCHMAKERS:
                    lovers = random.sample(pl, 2)
                    choose.func(cli, mm, mm, lovers[0] + " " + lovers[1], sendmsg=False)
                    pm(cli, mm, "Because you forgot to choose lovers at night, two lovers have been selected for you.")


    # Reset daytime variables
    var.VOTES = {}
    var.INVESTIGATED = set()
    var.WOUNDED = set()
    var.DAY_START_TIME = datetime.now()
    var.NO_LYNCH = set()
    var.DAY_COUNT += 1
    var.FIRST_DAY = (var.DAY_COUNT == 1)
    var.DEATH_TOTEM = []
    var.PROTECTED = []
    var.REVEALED = set()
    var.ASLEEP = set()
    var.DESPERATE = set()
    var.IMPATIENT = []
    var.PACIFISTS = []
    var.INFLUENTIAL = set()
    var.EXCHANGED = set()
    var.TOBELYCANTHROPES = set()
    var.TOBELUCKY = set()
    var.TOBEDISEASED = set()
    var.RETRIBUTION = set()
    var.MISDIRECTION = set()

    # Give out totems here
    for shaman, (victim, target) in var.SHAMANS.items():
        totemname = var.TOTEMS[shaman]
        if totemname == "death": # this totem stacks
            var.DEATH_TOTEM.append((shaman, victim))
        elif totemname == "protection": # this totem stacks
            var.PROTECTED.append(victim)
        elif totemname == "revealing":
            var.REVEALED.add(victim)
        elif totemname == "narcolepsy":
            var.ASLEEP.add(victim)
        elif totemname == "silence":
            var.TOBESILENCED.add(victim)
        elif totemname == "desperation":
            var.DESPERATE.add(victim)
        elif totemname == "impatience": # this totem stacks
            var.IMPATIENT.append(victim)
        elif totemname == "pacifism": # this totem stacks
            var.PACIFISTS.append(victim)
        elif totemname == "influence":
            var.INFLUENTIAL.add(victim)
        elif totemname == "exchange":
            var.EXCHANGED.add(victim)
        elif totemname == "lycanthropy":
            var.TOBELYCANTHROPES.add(victim)
        elif totemname == "luck":
            var.TOBELUCKY.add(victim)
        elif totemname == "pestilence":
            var.TOBEDISEASED.add(victim)
        elif totemname == "retribution":
            var.RETRIBUTION.add(victim)
        elif totemname == "misdirection":
            var.TOBEMISDIRECTED.add(victim)
        else:
            debuglog("{0} {1}: INVALID TOTEM {2} TO {3}".format(shaman, var.get_role(shaman), totemname, victim))
        if target != victim:
            pm(cli, shaman, "It seems that \u0002{0}\u0002 now has the totem you gave out last night.".format(victim))
        var.LASTGIVEN[shaman] = victim
    havetotem = sorted(x for x in var.LASTGIVEN.values() if x)

    # Send out PMs to players who have been charmed
    for victim in var.TOBECHARMED:
        charmedlist = list(var.CHARMED | var.TOBECHARMED - {victim})
        message = ("You hear the sweet tones of a flute coming from outside your window... You "
                   "inexorably walk outside and find yourself in the village square. ")

        if len(charmedlist) <= 0:
            pm(cli, victim, message + "There are no other charmed players.")
        elif len(charmedlist) == 1:
            pm(cli, victim, message + "You find out that \u0002{0}\u0002 is also charmed!".format(charmedlist[0]))
        elif len(charmedlist) == 2:
            pm(cli, victim, message + ("You find out that \u0002{0}\u0002 and \u0002{1}\u0002 "
                                     "are also charmed!").format(charmedlist[0], charmedlist[1]))
        else:
            pm(cli, victim, message + ("You find out that \u0002{0}\u0002, and \u0002{1}\u0002 "
                                     "are also charmed!").format("\u0002, \u0002".join(charmedlist[:-1]), charmedlist[-1]))

    if var.TOBECHARMED:
        tobecharmedlist = list(var.TOBECHARMED)
        for victim in var.CHARMED:
            if len(tobecharmedlist) == 1:
                message = "\u0002{0}\u0002 is now charmed!".format(tobecharmedlist[0])
            elif len(tobecharmedlist) == 2:
                message = "\u0002{0}\u0002 and \u0002{1}\u0002 are now charmed!".format(tobecharmedlist[0], tobecharmedlist[1])
            else:
                message = "\u0002{0}\u0002, and \u0002{1}\u0002 are also charmed!".format(
                          "\u0002, \u0002".join(tobecharmedlist[:-1]), tobecharmedlist[-1])

            previouscharmed = var.CHARMED - {victim}
            if len(previouscharmed):
                pm(cli, victim, message + (" Previously charmed players: "
                                           "{0}").format("\u0002, \u0002".join(previouscharmed)))
            else:
                pm(cli, victim, message)

    var.CHARMED.update(var.TOBECHARMED)
    var.TOBECHARMED.clear()
    

    if var.START_WITH_DAY and var.FIRST_DAY:
        # TODO: need to message everyone their roles and give a short thing saying "it's daytime"
        # but this is good enough for now to prevent it from crashing
        begin_day(cli)
        return

    td = var.DAY_START_TIME - var.NIGHT_START_TIME
    var.NIGHT_START_TIME = None
    var.NIGHT_TIMEDELTA += td
    min, sec = td.seconds // 60, td.seconds % 60

    # determine if we need to play the new wolf message due to bitten people
    new_wolf = False
    for (p, v) in var.BITTEN.items():
        if v <= 0:
            new_wolf = True
            break

    found = defaultdict(int)
    for v in var.KILLS.values():
        for p in v:
            found[p] += 1

    maxc = 0
    victims = []
    bitten = []
    # dict of victim: list of killers (for retribution totem)
    killers = defaultdict(list)
    # wolves targeted, others may have as well (needed for harlot visit and maybe other things)
    bywolves = set()
    # wolves and nobody else targeted (needed for lycan)
    onlybywolves = set()

    dups = []
    for v, c in found.items():
        if c > maxc:
            maxc = c
            dups = [v]
        elif c == maxc:
            dups.append(v)

    if maxc and dups:
        victim = random.choice(dups)
        victims.append(victim)
        bywolves.add(victim)
        onlybywolves.add(victim)
        # special key to let us know to randomly select a wolf
        killers[victim].append("@wolves")


    if victims and var.ANGRY_WOLVES:
        # they got a 2nd kill
        del found[victims[0]]
        maxc = 0
        dups = []
        for v, c in found.items():
            if c > maxc:
                maxc = c
                dups = [v]
            elif c == maxc:
                dups.append(v)
        if maxc and dups:
            victim = random.choice(dups)
            victims.append(victim)
            bywolves.add(victim)
            onlybywolves.add(victim)
            # special key to let us know to randomly select a wolf
            killers[victim].append("@wolves")

    if len(var.ROLES["fallen angel"]) == 0:
        for monster in var.ROLES["monster"]:
            if monster in victims:
                victims.remove(monster)
                bywolves.discard(monster)
                onlybywolves.discard(monster)

    wolfghostvictims = []
    for k, d in var.OTHER_KILLS.items():
        victims.append(d)
        onlybywolves.discard(d)
        killers[d].append(k)
        if var.VENGEFUL_GHOSTS.get(k) == "villagers":
            wolfghostvictims.append(d)
    # clear list so that it doesn't pm hunter / ghost about being able to kill again
    var.OTHER_KILLS = {}

    for k, d in var.DEATH_TOTEM:
        victims.append(d)
        onlybywolves.discard(d)
        killers[d].append(k)

    # remove duplicates
    victims_set = set(victims)
    # in the event that ever happens
    victims_set.discard(None)
    # this keeps track of the protections active on each nick, stored in var since del_player needs to access it for sake of assassin
    protected = {}
    vappend = []
    var.ACTIVE_PROTECTIONS = defaultdict(list)

    if var.ALPHA_ENABLED: # check for bites
        for (alpha, target) in var.BITE_PREFERENCES.items():
            # bite is now separate but some people may try to double up still, if bitten person is
            # also being killed by wolves, make the kill not apply
            # note that we cannot bite visiting harlots unless they are visiting a wolf,
            # and lycans/immunized people turn/die instead of being bitten, so keep the kills valid on those
            got_bit = False
            hvisit = var.HVISITED.get(target)
            if ((target not in var.ROLES["harlot"]
                        or not hvisit
                        or var.get_role(hvisit) in var.WOLFCHAT_ROLES
                        or (hvisit in bywolves and hvisit not in protected))
                    and target not in var.ROLES["lycan"]
                    and target not in var.LYCANTHROPES
                    and target not in var.IMMUNIZED):
                # mark them as bitten
                got_bit = True
                # if they were also being killed by wolves, undo that
                if target in bywolves:
                    victims.remove(target)
                    bywolves.discard(target)
                    onlybywolves.discard(target)
                    killers[target].remove("@wolves")
                    if target not in victims:
                        victims_set.discard(target)

            if target in victims_set:
                # bite was unsuccessful due to someone else killing them
                var.ALPHA_WOLVES.remove(alpha)
            elif target in var.IMMUNIZED or target in var.ROLES["lycan"] or target in var.LYCANTHROPES:
                # target immunized or a lycan, kill them instead and refund the bite
                # (for lycans, this effectively gives alpha a free kill on top of regular wolf kill, deal with it)
                var.ALPHA_WOLVES.remove(alpha)
                if target not in victims:
                    onlybywolves.add(target)
                if target not in bywolves:
                    # don't count this as 2 separate kills for the purposes of protection if wolves already targeted this person
                    victims.append(target)
                    # and if the target is immunized and has retribution totem, (maybe) kill off the alpha that tried to bite them
                    killers[target].append(alpha)
                victims_set.add(target)
                bywolves.add(target)
            elif got_bit:
                var.BITTEN[target] = var.ALPHA_WOLF_NIGHTS
                bitten.append(target)
            else:
                # bite failed due to some other reason (namely harlot)
                var.ALPHA_WOLVES.remove(alpha)

            if alpha in var.ALPHA_WOLVES:
                pm(cli, alpha, "You have bitten \u0002{0}\u0002.".format(target))
            else:
                pm(cli, alpha, "You tried to bite \u0002{0}\u0002, but it didn't work. Better luck next time!".format(target))

    # Logic out stacked kills and protections. If we get down to 1 kill remaining that is valid and the victim is in bywolves,
    # we re-add them to onlybywolves to indicate that the other kill attempts were guarded against (and the wolf kill is what went through)
    # If protections >= kills, we keep track of which protection message to show (prot totem > GA > bodyguard)
    pl = var.list_players()
    for v in pl:
        if v in victims_set:
            numkills = victims.count(v)
            numtotems = var.PROTECTED.count(v)
            if numtotems >= numkills:
                protected[v] = "totem"
                if numtotems > numkills:
                    for i in range(0, numtotems - numkills):
                        var.ACTIVE_PROTECTIONS[v].append("totem")
            numkills -= numtotems
            for g in var.ROLES["guardian angel"]:
                if var.GUARDED.get(g) == v:
                    numkills -= 1
                    if numkills <= 0 and v not in protected:
                        protected[v] = "angel"
                    elif numkills <= 0:
                        var.ACTIVE_PROTECTIONS[v].append("angel")
            for g in var.ROLES["bodyguard"]:
                if var.GUARDED.get(g) == v:
                    numkills -= 1
                    if numkills <= 0 and v not in protected:
                        protected[v] = "bodyguard"
                    elif numkills <= 0:
                        var.ACTIVE_PROTECTIONS[v].append("bodyguard")
                    numkills -= 1
            if numkills == 1 and v in bywolves:
                onlybywolves.add(v)
        else:
            # player wasn't targeted, but apply protections on them
            numtotems = var.PROTECTED.count(v)
            for i in range(0, numtotems):
                var.ACTIVE_PROTECTIONS[v].append("totem")
            for g in var.ROLES["guardian angel"]:
                if var.GUARDED.get(g) == v:
                    var.ACTIVE_PROTECTIONS[v].append("angel")
            for g in var.ROLES["bodyguard"]:
                if var.GUARDED.get(g) == v:
                    var.ACTIVE_PROTECTIONS[v].append("bodyguard")

    fallenkills = set()
    brokentotem = set()
    if len(var.ROLES["fallen angel"]) > 0:
        for p, t in list(protected.items()):
            if p in bywolves:
                for g in var.ROLES["guardian angel"]:
                    if var.GUARDED.get(g) == p and random.random() < var.FALLEN_ANGEL_KILLS_GUARDIAN_ANGEL_CHANCE:
                        if g in protected:
                            del protected[g]
                        bywolves.add(g)
                        victims.append(g)
                        fallenkills.add(g)
                        if g not in victims_set:
                            victims_set.add(g)
                            onlybywolves.add(g)
                for g in var.ROLES["bodyguard"]:
                    if var.GUARDED.get(g) == p:
                        if g in protected:
                            del protected[g]
                        bywolves.add(g)
                        victims.append(g)
                        fallenkills.add(g)
                        if g not in victims_set:
                            victims_set.add(g)
                            onlybywolves.add(g)
                # we'll never end up killing a shaman who gave out protection, but delete the totem since
                # story-wise it gets demolished at night by the FA
                while p in havetotem:
                    havetotem.remove(p)
                    brokentotem.add(p)
            if p in protected:
                del protected[p]
            if p in var.ACTIVE_PROTECTIONS:
                del var.ACTIVE_PROTECTIONS[p]

    var.BITE_PREFERENCES = {}
    victims = []
    # Ensures that special events play for bodyguard and harlot-visiting-victim so that kill can
    # be correctly attributed to wolves (for vengeful ghost lover), and that any gunner events
    # can play. Harlot visiting wolf doesn't play special events if they die via other means since
    # that assumes they die en route to the wolves (and thus don't shoot/give out gun/etc.)
    for v in victims_set:
        if v in var.ROLES["bodyguard"] and var.GUARDED.get(v) in victims_set:
            vappend.append(v)
        elif v in var.ROLES["harlot"] and var.HVISITED.get(v) in victims_set:
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
        for v in copy.copy(vappend):
            if v in var.ROLES["bodyguard"] and var.GUARDED.get(v) not in vappend:
                vappend.remove(v)
                victims.append(v)
            elif v in var.ROLES["harlot"] and var.HVISITED.get(v) not in vappend:
                vappend.remove(v)
                victims.append(v)

    # If FA is killing through a guard, let them as well as the victim know so they don't
    # try to report the extra kills as a bug
    fallenmsg = set()
    if len(var.ROLES["fallen angel"]) > 0:
        for v in fallenkills:
            t = var.GUARDED.get(v)
            if v not in fallenmsg:
                fallenmsg.add(v)
                if v != t:
                    pm(cli, v, ("A fell wind starts blowing through the village and you catch the flurry of blackened wings out of the corner of your eye. " +
                                "No longer caring for \u0002{0}\u0002's safety, you attempt to get away before your own life is taken...").format(t))
                else:
                    pm(cli, v, "A fell wind blows through you and chills you to the bone. You no longer feel safe or protected...")
            if v != t and t not in fallenmsg:
                fallenmsg.add(t)
                pm(cli, t, "A fell wind blows through you and chills you to the bone. You no longer feel safe or protected...")
        # Also message GAs that don't die and their victims
        for g in var.ROLES["guardian angel"]:
            v = var.GUARDED.get(g)
            if v in bywolves and g not in fallenkills:
                if g not in fallenmsg:
                    fallenmsg.add(g)
                    if g != v:
                        pm(cli, g, ("A fell wind starts blowing through the village and you catch the flurry of blackened wings out of the corner of your eye. " +
                                    "No longer caring for \u0002{0}\u0002's safety, you attempt to get away before your own life is taken...").format(v))
                    else:
                        pm(cli, g, "A fell wind blows through you and chills you to the bone. You no longer feel safe or protected...")
                if g != v and v not in fallenmsg:
                    fallenmsg.add(g)
                    pm(cli, v, "A fell wind blows through you and chills you to the bone. You no longer feel safe or protected...")

    # Select a random target for assassin that isn't already going to die if they didn't target
    pl = var.list_players()
    for ass in var.ROLES["assassin"]:
        if ass not in var.TARGETED and ass not in var.SILENCED:
            ps = pl[:]
            ps.remove(ass)
            for victim in victims:
                if victim in ps:
                    ps.remove(victim)
            if len(ps) > 0:
                target = random.choice(ps)
                var.TARGETED[ass] = target
                pm(cli, ass, "Because you forgot to select a target at night, you are now targeting \u0002{0}\u0002.".format(target))

    message = [("Night lasted \u0002{0:0>2}:{1:0>2}\u0002. It is now daytime. "+
               "The villagers awake, thankful for surviving the night, "+
               "and search the village... ").format(min, sec)]

    # This needs to go down here since having them be their night value matters above
    var.ANGRY_WOLVES = False
    var.DISEASED_WOLVES = False
    var.ALPHA_ENABLED = False

    dead = []
    for crow, target in iter(var.OBSERVED.items()):
        if crow not in var.ROLES["werecrow"]:
            continue
        if ((target in list(var.HVISITED.keys()) and var.HVISITED[target]) or  # if var.HVISITED[target] is None, harlot visited self
            target in var.SEEN or target in var.SHAMANS or (target in list(var.GUARDED.keys()) and var.GUARDED[target])):
            pm(cli, crow, ("As the sun rises, you conclude that \u0002{0}\u0002 was not in "+
                          "bed all night, and you fly back to your house.").format(target))

        else:
            pm(cli, crow, ("As the sun rises, you conclude that \u0002{0}\u0002 was sleeping "+
                          "all night long, and you fly back to your house.").format(target))

    vlist = copy.copy(victims)
    novictmsg = True
    if new_wolf:
        message.append("A chilling howl was heard last night. It appears there is another werewolf in our midst!")
        var.EXTRA_WOLVES += 1
        novictmsg = False

    for victim in vlist:
        if victim in var.ROLES["harlot"] and var.HVISITED.get(victim) and victim not in dead and victim in onlybywolves:
            # alpha wolf can bite a harlot visiting another wolf, don't play a message in that case
            # kept as a nested if so that the other victim logic does not run
            if victim not in bitten:
                message.append("The wolves' selected victim was a harlot, who was not at home last night.")
                novictmsg = False
        elif protected.get(victim) == "totem":
            message.append(("\u0002{0}\u0002 was attacked last night, but their totem " +
                            "emitted a brilliant flash of light, blinding the attacker and " +
                            "allowing them to escape.").format(victim))
            novictmsg = False
        elif protected.get(victim) == "angel":
            message.append(("\u0002{0}\u0002 was attacked last night, but luckily, the guardian angel was on duty.").format(victim))
            novictmsg = False
        elif protected.get(victim) == "bodyguard":
            for bodyguard in var.ROLES["bodyguard"]:
                if var.GUARDED.get(bodyguard) == victim:
                    dead.append(bodyguard)
                    message.append(("\u0002{0}\u0002 sacrificed their life to guard that of another.").format(bodyguard))
                    novictmsg = False
                    break
        elif (victim in var.ROLES["lycan"] or victim in var.LYCANTHROPES) and victim in onlybywolves and victim not in var.IMMUNIZED:
            vrole = var.get_role(victim)
            if vrole not in var.WOLFCHAT_ROLES:
                message.append("A chilling howl was heard last night. It appears there is another werewolf in our midst!")
                var.EXTRA_WOLVES += 1
                pm(cli, victim, "HOOOOOOOOOWL. You have become... a wolf!")
                var.LYCAN_ROLES[victim] = vrole
                var.ROLES[vrole].remove(victim)
                var.ROLES["wolf"].add(victim)
                var.FINAL_ROLES[victim] = "wolf"
                wolves = var.list_players(var.WOLFCHAT_ROLES)
                random.shuffle(wolves)
                wolves.remove(victim)  # remove self from list
                for i, wolf in enumerate(wolves):
                    pm(cli, wolf, "\u0002{0}\u0002 is now a wolf!".format(victim))
                    role = var.get_role(wolf)
                    cursed = ""
                    if wolf in var.ROLES["cursed villager"]:
                        cursed = "cursed "
                    wolves[i] = "\u0002{0}\u0002 ({1}{2})".format(wolf, cursed, role)

                pm(cli, victim, "Wolves: " + ", ".join(wolves))
                novictmsg = False
        elif victim not in dead: # not already dead via some other means
            if victim in var.RETRIBUTION:
                loser = random.choice(killers[victim])
                if loser == "@wolves":
                    wolves = var.list_players(var.WOLF_ROLES)
                    for crow in var.ROLES["werecrow"]:
                        if crow in var.OBSERVED:
                            wolves.remove(crow)
                    loser = random.choice(wolves)
                if loser in var.VENGEFUL_GHOSTS.keys():
                    # mark ghost as being unable to kill any more
                    var.VENGEFUL_GHOSTS[loser] = "!" + var.VENGEFUL_GHOSTS[loser]
                    message.append(("\u0002{0}\u0002's totem emitted a brilliant flash of light last night. " +
                                    "It appears that \u0002{1}\u0002's spirit was driven away by the flash.").format(victim, loser))
                else:
                    dead.append(loser)
                    if var.ROLE_REVEAL in ("on", "team"):
                        role = var.get_reveal_role(loser)
                        an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                        message.append(("\u0002{0}\u0002's totem emitted a brilliant flash of light last night. " +
                                        "The dead body of \u0002{1}\u0002, a{2} \u0002{3}\u0002, was found at the scene.").format(victim, loser, an, role))
                    else:
                        message.append(("\u0002{0}\u0002's totem emitted a brilliant flash of light last night. " +
                                        "The dead body of \u0002{1}\u0002 was found at the scene.").format(victim, loser))
            if var.ROLE_REVEAL in ("on", "team"):
                role = var.get_reveal_role(victim)
                an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                message.append(("The dead body of \u0002{0}\u0002, a{1} \u0002{2}\u0002, is found. " +
                                "Those remaining mourn the tragedy.").format(victim, an, role))
            else:
                message.append(("The dead body of \u0002{0}\u0002 is found. " +
                                "Those remaining mourn the tragedy.").format(victim))
            dead.append(victim)
            if random.random() < var.GIF_CHANCE:
                message.append(random.choice(
                    ["https://i.imgur.com/nO8rZ.gifv",
                    "https://i.imgur.com/uGVfZ.gifv",
                    "https://i.imgur.com/mUcM09n.gifv",
                    "https://i.imgur.com/P7TEGyQ.gifv",
                    "https://i.imgur.com/b8HAvjL.gifv",
                    "https://i.imgur.com/PIIfL15.gifv"]
                    ))
            elif random.random() < var.FORTUNE_CHANCE:
                try:
                    out = subprocess.check_output(("fortune", "-s"))
                except OSError as e:
                    if e.errno != 2:
                        # No such file or directory (fortune is not installed)
                        raise
                else:
                    out = out.decode("utf-8", "replace")
                    out = out.replace("\n", " ")
                    out = re.sub(r"\s+", " ", out)  # collapse whitespace
                    out = out.strip()  # remove surrounding whitespace

                    message.append(out)

    # handle separately so it always happens no matter how victim dies, and so that we can account for bitten victims as well
    for victim in victims + bitten:
        if victim in dead and victim in var.HVISITED.values() and (victim in bywolves or victim in bitten):  #  victim was visited by some harlot and victim was attacked by wolves
            for hlt in var.HVISITED.keys():
                if var.HVISITED[hlt] == victim and hlt not in bitten and hlt not in dead:
                    message.append(("\u0002{0}\u0002, a \u0002harlot\u0002, made the unfortunate mistake of "+
                                    "visiting the victim's house last night and is "+
                                    "now dead.").format(hlt))
                    bywolves.add(hlt)
                    onlybywolves.add(hlt)
                    dead.append(hlt)

    if novictmsg and len(dead) == 0:
        message.append(random.choice(var.NO_VICTIMS_MESSAGES) + " All villagers, however, have survived.")

    for harlot in var.ROLES["harlot"]:
        if var.HVISITED.get(harlot) in var.list_players(var.WOLF_ROLES) and harlot not in dead and harlot not in bitten:
            message.append(("\u0002{0}\u0002, a \u0002harlot\u0002, made the unfortunate mistake of "+
                            "visiting a wolf's house last night and is "+
                            "now dead.").format(harlot))
            bywolves.add(harlot)
            onlybywolves.add(harlot)
            dead.append(harlot)
    for bodyguard in var.ROLES["bodyguard"]:
        if var.GUARDED.get(bodyguard) in var.list_players(var.WOLF_ROLES) and bodyguard not in dead and bodyguard not in bitten:
            r = random.random()
            if r < var.BODYGUARD_DIES_CHANCE:
                bywolves.add(bodyguard)
                onlybywolves.add(bodyguard)
                if var.ROLE_REVEAL == "on":
                    message.append(("\u0002{0}\u0002, a \u0002bodyguard\u0002, "+
                                    "made the unfortunate mistake of guarding a wolf "+
                                    "last night, and is now dead.").format(bodyguard))
                else: # off and team
                    message.append(("\u0002{0}\u0002 "+
                                    "made the unfortunate mistake of guarding a wolf "+
                                    "last night, and is now dead.").format(bodyguard))
                dead.append(bodyguard)
    for gangel in var.ROLES["guardian angel"]:
        if var.GUARDED.get(gangel) in var.list_players(var.WOLF_ROLES) and gangel not in dead and gangel not in bitten:
            r = random.random()
            if r < var.GUARDIAN_ANGEL_DIES_CHANCE:
                bywolves.add(gangel)
                onlybywolves.add(gangel)
                if var.ROLE_REVEAL == "on":
                    message.append(("\u0002{0}\u0002, a \u0002guardian angel\u0002, "+
                                    "made the unfortunate mistake of guarding a wolf "+
                                    "last night, and is now dead.").format(gangel))
                else: # off and team
                    message.append(("\u0002{0}\u0002 "+
                                    "made the unfortunate mistake of guarding a wolf "+
                                    "last night, and is now dead.").format(gangel))
                dead.append(gangel)

    for victim in list(dead):
        if victim in var.GUNNERS.keys() and var.GUNNERS[victim] > 0 and victim in bywolves:
            if random.random() < var.GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE:
                # pick a random wolf to be shot, but don't kill off werecrows that observed
                killlist = [wolf for wolf in var.list_players(var.WOLF_ROLES) if wolf not in var.OBSERVED.keys() and wolf not in dead]
                if killlist:
                    deadwolf = random.choice(killlist)
                    if var.ROLE_REVEAL in ("on", "team"):
                        message.append(("Fortunately, \u0002{0}\u0002 had bullets and "+
                                        "\u0002{1}\u0002, a \u0002{2}\u0002, was shot dead.").format(victim, deadwolf, var.get_reveal_role(deadwolf)))
                    else:
                        message.append(("Fortunately, \u0002{0}\u0002 had bullets and "+
                                        "\u0002{1}\u0002 was shot dead.").format(victim, deadwolf))
                    dead.append(deadwolf)
                    var.GUNNERS[victim] -= 1 # deduct the used bullet

    for victim in dead:
        if victim in bywolves and victim in var.DISEASED:
            var.DISEASED_WOLVES = True

        if var.WOLF_STEALS_GUN and victim in bywolves and victim in var.GUNNERS.keys() and var.GUNNERS[victim] > 0:
            # victim has bullets
            try:
                looters = var.list_players(var.WOLFCHAT_ROLES)
                while len(looters) > 0:
                    guntaker = random.choice(looters)  # random looter
                    if guntaker not in dead:
                        break
                    else:
                        looters.remove(guntaker)
                if guntaker not in dead:
                    numbullets = var.GUNNERS[victim]
                    if guntaker not in var.WOLF_GUNNERS:
                        var.WOLF_GUNNERS[guntaker] = 0
                    var.WOLF_GUNNERS[guntaker] += 1  # transfer bullets a wolf
                    mmsg = ("While searching {0}'s belongings, you found " +
                            "a gun loaded with 1 silver bullet! " +
                            "You may only use it during the day. " +
                            "If you shoot at a wolf, you will intentionally miss. " +
                            "If you shoot a villager, it is likely that they will be injured.")
                    mmsg = mmsg.format(victim)
                    pm(cli, guntaker, mmsg)
            except IndexError:
                pass # no wolves to give gun to (they were all killed during night or something)
            var.GUNNERS[victim] = 0  # just in case

    cli.msg(chan, "\n".join(message))

    for chump in var.BITTEN.keys():
        if chump not in dead and var.get_role(chump) not in var.WOLF_ROLES:
            pm(cli, chump, get_bitten_message(chump))

    for chump in bitten:
        if chump not in dead and chump not in var.WOLF_ROLES:
            if chump in var.ROLES["harlot"] and var.HVISITED.get(chump):
                pm(cli, chump, "While out visiting last night, you were overcome by a fierce-looking wolf and bitten on your neck...")
            else:
                pm(cli, chump, "You woke up today feeling light-headed, and you notice some odd bite marks on your neck...")

    for deadperson in dead:  # kill each player, but don't end the game if one group outnumbers another
        # take a shortcut for killer_role here since vengeful ghost only cares about team and not particular roles
        # this will have to be modified to track the actual killer if that behavior changes
        # we check if they have already been killed as well since del_player could do chain reactions and we want
        # to avoid sending duplicate messages.
        if deadperson in var.list_players():
            del_player(cli, deadperson, end_game = False, killer_role = "wolf" if deadperson in onlybywolves or deadperson in wolfghostvictims else "villager", deadlist = dead, original = deadperson)

    message = []

    for player, tlist in itertools.groupby(havetotem):
        ntotems = len(list(tlist))
        message.append("\u0002{0}\u0002 seem{1} to be in possession of {2} mysterious totem{3}...".format(
            player, "ed" if player not in var.list_players() else "s", "a" if ntotems == 1 else "\u0002{0}\u0002".format(ntotems), "s" if ntotems > 1 else ""))

    for brokentotem in brokentotem:
        message.append("Broken totem pieces were found next to \u0002{0}\u0002's body...".format(brokentotem))
    cli.msg(chan, "\n".join(message))

    if chk_win(cli):  # if after the last person is killed, one side wins, then actually end the game here
        return

    begin_day(cli)

def chk_nightdone(cli):
    if var.PHASE != "night":
        return

    # TODO: alphabetize and/or arrange sensibly
    pl = var.list_players()
    actedcount = sum(map(len, (var.SEEN, var.HVISITED, var.GUARDED, var.KILLS,
                               var.OTHER_KILLS, var.PASSED, var.OBSERVED,
                               var.HEXED, var.SHAMANS, var.CURSED, var.CHARMERS)))

    nightroles = get_roles("seer", "oracle", "harlot", "bodyguard", "guardian angel",
                           "wolf", "werecrow", "alpha wolf", "sorcerer", "hunter",
                           "hag", "shaman", "crazed shaman", "augur", "werekitten",
                           "warlock", "piper", "wolf mystic", "fallen angel")

    for ghost, against in var.VENGEFUL_GHOSTS.items():
        if not against.startswith("!"):
            nightroles.append(ghost)

    if var.FIRST_NIGHT:
        actedcount += len(var.MATCHMAKERS | var.CLONED.keys())
        nightroles.extend(get_roles("matchmaker", "clone"))

    if var.DISEASED_WOLVES:
        nightroles = [p for p in nightroles if p not in var.list_players(var.WOLF_ROLES - {"wolf cub", "werecrow"})]
    elif var.ALPHA_ENABLED:
        # add in alphas that have bitten (note an alpha can kill or bite, but not both)
        actedcount += len([p for p in var.BITE_PREFERENCES if p in var.ROLES["alpha wolf"]])

    for p in var.HUNTERS:
        # only remove one instance of their name if they have used hunter ability, in case they have templates
        # the OTHER_KILLS check ensures we only remove them if they acted in a *previous* night
        if p in var.ROLES["hunter"] and p not in var.OTHER_KILLS:
            nightroles.remove(p)

    # but remove all instances of their name if they are silenced
    nightroles = [p for p in nightroles if p not in var.SILENCED]

    # add in turncoats who should be able to act -- if they passed they're already in var.PASSED
    # but if they can act they're in var.TURNCOATS where the second tuple item is the current night
    # (if said tuple item is the previous night, then they are not allowed to act tonight)
    for tc, tu in var.TURNCOATS.items():
        if tc not in pl:
            continue
        if tu[1] == var.NIGHT_COUNT:
            nightroles.append(tc)
            actedcount += 1
        elif tu[1] < var.NIGHT_COUNT - 1:
            nightroles.append(tc)

    if var.PHASE == "night" and actedcount >= len(nightroles):
        # check for assassins that have not yet targeted
        # must be handled separately because assassin only acts on nights when their target is dead
        # and silenced assassin shouldn't add to actedcount
        for ass in var.ROLES["assassin"]:
            if ass not in var.TARGETED.keys() | var.SILENCED:
                return
        if not var.DISEASED_WOLVES:
            # flatten var.KILLS
            kills = set()
            for ls in var.KILLS.values():
                if not isinstance(ls, str):
                    kills.update(ls)
                else:
                    kills.add(ls)
            # check if wolves are actually agreeing
            # allow len(kills) == 0 through as that means that crow was dumb and observed instead
            # of killingor alpha wolf was alone and chose to bite instead of kill
            if not var.ANGRY_WOLVES and len(kills) > 1:
                return
            elif var.ANGRY_WOLVES and (len(kills) == 1 or len(kills) > 2):
                return

        for x, t in var.TIMERS.items():
            t[0].cancel()

        var.TIMERS = {}
        if var.PHASE == "night":  # Double check
            transition_day(cli)

@cmd("nolynch", "nl", "novote", "nv", "abstain", "abs", playing=True, phases=("day",))
def no_lynch(cli, nick, chan, rest):
    """Allows you to abstain from voting for the day."""
    if chan == botconfig.CHANNEL:
        if not var.ABSTAIN_ENABLED:
            cli.notice(nick, "This command has been disabled.")
            return
        elif var.LIMIT_ABSTAIN and var.ABSTAINED:
            cli.notice(nick, "The village has already abstained once this game and may not do so again.")
            return
        elif var.LIMIT_ABSTAIN and var.FIRST_DAY:
            cli.notice(nick, "The village may not abstain on the first day.")
            return
        elif nick in var.WOUNDED:
            cli.msg(chan, "{0}: You are wounded and resting, thus you are unable to vote for the day.".format(nick))
            return
        candidates = var.VOTES.keys()
        for voter in list(candidates):
            if nick in var.VOTES[voter]:
                var.VOTES[voter].remove(nick)
                if not var.VOTES[voter]:
                    del var.VOTES[voter]
        var.NO_LYNCH.add(nick)
        cli.msg(chan, "\u0002{0}\u0002 votes not to lynch anyone today.".format(nick))

        chk_decision(cli)
        return

@cmd("lynch", playing=True, pm=True, phases=("day",))
def lynch(cli, nick, chan, rest):
    """Use this to vote for a candidate to be lynched."""
    if not rest:
        show_votes.caller(cli, nick, chan, rest)
        return
    if chan != botconfig.CHANNEL:
        return

    rest = re.split(" +",rest)[0].strip()

    if nick in var.WOUNDED:
        cli.msg(chan, ("{0}: You are wounded and resting, "+
                      "thus you are unable to vote for the day.").format(nick))
        return
    if nick in var.ASLEEP:
        pm(cli, nick, "As you place your vote, your totem emits a brilliant flash of light. " +
                      "After recovering, you notice that you are still in your bed. " +
                      "That entire sequence of events must have just been a dream...")
        return

    var.NO_LYNCH.discard(nick)

    voted = get_victim(cli, nick, rest, True, var.SELF_LYNCH_ALLOWED)
    if not voted:
        return

    if not var.SELF_LYNCH_ALLOWED:
        if nick == voted:
            if nick in var.ROLES["fool"] | var.ROLES["jester"]:
                cli.notice(nick, "You may not vote yourself.")
            else:
                cli.notice(nick, "Please try to save yourself.")
            return

    lcandidates = list(var.VOTES.keys())
    for voters in lcandidates:  # remove previous vote
        if voters == voted and nick in var.VOTES[voters]:
            break
        if nick in var.VOTES[voters]:
            var.VOTES[voters].remove(nick)
            if not var.VOTES.get(voters) and voters != voted:
                del var.VOTES[voters]
            break

    if voted not in var.VOTES.keys():
        var.VOTES[voted] = []
    if nick not in var.VOTES[voted]:
        var.VOTES[voted].append(nick)
        cli.msg(chan, ("\u0002{0}\u0002 votes for "+
                       "\u0002{1}\u0002.").format(nick, voted))

    var.LAST_VOTES = None # reset

    chk_decision(cli)


# chooses a target given nick, taking luck totem/misdirection totem into effect
# returns the actual target
def choose_target(actor, nick):
    pl = var.list_players()
    if actor in var.MISDIRECTED:
        i = var.ALL_PLAYERS.index(nick)
        if random.randint(0, 1) == 0:
            # going left
            while True:
                i -= 1
                if i < 0:
                    i = len(var.ALL_PLAYERS) - 1
                if var.ALL_PLAYERS[i] in pl:
                    nick = var.ALL_PLAYERS[i]
                    break
        else:
            # going right
            while True:
                i += 1
                if i >= len(var.ALL_PLAYERS):
                    i = 0
                if var.ALL_PLAYERS[i] in pl:
                    nick = var.ALL_PLAYERS[i]
                    break
    if nick in var.LUCKY:
        i = var.ALL_PLAYERS.index(nick)
        if random.randint(0, 1) == 0:
            # going left
            while True:
                i -= 1
                if i < 0:
                    i = len(var.ALL_PLAYERS) - 1
                if var.ALL_PLAYERS[i] in pl:
                    nick = var.ALL_PLAYERS[i]
                    break
        else:
            # going right
            while True:
                i += 1
                if i >= len(var.ALL_PLAYERS):
                    i = 0
                if var.ALL_PLAYERS[i] in pl:
                    nick = var.ALL_PLAYERS[i]
                    break
    return nick

# returns true if a swap happened
# check for that to short-circuit the nightrole
def check_exchange(cli, actor, nick):
    #some roles can act on themselves, ignore this
    if actor == nick:
        return False
    if nick in var.EXCHANGED:
        var.EXCHANGED.remove(nick)
        actor_role = var.get_role(actor)
        nick_role = var.get_role(nick)

        # var.PASSED is used by many roles
        var.PASSED.discard(actor)

        if actor_role == "amnesiac":
            actor_role = var.AMNESIAC_ROLES[actor]
            if nick in var.AMNESIAC_ROLES:
                var.AMNESIAC_ROLES[actor] = var.AMNESIAC_ROLES[nick]
                var.AMNESIAC_ROLES[nick] = actor_role
            else:
                del var.AMNESIAC_ROLES[actor]
                var.AMNESIAC_ROLES[nick] = actor_role
        elif actor_role == "clone":
            if actor in var.CLONED:
                actor_target = var.CLONED.pop(actor)
        elif actor_role in var.TOTEM_ORDER:
            actor_totem = var.TOTEMS.pop(actor)
            if actor in var.SHAMANS:
                del var.SHAMANS[actor]
            if actor in var.LASTGIVEN:
                del var.LASTGIVEN[actor]
        elif actor_role in var.WOLF_ROLES - {"werecrow", "wolf cub", "alpha wolf"}:
            if actor in var.KILLS:
                del var.KILLS[actor]
        elif actor_role == "hunter":
            if actor in var.OTHER_KILLS:
                del var.OTHER_KILLS[actor]
            var.HUNTERS.discard(actor)
        elif actor_role in ("bodyguard", "guardian angel"):
            if actor in var.GUARDED:
                pm(cli, var.GUARDED.pop(actor), "Your protector seems to have disappeared...")
            if actor in var.LASTGUARDED:
                del var.LASTGUARDED[actor]
        elif actor_role in ("werecrow", "sorcerer"):
            if actor in var.OBSERVED:
                del var.OBSERVED[actor]
            if actor in var.KILLS:
                del var.KILLS[actor]
        elif actor_role == "harlot":
            if actor in var.HVISITED:
                if var.HVISITED[actor] is not None:
                    pm(cli, var.HVISITED[actor], "\u0002{0}\u0002 seems to have disappeared...".format(actor))
                del var.HVISITED[actor]
        elif actor_role in ("seer", "oracle", "augur"):
            var.SEEN.discard(actor)
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
            if actor in var.KILLS:
                del var.KILLS[actor]
        elif actor_role == "warlock":
            var.CURSED.discard(actor)
        elif actor_role == "turncoat":
            del var.TURNCOATS[actor]


        # var.PASSED is used by many roles
        var.PASSED.discard(nick)

        if nick_role == "amnesiac":
            if actor not in var.AMNESIAC_ROLES:
                nick_role = var.AMNESIAC_ROLES[nick]
                var.AMNESIAC_ROLES[actor] = nick_role
                del var.AMNESIAC_ROLES[nick]
            else: # we swapped amnesiac_roles earlier on, get our version back
                nick_role = var.AMNESIAC_ROLES[actor]
        elif nick_role == "clone":
            if nick in var.CLONED:
                nick_target = var.CLONED.pop(nick)
        elif nick_role in var.TOTEM_ORDER:
            nick_totem = var.TOTEMS.pop(nick)
            if nick in var.SHAMANS:
                del var.SHAMANS[nick]
            if nick in var.LASTGIVEN:
                del var.LASTGIVEN[nick]
        elif nick_role in var.WOLF_ROLES - {"werecrow", "wolf cub", "alpha wolf"}:
            if nick in var.KILLS:
                del var.KILLS[nick]
        elif nick_role == "hunter":
            if nick in var.OTHER_KILLS:
                del var.OTHER_KILLS[nick]
            var.HUNTERS.discard(nick)
        elif nick_role in ("bodyguard", "guardian angel"):
            if nick in var.GUARDED:
                pm(cli, var.GUARDED.pop(nick), "Your protector seems to have disappeared...")
            if nick in var.LASTGUARDED:
                del var.LASTGUARDED[nick]
        elif nick_role in ("werecrow", "sorcerer"):
            if nick in var.OBSERVED:
                del var.OBSERVED[nick]
            if nick in var.KILLS:
                del var.KILLS[nick]
        elif nick_role == "harlot":
            if nick in var.HVISITED:
                if var.HVISITED[nick] is not None:
                    pm(cli, var.HVISITED[nick], "\u0002{0}\u0002 seems to have disappeared...".format(nick))
                del var.HVISITED[nick]
        elif nick_role in ("seer", "oracle", "augur"):
            var.SEEN.discard(nick)
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
            if nick in var.KILLS:
                del var.KILLS[nick]
        elif nick_role == "warlock":
            var.CURSED.discard(nick)
        elif nick_role == "turncoat":
            del var.TURNCOATS[nick]


        var.FINAL_ROLES[actor] = nick_role
        var.FINAL_ROLES[nick] = actor_role
        var.ROLES[actor_role].add(nick)
        var.ROLES[actor_role].remove(actor)
        var.ROLES[nick_role].add(actor)
        var.ROLES[nick_role].remove(nick)
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
        if actor_role == "vengeful ghost":
            actor_rev_role = var.DEFAULT_ROLE
        elif actor_role == "time lord":
            actor_rev_role = "villager"

        nick_rev_role = nick_role
        if nick_role == "vengeful ghost":
            nick_rev_role = var.DEFAULT_ROLE
        elif actor_role == "time lord":
            nick_rev_role = "villager"

        # don't say who, since misdirection/luck totem may have switched it
        # and this makes life far more interesting
        pm(cli, actor, "You have exchanged roles with someone! You are now a \u0002{0}\u0002.".format(nick_rev_role))
        pm(cli, nick,  "You have exchanged roles with someone! You are now a \u0002{0}\u0002.".format(actor_rev_role))

        if nick_role == "clone":
            pm(cli, actor, "You are cloning \u0002{0}\u0002.".format(nick_target))
        elif nick_role in var.TOTEM_ORDER:
            if nick_role == "shaman":
                pm(cli, actor, "You have a \u0002{0}\u0002 totem.".format(nick_totem))
            var.TOTEMS[actor] = nick_totem
        elif nick_role == "mystic":
            numevil = len(var.list_players(var.WOLFTEAM_ROLES))
            pm(cli, actor, "There {0} \u0002{1}\u0002 evil villager{2} still alive.".format("are" if numevil != 1 else "is", numevil, "s" if numevil != 1 else ""))
        elif nick_role in var.WOLFCHAT_ROLES and actor_role not in var.WOLFCHAT_ROLES:
            pl = var.list_players()
            random.shuffle(pl)
            pl.remove(actor)  # remove self from list
            for i, player in enumerate(pl):
                prole = var.get_role(player)
                if prole in var.WOLFCHAT_ROLES:
                    cursed = ""
                    if player in var.ROLES["cursed villager"]:
                        cursed = "cursed "
                    pl[i] = "\u0002{0}\u0002 ({1}{2})".format(player, cursed, prole)
                    pm(cli, player, "\u0002{0}\u0002 and \u0002{1}\u0002 have exchanged roles!".format(nick, actor))
                elif player in var.ROLES["cursed villager"]:
                    pl[i] = player + " (cursed)"

            pm(cli, actor, "Players: " + ", ".join(pl))
            if actor_role == "wolf mystic":
                # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
                numvills = len(ps) - len(var.list_players(var.WOLFTEAM_ROLES)) - len(var.list_players(("villager", "vengeful ghost", "time lord", "amnesiac", "lycan"))) - len(var.list_players(var.TRUE_NEUTRAL_ROLES))
                pm(cli, actor, "There {0} \u0002{1}\u0002 special villager{2} still alive.".format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
            if var.DISEASED_WOLVES:
                pm(cli, actor, 'You are feeling ill tonight, and are unable to kill anyone.')
            elif var.ANGRY_WOLVES and actor_role in var.WOLF_ROLES and actor_role != "wolf cub":
                pm(cli, actor, 'You are \u0002angry\u0002 tonight, and may kill two targets by using "kill <nick1> and <nick2>".')
            if var.ALPHA_ENABLED and actor_role == "alpha wolf" and actor not in var.ALPHA_WOLVES:
                pm(cli, actor, ('You may use "bite <nick>" tonight in order to turn the wolves\' target into a wolf instead of killing them. ' +
                                'They will turn into a wolf in {0} night{1}.').format(var.ALPHA_WOLF_NIGHTS, 's' if var.ALPHA_WOLF_NIGHTS > 1 else ''))
        elif nick_role == "minion":
            wolves = var.list_players(var.WOLF_ROLES)
            random.shuffle(wolves)
            pm(cli, actor, "Wolves: " + ", ".join(wolves))
        elif nick_role == "turncoat":
            var.TURNCOATS[actor] = ("none", -1)

        if actor_role == "clone":
            pm(cli, nick, "You are cloning \u0002{0}\u0002.".format(actor_target))
        elif actor_role in var.TOTEM_ORDER:
            if actor_role == "shaman":
                pm(cli, nick, "You have a \u0002{0}\u0002 totem.".format(actor_totem))
            var.TOTEMS[nick] = actor_totem
        elif actor_role == "mystic":
            numevil = len(var.list_players(var.WOLFTEAM_ROLES))
            pm(cli, nick, "There {0} \u0002{1}\u0002 evil villager{2} still alive.".format("are" if numevil != 1 else "is", numevil, "s" if numevil != 1 else ""))
        elif actor_role in var.WOLFCHAT_ROLES and nick_role not in var.WOLFCHAT_ROLES:
            pl = var.list_players()
            random.shuffle(pl)
            pl.remove(nick)  # remove self from list
            for i, player in enumerate(pl):
                prole = var.get_role(player)
                if prole in var.WOLFCHAT_ROLES:
                    cursed = ""
                    if player in var.ROLES["cursed villager"]:
                        cursed = "cursed "
                    pl[i] = "\u0002{0}\u0002 ({1}{2})".format(player, cursed, prole)
                    pm(cli, player, "\u0002{0}\u0002 and \u0002{1}\u0002 have exchanged roles!".format(actor, nick))
                elif player in var.ROLES["cursed villager"]:
                    pl[i] = player + " (cursed)"

            pm(cli, nick, "Players: " + ", ".join(pl))
            if nick_role == "wolf mystic":
                # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
                numvills = len(ps) - len(var.list_players(var.WOLFTEAM_ROLES)) - len(var.list_players(("villager", "vengeful ghost", "time lord", "amnesiac", "lycan"))) - len(var.list_players(var.TRUE_NEUTRAL_ROLES))
                pm(cli, nick, "There {0} \u0002{1}\u0002 special villager{2} still alive.".format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
            if var.DISEASED_WOLVES:
                pm(cli, nick, 'You are feeling ill tonight, and are unable to kill anyone.')
            elif var.ANGRY_WOLVES and nick_role in ("wolf", "werecrow", "alpha wolf", "werekitten"):
                pm(cli, nick, 'You are \u0002angry\u0002 tonight, and may kill two targets by using "kill <nick1> and <nick2>".')
            if var.ALPHA_ENABLED and nick_role == "alpha wolf" and nick not in var.ALPHA_WOLVES:
                pm(cli, nick, ('You may use "bite <nick>" tonight in order to turn the wolves\' target into a wolf instead of killing them. ' +
                               'They will turn into a wolf in {0} night{1}.').format(var.ALPHA_WOLF_NIGHTS, 's' if var.ALPHA_WOLF_NIGHTS > 1 else ''))
        elif actor_role == "minion":
            wolves = var.list_players(var.WOLF_ROLES)
            random.shuffle(wolves)
            pm(cli, nick, "Wolves: " + ", ".join(wolves))
        elif actor_role == "turncoat":
            var.TURNCOATS[nick] = ("none", -1)

        var.EXCHANGED_ROLES.append((actor, nick))
        return True
    return False

@cmd("retract", "r", pm=True, phases=("day", "night", "join"))
def retract(cli, nick, chan, rest):
    """Takes back your vote during the day (for whom to lynch)."""

    if chan not in (botconfig.CHANNEL, nick):
        return
    if (nick not in var.VENGEFUL_GHOSTS.keys() and nick not in var.list_players()) or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return

    with var.GRAVEYARD_LOCK, var.WARNING_LOCK:
        if var.PHASE == "join":
            if not nick in var.START_VOTES:
                cli.notice(nick, "You haven't voted to start.")
            else:
                var.START_VOTES.discard(nick)
                cli.msg(chan, "\u0002{0}\u0002's vote to start was retracted.".format(nick))

                if len(var.START_VOTES) < 1:
                    var.TIMERS['start_votes'][0].cancel()
                    del var.TIMERS['start_votes']
            return

    if chan == nick: # PM, use different code
        role = var.get_role(nick)
        if role not in var.WOLF_ROLES - {"wolf cub"} and role != "hunter" and nick not in var.VENGEFUL_GHOSTS.keys():
            return
        if var.PHASE != "night":
            return
        if role == "werecrow":  # Check if already observed
            if var.OBSERVED.get(nick):
                pm(cli, nick, ("You have already transformed into a crow, and "+
                               "cannot turn back until day."))
                return
        elif role == "hunter" and nick in var.HUNTERS and nick not in var.OTHER_KILLS.keys():
            return

        if role in var.WOLF_ROLES and nick in var.KILLS.keys():
            del var.KILLS[nick]
            pm(cli, nick, "You have retracted your kill.")
            wolfchatwolves = var.list_players(var.WOLFCHAT_ROLES)
            for wolf in wolfchatwolves:
                if wolf != nick:
                    pm(cli, wolf, "\u0002{0}\u0002 has retracted their kill.".format(nick))
        elif role not in var.WOLF_ROLES and nick in var.OTHER_KILLS.keys():
            del var.OTHER_KILLS[nick]
            if role == "hunter":
                var.HUNTERS.remove(nick)
            pm(cli, nick, "You have retracted your kill.")
        elif role == "alpha wolf" and nick in var.BITE_PREFERENCES.keys():
            del var.BITE_PREFERENCES[nick]
            var.ALPHA_WOLVES.remove(nick)
            pm(cli, nick, "You have decided not to bite anyone tonight.")
            wolfchatwolves = var.list_players(var.WOLFCHAT_ROLES)
            for wolf in wolfchatwolves:
                if wolf != nick:
                    pm(cli, wolf, "\u0002{0}\u0002 has decided not to bite anyone tonight.".format(nick))
        elif role == "alpha wolf" and var.ALPHA_ENABLED:
            pm(cli, nick, "You have not chosen to kill or bite anyone yet.")
        else:
            pm(cli, nick, "You have not chosen to kill anyone yet.")
        return

    if var.PHASE != "day":
        return
    if nick in var.NO_LYNCH:
        var.NO_LYNCH.remove(nick)
        cli.msg(chan, "\u0002{0}\u0002's vote was retracted.".format(nick))
        var.LAST_VOTES = None # reset
        return

    candidates = var.VOTES.keys()
    for voter in list(candidates):
        if nick in var.VOTES[voter]:
            var.VOTES[voter].remove(nick)
            if not var.VOTES[voter]:
                del var.VOTES[voter]
            cli.msg(chan, "\u0002{0}\u0002's vote was retracted.".format(nick))
            var.LAST_VOTES = None # reset
            break
    else:
        cli.notice(nick, "You haven't voted yet.")

@cmd("shoot", playing=True, silenced=True, phases=("day",))
def shoot(cli, nick, chan, rest):
    """Use this to fire off a bullet at someone in the day if you have bullets."""

    if chan != botconfig.CHANNEL:
        return

    if nick not in var.GUNNERS.keys() | var.WOLF_GUNNERS.keys():
        cli.notice(nick, "You don't have a gun.")
        return
    elif not var.GUNNERS.get(nick) and not var.WOLF_GUNNERS.get(nick):
        cli.notice(nick, "You don't have any more bullets.")
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], True)
    if not victim:
        return
    if victim == nick:
        cli.notice(nick, "You are holding it the wrong way.")
        return
    # get actual victim
    victim = choose_target(nick, victim)

    wolfshooter = nick in var.list_players(var.WOLFCHAT_ROLES)

    if wolfshooter and nick in var.WOLF_GUNNERS and var.WOLF_GUNNERS[nick]:
        var.WOLF_GUNNERS[nick] -= 1
    else:
        var.GUNNERS[nick] -= 1

    rand = random.random()
    if nick in var.ROLES["village drunk"]:
        chances = var.DRUNK_GUN_CHANCES
    elif nick in var.ROLES["sharpshooter"]:
        chances = var.SHARPSHOOTER_GUN_CHANCES
    else:
        chances = var.GUN_CHANCES

    wolfvictim = victim in var.list_players(var.WOLF_ROLES)
    realrole = var.get_role(victim)
    victimrole = var.get_reveal_role(victim)

    alwaysmiss = (realrole == "werekitten")

    if rand <= chances[0] and not (wolfshooter and wolfvictim) and not alwaysmiss:
        # didn't miss or suicide and it's not a wolf shooting another wolf

        cli.msg(chan, ("\u0002{0}\u0002 shoots \u0002{1}\u0002 with "+
                       "a silver bullet!").format(nick, victim))
        an = "n" if victimrole.startswith(("a", "e", "i", "o", "u")) else ""
        if realrole in var.WOLF_ROLES:
            if var.ROLE_REVEAL == "on":
                cli.msg(chan, ("\u0002{0}\u0002 is a{1} \u0002{2}\u0002, and is dying from "+
                               "the silver bullet.").format(victim,an, victimrole))
            else: # off and team
                cli.msg(chan, ("\u0002{0}\u0002 is a wolf, and is dying from "+
                               "the silver bullet.").format(victim))
            if not del_player(cli, victim, killer_role = var.get_role(nick)):
                return
        elif random.random() <= chances[3]:
            accident = "accidentally "
            if nick in var.ROLES["sharpshooter"]:
                accident = "" # it's an accident if the sharpshooter DOESN'T headshot :P
            cli.msg(chan, ("\u0002{0}\u0002 is not a wolf "+
                           "but was {1}fatally injured.").format(victim, accident))
            if var.ROLE_REVEAL in ("on", "team"):
                cli.msg(chan, "The village has sacrificed a{0} \u0002{1}\u0002.".format(an, victimrole))
            if not del_player(cli, victim, killer_role = var.get_role(nick)):
                return
        else:
            cli.msg(chan, ("\u0002{0}\u0002 is a villager and was injured. Luckily "+
                          "the injury is minor and will heal after a day of "+
                          "rest.").format(victim))
            var.WOUNDED.add(victim)
            lcandidates = list(var.VOTES.keys())
            for cand in lcandidates:  # remove previous vote
                if victim in var.VOTES[cand]:
                    var.VOTES[cand].remove(victim)
                    if not var.VOTES.get(cand):
                        del var.VOTES[cand]
                    break
            chk_decision(cli)
            chk_win(cli)
    elif rand <= chances[0] + chances[1]:
        cli.msg(chan, "\u0002{0}\u0002 is a lousy shooter and missed!".format(nick))
    else:
        if var.ROLE_REVEAL in ("on", "team"):
            cli.msg(chan, ("Oh no! \u0002{0}\u0002's gun was poorly maintained and has exploded! "+
                           "The village mourns a gunner-\u0002{1}\u0002.").format(nick, var.get_reveal_role(nick)))
        else:
            cli.msg(chan, ("Oh no! \u0002{0}\u0002's gun was poorly maintained and has exploded!").format(nick))
        if not del_player(cli, nick, killer_role = "villager"): # blame explosion on villager's shoddy gun construction or something
            return  # Someone won.



@cmd("kill", chan=False, pm=True, phases=("night",))
def kill(cli, nick, chan, rest):
    """Kill a player. Behaviour varies depending on your role."""
    if (nick not in var.VENGEFUL_GHOSTS.keys() and nick not in var.list_players()) or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    try:
        role = var.get_role(nick)
    except KeyError:
        role = None
    wolfroles = var.WOLF_ROLES - {"wolf cub"}
    if role in var.WOLFCHAT_ROLES and role not in wolfroles:
        return  # they do this a lot.
    if role not in wolfroles | {"hunter"} and nick not in var.VENGEFUL_GHOSTS.keys():
        return
    if nick in var.VENGEFUL_GHOSTS.keys() and var.VENGEFUL_GHOSTS[nick][0] == "!":
        # ghost was driven away by retribution
        return
    if role == "hunter" and nick in var.HUNTERS and nick not in var.OTHER_KILLS:
        # they are a hunter and did not kill this night (if they killed this night, this allows them to switch)
        pm(cli, nick, "You have already killed someone this game.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    if role in wolfroles and var.DISEASED_WOLVES:
        pm(cli, nick, "You are feeling ill, and are unable to kill anyone tonight.")
        return
    if role == "alpha wolf" and nick in var.BITE_PREFERENCES:
        pm(cli, nick, 'You have chosen to bite someone tonight and cannot participate in the kill. Use "retract" if you want to not bite anyone tonight.')
        return
    pieces = re.split(" +",rest)
    victim = pieces[0]
    victim2 = None
    if role in wolfroles and var.ANGRY_WOLVES:
        if len(pieces) > 1:
            if len(pieces) > 2 and pieces[1].lower() == "and":
                victim2 = pieces[2]
            else:
                victim2 = pieces[1]
        else:
            victim2 = None
    if role == "werecrow":  # Check if flying to observe
        if var.OBSERVED.get(nick):
            pm(cli, nick, ("You have already transformed into a crow; therefore, "+
                           "you are physically unable to kill a villager."))
            return

    victim = get_victim(cli, nick, victim, False)
    if not victim:
        return
    if victim2 != None:
        victim2 = get_victim(cli, nick, victim2, False)
        if not victim2:
            return

    if victim == nick or victim2 == nick:
        if nick in var.VENGEFUL_GHOSTS.keys():
            pm(cli, nick, "You are already dead.")
        else:
            pm(cli, nick, "Suicide is bad. Don't do it.")
        return

    if nick in var.VENGEFUL_GHOSTS.keys():
        allwolves = var.list_players(var.WOLFTEAM_ROLES)
        if var.VENGEFUL_GHOSTS[nick] == "wolves" and victim not in allwolves:
            pm(cli, nick, "You must target a wolf.")
            return
        elif var.VENGEFUL_GHOSTS[nick] == "villagers" and victim in allwolves:
            pm(cli, nick, "You must target a villager.")
            return

    if role in wolfroles:
        wolfchatwolves = var.list_players(var.WOLFCHAT_ROLES)
        if victim in wolfchatwolves or victim2 in wolfchatwolves:
            pm(cli, nick, "You may only kill villagers, not other wolves.")
            return
        if var.ANGRY_WOLVES and victim2 != None:
            if victim == victim2:
                pm(cli, nick, "You should select two different players.")
                return
            else:
                rv = choose_target(nick, victim)
                rv2 = choose_target(nick, victim2)
                if check_exchange(cli, nick, rv):
                    return
                if check_exchange(cli, nick, rv2):
                    return
                var.KILLS[nick] = [rv, rv2]
        else:
            rv = choose_target(nick, victim)
            if check_exchange(cli, nick, rv):
                return
            var.KILLS[nick] = [rv]
    else:
        rv = choose_target(nick, victim)
        if nick not in var.VENGEFUL_GHOSTS.keys():
            if check_exchange(cli, nick, rv):
                return
        var.OTHER_KILLS[nick] = rv
        if role == "hunter":
            var.HUNTERS.add(nick)
            var.PASSED.discard(nick)

    if victim2 != None:
        msg = " selected \u0002{0}\u0002 and \u0002{1}\u0002 to be killed.".format(victim, victim2)
        pm(cli, nick, "You have{0}".format(msg))
    else:
        msg = " selected \u0002{0}\u0002 to be killed.".format(victim)
        pm(cli, nick, "You have{0}".format(msg))
        if var.ANGRY_WOLVES and role in wolfroles:
            pm(cli, nick, 'You are angry tonight and may kill a second target. Use "kill <nick1> and <nick2>" to select multiple targets.')

    wolfchatwolves = var.list_players(var.WOLFCHAT_ROLES)
    if nick in wolfchatwolves:
        for wolf in wolfchatwolves:
            if wolf != nick:
                pm(cli, wolf, "\u0002{0}\u0002 has{1}".format(nick, msg))

    if victim2:
        debuglog("{0} ({1}) KILL: {2} and {3} ({4})".format(nick, role, victim, victim2, var.get_role(victim2)))
    else:
        debuglog("{0} ({1}) KILL: {2} ({3})".format(nick, role, victim, var.get_role(victim)))

    chk_nightdone(cli)

@cmd("guard", "protect", "save", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("bodyguard", "guardian angel"))
def guard(cli, nick, chan, rest):
    """Guard a player, preventing them from being targetted that night."""
    if var.GUARDED.get(nick):
        pm(cli, nick, "You are already protecting someone tonight.")
        return
    role = var.get_role(nick)
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, role == "bodyguard" or var.GUARDIAN_ANGEL_CAN_GUARD_SELF)
    if not victim:
        return

    if role == "guardian angel" and var.LASTGUARDED.get(nick) == victim:
        pm(cli, nick, ("You protected \u0002{0}\u0002 last night. " +
                       "You cannot protect the same person two nights in a row.").format(victim))
        return
    if victim == nick:
        if role == "bodyguard" or not var.GUARDIAN_ANGEL_CAN_GUARD_SELF:
            pm(cli, nick, "You cannot guard yourself. Use pass if you do not wish to guard anyone tonight.")
            return
        elif role == "guardian angel": # choosing to guard self bypasses lucky/misdirection
            var.GUARDED[nick] = nick
            var.LASTGUARDED[nick] = nick
            pm(cli, nick, "You have decided to guard yourself tonight.")
    else:
        victim = choose_target(nick, victim)
        if check_exchange(cli, nick, victim):
            return
        var.GUARDED[nick] = victim
        var.LASTGUARDED[nick] = victim
        pm(cli, nick, "You are protecting \u0002{0}\u0002 tonight. Farewell!".format(var.GUARDED[nick]))
        pm(cli, var.GUARDED[nick], "You can sleep well tonight, for you are being protected.")
    debuglog("{0} ({1}) GUARD: {2} ({3})".format(nick, role, victim, var.get_role(victim)))
    chk_nightdone(cli)



@cmd("observe", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("werecrow", "sorcerer"))
def observe(cli, nick, chan, rest):
    """Observe a player to obtain various information."""
    role = var.get_role(nick)
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if victim == nick:
        if role == "werecrow":
            pm(cli, nick, "Instead of doing that, you should probably go kill someone.")
        else:
            pm(cli, nick, "That would be a waste.")
        return
    if nick in var.OBSERVED.keys():
        if role == "werecrow":
            pm(cli, nick, "You are already flying to \u0002{0}\u0002's house.".format(var.OBSERVED[nick]))
        else:
            pm(cli, nick, "You have already observed tonight.")
        return
    if var.get_role(victim) in var.WOLFCHAT_ROLES:
        if role == "werecrow":
            pm(cli, nick, "Flying to another wolf's house is a waste of time.")
        else:
            pm(cli, nick, "Observing another wolf is a waste of time.")
        return
    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return
    var.OBSERVED[nick] = victim
    if nick in var.KILLS.keys():
        del var.KILLS[nick]
    if role == "werecrow":
        pm(cli, nick, ("You transform into a large crow and start your flight "+
                       "to \u0002{0}'s\u0002 house. You will return after "+
                      "collecting your observations when day begins.").format(victim))
        wolfchatwolves = var.list_players(var.WOLFCHAT_ROLES)
        for wolf in wolfchatwolves:
            if wolf != nick:
                pm(cli, wolf, "\u0002{0}\u0002 is observing \u0002{1}\u0002.".format(nick, victim))
    elif role == "sorcerer":
        vrole = var.get_role(victim)
        if vrole == "amnesiac":
            vrole = var.AMNESIAC_ROLES[victim]
        if vrole in ("seer", "oracle", "augur", "sorcerer"):
            an = "n" if vrole.startswith(("a", "e", "i", "o", "u")) else ""
            pm(cli, nick, ("After casting your ritual, you determine that \u0002{0}\u0002 " +
                           "is a{1} \u0002{2}\u0002!").format(victim, an, vrole))
        else:
            pm(cli, nick, ("After casting your ritual, you determine that \u0002{0}\u0002 " +
                           "does not have paranormal senses.").format(victim))
    debuglog("{0} ({1}) OBSERVE: {2} ({3})".format(nick, role, victim, var.get_role(victim)))
    chk_nightdone(cli)

@cmd("id", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("detective",))
def investigate(cli, nick, chan, rest):
    """Investigate a player to determine their exact role."""
    if nick in var.INVESTIGATED:
        pm(cli, nick, "You may only investigate one person per round.")
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if victim == nick:
        pm(cli, nick, "Investigating yourself would be a waste.")
        return

    victim = choose_target(nick, victim)
    var.INVESTIGATED.add(nick)
    vrole = var.get_role(victim)
    if vrole == "amnesiac":
        vrole = var.AMNESIAC_ROLES[victim]
    pm(cli, nick, ("The results of your investigation have returned. \u0002{0}\u0002"+
                   " is a... \u0002{1}\u0002!").format(victim, vrole))
    debuglog("{0} ({1}) ID: {2} ({3})".format(nick, var.get_role(nick), victim, vrole))
    if random.random() < var.DETECTIVE_REVEALED_CHANCE:  # a 2/5 chance (should be changeable in settings)
        # The detective's identity is compromised!
        for badguy in var.list_players(var.WOLFCHAT_ROLES):
            pm(cli, badguy, ("Someone accidentally drops a paper. The paper reveals "+
                            "that \u0002{0}\u0002 is the detective!").format(nick))
        debuglog("{0} ({1}) PAPER DROP".format(nick, var.get_role(nick)))

@cmd("visit", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("harlot",))
def hvisit(cli, nick, chan, rest):
    """Visit a player. You will die if you visit a wolf or a target of the wolves."""
    if var.HVISITED.get(nick):
        pm(cli, nick, ("You are already spending the night "+
                      "with \u0002{0}\u0002.").format(var.HVISITED[nick]))
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, True)
    if not victim:
        return

    if nick == victim:  # Staying home (same as calling pass, so call pass)
        pass_cmd.func(cli, nick, chan, "")
        return
    else:
        victim = choose_target(nick, victim)
        if check_exchange(cli, nick, victim):
            return
        var.HVISITED[nick] = victim
        pm(cli, nick, ("You are spending the night with \u0002{0}\u0002. "+
                      "Have a good time!").format(victim))
        if nick != victim: #prevent luck/misdirection totem weirdness
            pm(cli, victim, ("You are spending the night with \u0002{0}"+
                                     "\u0002. Have a good time!").format(nick))
    debuglog("{0} ({1}) VISIT: {2} ({3})".format(nick, var.get_role(nick), victim, var.get_role(victim)))
    chk_nightdone(cli)

def is_fake_nick(who):
    return re.search(r"^[0-9]+$", who)

@cmd("see", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("seer", "oracle", "augur"))
def see(cli, nick, chan, rest):
    """Use your paranormal powers to determine the role or alignment of a player."""
    role = var.get_role(nick)
    if nick in var.SEEN:
        pm(cli, nick, "You may only have one vision per round.")
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if victim == nick:
        pm(cli, nick, "Seeing yourself would be a waste.")
        return
    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return
    victimrole = var.get_role(victim)
    vrole = victimrole # keep a copy for logging
    if role == "seer":
        if (victimrole in var.SEEN_WOLF and victimrole not in var.SEEN_DEFAULT) or victim in var.ROLES["cursed villager"]:
            victimrole = "wolf"
        elif victimrole in var.SEEN_DEFAULT:
            victimrole = var.DEFAULT_ROLE
            if var.DEFAULT_SEEN_AS_VILL:
                victimrole = "villager"
        pm(cli, nick, ("You have a vision; in this vision, "+
                        "you see that \u0002{0}\u0002 is a "+
                        "\u0002{1}\u0002!").format(victim, victimrole))
        debuglog("{0} ({1}) SEE: {2} ({3}) as {4}".format(nick, role, victim, vrole, victimrole))
    elif role == "oracle":
        iswolf = False
        if (victimrole in var.SEEN_WOLF and victimrole not in var.SEEN_DEFAULT) or victim in var.ROLES["cursed villager"]:
            iswolf = True
        pm(cli, nick, ("Your paranormal senses are tingling! "+
                        "The spirits tell you that \u0002{0}\u0002 is {1}"+
                        "a {2}wolf{2}!").format(victim, "" if iswolf else "\u0002not\u0002 ", "\u0002" if iswolf else ""))
        debuglog("{0} ({1}) SEE: {2} ({3}) (Wolf: {4})".format(nick, role, victim, vrole, str(iswolf)))
    elif role == "augur":
        if victimrole == "amnesiac":
            victimrole = var.AMNESIAC_ROLES[victim]
        aura = "blue"
        if victimrole in var.WOLFTEAM_ROLES:
            aura = "red"
        elif victimrole in var.TRUE_NEUTRAL_ROLES:
            aura = "grey"
        pm(cli, nick, ("You have a vision; in this vision, " +
                       "you see that \u0002{0}\u0002 exudes " +
                       "a \u0002{1}\u0002 aura!").format(victim, aura))
        debuglog("{0} ({1}) SEE: {2} ({3}) as {4} ({5} aura)".format(nick, role, victim, vrole, victimrole, aura))
    var.SEEN.add(nick)
    chk_nightdone(cli)

@cmd("give", chan=False, pm=True, playing=True, silenced=True, phases=("day", "night"), roles=var.TOTEM_ORDER+("doctor",))
def give(cli, nick, chan, rest):
    """Give a totem or immunization to a player."""
    role = var.get_role(nick)
    if role in var.TOTEM_ORDER:
        totem.caller(cli, nick, chan, rest)
    elif role == "doctor":
        immunize.caller(cli, nick, chan, rest)

@cmd("totem", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=var.TOTEM_ORDER)
def totem(cli, nick, chan, rest, prefix="You"):
    """Give a totem to a player."""
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, True)
    if not victim:
        return
    if var.LASTGIVEN.get(nick) == victim:
        pm(cli, nick, "You gave your totem to \u0002{0}\u0002 last time, you must choose someone else.".format(victim))
        return

    original_victim = victim
    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return
    totem = ""
    role = var.get_role(nick)
    if role != "crazed shaman":
        totem = " of " + var.TOTEMS[nick]
    pm(cli, nick, ("{0} have given a totem{1} to \u0002{2}\u0002.").format(prefix, totem, original_victim))
    var.SHAMANS[nick] = (victim, original_victim)
    debuglog("{0} ({1}) TOTEM: {2} ({3})".format(nick, role, victim, totem))
    chk_nightdone(cli)

@cmd("immunize", "immunise", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("doctor",))
def immunize(cli, nick, chan, rest):
    """Immunize a player, preventing them from turning into a wolf."""
    if nick not in var.DOCTORS: # something with amnesiac or clone or exchange totem
        var.DOCTORS[nick] = math.ceil(var.DOCTOR_IMMUNIZATION_MULTIPLIER * len(var.ALL_PLAYERS))
    if not var.DOCTORS.get(nick):
        pm(cli, nick, "You have run out of immunizations.")
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, True)
    if not victim:
        return
    victim = choose_target(nick, victim)
    vrole = var.get_role(victim)
    if check_exchange(cli, nick, victim):
        return
    pm(cli, nick, "You have given an immunization to \u0002{0}\u0002.".format(victim))
    lycan = False
    if vrole == "lycan":
        lycan = True
        lycan_message = ("You feel as if a curse has been lifted from you... It seems that your lycanthropy is cured " +
                         "and you will no longer become a werewolf if targeted by the wolves!")
        var.ROLES["lycan"].remove(victim)
        var.ROLES["villager"].add(victim)
        var.FINAL_ROLES[victim] = "villager"
        var.CURED_LYCANS.add(victim)
        var.IMMUNIZED.add(victim)
    elif victim in var.BITTEN:
        # fun fact: immunizations in real life are done by injecting a small amount of (usually neutered) virus into the person
        # so that their immune system can fight it off and build up antibodies. This doesn't work very well if that person is
        # currently afflicted with the virus however, as you're just adding more virus to the mix...
        # naturally, we would want to mimic that behavior here, and what better way of indicating that things got worse than
        # by making the turning happen a night earlier? :)
        var.BITTEN[victim] -= 1
        lycan_message = ("You have a brief flashback to {0} last night. " +
                         "The event quickly subsides, but a lingering thought remains in your mind...").format(
                                 "the events of" if vrole == "guardian angel" else "your dream")
    else:
        lycan_message = "You don't feel any different..."
        var.IMMUNIZED.add(victim)
    pm(cli, victim, ("You feel a sharp prick in the back of your arm and temporarily black out. " +
                     "When you come to, you notice an empty syringe lying on the ground. {0}").format(lycan_message))
    var.DOCTORS[nick] -= 1
    debuglog("{0} ({1}) IMMUNIZE: {2} ({3})".format(nick, var.get_role(nick), victim, "lycan" if lycan else var.get_role(victim)))

def get_bitten_message(nick):
    time_left = var.BITTEN[nick]
    role = var.get_role(nick)
    message = ""
    if role == "guardian angel":
        if time_left <= 1:
            message = ("After returning from last night's activities, you felt another wave of pain, this time on your back. " +
                       "Your wings grew larger and you can now fly faster and farther than ever before. Along with " +
                       "the size change, their color shifted from pure white to a midnight black. You didn't spend much " +
                       "time thinking on what happened, as you were tired and went to sleep shortly thereafter.")
        elif time_left == 2:
            message = ("Despite the gloves, it seems that the villagers have been keeping their distance from you as of late. " +
                       "None of them seem to know about your changes, so the change of behavior greatly angers you. You're " +
                       "doing just as good a job as ever, and if anything the changes make you MORE effective and powerful. " +
                       "These thoughts lingered for the rest of last night until you finally drifted off to an uneasy sleep.")
        else:
            message = ("As you were out last night, you felt a painful sensation as your hands grew very sharp claws. " +
                       "You figure they are now sharp enough to cut through most anything, but to avoid alarming the village " +
                       "you decide to fashion some gloves and wear them around from now on in an attempt to show nothing is " +
                       "happening.")
    else:
        if time_left <= 1:
            message = ("You had the same dream again, but this time YOU were the pursuer. You smell fear from your quarry " +
                       "as you give an exhilerating chase, going only half your speed in order to draw out the fun. " +
                       "Suddenly your prey trips over a rock and falls down, allowing you to close in the remaining distance. " +
                       "You savor the fear in their eyes briefly before you raise your claw to deal a killing blow. " +
                       "Right before it connects, you wake up.")
        elif time_left == 2:
            message = ("You dreamt of running through the woods outside the village at night, wind blowing across your " +
                       "face as you weave between the pines. Suddenly you hear a rustling sound as a monstrous creature " +
                       "jumps out at you - a werewolf! You start running as fast as you can, you soon feel yourself falling " +
                       "down as you trip over a rock. You look up helplessly as the werewolf catches up to you, " +
                       "then wake up screaming.")
        else:
            message = ("You had a strange dream last night; a person was running away from something through a forest. " +
                       "They tripped and fell over a rock as a shadow descended upon them. Before you could actually see " +
                       "who or what the pursuer was, you woke with a start.")
    return message

@cmd("bite", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("alpha wolf",))
def bite_cmd(cli, nick, chan, rest):
    """Bite a player, turning them into a wolf after a certain number of nights."""
    if nick in var.ALPHA_WOLVES and nick not in var.BITE_PREFERENCES:
        pm(cli, nick, "You have already bitten someone this game.")
        return
    if not var.ALPHA_ENABLED:
        pm(cli, nick, "You may only bite someone after another wolf has died during the day.")
        return
    if var.DISEASED_WOLVES:
        pm(cli, nick, "You are feeling ill, and are unable to kill anyone tonight.")
        return

    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, False)

    if not victim:
        pm(cli, nick, "Please choose who to bite by specifying their nick.")
        return

    vrole = var.get_role(victim)
    actual = choose_target(nick, victim)

    if vrole in var.WOLFCHAT_ROLES:
        pm(cli, nick, "You may not bite other wolves.")
        return

    var.ALPHA_WOLVES.add(nick)

    var.BITE_PREFERENCES[nick] = actual

    # biting someone makes them ineligible to participate in the kill
    if nick in var.KILLS:
        del var.KILLS[nick]

    pm(cli, nick, "You have chosen to bite \u0002{0}\u0002.".format(victim))
    wolfchat = var.list_players(var.WOLFCHAT_ROLES)
    for wolf in wolfchat:
        if wolf != nick:
            pm(cli, wolf, "\u0002{0}\u0002 has chosen to bite \u0002{1}\u0002.".format(nick, victim))

    debuglog("{0} ({1}) BITE: {2} ({3})".format(nick, var.get_role(nick), actual, var.get_role(actual)))
    chk_nightdone(cli)

@cmd("pass", chan=False, pm=True, playing=True, phases=("night",), roles=("hunter","harlot","bodyguard","guardian angel","turncoat","warlock","piper"))
def pass_cmd(cli, nick, chan, rest):
    """Decline to use your special power for that night."""
    nickrole = var.get_role(nick)

    # turncoats can change roles and pass even if silenced
    if nickrole != "turncoat" and nick in var.SILENCED:
        if chan == nick:
            pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        else:
            cli.notice(nick, "You have been silenced, and are unable to use any special powers.")
        return

    if nickrole == "hunter":
        if nick in var.OTHER_KILLS.keys():
            del var.OTHER_KILLS[nick]
            var.HUNTERS.remove(nick)
        if nick in var.HUNTERS:
            pm(cli, nick, "You have already killed someone this game.")
            return

        pm(cli, nick, "You have decided not to kill anyone tonight.")
        var.PASSED.add(nick)
    elif nickrole == "harlot":
        if var.HVISITED.get(nick):
            pm(cli, nick, ("You are already spending the night "+
                          "with \u0002{0}\u0002.").format(var.HVISITED[nick]))
            return
        var.HVISITED[nick] = None
        pm(cli, nick, "You have chosen to stay home for the night.")
    elif nickrole == "bodyguard" or nickrole == "guardian angel":
        if var.GUARDED.get(nick):
            pm(cli, nick, "You are already protecting someone tonight.")
            return
        var.GUARDED[nick] = None
        pm(cli, nick, "You have chosen not to guard anyone tonight.")
    elif nickrole == "turncoat":
        if var.TURNCOATS[nick][1] == var.NIGHT_COUNT:
            # theoretically passing would revert them to how they were before, but
            # we aren't tracking that, so just tell them to change it back themselves.
            pm(cli, nick, ("You have already changed sides tonight. Use " +
                           '"side villagers" or "side wolves" to modify your selection.'))
            return
        pm(cli, nick, "You have decided not to change sides tonight.")
        if var.TURNCOATS[nick][1] == var.NIGHT_COUNT - 1:
            # don't add to var.PASSED since we aren't counting them anyway for nightdone
            # let them still use !pass though to make them feel better or something
            return
        var.PASSED.add(nick)
    elif nickrole == "warlock":
        if nick in var.CURSED:
            pm(cli, nick, "You have already cursed someone tonight.")
            return
        pm(cli, nick, "You have chosen not to curse anyone tonight.")

        wolfchatwolves = var.list_players(var.WOLFCHAT_ROLES)
        for wolf in wolfchatwolves:
            if wolf != nick:
                pm(cli, wolf, "\u0002{0}\u0002 has chosen not to curse anyone tonight.".format(nick))

        var.PASSED.add(nick)
    elif nickrole == "piper":
        if nick in var.CHARMERS:
            pm(cli, nick, "You have already charmed players tonight.")
            return
        pm(cli, nick, "You have chosen not to charm anyone tonight.")
        var.PASSED.add(nick)

    debuglog("{0} ({1}) PASS".format(nick, var.get_role(nick)))
    chk_nightdone(cli)

@cmd("side", chan=False, pm=True, playing=True, phases=("night",), roles=("turncoat",))
def change_sides(cli, nick, chan, rest, sendmsg=True):
    if var.TURNCOATS[nick][1] == var.NIGHT_COUNT - 1:
        pm(cli, nick, "You have changed sides yesterday night, and may not do so again tonight.")
        return

    team = re.split(" +", rest)[0]
    team, _ = complete_match(team, ("villagers", "wolves"))
    if not team:
        pm(cli, nick, "Please specify which team you wish to side with, villagers or wolves.")
        return

    pm(cli, nick, "You are now siding with \u0002{0}\u0002.".format(team))
    var.TURNCOATS[nick] = (team, var.NIGHT_COUNT)
    debuglog("{0} ({1}) SIDE {2}".format(nick, var.get_role(nick), team))
    chk_nightdone(cli)

@cmd("choose", "match", chan=False, pm=True, playing=True, phases=("night",), roles=("matchmaker",))
def choose(cli, nick, chan, rest, sendmsg=True):
    """Select two players to fall in love. You may select yourself as one of the lovers."""
    if not var.FIRST_NIGHT:
        return
    if nick in var.MATCHMAKERS:
        pm(cli, nick, "You have already chosen lovers.")
        return
    # no var.SILENCED check for night 1 only roles; silence should only apply for the night after
    # but just in case, it also sucks if the one night you're allowed to act is when you are
    # silenced, so we ignore it here anyway.
    pieces = re.split(" +",rest)
    victim = pieces[0]
    if len(pieces) > 1:
        if len(pieces) > 2 and pieces[1].lower() == "and":
            victim2 = pieces[2]
        else:
            victim2 = pieces[1]
    else:
        victim2 = None

    victim = get_victim(cli, nick, victim, False, True)
    if not victim:
        return
    victim2 = get_victim(cli, nick, victim2, False, True)
    if not victim2:
        return

    if victim == victim2:
        pm(cli, nick, "You must choose two different people.")
        return

    var.MATCHMAKERS.add(nick)
    if victim in var.LOVERS:
        var.LOVERS[victim].add(victim2)
        var.ORIGINAL_LOVERS[victim].add(victim2)
    else:
        var.LOVERS[victim] = {victim2}
        var.ORIGINAL_LOVERS[victim] = {victim2}

    if victim2 in var.LOVERS:
        var.LOVERS[victim2].add(victim)
        var.ORIGINAL_LOVERS[victim2].add(victim)
    else:
        var.LOVERS[victim2] = {victim}
        var.ORIGINAL_LOVERS[victim2] = {victim}

    if sendmsg:
        pm(cli, nick, "You have selected \u0002{0}\u0002 and \u0002{1}\u0002 to be lovers.".format(victim, victim2))

    if victim in var.PLAYERS and not is_user_simple(victim):
        pm(cli, victim, ("You are \u0002in love\u0002 with {0}. If that player dies for any " +
                         "reason, the pain will be too much for you to bear and you will " +
                         "commit suicide.").format(victim2))
    else:
        pm(cli, victim, "You are \u0002in love\u0002 with {0}.".format(victim2))

    if victim2 in var.PLAYERS and not is_user_simple(victim2):
        pm(cli, victim2, ("You are \u0002in love\u0002 with {0}. If that player dies for any " +
                         "reason, the pain will be too much for you to bear and you will " +
                         "commit suicide.").format(victim))
    else:
        pm(cli, victim2, "You are \u0002in love\u0002 with {0}.".format(victim))

    debuglog("{0} ({1}) MATCH: {2} ({3}) + {4} ({5})".format(nick, var.get_role(nick), victim, var.get_role(victim), victim2, var.get_role(victim2)))
    chk_nightdone(cli)

@cmd("target", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("assassin",))
def target(cli, nick, chan, rest):
    """Pick a player as your target, killing them if you die."""
    if var.TARGETED.get(nick) is not None:
        pm(cli, nick, "You have already chosen a target.")
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if nick == victim:
        pm(cli, nick, "You may not target yourself.")
        return

    victim = choose_target(nick, victim)
    # assassin is a template so it will never get swapped, so don't check for exchanges with it
    var.TARGETED[nick] = victim
    pm(cli, nick, "You have selected \u0002{0}\u0002 as your target.".format(victim))

    debuglog("{0} ({1}-{2}) TARGET: {3} ({4})".format(nick, "-".join(var.get_templates(nick)), var.get_role(nick), victim, var.get_role(victim)))
    chk_nightdone(cli)

@cmd("hex", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hag",))
def hex_target(cli, nick, chan, rest):
    """Hex someone, preventing them from acting the next day and night."""
    if nick in var.HEXED:
        pm(cli, nick, "You have already hexed someone tonight.")
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if nick == victim:
        pm(cli, nick, "You may not target yourself.")
        return
    if var.LASTHEXED.get(nick) == victim:
        pm(cli, nick, ("You hexed \u0002{0}\u0002 last night. " +
                       "You cannot hex the same person two nights in a row.").format(victim))
        return

    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return
    vrole = var.get_role(victim)
    if vrole in var.WOLFCHAT_ROLES:
        pm(cli, nick, "Hexing another wolf would be a waste.")
        return

    var.HEXED.add(nick)
    var.LASTHEXED[nick] = victim
    var.TOBESILENCED.add(victim)

    pm(cli, nick, "You have cast a hex on \u0002{0}\u0002.".format(victim))

    wolfchatwolves = var.list_players(var.WOLFCHAT_ROLES)
    for wolf in wolfchatwolves:
        if wolf != nick:
            pm(cli, wolf, "\u0002{0}\u0002 has cast a hex on \u0002{1}\u0002.".format(nick, victim))

    debuglog("{0} ({1}) HEX: {2} ({3})".format(nick, var.get_role(nick), victim, var.get_role(victim)))
    chk_nightdone(cli)

@cmd("curse", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def curse(cli, nick, chan, rest):
    if nick in var.CURSED:
        # CONSIDER: this happens even if they choose to not curse, should maybe let them
        # pick again in that case instead of locking them into doing nothing.
        pm(cli, nick, "You have already cursed someone tonight.")
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    # There may actually be valid strategy in cursing other wolfteam members,
    # but for now it is not allowed. If someone seems suspicious and shows as
    # villager across multiple nights, safes can use that as a tell that the
    # person is likely wolf-aligned.
    vrole = var.get_role(victim)
    if victim in var.ROLES["cursed villager"]:
        pm(cli, nick, "\u0002{0}\u0002 is already cursed.".format(victim))
        return
    if vrole in var.WOLFCHAT_ROLES:
        pm(cli, nick, "Cursing a fellow wolf would be a waste.")
        return

    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return

    var.CURSED.add(nick)
    var.PASSED.discard(nick)
    var.ROLES["cursed villager"].add(victim)

    pm(cli, nick, "You have cast a curse on \u0002{0}\u0002.".format(victim))

    wolfchatwolves = var.list_players(var.WOLFCHAT_ROLES)
    for wolf in wolfchatwolves:
        if wolf != nick:
            pm(cli, wolf, "\u0002{0}\u0002 has cast a curse on \u0002{1}\u0002.".format(nick, victim))


    debuglog("{0} ({1}) CURSE: {2} ({3})".format(nick, var.get_role(nick), victim, var.get_role(victim)))
    chk_nightdone(cli)

@cmd("clone", chan=False, pm=True, playing=True, phases=("night",), roles=("clone",))
def clone(cli, nick, chan, rest):
    """Clone another player. You will turn into their role if they die."""
    if not var.FIRST_NIGHT:
        return
    if nick in var.CLONED.keys():
        pm(cli, nick, "You have already chosen to clone someone.")
        return
    # no var.SILENCED check for night 1 only roles; silence should only apply for the night after
    # but just in case, it also sucks if the one night you're allowed to act is when you are
    # silenced, so we ignore it here anyway.

    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if nick == victim:
        pm(cli, nick, "You may not target yourself.")
        return

    var.CLONED[nick] = victim
    pm(cli, nick, "You have chosen to clone \u0002{0}\u0002.".format(victim))

    debuglog("{0} ({1}) CLONE: {2} ({3})".format(nick, var.get_role(nick), victim, var.get_role(victim)))
    chk_nightdone(cli)

@cmd("charm", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("piper",))
def charm(cli, nick, chan, rest):
    """Charm a player, slowly leading to your win!"""
    if nick in var.CHARMERS:
        pm(cli, nick, "You have already charmed players tonight.")
        return

    pieces = re.split(" +",rest)
    victim = pieces[0]
    if len(pieces) > 1:
        if len(pieces) > 2 and pieces[1].lower() == "and":
            victim2 = pieces[2]
        else:
            victim2 = pieces[1]
    else:
        victim2 = None

    victim = get_victim(cli, nick, victim, False, True)
    if not victim:
        return
    if victim2 is not None:
        victim2 = get_victim(cli, nick, victim2, False, True)
        if not victim2:
            return

    if victim == victim2:
        pm(cli, nick, "You must choose two different people.")
        return
    if nick in (victim, victim2):
        pm(cli, nick, "You may not charm yourself.")
        return
    charmedlist = var.CHARMED|var.TOBECHARMED
    if victim in charmedlist or victim2 and victim2 in charmedlist:
        if victim in charmedlist and victim2 and victim2 in charmedlist:
            pm(cli, nick, "\u0002{0}\u0002 and \u0002{1}\u0002 are already charmed!".format(victim, victim2))
            return
        if (len(var.list_players()) - len(var.ROLES["piper"]) - len(charmedlist) - 2 >= 0 or
            victim in charmedlist and not victim2):
            pm(cli, nick, "\u0002{0}\u0002 is already charmed!".format(victim in charmedlist and victim or victim2))
            return

    var.CHARMERS.add(nick)
    var.PASSED.discard(nick)

    var.TOBECHARMED.add(victim)
    if victim2:
        var.TOBECHARMED.add(victim2)

    pm(cli, nick, "You have charmed \u0002{0}\u0002{1}.".format(victim, victim2 and " and \u0002{0}\u0002".format(victim2) or ""))

    # if there are other pipers, tell them who gets charmed (so they don't have to keep guessing who they are still allowed to charm)
    for piper in var.ROLES["piper"]:
        if piper != nick:
            if victim2:
                pm(cli, piper, "Another piper has charmed \u0002{0}\u0002 and \u0002{1}\u0002!".format(victim, victim2))
            else:
                pm(cli, piper, "Another piper has charmed \u0002{0}\u0002!".format(victim))

    if victim2:
        debuglog("{0} ({1}) CHARM {2} ({3}) && {4} ({5})".format(nick, var.get_role(nick),
                                                                 victim, var.get_role(victim),
                                                                 victim2, var.get_role(victim2)))
    else:
        debuglog("{0} ({1}) CHARM {2} ({3})".format(nick, var.get_role(nick),
                                                    victim, var.get_role(victim)))

    chk_nightdone(cli)

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
            if var.AUTO_TOGGLE_MODES:
                tocheck = set(var.AUTO_TOGGLE_MODES)
                var.AUTO_TOGGLE_MODES = set(var.AUTO_TOGGLE_MODES)
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

def mass_privmsg(cli, targets, msg, notice=False, privmsg=False):
    if not notice and not privmsg:
        msg_targs = []
        not_targs = []
        for target in targets:
            if is_user_notice(target):
                not_targs.append(target)
            else:
                msg_targs.append(target)
        while msg_targs:
            if len(msg_targs) <= var.MAX_PRIVMSG_TARGETS:
                bgs = ",".join(msg_targs)
                msg_targs = None
            else:
                bgs = ",".join(msg_targs[:var.MAX_PRIVMSG_TARGETS])
                msg_targs = msg_targs[var.MAX_PRIVMSG_TARGETS:]
            cli.msg(bgs, msg)
        while not_targs:
            if len(not_targs) <= var.MAX_PRIVMSG_TARGETS:
                bgs = ",".join(not_targs)
                not_targs = None
            else:
                bgs = ",".join(not_targs[:var.MAX_PRIVMSG_TARGETS])
                not_targs = not_targs[var.MAX_PRIVMSG_TARGETS:]
            cli.notice(bgs, msg)
    else:
        while targets:
            if len(targets) <= var.MAX_PRIVMSG_TARGETS:
                bgs = ",".join(targets)
                targets = None
            else:
                bgs = ",".join(targets[:var.MAX_PRIVMSG_TARGETS])
                target = targets[var.MAX_PRIVMSG_TARGETS:]
            if notice:
                cli.notice(bgs, msg)
            else:
                cli.msg(bgs, msg)

@cmd("", chan=False, pm=True)
def relay(cli, nick, chan, rest):
    """Let the wolves talk to each other through the bot"""
    if rest.startswith("\u0001PING"):
        cli.notice(nick, rest)
        return
    if var.PHASE not in ("night", "day"):
        return

    if nick in var.list_players() and nick in getattr(var, "IDLE_WARNED_PM", ()):
        cli.msg(nick, ("\u0002You have been idling in {0} for a while. Please say something in {0} "
                       "or you will be declared dead.\u0002").format(botconfig.CHANNEL))
        var.IDLE_WARNED_PM.add(nick)

    badguys = var.list_players(var.WOLFCHAT_ROLES)
    if len(badguys) > 1:
        if nick in badguys:
            badguys.remove(nick)  #  remove self from list

            if rest.startswith("\u0001ACTION"):
                rest = rest[7:-1]
                mass_privmsg(cli, [guy for guy in badguys
                    if guy in var.PLAYERS], "* \u0002{0}\u0002{1}".format(nick, rest))
            else:
                mass_privmsg(cli, [guy for guy in badguys
                    if guy in var.PLAYERS], "\u0002{0}\u0002 says: {1}".format(nick, rest))

def transition_night(cli):
    if var.PHASE == "night":
        return
    var.PHASE = "night"
    var.GAMEPHASE = "night"

    if var.DEVOICE_DURING_NIGHT:
        modes = []
        for player in var.list_players():
            modes.append(("-v", player))
        mass_mode(cli, modes, [])

    for x, tmr in var.TIMERS.items():  # cancel daytime timer
        tmr[0].cancel()
    var.TIMERS = {}

    # Reset nighttime variables
    var.KILLS = {}
    var.GUARDED = {}  # key = by whom, value = the person that is visited
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = set()  # set of seers that have had visions
    var.HEXED = set() # set of hags that have hexed
    var.CURSED = set() # set of warlocks that have cursed
    var.SHAMANS = {}
    var.PASSED = set() # set of hunters that have chosen not to kill
    var.OBSERVED = {}  # those whom werecrows have observed
    var.CHARMERS = set() # pipers who have charmed
    var.HVISITED = {}
    var.ASLEEP = set()
    var.PROTECTED = []
    var.DESPERATE = set()
    var.REVEALED = set()
    var.TOBESILENCED = set()
    var.IMPATIENT = []
    var.DEATH_TOTEM = []
    var.PACIFISTS = []
    var.INFLUENTIAL = set()
    var.TOBELYCANTHROPES = set()
    var.TOBELUCKY = set()
    var.TOBEDISEASED = set()
    var.RETRIBUTION = set()
    var.TOBEMISDIRECTED = set()
    var.NIGHT_START_TIME = datetime.now()
    var.NIGHT_COUNT += 1
    var.FIRST_NIGHT = (var.NIGHT_COUNT == 1)
    var.TOTEMS = {}

    daydur_msg = ""

    if var.NIGHT_TIMEDELTA or var.START_WITH_DAY:  #  transition from day
        td = var.NIGHT_START_TIME - var.DAY_START_TIME
        var.DAY_START_TIME = None
        var.DAY_TIMEDELTA += td
        min, sec = td.seconds // 60, td.seconds % 60
        daydur_msg = "Day lasted \u0002{0:0>2}:{1:0>2}\u0002. ".format(min,sec)

    chan = botconfig.CHANNEL

    if var.NIGHT_TIME_LIMIT > 0:
        var.NIGHT_ID = time.time()
        t = threading.Timer(var.NIGHT_TIME_LIMIT, transition_day, [cli, var.NIGHT_ID])
        var.TIMERS["night"] = (t, var.NIGHT_ID, var.NIGHT_TIME_LIMIT)
        t.daemon = True
        t.start()

    if var.NIGHT_TIME_WARN > 0:
        t2 = threading.Timer(var.NIGHT_TIME_WARN, night_warn, [cli, var.NIGHT_ID])
        var.TIMERS["night_warn"] = (t2, var.NIGHT_ID, var.NIGHT_TIME_WARN)
        t2.daemon = True
        t2.start()

    # convert bitten people to wolves, and advance bite stage
    bittencopy = copy.copy(var.BITTEN)
    for chump in bittencopy:
        var.BITTEN[chump] -= 1
        # short-circuit if they are already a wolf
        # this makes playing the day transition message easier since we can keep
        # var.BITTEN around for a day after they turn
        chumprole = var.get_role(chump)

        if chumprole in var.WOLF_ROLES:
            del var.BITTEN[chump]
            continue

        if var.BITTEN[chump] <= 0:
            # now a wolf
            newrole = "wolf"
            if chumprole == "guardian angel":
                pm(cli, chump, ("As the moonlight filters through your window, you think back on the past few days. " +
                                "Your power has been growing, but the villagers you protect subconsciously detected " +
                                "your shift and have been keeping more distant from you. Grinning with wicked resolve, " +
                                "you vow to show them what fools they have been as you take to the skies once more " +
                                "with an unholy vengeance. Soon they will know true fear."))
                # fallen angels also automatically gain the assassin template if they don't already have it
                # by default GA can never be assassin, but this guards against non-default cases
                newrole = "fallen angel"
                var.ROLES["assassin"].add(chump)
                debuglog("{0} ({1}) TURNED FALLEN ANGEL".format(chump, chumprole))
            else:
                pm(cli, chump, ("As you prepare for bed, you watch in horror as your body starts growing a coat of fur! " +
                                "Sudden realization hits you as you grin with your now muzzled face; that mysterious bite " +
                                "earlier slowly changed you into a werewolf! You feel bigger, stronger, faster, and ready to " +
                                "seize the night as you stealthily exit your home and search for the rest of your pack..."))
                debuglog("{0} ({1}) TURNED WOLF".format(chump, chumprole))
            var.BITTEN_ROLES[chump] = chumprole
            var.ROLES[chumprole].remove(chump)
            var.ROLES[newrole].add(chump)
            var.FINAL_ROLES[chump] = newrole
            for wolf in var.list_players(var.WOLFCHAT_ROLES):
                if wolf != chump:
                    # no need for a/an since newrole is either wolf or fallen angel
                    pm(cli, wolf, "\u0002{0}\u0002 is now a \u0002{1}\u0002!".format(chump, newrole))

    # convert amnesiac
    if var.NIGHT_COUNT == var.AMNESIAC_NIGHTS:
        amns = copy.copy(var.ROLES["amnesiac"])

        for amn in amns:
            event = Event("amnesiac_turn", {})
            if event.dispatch(var, amn, var.AMNESIAC_ROLES[amn]):
                amnrole = var.AMNESIAC_ROLES[amn]
                var.ROLES["amnesiac"].remove(amn)
                var.ROLES[amnrole].add(amn)
                var.AMNESIACS.add(amn)
                var.FINAL_ROLES[amn] = amnrole
                if var.FIRST_NIGHT: # we don't need to tell them twice if they remember right away
                    continue
                showrole = amnrole
                if showrole == "time lord":
                    showrole = "villager"
                elif showrole == "vengeful ghost":
                    showrole = var.DEFAULT_ROLE
                n = ""
                if showrole.startswith(("a", "e", "i", "o", "u")):
                    n = "n"
                pm(cli, amn, "Your amnesia clears and you now remember that you are a{0} \u0002{1}\u0002!".format(n, showrole))
                if amnrole in var.WOLFCHAT_ROLES:
                    for wolf in var.list_players(var.WOLFCHAT_ROLES):
                        if wolf != amn: # don't send "Foo is now a wolf!" to 'Foo'
                            pm(cli, wolf, "\u0002{0}\u0002 is now a \u0002{1}\u0002!".format(amn, showrole))
                elif amnrole == "turncoat":
                    var.TURNCOATS[amn] = ("none", -1)
                debuglog("{0} REMEMBER: {1} as {2}".format(amn, amnrole, showrole))

    if var.FIRST_NIGHT and chk_win(cli, end_game=False): # prevent game from ending as soon as it begins (useful for the random game mode)
        start(cli, botconfig.NICK, botconfig.CHANNEL, restart=var.CURRENT_GAMEMODE.name)
        return

    # game ended from bitten / amnesiac turning, narcolepsy totem expiring, or other weirdness
    if chk_win(cli):
        return

    # send PMs
    ps = var.list_players()
    wolves = var.list_players(var.WOLFCHAT_ROLES)
    for wolf in wolves:
        normal_notify = wolf in var.PLAYERS and not is_user_simple(wolf)
        role = var.get_role(wolf)
        cursed = "cursed " if wolf in var.ROLES["cursed villager"] else ""

        if normal_notify:
            if role == "wolf":
                pm(cli, wolf, ('You are a \u0002wolf\u0002. It is your job to kill all the '+
                               'villagers. Use "kill <nick>" to kill a villager.'))
            elif role == "traitor":
                if cursed:
                    pm(cli, wolf, ('You are a \u0002cursed traitor\u0002. Normally, you would be '
                                   'seen as a villager by the seer and oracle, but since you\'re '
                                   'cursed, you are seen as a wolf.'))
                else:
                    pm(cli, wolf, ('You are a \u0002traitor\u0002. You are exactly like a villager '
                                   'and not even a seer or oracle can see your true identity, '
                                   'only detectives and augurs can.'))
            elif role == "werecrow":
                pm(cli, wolf, ('You are a \u0002werecrow\u0002. You are able to fly at night. '+
                               'Use "kill <nick>" to kill a villager. Alternatively, you can '+
                               'use "observe <nick>" to check if someone is in bed or not. '+
                               'Observing will prevent you from participating in a killing.'))
            elif role == "hag":
                pm(cli, wolf, ('You are a \u0002{0}hag\u0002. You can hex someone to prevent them ' +
                               'from using any special powers they may have during the next day ' +
                               'and night. Use "hex <nick>" to hex them. Only detectives can reveal ' +
                               'your true identity, seers will see you as a regular villager.').format(cursed))
            elif role == "sorcerer":
                pm(cli, wolf, ('You are a \u0002{0}sorcerer\u0002. You can use "observe <nick>" to ' +
                               'observe someone and determine if they are the seer, oracle, or augur. ' +
                               'Only detectives can reveal your true identity, seers will see you ' +
                               'as a regular villager.').format(cursed))
            elif role == "wolf cub":
                pm(cli, wolf, ('You are a \u0002wolf cub\u0002. While you cannot kill anyone, ' +
                               'the other wolves will become enraged if you die and will get ' +
                               'two kills the following night.'))
            elif role == "alpha wolf":
                pm(cli, wolf, ('You are an \u0002alpha wolf\u0002. Once per game following the death of another wolf ' +
                               'during the day, you can choose to bite the wolves\' next target to turn ' +
                               'them into a wolf instead of killing them. Kill villagers by using '
                               '"kill <nick>" and "bite" to use your once-per-game bite power.'))
            elif role == "werekitten":
                pm(cli, wolf, ('You are a \u0002werekitten\u0002. Due to your overwhelming cuteness, the seer ' +
                               'always sees you as villager and the gunner will always miss you. Detectives can ' +
                               'still reveal your true identity, however. Use "kill <nick>" to kill a villager.'))
            elif role == "warlock":
                pm(cli, wolf, ('You are a \u0002{0}warlock\u0002. Each night you can curse someone with "curse <nick>" ' +
                               'to turn them into a cursed villager, so the seer sees them as wolf. Act quickly, as ' +
                               'your curse applies as soon as you cast it! Only detectives can reveal your true identity, ' +
                               'seers will see you as a regular villager.').format(cursed))
            elif role == "wolf mystic":
                pm(cli, wolf, ('You are a \u0002wolf mystic\u0002. Each night you divine the number of alive good villagers ' +
                               'who have a special role. You may also use "kill <nick>" to kill a villager.'))
            elif role == "fallen angel":
                pm(cli, wolf, ('You are a \u0002fallen angel\u0002. Your sharp claws will rend any protection the villagers ' +
                               'may have, and will likely kill living guardians as well. Use "kill <nick>" to kill a villager.'))
            else:
                # catchall in case we forgot something above
                an = 'n' if role.startswith(("a", "e", "i", "o", "u")) else ""
                pm(cli, wolf, ('You are a{0} \u0002{1}\u0002. There would normally be instructions ' +
                               'here, but someone forgot to add them in. Please report this to ' +
                               'the admins, you can PM me "admins" for a list of available ones.').format(an, role))

            if len(wolves) > 1:
                pm(cli, wolf, 'Also, if you PM me, your message will be relayed to other wolves.')
        else:
            an = "n" if cursed == "" and role.startswith(("a", "e", "i", "o", "u")) else ""
            pm(cli, wolf, 'You are a{0} \u0002{1}{2}\u0002.'.format(an, cursed, role))  # !simple

        pl = ps[:]
        random.shuffle(pl)
        pl.remove(wolf)  # remove self from list
        for i, player in enumerate(pl):
            prole = var.get_role(player)
            if prole in var.WOLFCHAT_ROLES:
                cursed = ""
                if player in var.ROLES["cursed villager"]:
                    cursed = "cursed "
                pl[i] = "\u0002{0}\u0002 ({1}{2})".format(player, cursed, prole)
            elif player in var.ROLES["cursed villager"]:
                pl[i] = player + " (cursed)"

        pm(cli, wolf, "Players: " + ", ".join(pl))
        if role == "wolf mystic":
            # if adding this info to !myrole, you will need to save off this count so that they can't get updated info until the next night
            # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
            numvills = len(ps) - len(var.list_players(var.WOLFTEAM_ROLES)) - len(var.list_players(("villager", "vengeful ghost", "time lord", "amnesiac", "lycan"))) - len(var.list_players(var.TRUE_NEUTRAL_ROLES))
            pm(cli, wolf, "There {0} \u0002{1}\u0002 special villager{2} still alive.".format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
        if wolf in var.WOLF_GUNNERS.keys() and var.WOLF_GUNNERS[wolf] > 0:
            pm(cli, wolf, "You have a \u0002gun\u0002 with {0} bullet{1}.".format(var.WOLF_GUNNERS[wolf], "s" if var.WOLF_GUNNERS[wolf] > 1 else ""))
        if var.DISEASED_WOLVES:
            pm(cli, wolf, 'You are feeling ill tonight, and are unable to kill anyone.')
        elif var.ANGRY_WOLVES and role in var.WOLF_ROLES and role != "wolf cub":
            pm(cli, wolf, 'You are \u0002angry\u0002 tonight, and may kill two targets by using "kill <nick1> and <nick2>".')
        if var.ALPHA_ENABLED and role == "alpha wolf" and wolf not in var.ALPHA_WOLVES:
            pm(cli, wolf, ('You may use "bite <nick>" tonight in order to turn your target into a wolf instead of participating in tonight\'s kill. ' +
                           'They will turn into a wolf in {0} night{1}.').format(var.ALPHA_WOLF_NIGHTS, 's' if var.ALPHA_WOLF_NIGHTS > 1 else ''))

    for seer in var.list_players(("seer", "oracle", "augur")):
        pl = ps[:]
        random.shuffle(pl)
        role = var.get_role(seer)
        pl.remove(seer)  # remove self from list

        a = "a"
        if role in ("oracle", "augur"):
            a = "an"

        if role == "seer":
            what = "the role of a player"
        elif role == "oracle":
            what = "whether or not a player is a wolf"
        elif role == "augur":
            what = "which team a player is on"
        else:
            what = "??? (this is a bug, please report to admins)"

        if seer in var.PLAYERS and not is_user_simple(seer):
            pm(cli, seer, ('You are {0} \u0002{1}\u0002. '+
                          'It is your job to detect the wolves, you '+
                          'may have a vision once per night. '+
                          'Use "see <nick>" to see {2}.').format(a, role, what))
        else:
            pm(cli, seer, "You are {0} \u0002{1}\u0002.".format(a, role))  # !simple
        pm(cli, seer, "Players: " + ", ".join(pl))

    for harlot in var.ROLES["harlot"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(harlot)
        if harlot in var.PLAYERS and not is_user_simple(harlot):
            pm(cli, harlot, ('You are a \u0002harlot\u0002. '+
                             'You may spend the night with one person per round. '+
                             'If you visit a victim of a wolf, or visit a wolf, '+
                             'you will die. You may stay home by visiting yourself. ' +
                             'Use "visit <nick>" to visit a player.'))
        else:
            pm(cli, harlot, "You are a \u0002harlot\u0002.")  # !simple
        pm(cli, harlot, "Players: " + ", ".join(pl))

    # the messages for angel and guardian angel are different enough to merit individual loops
    for g_angel in var.ROLES["bodyguard"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(g_angel)
        chance = math.floor(var.BODYGUARD_DIES_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = "If you guard a wolf, there is a {0}% chance of you dying. ".format(chance)

        if g_angel in var.PLAYERS and not is_user_simple(g_angel):
            pm(cli, g_angel, ('You are a \u0002bodyguard\u0002. '+
                              'It is your job to protect the villagers. {0}If you guard '+
                              'a victim, you will sacrifice yourself to save them. ' +
                              'Use "pass" to not guard anyone tonight. ' +
                              'Use "guard <nick>" to guard a player.').format(warning))
        else:
            pm(cli, g_angel, "You are a \u0002bodyguard\u0002.")  # !simple
        pm(cli, g_angel, "Players: " + ", ".join(pl))

    for gangel in var.ROLES["guardian angel"]:
        pl = ps[:]
        random.shuffle(pl)
        gself = "You may also guard yourself. "
        if not var.GUARDIAN_ANGEL_CAN_GUARD_SELF:
            pl.remove(gangel)
            gself = ""
        if var.LASTGUARDED.get(gangel) in pl:
            pl.remove(var.LASTGUARDED[gangel])
        chance = math.floor(var.GUARDIAN_ANGEL_DIES_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = "If you guard a wolf, there is a {0}% chance of you dying. ".format(chance)

        if gangel in var.PLAYERS and not is_user_simple(gangel):
            pm(cli, gangel, ('You are a \u0002guardian angel\u0002. '+
                              'It is your job to protect the villagers. {0}If you guard '+
                              'a victim, they will live. You may not guard the same person two nights in a row. ' +
                              '{1}Use "guard <nick>" to guard a player.').format(warning, gself))
        else:
            pm(cli, gangel, "You are a \u0002guardian angel\u0002.")  # !simple
        pm(cli, gangel, "Players: " + ", ".join(pl))

    for dttv in var.ROLES["detective"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(dttv)
        chance = math.floor(var.DETECTIVE_REVEALED_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = ("Each time you use your ability, you risk a {0}% chance of having " +
                       "your identity revealed to the wolves. ").format(chance)
        if dttv in var.PLAYERS and not is_user_simple(dttv):
            pm(cli, dttv, ("You are a \u0002detective\u0002.\n"+
                          "It is your job to determine all the wolves and traitors. "+
                          "Your job is during the day, and you can see the true "+
                          "identity of all players, even traitors.\n"+
                          '{0}Use "id <nick>" in PM to identify any player during the day.').format(warning))
        else:
            pm(cli, dttv, "You are a \u0002detective\u0002.")  # !simple
        pm(cli, dttv, "Players: " + ", ".join(pl))

    for drunk in var.ROLES["village drunk"]:
        if drunk in var.PLAYERS and not is_user_simple(drunk):
            pm(cli, drunk, "You have been drinking too much! You are the \u0002village drunk\u0002.")
        else:
            pm(cli, drunk, "You are the \u0002village drunk\u0002.")

    for mystic in var.ROLES["mystic"]:
        if mystic in var.PLAYERS and not is_user_simple(mystic):
            pm(cli, mystic, ("You are the \u0002mystic\u0002. Each night you divine the number of evil " +
                             "villagers (including wolves) that are still alive."))
        else:
            pm(cli, mystic, "You are the \u0002mystic\u0002.")
        # if adding this info to !myrole, you will need to save off this count so that they can't get updated info until the next night
        numevil = len(var.list_players(var.WOLFTEAM_ROLES))
        pm(cli, mystic, "There {0} \u0002{1}\u0002 evil villager{2} still alive.".format("are" if numevil != 1 else "is", numevil, "s" if numevil != 1 else ""))

    max_totems = defaultdict(int)
    for ix in range(len(var.TOTEM_ORDER)):
        for c in var.TOTEM_CHANCES.values():
            max_totems[var.TOTEM_ORDER[ix]] += c[ix]
    for shaman in var.list_players(var.TOTEM_ORDER):
        pl = ps[:]
        random.shuffle(pl)
        if shaman in var.LASTGIVEN:
            if var.LASTGIVEN[shaman] in pl:
                pl.remove(var.LASTGIVEN[shaman])
        role = var.get_role(shaman)
        indx = var.TOTEM_ORDER.index(role)
        target = 0
        rand = random.random() * max_totems[var.TOTEM_ORDER[indx]]
        for t in var.TOTEM_CHANCES.keys():
            target += var.TOTEM_CHANCES[t][indx]
            if rand <= target:
                var.TOTEMS[shaman] = t
                break
        if shaman in var.PLAYERS and not is_user_simple(shaman):
            pm(cli, shaman, ('You are a \u0002{0}\u0002. You can select a player to receive ' +
                             'a {1}totem each night by using "give <nick>". You may give yourself a totem, but you ' +
                             'may not give the same player a totem two nights in a row. ' +
                             'If you do not give the totem to anyone, it will be given to a random player.').format(role, "random " if shaman in var.ROLES["crazed shaman"] else ""))
            if role != "crazed shaman":
                totem = var.TOTEMS[shaman]
                tmsg = 'You have the \u0002{0}\u0002 totem. '.format(totem)
                if totem == "death":
                    tmsg += 'The player who is given this totem will die tonight, even if they are being protected.'
                elif totem == "protection":
                    tmsg += 'The player who is given this totem is protected from dying tonight.'
                elif totem == "revealing":
                    tmsg += 'If the player who is given this totem is lynched, their role is revealed to everyone instead of them dying.'
                elif totem == "narcolepsy":
                    tmsg += 'The player who is given this totem will be unable to vote during the day tomorrow.'
                elif totem == "silence":
                    tmsg += 'The player who is given this totem will be unable to use any special powers during the day tomorrow and the night after.'
                elif totem == "desperation":
                    tmsg += 'If the player who is given this totem is lynched, the last player to vote them will also die.'
                elif totem == "impatience":
                    tmsg += 'The player who is given this totem is counted as voting for everyone except themselves, even if they do not !vote.'
                elif totem == "pacifism":
                    tmsg += 'Votes by the player who is given this totem do not count.'
                elif totem == "influence":
                    tmsg += 'Votes by the player who is given this totem count twice.'
                elif totem == "exchange":
                    tmsg += 'The first person to use a power on the player given this totem tomorrow night will have their role swapped with the recipient.'
                elif totem == "lycanthropy":
                    tmsg += 'If the player who is given this totem is targeted by wolves tomorrow night, they will become a wolf.'
                elif totem == "luck":
                    tmsg += 'If the player who is given this totem is targeted tomorrow night, one of the players adjacent to them will be targeted instead.'
                elif totem == "pestilence":
                    tmsg += 'If the player who is given this totem is killed by wolves tomorrow night, the wolves will not be able to kill the night after.'
                elif totem == "retribution":
                    tmsg += 'If the player who is given this totem will die tonight, they also kill anyone who killed them.'
                elif totem == "misdirection":
                    tmsg += 'If the player who is given this totem attempts to use a power the following day or night, they will target a player adjacent to their intended target instead of the player they targeted.'
                else:
                    tmsg += 'No description for this totem is available. This is a bug, so please report this to the admins.'
                pm(cli, shaman, tmsg)
        else:
            pm(cli, shaman, "You are a \u0002{0}\u0002.".format(role))
            if role != "crazed shaman":
                pm(cli, shaman, "You have the \u0002{0}\u0002 totem.".format(var.TOTEMS[shaman]))
        pm(cli, shaman, "Players: " + ", ".join(pl))

    for hunter in var.ROLES["hunter"]:
        if hunter in var.HUNTERS:
            continue #already killed
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(hunter)
        if hunter in var.PLAYERS and not is_user_simple(hunter):
            pm(cli, hunter, ('You are a \u0002hunter\u0002. Once per game, you may kill another ' +
                             'player with "kill <nick>". If you do not wish to kill anyone tonight, ' +
                             'use "pass" instead.'))
        else:
            pm(cli, hunter, "You are a \u0002hunter\u0002.")
        pm(cli, hunter, "Players: " + ", ".join(pl))


    for ms in var.ROLES["mad scientist"]:
        pl = ps[:]
        index = var.ALL_PLAYERS.index(ms)
        targets = []
        target1 = var.ALL_PLAYERS[index - 1]
        target2 = var.ALL_PLAYERS[index + 1 if index < len(var.ALL_PLAYERS) - 1 else 0]
        if len(var.ALL_PLAYERS) >= var.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS:
            # determine left player
            i = index
            while True:
                i -= 1
                if i < 0:
                    i = len(var.ALL_PLAYERS) - 1
                if var.ALL_PLAYERS[i] in pl or var.ALL_PLAYERS[i] == ms:
                    target1 = var.ALL_PLAYERS[i]
                    break
            # determine right player
            i = index
            while True:
                i += 1
                if i >= len(var.ALL_PLAYERS):
                    i = 0
                if var.ALL_PLAYERS[i] in pl or var.ALL_PLAYERS[i] == ms:
                    target2 = var.ALL_PLAYERS[i]
                    break
        targets = "\u0002{0}\u0002 and \u0002{1}\u0002".format(target1, target2)
        if ms in var.PLAYERS and not is_user_simple(ms):
            pm(cli, ms, ("You are the \u0002mad scientist\u0002. If you die, " +
                         "you will let loose a potent chemical concoction that " +
                         "will kill {0} if they are still alive.".format(targets)))
        else:
            pm(cli, ms, "You are the \u0002mad scientist\u0002. Targets: {0}".format(targets))

    for doctor in var.ROLES["doctor"]:
        if doctor in var.DOCTORS and var.DOCTORS[doctor] > 0: # has immunizations remaining
            pl = ps[:]
            random.shuffle(pl)
            if doctor in var.PLAYERS and not is_user_simple(doctor):
                pm(cli, doctor, ('You are a \u0002doctor\u0002. You can give out immunizations to ' +
                                 'villagers by using "give <nick>" in PM during the daytime. ' +
                                 'An immunized villager will die instead of turning into a wolf due to the ' +
                                 'alpha wolf\'s or lycan\'s power.'))
            else:
                pm(cli, doctor, "You are a \u0002doctor\u0002.")
            pm(cli, doctor, 'You have \u0002{0}\u0002 immunization{1}.'.format(var.DOCTORS[doctor], 's' if var.DOCTORS[doctor] > 1 else ''))

    for fool in var.ROLES["fool"]:
        if fool in var.PLAYERS and not is_user_simple(fool):
            pm(cli, fool, ('You are a \u0002fool\u0002. The game immediately ends with you ' +
                           'being the only winner if you are lynched during the day. You cannot ' +
                           'otherwise win this game.'))
        else:
            pm(cli, fool, "You are a \u0002fool\u0002.")

    for jester in var.ROLES["jester"]:
        if jester in var.PLAYERS and not is_user_simple(jester):
            pm(cli, jester, ('You are a \u0002jester\u0002. You will win alongside the normal winners ' +
                             'if you are lynched during the day. You cannot otherwise win this game.'))
        else:
            pm(cli, jester, "You are a \u0002jester\u0002.")

    for monster in var.ROLES["monster"]:
        if monster in var.PLAYERS and not is_user_simple(monster):
            pm(cli, monster, ('You are a \u0002monster\u0002. You cannot be killed by the wolves. ' +
                              'If you survive until the end of the game, you win instead of the ' +
                              'normal winners.'))
        else:
            pm(cli, monster, "You are a \u0002monster\u0002.")

    for lycan in var.ROLES["lycan"]:
        if lycan in var.PLAYERS and not is_user_simple(lycan):
            pm(cli, lycan, ('You are a \u0002lycan\u0002. You are currently on the side of the ' +
                            'villagers, but will turn into a wolf instead of dying if you are ' +
                            'targeted by the wolves during the night.'))
        else:
            pm(cli, lycan, "You are a \u0002lycan\u0002.")

    for v_ghost, who in var.VENGEFUL_GHOSTS.items():
        if who[0] == "!":
            continue
        wolves = var.list_players(var.WOLFTEAM_ROLES)
        if who == "wolves":
            pl = wolves
        else:
            pl = ps[:]
            for wolf in wolves:
                pl.remove(wolf)

        random.shuffle(pl)

        if v_ghost in var.PLAYERS and not is_user_simple(v_ghost):
            pm(cli, v_ghost, ('You are a \u0002vengeful ghost\u0002, sworn to take revenge on the ' +
                              '{0} that you believe killed you. You must kill one of them with ' +
                              '"kill <nick>" tonight. If you do not, one of them will be selected ' +
                              'at random.').format(who))
        else:
            pm(cli, v_ghost, "You are a \u0002vengeful ghost\u0002.")
        pm(cli, v_ghost, who.capitalize() + ": " + ", ".join(pl))
        debuglog("GHOST: {0} (target: {1}) - players: {2}".format(v_ghost, who, ", ".join(pl)))

    for ass in var.ROLES["assassin"]:
        if ass in var.TARGETED and var.TARGETED[ass] != None:
            continue # someone already targeted
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(ass)
        role = var.get_role(ass)
        if role == "village drunk":
            var.TARGETED[ass] = random.choice(pl)
            message = ("You are an \u0002assassin\u0002. In your drunken stupor you have selected " +
                       "\u0002{0}\u0002 as your target.").format(var.TARGETED[ass])
            if ass in var.PLAYERS and not is_user_simple(ass):
                message += " If you die you will take out your target with you."
            pm(cli, ass, message)
        else:
            if ass in var.PLAYERS and not is_user_simple(ass):
                pm(cli, ass, ('You are an \u0002assassin\u0002. Choose a target with ' +
                              '"target <nick>". If you die you will take out your target with you. ' +
                              'If your target dies you may choose another one.'))
            else:
                pm(cli, ass, "You are an \u0002assassin\u0002.")
            pm(cli, ass, "Players: " + ", ".join(pl))

    for piper in var.ROLES["piper"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(piper)
        for charmed in var.CHARMED:
            if charmed in pl: # corner case: if there are multiple pipers and a piper is charmed, the piper will be in var.CHARMED but not in pl
                pl.remove(charmed)
        if piper in var.PLAYERS and not is_user_simple(piper):
            pm(cli, piper, ('You are a \u0002piper\u0002. You must select two players ' +
                            'to charm each night. The charmed players will know each ' +
                            'other, but not who charmed them. You win when all other ' +
                            'players are charmed. Use "charm <nick1> and <nick2>" to ' +
                            'select the players to charm.'))
        else:
            pm(cli, piper, "You are a \u0002piper\u0002.")
        pm(cli, piper, "Players: " + ", ".join(pl))

    for turncoat in var.ROLES["turncoat"]:
        # they start out as unsided, but can change n1
        if turncoat not in var.TURNCOATS:
            var.TURNCOATS[turncoat] = ("none", -1)

        if turncoat in var.PLAYERS and not is_user_simple(turncoat):
            message = ('You are a \u0002turncoat\u0002. You can change which team you\'re siding with every other night. ' +
                       'Use "side villagers" or "side wolves" to select your team. ')
            if var.TURNCOATS[turncoat][0] != "none":
                message += 'You are currently siding with \u0002{0}\u0002.'.format(var.TURNCOATS[turncoat][0])
            else:
                message += 'If you die before selecting a side, you will not win.'
            pm(cli, turncoat, message)
        else:
            pm(cli, turncoat, 'You are a \u0002turncoat\u0002. Current side: \u0002{0}\u0002.'.format(var.TURNCOATS[turncoat][0]))

    if var.FIRST_NIGHT:
        for mm in var.ROLES["matchmaker"]:
            pl = ps[:]
            random.shuffle(pl)
            if mm in var.PLAYERS and not is_user_simple(mm):
                pm(cli, mm, ('You are a \u0002matchmaker\u0002. You can select two players ' +
                             'to be lovers with "choose <nick1> and <nick2>". If one lover ' +
                             'dies, the other will as well. You may select yourself as one ' +
                             'of the lovers. You may only select lovers during the first night. ' +
                             'If you do not select lovers, they will be randomly selected and ' +
                             'you will not be told who they are (unless you are one of them).'))
            else:
                pm(cli, mm, "You are a \u0002matchmaker\u0002.")
            pm(cli, mm, "Players: " + ", ".join(pl))

        for clone in var.ROLES["clone"]:
            pl = ps[:]
            random.shuffle(pl)
            pl.remove(clone)
            if clone in var.PLAYERS and not is_user_simple(clone):
                pm(cli, clone, ('You are a \u0002clone\u0002. You can select someone to clone ' +
                                'with "clone <nick>". If that player dies, you become their ' +
                                'role(s). You may only clone someone during the first night.'))
            else:
                pm(cli, clone, "You are a \u0002clone\u0002.")
            pm(cli, clone, "Players: "+", ".join(pl))

        for minion in var.ROLES["minion"]:
            wolves = var.list_players(var.WOLF_ROLES)
            random.shuffle(wolves)
            if minion in var.PLAYERS and not is_user_simple(minion):
                pm(cli, minion, "You are a \u0002minion\u0002. It is your job to help the wolves kill all of the villagers.")
            else:
                pm(cli, minion, "You are a \u0002minion\u0002.")
            pm(cli, minion, "Wolves: " + ", ".join(wolves))

        villagers = copy.copy(var.ROLES["villager"])
        villagers |= var.ROLES["time lord"]
        if var.DEFAULT_ROLE == "villager":
            villagers |= var.ROLES["vengeful ghost"] | var.ROLES["amnesiac"]
        for villager in villagers:
            if villager in var.PLAYERS and not is_user_simple(villager):
                pm(cli, villager, "You are a \u0002villager\u0002. It is your job to lynch all of the wolves.")
            else:
                pm(cli, villager, "You are a \u0002villager\u0002.")

        cultists = copy.copy(var.ROLES["cultist"])
        if var.DEFAULT_ROLE == "cultist":
            cultists |= var.ROLES["vengeful ghost"] | var.ROLES["amnesiac"]
        for cultist in cultists:
            if cultist in var.PLAYERS and not is_user_simple(cultist):
                pm(cli, cultist, "You are a \u0002cultist\u0002. It is your job to help the wolves kill all of the villagers.")
            else:
                pm(cli, cultist, "You are a \u0002cultist\u0002.")

    for g in var.GUNNERS.keys():
        if g not in ps:
            continue
        elif not var.GUNNERS[g]:
            continue
        elif var.GUNNERS[g] == 0:
            continue
        norm_notify = g in var.PLAYERS and not is_user_simple(g)
        role = "gunner"
        if g in var.ROLES["sharpshooter"]:
            role = "sharpshooter"
        if norm_notify:
            if role == "gunner":
                gun_msg = ('You are a \u0002{0}\u0002 and hold a gun that shoots special silver bullets. ' +
                           'You may only use it during the day by typing "{0}shoot <nick>" in channel. '.format(botconfig.CMD_CHAR) +
                           'Wolves and the crow will die instantly when shot, but anyone else will ' +
                           'likely survive. You have {1}.')
            elif role == "sharpshooter":
                gun_msg = ('You are a \u0002{0}\u0002 and hold a gun that shoots special silver bullets. ' +
                           'You may only use it during the day by typing "{0}shoot <nick>" in channel. '.format(botconfig.CMD_CHAR) +
                           'Wolves and the crow will die instantly when shot, and anyone else will ' +
                           'likely die as well due to your skill with the gun. You have {1}.')
        else:
            gun_msg = ("You are a \u0002{0}\u0002 and have a gun with {1}.")
        if var.GUNNERS[g] == 1:
            gun_msg = gun_msg.format(role, "1 bullet")
        elif var.GUNNERS[g] > 1:
            gun_msg = gun_msg.format(role, str(var.GUNNERS[g]) + " bullets")
        else:
            continue

        pm(cli, g, gun_msg)

    dmsg = (daydur_msg + "It is now nighttime. All players "+
                   "check for PMs from me for instructions.")

    if not var.FIRST_NIGHT:
        dmsg = (dmsg + " If you did not receive one, simply sit back, "+
                   "relax, and wait patiently for morning.")
    cli.msg(chan, dmsg)
    debuglog("BEGIN NIGHT")
    # If there are no nightroles that can act, immediately turn it to daytime
    chk_nightdone(cli)


def cgamemode(cli, arg):
    chan = botconfig.CHANNEL
    if var.ORIGINAL_SETTINGS:  # needs reset
        reset_settings()

    modeargs = arg.split("=", 1)

    modeargs = [a.strip() for a in modeargs]
    if modeargs[0] in var.GAME_MODES.keys():
        md = modeargs.pop(0)
        try:
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
        except var.InvalidModeException as e:
            cli.msg(botconfig.CHANNEL, "Invalid mode: "+str(e))
            return False
    else:
        cli.msg(chan, "Mode \u0002{0}\u0002 not found.".format(modeargs[0]))


def expire_start_votes(cli, chan):
    # Should never happen as the timer is removed on game start, but just to be safe
    if var.PHASE != 'join':
        return

    with var.WARNING_LOCK:
        var.START_VOTES = set()
        cli.msg(chan, "Not enough votes to start were accumulated in 1 minute, removing start votes.")

@cmd("start", phases=("join",))
def start_cmd(cli, nick, chan, rest):
    """Starts a game of Werewolf."""
    start(cli, nick, chan)

def start(cli, nick, chan, forced = False, restart = ""):
    if (not forced and var.LAST_START and nick in var.LAST_START and
            var.LAST_START[nick] + timedelta(seconds=var.START_RATE_LIMIT) >
            datetime.now() and not restart):
        cli.notice(nick, ("This command is rate-limited. Please wait a while "
                          "before using it again."))
        return

    if restart:
        var.RESTART_TRIES += 1
    if var.RESTART_TRIES > 3:
        stop_game(cli, abort=True)
        return

    if not restart:
        var.LAST_START[nick] = datetime.now()

    if chan != botconfig.CHANNEL:
        return

    villagers = var.list_players()
    pl = villagers[:]

    if not restart:
        if var.PHASE == "none":
            cli.notice(nick, "No game is currently running.")
            return
        if var.PHASE != "join":
            cli.notice(nick, "Werewolf is already in play.")
            return
        if nick not in villagers and nick != chan and not forced:
            cli.notice(nick, "You're not currently playing.")
            return

        now = datetime.now()
        var.GAME_START_TIME = now  # Only used for the idler checker
        dur = int((var.CAN_START_TIME - now).total_seconds())
        if dur > 0 and not forced:
            plural = "" if dur == 1 else "s"
            cli.msg(chan, "Please wait at least {0} more second{1}.".format(dur, plural))
            return

        if len(villagers) < var.MIN_PLAYERS:
            cli.msg(chan, "{0}: \u0002{1}\u0002 or more players are required to play.".format(nick, var.MIN_PLAYERS))
            return

        if len(villagers) > var.MAX_PLAYERS:
            cli.msg(chan, "{0}: At most \u0002{1}\u0002 players may play.".format(nick, var.MAX_PLAYERS))
            return

        with var.WARNING_LOCK:
            if not forced and nick in var.START_VOTES:
                cli.notice(nick, "You have already voted to start the game.")
                return

            start_votes_required = min(math.ceil(len(villagers) * var.START_VOTES_SCALE), var.START_VOTES_MAX)
            if not forced and len(var.START_VOTES) < start_votes_required:
                # If there's only one more vote required, start the game immediately.
                # Checked here to make sure that a player that has already voted can't
                # vote again for the final start.
                if len(var.START_VOTES) < start_votes_required - 1:
                    var.START_VOTES.add(nick)
                    msg = "{0} has voted to \u0002start\u0002 the game. \u0002{1}\u0002 more {2} required."
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
                cgamemode(cli, random.choice(voted))
            else:
                possiblegamemodes = []
                for gamemode in var.GAME_MODES.keys():
                    if len(villagers) >= var.GAME_MODES[gamemode][1] and len(villagers) <= var.GAME_MODES[gamemode][2] and var.GAME_MODES[gamemode][3] > 0:
                        possiblegamemodes += [gamemode]*(var.GAME_MODES[gamemode][3]+votes.get(gamemode, 0)*15)
                cgamemode(cli, random.choice(possiblegamemodes))

    else:
        cgamemode(cli, restart)
        var.GAME_ID = time.time() # restart reaper timer

    addroles = {}

    event = Event("role_attribution", {"addroles": addroles})
    if event.dispatch(cli, chk_win_conditions, var, villagers):
        for index in range(len(var.ROLE_INDEX) - 1, -1, -1):
            if var.ROLE_INDEX[index] <= len(villagers):
                for role, num in var.ROLE_GUIDE.items(): # allow event to override some roles
                    addroles[role] = addroles.get(role, num[index])
                break
        else:
            cli.msg(chan, "{0}: No game settings are defined for \u0002{1}\u0002 player games.".format(nick, len(villagers)))
            return

    if var.ORIGINAL_SETTINGS and not restart:  # Custom settings
        need_reset = True
        wvs = sum(addroles[r] for r in var.WOLFCHAT_ROLES)
        if len(villagers) < (sum(addroles.values()) - sum(addroles[r] for r in var.TEMPLATE_RESTRICTIONS.keys())):
            cli.msg(chan, "There are too few players in the "+
                          "game to use the custom roles.")
        elif not wvs:
            cli.msg(chan, "There has to be at least one wolf!")
        elif wvs > (len(villagers) / 2):
            cli.msg(chan, "Too many wolves.")
        elif set(addroles) != set(var.ROLE_GUIDE):
            cli.msg(chan, "Error: Not all roles have defined player counts.")
        else:
            need_reset = False

        if need_reset:
            reset_settings()
            cli.msg(chan, "The default settings have been restored. Please !start again.")
            var.PHASE = "join"
            return

    if var.ADMIN_TO_PING and not restart:
        for decor in (COMMANDS.get("join", []) + COMMANDS.get("start", [])):
            decor(lambda *spam: cli.msg(chan, "This command has been disabled by an admin."))

    var.ROLES = {}
    var.GUNNERS = {}
    var.WOLF_GUNNERS = {}
    var.SEEN = set()
    var.OBSERVED = {}
    var.KILLS = {}
    var.GUARDED = {}
    var.HVISITED = {}
    var.HUNTERS = set()
    var.VENGEFUL_GHOSTS = {}
    var.CLONED = {}
    var.TARGETED = {}
    var.LASTGUARDED = {}
    var.LASTHEXED = {}
    var.LASTGIVEN = {}
    var.MATCHMAKERS = set()
    var.REVEALED_MAYORS = set()
    var.SILENCED = set()
    var.TOBESILENCED = set()
    var.DESPERATE = set()
    var.REVEALED = set()
    var.ASLEEP = set()
    var.PROTECTED = []
    var.JESTERS = set()
    var.AMNESIACS = set()
    var.NIGHT_COUNT = 0
    var.DAY_COUNT = 0
    var.ANGRY_WOLVES = False
    var.DISEASED_WOLVES = False
    var.TRAITOR_TURNED = False
    var.FINAL_ROLES = {}
    var.ORIGINAL_LOVERS = {}
    var.IMPATIENT = []
    var.DEATH_TOTEM = []
    var.PACIFISTS = []
    var.INFLUENTIAL = set()
    var.LYCANTHROPES = set()
    var.TOBELYCANTHROPES = set()
    var.LUCKY = set()
    var.TOBELUCKY = set()
    var.DISEASED = set()
    var.TOBEDISEASED = set()
    var.RETRIBUTION = set()
    var.MISDIRECTED = set()
    var.TOBEMISDIRECTED = set()
    var.EXCHANGED = set()
    var.SHAMANS = {}
    var.HEXED = set()
    var.OTHER_KILLS = {}
    var.ABSTAINED = False
    var.DOCTORS = {}
    var.IMMUNIZED = set()
    var.CURED_LYCANS = set()
    var.ALPHA_WOLVES = set()
    var.ALPHA_ENABLED = False
    var.BITTEN = {}
    var.BITE_PREFERENCES = {}
    var.BITTEN_ROLES = {}
    var.LYCAN_ROLES = {}
    var.AMNESIAC_ROLES = {}
    var.CHARMERS = set()
    var.CHARMED = set()
    var.TOBECHARMED = set()
    var.ACTIVE_PROTECTIONS = defaultdict(list)
    var.TURNCOATS = {}
    var.EXCHANGED_ROLES = []
    var.EXTRA_WOLVES = 0

    for role, count in addroles.items():
        if role in var.TEMPLATE_RESTRICTIONS.keys():
            var.ROLES[role] = [None] * count
            continue # We deal with those later, see below
        selected = random.sample(villagers, count)
        var.ROLES[role] = set(selected)
        for x in selected:
            villagers.remove(x)

    for v in villagers:
        var.ROLES[var.DEFAULT_ROLE].add(v)

    # Now for the templates
    for template, restrictions in var.TEMPLATE_RESTRICTIONS.items():
        if template == "sharpshooter":
            continue # sharpshooter gets applied specially
        possible = pl[:]
        for cannotbe in var.list_players(restrictions):
            if cannotbe in possible:
                possible.remove(cannotbe)
        if len(possible) < len(var.ROLES[template]):
            cli.msg(chan, "Not enough valid targets for the {0} template.".format(template))
            if var.ORIGINAL_SETTINGS:
                var.ROLES = {"person": var.ALL_PLAYERS}
                reset_settings()
                cli.msg(chan, "The default settings have been restored. Please !start again.")
                var.PHASE = "join"
                return
            else:
                cli.msg(chan, "This role has been skipped for this game.")
                var.ROLES[template] = set()
                continue

        var.ROLES[template] = set(random.sample(possible, len(var.ROLES[template])))

    # Handle gunner
    cannot_be_sharpshooter = var.list_players(var.TEMPLATE_RESTRICTIONS["sharpshooter"])
    gunner_list = copy.copy(var.ROLES["gunner"])
    num_sharpshooters = 0
    for gunner in gunner_list:
        if gunner in var.ROLES["village drunk"]:
            var.GUNNERS[gunner] = (var.DRUNK_SHOTS_MULTIPLIER * math.ceil(var.SHOTS_MULTIPLIER * len(pl)))
        elif num_sharpshooters < addroles["sharpshooter"] and gunner not in cannot_be_sharpshooter and random.random() <= var.SHARPSHOOTER_CHANCE:
            var.GUNNERS[gunner] = math.ceil(var.SHARPSHOOTER_MULTIPLIER * len(pl))
            var.ROLES["gunner"].remove(gunner)
            var.ROLES["sharpshooter"].append(gunner)
            num_sharpshooters += 1
        else:
            var.GUNNERS[gunner] = math.ceil(var.SHOTS_MULTIPLIER * len(pl))

    var.ROLES["sharpshooter"] = set(var.ROLES["sharpshooter"])

    var.ROLES["sharpshooter"].discard(None)

    if not restart:
        var.SPECIAL_ROLES["goat herder"] = []
        if var.GOAT_HERDER:
            var.SPECIAL_ROLES["goat herder"] = [ nick ]

    with var.WARNING_LOCK: # cancel timers
        for name in ("join", "join_pinger", "start_votes"):
            if name in var.TIMERS:
                var.TIMERS[name][0].cancel()
                del var.TIMERS[name]

    var.LAST_STATS = None
    var.LAST_TIME = None
    var.LAST_VOTES = None

    if not restart:
        gamemode = var.CURRENT_GAMEMODE.name

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

        cli.msg(chan, ("{0}: Welcome to Werewolf, the popular detective/social party "+
                       "game (a theme of Mafia). Using the \u0002{1}\u0002 game mode{2}.").format(", ".join(pl), gamemode, options))
        cli.mode(chan, "+m")

    var.ORIGINAL_ROLES = copy.deepcopy(var.ROLES)  # Make a copy

    # Handle amnesiac;
    # matchmaker is blacklisted if AMNESIAC_NIGHTS > 1 due to only being able to act night 1
    # clone and traitor are blacklisted due to assumptions made in default !stats computations.
    # If you remove these from the blacklist you will need to modify the default !stats logic
    # chains in order to correctly account for these. As a forewarning, such modifications are
    # nontrivial and will likely require a great deal of thought (and likely new tracking vars)
    amnroles = var.ROLE_GUIDE.keys() - {var.DEFAULT_ROLE, "amnesiac", "clone", "traitor"}
    if var.AMNESIAC_NIGHTS > 1 and "matchmaker" in amnroles:
        amnroles.remove("matchmaker")
    for nope in var.AMNESIAC_BLACKLIST:
        amnroles.discard(nope)
    for nope in var.TEMPLATE_RESTRICTIONS.keys():
        amnroles.discard(nope)
    for amnesiac in var.ROLES["amnesiac"]:
        var.AMNESIAC_ROLES[amnesiac] = random.choice(list(amnroles))

    # Handle doctor
    for doctor in var.ROLES["doctor"]:
        var.DOCTORS[doctor] = math.ceil(var.DOCTOR_IMMUNIZATION_MULTIPLIER * len(pl))
    for amn in var.AMNESIAC_ROLES:
        if var.AMNESIAC_ROLES[amn] == "doctor":
            var.DOCTORS[amn] = math.ceil(var.DOCTOR_IMMUNIZATION_MULTIPLIER * len(pl))

    var.DAY_TIMEDELTA = timedelta(0)
    var.NIGHT_TIMEDELTA = timedelta(0)
    var.DAY_START_TIME = datetime.now()
    var.NIGHT_START_TIME = datetime.now()

    var.LAST_PING = None

    var.PLAYERS = {plr:dict(var.USERS[plr]) for plr in pl if plr in var.USERS}

    debuglog("ROLES:", " | ".join("{0}: {1}".format(role, ", ".join(players))
        for role, players in sorted(var.ROLES.items()) if players and role not in var.TEMPLATE_RESTRICTIONS.keys()))
    templates = " | ".join("{0}: {1}".format(tmplt, ", ".join(players))
        for tmplt, players in sorted(var.ROLES.items()) if players and tmplt in var.TEMPLATE_RESTRICTIONS.keys())
    if not templates:
        templates = "None"
    debuglog("TEMPLATES:", templates)

    if restart:
        var.PHASE = None # allow transition_* to run properly if game was restarted on first night
    var.FIRST_NIGHT = True
    if not var.START_WITH_DAY:
        var.GAMEPHASE = "night"
        transition_night(cli)
    else:
        var.FIRST_DAY = True
        var.GAMEPHASE = "day"
        transition_day(cli)

    for hostmask in list(var.STASISED.keys()):
        var.STASISED[hostmask] -= 1
        var.set_stasis(hostmask, var.STASISED[hostmask])
        if var.STASISED[hostmask] <= 0:
            del var.STASISED[hostmask]

    if not var.DISABLE_ACCOUNTS:
        for acc in list(var.STASISED_ACCS.keys()):
            var.STASISED_ACCS[acc] -= 1
            var.set_stasis_acc(acc, var.STASISED_ACCS[acc])
            if var.STASISED_ACCS[acc] <= 0:
                del var.STASISED_ACCS[acc]

    if not botconfig.DEBUG_MODE or not var.DISABLE_DEBUG_MODE_REAPER:
        # DEATH TO IDLERS!
        reapertimer = threading.Thread(None, reaper, args=(cli,var.GAME_ID))
        reapertimer.daemon = True
        reapertimer.start()



@hook("error")
def on_error(cli, pfx, msg):
    if var.RESTARTING or msg.endswith("(Excess Flood)"):
        _restart_program(cli)
    elif msg.startswith("Closing Link:"):
        raise SystemExit

@cmd("fstasis", admin_only=True, pm=True)
def fstasis(cli, nick, chan, rest):
    """Removes or sets stasis penalties."""

    data = rest.split()
    msg = None

    if data:
        lusers = {k.lower(): v for k, v in var.USERS.items()}
        user = data[0]

        if user.lower() in lusers:
            ident = lusers[user.lower()]["ident"]
            host = lusers[user.lower()]["host"]
            acc = lusers[user.lower()]["account"]
            hostmask = ident + "@" + host
        else:
            hostmask = user
            acc = None
        if var.ACCOUNTS_ONLY and acc == "*":
            acc = None
            hostmask = None
            msg = "{0} is not logged in to NickServ.".format(user)
        if not acc and user in var.STASISED_ACCS:
            acc = user

        err_msg = "The amount of stasis has to be a non-negative integer."
        if (not var.ACCOUNTS_ONLY or not acc) and hostmask:
            if len(data) == 1:
                if hostmask in var.STASISED:
                    plural = "" if var.STASISED[hostmask] == 1 else "s"
                    msg = "\u0002{0}\u0002 (Host: {1}) is in stasis for \u0002{2}\u0002 game{3}.".format(data[0], hostmask, var.STASISED[hostmask], plural)
                else:
                    msg = "\u0002{0}\u0002 (Host: {1}) is not in stasis.".format(data[0], hostmask)
            else:
                try:
                    amt = int(data[1])
                except ValueError:
                    if chan == nick:
                        pm(cli, nick, err_msg)
                    else:
                        cli.notice(nick, err_msg)

                    return

                if amt < 0:
                    if chan == nick:
                        pm(cli, nick, err_msg)
                    else:
                        cli.notice(nick, err_msg)

                    return
                elif amt > 2**31-1:
                    amt = 2**31-1

                if amt > 0:
                    var.STASISED[hostmask] = amt
                    var.set_stasis(hostmask, amt)
                    plural = "" if amt == 1 else "s"
                    msg = "\u0002{0}\u0002 (Host: {1}) is now in stasis for \u0002{2}\u0002 game{3}.".format(data[0], hostmask, amt, plural)
                elif amt == 0:
                    if hostmask in var.STASISED:
                        del var.STASISED[hostmask]
                        var.set_stasis(hostmask, 0)
                        msg = "\u0002{0}\u0002 (Host: {1}) is no longer in stasis.".format(data[0], hostmask)
                    else:
                        msg = "\u0002{0}\u0002 (Host: {1}) is not in stasis.".format(data[0], hostmask)
        if not var.DISABLE_ACCOUNTS and acc:
            if len(data) == 1:
                if acc in var.STASISED_ACCS:
                    plural = "" if var.STASISED_ACCS[acc] == 1 else "s"
                    msg = "\u0002{0}\u0002 (Account: {1}) is in stasis for \u0002{2}\u0002 game{3}.".format(data[0], acc, var.STASISED_ACCS[acc], plural)
                else:
                    msg = "\u0002{0}\u0002 (Account: {1}) is not in stasis.".format(data[0], acc)
            else:
                try:
                    amt = int(data[1])
                except ValueError:
                    if chan == nick:
                        pm(cli, nick, err_msg)
                    else:
                        cli.notice(nick, err_msg)
                    return

                if amt < 0:
                    if chan == nick:
                        pm(cli, nick, err_msg)
                    else:
                        cli.notice(nick, err_msg)
                    return
                elif amt > 2**31-1:
                    amt = 2**31-1

                if amt > 0:
                    var.STASISED_ACCS[acc] = amt
                    var.set_stasis_acc(acc, amt)
                    plural = "" if amt == 1 else "s"
                    msg = "\u0002{0}\u0002 (Account: {1}) is now in stasis for \u0002{2}\u0002 game{3}.".format(data[0], acc, amt, plural)
                elif amt == 0:
                    if acc in var.STASISED_ACCS:
                        del var.STASISED_ACCS[acc]
                        var.set_stasis_acc(acc, 0)
                        msg = "\u0002{0}\u0002 (Account: {1}) is no longer in stasis.".format(data[0], acc)
                    else:
                        msg = "\u0002{0}\u0002 (Account: {1}) is not in stasis.".format(data[0], acc)
    elif var.STASISED or var.STASISED_ACCS:
        stasised = {}
        for hostmask in var.STASISED:
            if var.DISABLE_ACCOUNTS:
                stasised[hostmask] = var.STASISED[hostmask]
            else:
                stasised[hostmask+" (Host)"] = var.STASISED[hostmask]
        if not var.DISABLE_ACCOUNTS:
            for acc in var.STASISED_ACCS:
                stasised[acc+" (Account)"] = var.STASISED_ACCS[acc]
        msg = "Currently stasised: {0}".format(", ".join(
            "\u0002{0}\u0002 ({1})".format(usr, number)
            for usr, number in stasised.items()))
    else:
        msg = "Nobody is currently stasised."

    if msg:
        if chan == nick:
            pm(cli, nick, msg)
        else:
            cli.msg(chan, msg)

def is_user_stasised(nick):
    """Checks if a user is in stasis. Returns a number of games in stasis."""

    if nick in var.USERS:
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        acc = var.USERS[nick]["account"]
    else:
        return 0
    amount = 0
    if not var.DISABLE_ACCOUNTS and acc and acc != "*":
        if acc in var.STASISED_ACCS:
            amount = var.STASISED_ACCS[acc]
    for hostmask in var.STASISED:
        if var.match_hostmask(hostmask, nick, ident, host):
           amount = max(amount, var.STASISED[hostmask])
    return amount

def allow_deny(cli, nick, chan, rest, mode):
    data = rest.split()
    msg = None

    modes = ("allow", "deny")
    assert mode in modes, "mode not in {!r}".format(modes)

    opts = defaultdict(bool)

    if data and data[0].startswith("-"):
        if data[0] == "-cmds":
            opts["cmds"] = True
        elif data[0] == "-cmd":
            if len(data) < 2:
                if chan == nick:
                    pm(cli, nick, "Error: No command specified. Did you mean \u0002-cmds\u0002?")
                else:
                    cli.notice(nick, "Error: No command specified. Did you mean \u0002-cmds\u0002?")

                return

            opts["cmd"] = data[1]
            data = data[1:]
        elif data[0] == "-acc" or data[0] == "-account":
            opts["acc"] = True
        elif data[0] == "-host":
            opts["host"] = True
        else:
            if chan == nick:
                pm(cli, nick, "Invalid option: {0}".format(data[0][1:]))
            else:
                cli.notice(nick, "Invalid option: {0}".format(data[0][1:]))

            return

        data = data[1:]

    if data and not opts["cmd"]:
        lusers = {k.lower(): v for k, v in var.USERS.items()}
        user = data[0]

        if opts["acc"] and user != "*":
            hostmask = None
            acc = user
        elif not opts["host"] and user.lower() in lusers:
            ident = lusers[user.lower()]["ident"]
            host = lusers[user.lower()]["host"]
            acc = lusers[user.lower()]["account"]
            hostmask = ident + "@" + host
        else:
            hostmask = user
            m = re.match('(?:(?:(.*?)!)?(.*)@)?(.*)', hostmask)
            user = m.group(1) or ""
            ident = m.group(2) or ""
            host = m.group(3)
            acc = None

        if user == "*":
            opts["host"] = True

        if not var.DISABLE_ACCOUNTS and acc:
            if mode == "allow":
                variable = var.ALLOW_ACCOUNTS
                noaccvar = var.ALLOW
            else:
                variable = var.DENY_ACCOUNTS
                noaccvar = var.DENY
            if len(data) == 1:
                cmds = set()
                if acc in variable:
                    cmds |= set(variable[acc])

                if hostmask and not opts["acc"]:
                    for mask in noaccvar:
                        if var.match_hostmask(mask, user, ident, host):
                            cmds |= set(noaccvar[mask])

                if cmds:
                    msg = "\u0002{0}\u0002 (Account: {1}) is {2} the following {3}commands: {4}.".format(
                        data[0], acc, "allowed" if mode == "allow" else "denied", "special " if mode == "allow" else "", ", ".join(cmds))
                else:
                    msg = "\u0002{0}\u0002 (Account: {1}) is not {2} commands.".format(data[0], acc, "allowed any special" if mode == "allow" else "denied any")
            else:
                if acc not in variable:
                    variable[acc] = set()
                commands = data[1:]
                for command in commands: # Add or remove commands one at a time to a specific account
                    if "-*" in commands: # Remove all
                        for cmd in variable[acc]:
                            if mode == "allow":
                                var.remove_allow_acc(acc, cmd)
                            else:
                                var.remove_deny_acc(acc, cmd)
                        del variable[acc]
                        break
                    if command[0] == "-": # Starting with - (to remove)
                        rem = True
                        command = command[1:]
                    else:
                        rem = False
                    if command.startswith(botconfig.CMD_CHAR): # ignore command prefix
                        command = command[len(botconfig.CMD_CHAR):]

                    if not rem:
                        if command in COMMANDS and command not in ("fdeny", "fallow", "fsend", "exec", "eval") and command not in variable[acc]:
                            variable[acc].add(command)
                            if mode == "allow":
                                var.add_allow_acc(acc, command)
                            else:
                                var.add_deny_acc(acc, command)
                    elif command in variable[acc]:
                        variable[acc].remove(command)
                        if mode == "allow":
                            var.remove_allow_acc(acc, command)
                        else:
                            var.remove_deny_acc(acc, command)
                if acc in variable and variable[acc]:
                    msg = "\u0002{0}\u0002 (Account: {1}) is now {2} the following {3}commands: {4}{5}.".format(
                        data[0], acc, "allowed" if mode == "allow" else "denied", "special " if mode == "allow" else "", botconfig.CMD_CHAR, ", {0}".format(botconfig.CMD_CHAR).join(variable[acc]))
                else:
                    if acc in variable:
                        del variable[acc]
                    msg = "\u0002{0}\u0002 (Account: {1}) is no longer {2} commands.".format(data[0], acc, "allowed any special" if mode == 'allow' else "denied any")
        elif var.ACCOUNTS_ONLY and not opts["host"]:
            msg = "Error: \u0002{0}\u0002 is not logged in to NickServ.".format(data[0])
        else:
            if mode == "allow":
                variable = var.ALLOW
            else:
                variable = var.DENY
            if len(data) == 1: # List commands for a specific hostmask
                cmds = []
                for mask in variable:
                    if var.match_hostmask(mask, user, ident, host):
                        cmds.extend(variable[mask])

                if cmds:
                    msg = "\u0002{0}\u0002 (Host: {1}) is {2} the following {3}commands: {4}.".format(
                        data[0], hostmask, "allowed" if mode == "allow" else "denied", "special " if mode == "allow" else "", ", ".join(cmds))
                else:
                    msg = "\u0002{0}\u0002 (Host: {1}) is not {2} commands.".format(data[0], hostmask, "allowed any special" if mode == "allow" else "denied any")
            else:
                if hostmask not in variable:
                    variable[hostmask] = set()
                commands = data[1:]
                for command in commands: #add or remove commands one at a time to a specific hostmask
                    if "-*" in commands: # Remove all
                        for cmd in variable[hostmask]:
                            if mode == "allow":
                                var.remove_allow(hostmask, cmd)
                            else:
                                var.remove_deny(hostmask, cmd)
                        del variable[hostmask]
                        break
                    if command[0] == '-': #starting with - removes
                        rem = True
                        command = command[1:]
                    else:
                        rem = False
                    if command.startswith(botconfig.CMD_CHAR): #ignore command prefix
                        command = command[len(botconfig.CMD_CHAR):]

                    if not rem:
                        if command in COMMANDS and command not in ("fdeny", "fallow", "fsend", "exec", "eval") and command not in variable[hostmask]:
                            variable[hostmask].add(command)
                            if mode == "allow":
                                var.add_allow(hostmask, command)
                            else:
                                var.add_deny(hostmask, command)
                    elif command in variable[hostmask]:
                        variable[hostmask].remove(command)
                        if mode == "allow":
                            var.remove_allow(hostmask, command)
                        else:
                            var.remove_deny(hostmask, command)

                if hostmask in variable and variable[hostmask]:
                    msg = "\u0002{0}\u0002 (Host: {1}) is now {2} the following {3}commands: {4}{5}.".format(
                        data[0], hostmask, "allowed" if mode == "allow" else "denied", "special " if mode == "allow" else "", botconfig.CMD_CHAR, ", {0}".format(botconfig.CMD_CHAR).join(variable[hostmask]))
                else:
                    if hostmask in variable:
                        del variable[hostmask]
                    msg = "\u0002{0}\u0002 (Host: {1}) is no longer {2} commands.".format(data[0], hostmask, "allowed any special" if mode == "allow" else "denied any")

    else:
        users_to_cmds = {}
        if not var.DISABLE_ACCOUNTS and not opts["host"]:
            if mode == "allow":
                variable = var.ALLOW_ACCOUNTS
                noaccvar = var.ALLOW
            else:
                variable = var.DENY_ACCOUNTS
                noaccvar = var.DENY

            if variable:
                for acc, varied in variable.items():
                    if opts["acc"] or (var.ACCOUNTS_ONLY and not noaccvar):
                        users_to_cmds[acc] = sorted(varied, key=str.lower)
                    else:
                        users_to_cmds[acc+" (Account)"] = sorted(varied, key=str.lower)
        if not opts["acc"]:
            if mode == "allow":
                variable = var.ALLOW
            else:
                variable = var.DENY
            if variable:
                for hostmask, varied in variable.items():
                    if var.DISABLE_ACCOUNTS or opts["host"]:
                        users_to_cmds[hostmask] = sorted(varied, key=str.lower)
                    else:
                        users_to_cmds[hostmask+" (Host)"] = sorted(varied, key=str.lower)


        if not users_to_cmds: # Deny or Allow list is empty
            msg = "Nobody is {0} commands.".format("allowed any special" if mode == "allow" else "denied any")
        else:
            if opts["cmds"] or opts["cmd"]:
                cmds_to_users = defaultdict(list)

                for user in sorted(users_to_cmds, key=str.lower):
                    for cmd in users_to_cmds[user]:
                        cmds_to_users[cmd].append(user)

                if opts["cmd"]:
                    cmd = opts["cmd"]
                    users = cmds_to_users[cmd]

                    if cmd not in COMMANDS:
                        if chan == nick:
                            pm(cli, nick, "That command does not exist.")
                        else:
                            cli.notice(nick, "That command does not exist.")

                        return

                    if users:
                        msg = "\u0002{0}{1}\u0002 is {2} to the following people: {3}".format(
                            botconfig.CMD_CHAR, opts["cmd"], "allowed" if mode == "allow" else "denied", ", ".join(users))
                    else:
                        msg = "\u0002{0}{1}\u0002 is not {2} to any special people.".format(
                            botconfig.CMD_CHAR, opts["cmd"], "allowed" if mode == "allow" else "denied")
                else:
                    msg = "{0}: {1}".format("Allowed" if mode == "allow" else "Denied", "; ".join("\u0002{0}\u0002 ({1})".format(
                        cmd, ", ".join(users)) for cmd, users in sorted(cmds_to_users.items(), key=lambda t: t[0].lower())))
            else:
                msg = "{0}: {1}".format("Allowed" if mode == "allow" else "Denied", "; ".join("\u0002{0}\u0002 ({1})".format(
                    user, ", ".join(cmds)) for user, cmds in sorted(users_to_cmds.items(), key=lambda t: t[0].lower())))

    if msg:
        msg = var.break_long_message(msg.split("; "), "; ")

        if chan == nick:
            pm(cli, nick, msg)
        else:
            cli.msg(chan, msg)

@cmd("fallow", admin_only=True, pm=True)
def fallow(cli, nick, chan, rest):
    """Allow someone to use an admin command."""
    allow_deny(cli, nick, chan, rest, "allow")

@cmd("fdeny", admin_only=True, pm=True)
def fdeny(cli, nick, chan, rest):
    """Deny someone from using a command."""
    allow_deny(cli, nick, chan, rest, "deny")

@cmd("wait", "w", playing=True, phases=("join",))
def wait(cli, nick, chan, rest):
    """Increases the wait time until !start can be used."""
    pl = var.list_players()

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
            cli.notice(nick, ("This command is rate-limited. Please wait a while "
                              "before using it again."))
            return

        var.LAST_WAIT[nick] = now
        var.WAIT_TB_TOKENS -= 1
        if now > var.CAN_START_TIME:
            var.CAN_START_TIME = now + timedelta(seconds=var.EXTRA_WAIT)
        else:
            var.CAN_START_TIME += timedelta(seconds=var.EXTRA_WAIT)
        cli.msg(chan, ("\u0002{0}\u0002 increased the wait time by "+
                      "{1} seconds.").format(nick, var.EXTRA_WAIT))


@cmd("fwait", admin_only=True, phases=("join",))
def fwait(cli, nick, chan, rest):
    """Forces an increase (or decrease) in wait time. Can be used with a number of seconds to wait."""

    pl = var.list_players()

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

    cli.msg(chan, ("\u0002{0}\u0002 forcibly {2}creased the wait time by {1} "
                   "second{3}.").format(nick,
                                        abs(extra),
                                        "in" if extra >= 0 else "de",
                                        "s" if extra != 1 else ""))


@cmd("fstop", admin_only=True, phases=("join", "day", "night"))
def reset_game(cli, nick, chan, rest):
    """Forces the game to stop."""
    if nick == "<stderr>":
        cli.msg(botconfig.CHANNEL, "Game stopped due to error.")
    else:
        cli.msg(botconfig.CHANNEL, "\u0002{0}\u0002 has forced the game to stop.".format(nick))
    if var.PHASE != "join":
        stop_game(cli)
    else:
        pl = var.list_players()
        reset_modes_timers(cli)
        reset()
        cli.msg(botconfig.CHANNEL, "PING! {0}".format(" ".join(pl)))


@cmd("rules", pm=True)
def show_rules(cli, nick, chan, rest):
    """Displays the rules."""
    if (var.PHASE in ("day", "night") and nick not in var.list_players()) and chan != botconfig.CHANNEL:
        cli.notice(nick, var.RULES)
        return
    cli.msg(chan, var.RULES)

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
            for fn in COMMANDS[cname]:
                if fn.__doc__:
                    got = True
                    if callable(fn.__doc__):
                        msg = botconfig.CMD_CHAR+cname+": "+fn.__doc__(rest)
                    else:
                        msg = botconfig.CMD_CHAR+cname+": "+fn.__doc__
                    if chan == nick:
                        pm(cli, nick, msg)
                    else:
                        cli.notice(nick, msg)
                    return
                else:
                    got = False
                    continue
            else:
                if got:
                    return
                elif chan == nick:
                    pm(cli, nick, "Documentation for this command is not available.")
                else:
                    cli.notice(nick, "Documentation for this command is not available.")

        elif chan == nick:
            pm(cli, nick, "Command not found.")
        else:
            cli.notice(nick, "Command not found.")
        return

    # if command was not found, or if no command was given:
    for name, fn in COMMANDS.items():
        if (name and not fn[0].admin_only and not fn[0].owner_only and
            name not in fn[0].aliases and fn[0].chan):
            fns.append("{0}{1}{0}".format("\u0002", name))
    afns = []
    if is_admin(nick, ident, host):
        for name, fn in COMMANDS.items():
            if fn[0].admin_only and name not in fn[0].aliases:
                afns.append("{0}{1}{0}".format("\u0002", name))
    fns.sort() # Output commands in alphabetical order
    if chan == nick:
        pm(cli, nick, "Commands: {0}".format(var.break_long_message(fns, ", ")))
    else:
        cli.notice(nick, "Commands: {0}".format(var.break_long_message(fns, ", ")))
    if afns:
        afns.sort()
        if chan == nick:
            pm(cli, nick, "Admin Commands: {0}".format(var.break_long_message(afns, ", ")))
        else:
            cli.notice(nick, "Admin Commands: {0}".format(var.break_long_message(afns, ", ")))

@cmd("wiki", pm=True)
def wiki(cli, nick, chan, rest):
    """Prints information on roles from the wiki."""

    # no arguments, just print a link to the wiki
    if not rest:
        cli.msg(chan, "https://github.com/lykoss/lykos/wiki")
        return

    try:
        page = urllib.request.urlopen("https://raw.githubusercontent.com/wiki/lykoss/lykos/Home.md", timeout=2).read().decode("ascii", errors="replace")
    except (urllib.error.URLError, socket.timeout):
        cli.notice(nick, "Request to https://github.com/lykoss/lykos/wiki timed out.")
        return
    if not page:
        cli.notice(nick, "Could not open https://github.com/lykoss/lykos/wiki")
        return

    query = re.escape(rest.strip())
    # look for exact match first, then for a partial match
    match = re.search(r"^##+ ({0})$\r?\n\r?\n^(.*)$".format(query), page, re.MULTILINE + re.IGNORECASE)
    if not match:
        match = re.search(r"^##+ ({0}.*)$\r?\n\r?\n^(.*)$".format(query), page, re.MULTILINE + re.IGNORECASE)
    if not match:
        cli.notice(nick, "Could not find information on that role in https://github.com/lykoss/lykos/wiki")
        return

    # wiki links only have lowercase ascii chars, and spaces are replaced with a dash
    wikilink = "https://github.com/lykoss/lykos/wiki#{0}".format("".join(
                x.lower() for x in match.group(1).replace(" ", "-") if x in string.ascii_letters+"-"))
    if nick == chan:
        pm(cli, nick, wikilink)
        pm(cli, nick, var.break_long_message(match.group(2).split()))
    else:
        cli.msg(chan, wikilink)
        cli.notice(nick, var.break_long_message(match.group(2).split()))

@hook("invite")
def on_invite(cli, raw_nick, something, chan):
    if chan == botconfig.CHANNEL:
        cli.join(chan)
        return # No questions
    (nick, _, ident, host) = parse_nick(raw_nick)
    if is_admin(nick, ident, host):
        cli.join(chan) # Allows the bot to be present in any channel
        debuglog(nick, "INVITE", chan, display=True)
    else:
        pm(cli, parse_nick(nick)[0], "You are not an admin.")

@cmd("fpart", raw_nick=True, admin_only=True, pm=True)
def fpart(cli, rnick, chan, rest):
    """Makes the bot forcibly leave a channel."""
    nick = parse_nick(rnick)[0]
    if nick == chan:
        rest = rest.split()
        if not rest:
            pm(cli, nick, "Usage: fpart <channel>")
            return
        if rest[0] == botconfig.CHANNEL:
            pm(cli, nick, "No, that won't be allowed.")
            return
        chan = rest[0]
        pm(cli, nick, "Leaving "+ chan)
    if chan == botconfig.CHANNEL:
        cli.notice(nick, "No, that won't be allowed.")
        return
    cli.part(chan)

@cmd("admins", "ops", pm=True)
def show_admins(cli, nick, chan, rest):
    """Pings the admins that are available."""

    admins = []
    pl = var.list_players()

    if (chan != nick and var.LAST_ADMINS and var.LAST_ADMINS +
            timedelta(seconds=var.ADMINS_RATE_LIMIT) > datetime.now()):
        cli.notice(nick, ("This command is rate-limited. Please wait a while "
                          "before using it again."))
        return

    if chan != nick or (var.PHASE in ("day", "night") or nick in pl):
        var.LAST_ADMINS = datetime.now()

    if var.ADMIN_PINGING:
        return

    var.ADMIN_PINGING = True

    @hook("whoreply", hookid=4)
    def on_whoreply(cli, server, _, chan, ident, host, ___, user, status, ____):
        if not var.ADMIN_PINGING:
            return

        if is_admin(user) and "G" not in status and user != botconfig.NICK:
            admins.append(user)

    @hook("endofwho", hookid=4)
    def show(*args):
        if not var.ADMIN_PINGING:
            return

        admins.sort(key=str.lower)

        msg = "Available admins: " + ", ".join(admins)

        if chan == nick:
            pm(cli, nick, msg)
        elif var.PHASE in ("day", "night") and nick not in pl:
            cli.notice(nick, msg)
        else:
            cli.msg(chan, msg)

        hook.unhook(4)
        var.ADMIN_PINGING = False

    if nick == chan:
        cli.who(botconfig.CHANNEL)
    else:
        cli.who(chan)

@cmd("coin", pm=True)
def coin(cli, nick, chan, rest):
    """It's a bad idea to base any decisions on this command."""

    if var.PHASE in ("day", "night") and nick not in var.list_players() and chan == botconfig.CHANNEL:
        cli.notice(nick, "You may not use this command right now.")
        return

    cli.msg(chan, "\2{0}\2 tosses a coin into the air...".format(nick))
    coin = random.choice(("heads", "tails"))
    specialty = random.randrange(0,10)
    if specialty == 0:
        coin = "its side"
    if specialty == 1:
        coin = botconfig.NICK
    cmsg = "The coin lands on \2{0}\2.".format(coin)
    cli.msg(chan, cmsg)

@cmd("pony", pm=True)
def pony(cli, nick, chan, rest):
    """For entertaining bronies."""

    if var.PHASE in ("day", "night") and nick not in var.list_players() and chan == botconfig.CHANNEL:
        cli.notice(nick, "You may not use this command right now.")
        return

    cli.msg(chan, "\2{0}\2 tosses a pony into the air...".format(nick))
    pony = random.choice(("hoof", "plot"))
    cmsg = "The pony lands on \2{0}\2.".format(pony)
    cli.msg(chan, cmsg)

@cmd("time", pm=True, phases=("join", "day", "night"))
def timeleft(cli, nick, chan, rest):
    """Returns the time left until the next day/night transition."""

    if (chan != nick and var.LAST_TIME and
            var.LAST_TIME + timedelta(seconds=var.TIME_RATE_LIMIT) > datetime.now()):
        cli.notice(nick, ("This command is rate-limited. Please wait a while "
                          "before using it again."))
        return

    if chan != nick:
        var.LAST_TIME = datetime.now()

    if var.PHASE == "join":
        dur = int((var.CAN_START_TIME - datetime.now()).total_seconds())
        msg = None
        if dur > 1:
            msg = "There are \u0002{0}\u0002 seconds remaining until the game may be started.".format(dur)
        elif dur == 1:
            msg = "There is \u00021\u0002 second remaining until the game may be started."

        if msg is not None:
            if nick == chan:
                pm(cli, nick, msg)
            else:
                cli.msg(chan, msg)

    if var.PHASE in var.TIMERS:
        remaining = timeleft_internal(var.PHASE)
        if var.PHASE == "day":
            what = "sunset"
        elif var.PHASE == "night":
            what = "sunrise"
        elif var.PHASE == "join":
            what = "the game is canceled if it's not started"
        msg = "There is \u0002{0[0]:0>2}:{0[1]:0>2}\u0002 remaining until {1}.".format(divmod(remaining, 60), what)
    else:
        msg = "{0} timers are currently disabled.".format(var.PHASE.capitalize())

    if nick == chan:
        pm(cli, nick, msg)
    elif nick not in var.list_players() and var.PHASE not in ("none", "join"):
        cli.notice(nick, msg)
    else:
        cli.msg(chan, msg)

def timeleft_internal(phase):
    return int((var.TIMERS[phase][1] + var.TIMERS[phase][2]) - time.time()) if phase in var.TIMERS else -1

@cmd("roles", pm=True)
def listroles(cli, nick, chan, rest):
    """Displays which roles are enabled at a certain number of players."""

    old = defaultdict(int)
    msg = []
    index = 0
    lpl = len(var.list_players()) + len(var.DEAD)
    roleindex = var.ROLE_INDEX
    roleguide = var.ROLE_GUIDE

    rest = re.split(" +", rest.strip(), 1)

    #message if this game mode has been disabled
    if (not rest[0] or rest[0].isdigit()) and not hasattr(var.CURRENT_GAMEMODE, "ROLE_GUIDE"):
        msg.append("{0}: There {1} \u0002{2}\u0002 playing. {3}roles is disabled for the {4} game mode.".format(nick,
                   "is" if lpl == 1 else "are", lpl, botconfig.CMD_CHAR, var.CURRENT_GAMEMODE.name))
        rest = []
        roleindex = {}
    #prepend player count if called without any arguments
    elif not rest[0] and lpl > 0:
        msg.append("{0}: There {1} \u0002{2}\u0002 playing.".format(nick, "is" if lpl == 1 else "are", lpl))
        if var.PHASE in ["night", "day"]:
            msg.append("Using the {0} game mode.".format(var.CURRENT_GAMEMODE.name))
            rest = [str(lpl)]

    #read game mode to get roles for
    elif rest[0] and not rest[0].isdigit():
        gamemode = rest[0]
        if gamemode not in var.GAME_MODES.keys():
            gamemode, _ = complete_match(rest[0], var.GAME_MODES.keys() - ["roles"])
        if gamemode in var.GAME_MODES.keys() and gamemode != "roles" and hasattr(var.GAME_MODES[gamemode][0](), "ROLE_GUIDE"):
            mode = var.GAME_MODES[gamemode][0]()
            if hasattr(mode, "ROLE_INDEX") and hasattr(mode, "ROLE_GUIDE"):
                roleindex = mode.ROLE_INDEX
                roleguide = mode.ROLE_GUIDE
            elif gamemode == "default" and "ROLE_INDEX" in var.ORIGINAL_SETTINGS and "ROLE_GUIDE" in var.ORIGINAL_SETTINGS:
                roleindex = var.ORIGINAL_SETTINGS["ROLE_INDEX"]
                roleguide = var.ORIGINAL_SETTINGS["ROLE_GUIDE"]
            rest.pop(0)
        else:
            if gamemode in var.GAME_MODES and gamemode != "roles" and not hasattr(var.GAME_MODES[gamemode][0](), "ROLE_GUIDE"):
                msg.append("{0}: {1}roles is disabled for the {2} game mode.".format(nick, botconfig.CMD_CHAR, gamemode))
            else:
                msg.append("{0}: {1} is not a valid game mode.".format(nick, rest[0]))
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
    roleguide = [(role, roleguide[role]) for role in var.role_order()]
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

    msg = " ".join(msg)

    if chan == nick:
        pm(cli, nick, msg)
    elif nick not in var.list_players() and var.PHASE not in ("none", "join"):
        cli.notice(nick, msg)
    else:
        cli.msg(chan, msg)

@cmd("myrole", pm=True, phases=("day", "night"))
def myrole(cli, nick, chan, rest):
    """Reminds you of your current role."""

    #special case vengeful ghost (that hasn't been driven away)
    if nick in var.VENGEFUL_GHOSTS.keys() and var.VENGEFUL_GHOSTS[nick][0] != "!":
        pm(cli, nick, "You are a \u0002vengeful ghost\u0002 who is against the \u0002{0}\u0002.".format(var.VENGEFUL_GHOSTS[nick]))
        return

    ps = var.list_players()
    if nick not in ps:
        cli.notice(nick, "You're not currently playing.")
        return

    role = var.get_role(nick)
    if role == "time lord":
        role = "villager"
    elif role in ("amnesiac", "vengeful ghost"):
        role = var.DEFAULT_ROLE
    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
    pm(cli, nick, "You are a{0} \u0002{1}\u0002.".format(an, role))

    # Remind shamans what totem they have
    if role in var.TOTEM_ORDER and role != "crazed shaman" and var.PHASE == "night" and nick not in var.SHAMANS:
        pm(cli, nick, "You have the \u0002{0}\u0002 totem.".format(var.TOTEMS[nick]))

    # Remind clone who they have cloned
    if role == "clone" and nick in var.CLONED:
        pm(cli, nick, "You are cloning \u0002{0}\u0002.".format(var.CLONED[nick]))

    # Give minion the wolf list they would have recieved night one
    if role == "minion":
        wolves = []
        for wolfrole in var.WOLF_ROLES:
            for player in var.ORIGINAL_ROLES[wolfrole]:
                wolves.append(player)
        pm(cli, nick, "Original wolves: " + ", ".join(wolves))

    # Remind turncoats of their side
    if role == "turncoat":
        pm(cli, nick, "Current side: \u0002{0}\u0002.".format(var.TURNCOATS.get(nick, "none")))

    # Check for gun/bullets
    if nick not in var.ROLES["amnesiac"] and nick in var.GUNNERS and var.GUNNERS[nick]:
        role = "gunner"
        if nick in var.ROLES["sharpshooter"]:
            role = "sharpshooter"
        if var.GUNNERS[nick] == 1:
            pm(cli, nick, "You are a {0} and have a \u0002gun\u0002 with {1} {2}.".format(role, var.GUNNERS[nick], "bullet"))
        else:
            pm(cli, nick, "You are a {0} and have a \u0002gun\u0002 with {1} {2}.".format(role, var.GUNNERS[nick], "bullets"))
    elif nick in var.WOLF_GUNNERS and var.WOLF_GUNNERS[nick]:
        if var.WOLF_GUNNERS[nick] == 1:
            pm(cli, nick, "You have a \u0002gun\u0002 with {0} {1}.".format(var.WOLF_GUNNERS[nick], "bullet"))
        else:
            pm(cli, nick, "You have a \u0002gun\u0002 with {0} {1}.".format(var.WOLF_GUNNERS[nick], "bullets"))

    # Check assassin
    if nick in var.ROLES["assassin"] and nick not in var.ROLES["amnesiac"]:
        pm(cli, nick, "You are an \u0002assassin\u0002{0}.".format(" and targeting {0}".format(var.TARGETED[nick]) if nick in var.TARGETED else ""))

    # Remind player if they were bitten by alpha wolf
    if nick in var.BITTEN and role not in var.WOLF_ROLES:
        pm(cli, nick, "You were bitten by an alpha wolf and have \u0002{0} night{1}\u0002 until your transformation.".format(max(var.BITTEN[nick], 0), "" if var.BITTEN[nick] == 1 else "s"))

    # Remind lovers of each other
    if nick in ps and nick in var.LOVERS:
        message = "You are \u0002in love\u0002 with "
        lovers = sorted(list(set(var.LOVERS[nick])))
        if len(lovers) == 1:
            message += lovers[0]
        elif len(lovers) == 2:
            message += lovers[0] + " and " + lovers[1]
        else:
            message += ", ".join(lovers[:-1]) + ", and " + lovers[-1]
        message += "."
        pm(cli, nick, message)

@cmd("faftergame", admin_only=True, raw_nick=True, pm=True)
def aftergame(cli, rawnick, chan, rest):
    """Schedule a command to be run after the current game."""
    nick = parse_nick(rawnick)[0]
    if not rest.strip():
        cli.notice(nick, "Incorrect syntax for this command.")
        return

    rst = re.split(" +", rest)
    cmd = rst.pop(0).lower().replace(botconfig.CMD_CHAR, "", 1).strip()

    if cmd in COMMANDS.keys():
        def do_action():
            for fn in COMMANDS[cmd]:
                fn.aftergame = True
                fn.caller(cli, rawnick, botconfig.CHANNEL if fn.chan else nick, " ".join(rst))
                fn.aftergame = False
    else:
        cli.notice(nick, "That command was not found.")
        return

    if var.PHASE == "none":
        do_action()
        return

    fullcmd = cmd
    if rst:
        fullcmd += " "
        fullcmd += " ".join(rst)

    cli.msg(botconfig.CHANNEL, ("The command \u0002{0}\u0002 has been scheduled to run "+
                  "after this game by \u0002{1}\u0002.").format(fullcmd, nick))
    var.AFTER_FLASTGAME = do_action


@cmd("flastgame", admin_only=True, raw_nick=True, pm=True)
def flastgame(cli, rawnick, chan, rest):
    """Disables starting or joining a game, and optionally schedules a command to run after the current game ends."""
    nick, _, ident, host = parse_nick(rawnick)

    chan = botconfig.CHANNEL
    if var.PHASE != "join":
        for decor in (COMMANDS.get("join", []) + COMMANDS.get("start", [])):
            decor(lambda *spam: cli.msg(chan, "This command has been disabled by an admin."))

    cli.msg(chan, "Creating a new game has now been disabled by \u0002{0}\u0002.".format(nick))
    var.ADMIN_TO_PING = nick

    if rest.strip():
        aftergame.func(cli, rawnick, botconfig.CHANNEL, rest)

@cmd("gamestats", "gstats", pm=True)
def game_stats(cli, nick, chan, rest):
    """Gets the game stats for a given game size or lists game totals for all game sizes if no game size is given."""
    if (chan != nick and var.LAST_GSTATS and var.GSTATS_RATE_LIMIT and
            var.LAST_GSTATS + timedelta(seconds=var.GSTATS_RATE_LIMIT) >
            datetime.now()):
        cli.notice(nick, ("This command is rate-limited. Please wait a while "
                          "before using it again."))
        return

    if chan != nick:
        var.LAST_GSTATS = datetime.now()
        if var.PHASE not in ("none", "join"):
            cli.notice(nick, "Wait until the game is over to view stats.")
            return

    gamemode = var.CURRENT_GAMEMODE.name
    gamesize = None
    rest = rest.split()
    # Check for gamemode
    if len(rest) and not rest[0].isdigit():
        gamemode = rest[0]
        if gamemode not in var.GAME_MODES.keys():
            gamemode, _ = complete_match(gamemode, var.GAME_MODES.keys())
        if not gamemode:
            cli.notice(nick, "{0} is not a valid game mode".format(rest[0]))
            return
        rest.pop(0)
    # Check for invalid input
    if len(rest) and rest[0].isdigit():
        gamesize = int(rest[0])
        if gamesize > var.GAME_MODES[gamemode][2] or gamesize < var.GAME_MODES[gamemode][1]:
            cli.notice(nick, "Please enter an integer between "+\
                              "{0} and {1}.".format(var.GAME_MODES[gamemode][1], var.GAME_MODES[gamemode][2]))
            return

    # List all games sizes and totals if no size is given
    if not gamesize:
        if chan == nick:
            pm(cli, nick, var.get_game_totals(gamemode))
        else:
            cli.msg(chan, var.get_game_totals(gamemode))
    else:
        # Attempt to find game stats for the given game size
        if chan == nick:
            pm(cli, nick, var.get_game_stats(gamemode, gamesize))
        else:
            cli.msg(chan, var.get_game_stats(gamemode, gamesize))

@cmd("playerstats", "pstats", "player", "p", pm=True)
def player_stats(cli, nick, chan, rest):
    """Gets the stats for the given player and role or a list of role totals if no role is given."""
    if (chan != nick and var.LAST_PSTATS and var.PSTATS_RATE_LIMIT and
            var.LAST_PSTATS + timedelta(seconds=var.PSTATS_RATE_LIMIT) >
            datetime.now()):
        cli.notice(nick, ("This command is rate-limited. Please wait a while "
                          "before using it again."))
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
    if luser in lusers and not var.DISABLE_ACCOUNTS:
        acc = lusers[luser]["account"]
        if acc == "*":
            if luser == nick.lower():
                cli.notice(nick, "You are not logged in to NickServ.")
            else:
                cli.notice(nick, user + " is not logged in to NickServ.")

            return
    else:
        acc = user

    # List the player's total games for all roles if no role is given
    if len(params) < 2:
        message = var.get_player_totals(acc)
        if chan == nick:
            pm(cli, nick, message)
        else:
            cli.notice(nick, message)
    else:
        role = " ".join(params[1:])
        # Attempt to find the player's stats
        message = var.get_player_stats(acc, role)

        if chan == nick:
            pm(cli, nick, message)
        elif var.PHASE not in ("none", "join"):
            cli.notice(nick, message)
        else:
            cli.msg(chan, message)

@cmd("mystats", "m", pm=True)
def my_stats(cli, nick, chan, rest):
    """Get your own stats."""
    rest = rest.split()
    player_stats.func(cli, nick, chan, " ".join([nick] + rest))

@cmd("game", playing=True, phases=("join",))
def game(cli, nick, chan, rest):
    """Vote for a game mode to be picked."""
    if rest:
        gamemode = rest.lower().split()[0]
    else:
        gamemodes = ", ".join("\u0002{0}\u0002".format(gamemode) if len(var.list_players()) in range(var.GAME_MODES[gamemode][1],
        var.GAME_MODES[gamemode][2]+1) else gamemode for gamemode in var.GAME_MODES.keys() if gamemode != "roles")
        cli.notice(nick, "No game mode specified. Available game modes: " + gamemodes)
        return

    if var.FGAMED:
        cli.notice(nick, "A game mode has already been forced by an admin.")
        return

    if gamemode not in var.GAME_MODES.keys():
        match, _ = complete_match(gamemode, var.GAME_MODES.keys() - ["roles"])
        if not match:
            cli.notice(nick, "\u0002{0}\u0002 is not a valid game mode.".format(gamemode))
            return
        gamemode = match

    if gamemode != "roles":
        if var.GAMEMODE_VOTES.get(nick) != gamemode:
            var.GAMEMODE_VOTES[nick] = gamemode
            cli.msg(chan, "\u0002{0}\u0002 votes for the \u0002{1}\u0002 game mode.".format(nick, gamemode))
    else:
        cli.notice(nick, "You can't vote for that game mode.")

@cmd("games", "modes", pm=True)
def show_modes(cli, nick, chan, rest):
    """Show the available game modes."""
    msg = "Available game modes: \u0002"
    modes = "\u0002, \u0002".join(sorted(var.GAME_MODES.keys() - {"roles"}))

    if chan == nick:
        pm(cli, nick, msg + modes + "\u0002")
    else:
        cli.notice(nick, msg + modes + "\u0002")

def game_help(args=""):
    return "Votes to make a specific game mode more likely. Available game mode setters: " +\
        ", ".join("\u0002{0}\u0002".format(gamemode) if len(var.list_players()) in range(var.GAME_MODES[gamemode][1], var.GAME_MODES[gamemode][2]+1)
        else gamemode for gamemode in var.GAME_MODES.keys() if gamemode != "roles")
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

@cmd("fpull", admin_only=True, pm=True)
def fpull(cli, nick, chan, rest):
    """Pulls from the repository to update the bot."""

    commands = ["git fetch",
                "git rebase --stat --preserve-merges"]

    for command in commands:
        child = subprocess.Popen(command.split(),
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        (out, err) = child.communicate()
        ret = child.returncode

        for line in (out + err).splitlines():
            if chan == nick:
                cli.msg(nick, line.decode("utf-8"))
            else:
                pm(cli, nick, line.decode("utf-8"))

        if ret != 0:
            if ret < 0:
                cause = "signal"
                ret *= -1
            else:
                cause = "status"

            if chan == nick:
                cli.msg(nick, "Process %s exited with %s %d" % (command, cause, ret))
            else:
                pm(cli, nick, "Process %s exited with %s %d" % (command, cause, ret))

@cmd("fsend", admin_only=True, pm=True)
def fsend(cli, nick, chan, rest):
    """Forcibly send raw IRC commands to the server."""
    cli.send(rest)

def _say(cli, raw_nick, rest, command, action=False):
    (nick, _, ident, host) = parse_nick(raw_nick)
    rest = rest.split(" ", 1)

    if len(rest) < 2:
        pm(cli, nick, "Usage: {0}{1} <target> <message>".format(
            botconfig.CMD_CHAR, command))

        return

    (target, message) = rest

    if not is_admin(nick, ident, host):
        if nick not in var.USERS:
            pm(cli, nick, "You have to be in {0} to use this command.".format(
                botconfig.CHANNEL))

            return

        if rest[0] != botconfig.CHANNEL:
            pm(cli, nick, ("You do not have permission to message this user "
                           "or channel."))

            return

    if action:
        message = "\u0001ACTION {0}\u0001".format(message)

    cli.send("PRIVMSG {0} :{1}".format(target, message))


@cmd("fsay", admin_only=True, raw_nick=True, pm=True)
def fsay(cli, raw_nick, chan, rest):
    """Talk through the bot as a normal message."""
    _say(cli, raw_nick, rest, "fsay")

@cmd("fact", "fdo", "fme", admin_only=True, raw_nick=True, pm=True)
def fact(cli, raw_nick, chan, rest):
    """Act through the bot as an action."""
    _say(cli, raw_nick, rest, "fact", action=True)

before_debug_mode_commands = list(COMMANDS.keys())

if botconfig.DEBUG_MODE or botconfig.ALLOWED_NORMAL_MODE_COMMANDS:

    @cmd("eval", owner_only=True, pm=True)
    def pyeval(cli, nick, chan, rest):
        """Evaluate a Python expression."""
        try:
            a = str(eval(rest))
            if len(a) < 500:
                cli.msg(chan, a)
            else:
                cli.msg(chan, a[:500])
        except Exception as e:
            cli.msg(chan, str(type(e))+":"+str(e))

    @cmd("exec", owner_only=True, pm=True)
    def py(cli, nick, chan, rest):
        """Execute arbitrary Python code."""
        try:
            exec(rest)
        except Exception as e:
            cli.msg(chan, str(type(e))+":"+str(e))

    @cmd("revealroles", admin_only=True, pm=True, phases=("day", "night"))
    def revealroles(cli, nick, chan, rest):
        """Reveal role information."""
        def is_authorized():
            # if allowed in normal games, restrict it so that it can only be used by dead players and
            # non-players (don't allow active vengeful ghosts either).
            # also don't allow in-channel (e.g. make it pm only)

            if botconfig.DEBUG_MODE:
                return True

            pl = var.list_players() + [vg for (vg, against) in var.VENGEFUL_GHOSTS.items() if not against.startswith("!")]

            if nick in pl:
                return False

            if nick in var.USERS and var.USERS[nick]["account"] in [var.USERS[player]["account"] for player in pl if player in var.USERS]:
                return False

            hostmask = var.USERS[nick]["ident"] + "@" + var.USERS[nick]["host"]
            if nick in var.USERS and hostmask in [var.USERS[player]["ident"] + "@" + var.USERS[player]["host"] for player in pl if player in var.USERS]:
                return False

            return True

        if not is_authorized():
            if chan == nick:
                pm(cli, nick, "You are not allowed to use that command right now.")
            else:
                cli.notice(nick, "You are not allowed to use that command right now.")
            return

        output = []
        for role in var.role_order():
            if var.ROLES.get(role):
                # make a copy since this list is modified
                nicks = list(var.ROLES[role])
                # go through each nickname, adding extra info if necessary
                for i in range(len(nicks)):
                    special_case = []
                    nickname = nicks[i]
                    if role == "assassin" and nickname in var.TARGETED:
                        special_case.append("targeting {0}".format(var.TARGETED[nickname]))
                    elif role in var.TOTEM_ORDER and nickname in var.TOTEMS:
                        if nickname in var.SHAMANS:
                            special_case.append("giving {0} totem to {1}".format(var.TOTEMS[nickname], var.SHAMANS[nickname][0]))
                        elif var.PHASE == "night":
                            special_case.append("has {0} totem".format(var.TOTEMS[nickname]))
                        elif nickname in var.LASTGIVEN:
                            special_case.append("gave {0} totem to {1}".format(var.TOTEMS[nickname], var.LASTGIVEN[nickname]))
                    elif role == "clone" and nickname in var.CLONED:
                        special_case.append("cloning {0}".format(var.CLONED[nickname]))
                    elif role == "amnesiac" and nickname in var.AMNESIAC_ROLES:
                        special_case.append("will become {0}".format(var.AMNESIAC_ROLES[nickname]))
                    # print how many bullets normal gunners have
                    elif (role == "gunner" or role == "sharpshooter") and nickname in var.GUNNERS:
                        special_case.append("{0} bullet{1}".format(var.GUNNERS[nickname], "" if var.GUNNERS[nickname] == 1 else "s"))
                    elif role == "turncoat" and nickname in var.TURNCOATS:
                        special_case.append("currently with \u0002{0}\u0002".format(var.TURNCOATS[nickname][0])
                                            if var.TURNCOATS[nickname][0] != "none" else "not currently on any side")
                    # print out how many bullets wolf gunners have
                    if nickname in var.WOLF_GUNNERS and role not in var.TEMPLATE_RESTRICTIONS:
                        special_case.append("wolf gunner with {0} bullet{1}".format(var.WOLF_GUNNERS[nickname], "" if var.WOLF_GUNNERS[nickname] == 1 else "s"))
                    if nickname not in var.ORIGINAL_ROLES[role] and role not in var.TEMPLATE_RESTRICTIONS:
                        for old_role in var.role_order(): # order doesn't matter here, but oh well
                            if nickname in var.ORIGINAL_ROLES[old_role] and nickname not in var.ROLES[old_role]:
                                special_case.append("was {0}".format(old_role))
                                break
                    if special_case:
                        nicks[i] = "".join((nicks[i], " (", ", ".join(special_case), ")"))
                output.append("\u0002{0}\u0002: {1}".format(role, ", ".join(nicks)))

        # print out lovers too
        done = {}
        lovers = []
        for lover1, llist in var.LOVERS.items():
            for lover2 in llist:
                # check if already said the pairing
                if (lover1 in done and lover2 in done[lover1]) or (lover2 in done and lover1 in done[lover2]):
                    continue
                lovers.append("{0}/{1}".format(lover1, lover2))
                if lover1 in done:
                    done[lover1].append(lover2)
                else:
                    done[lover1] = [lover2]
        if len(lovers) == 1 or len(lovers) == 2:
            output.append("\u0002lovers\u0002: {0}".format(" and ".join(lovers)))
        elif len(lovers) > 2:
            output.append("\u0002lovers\u0002: {0}, and {1}".format(", ".join(lovers[0:-1]), lovers[-1]))

        # print out vengeful ghosts, also vengeful ghosts that were driven away by 'retribution' totem
        if var.VENGEFUL_GHOSTS:
            output.append("\u0002dead vengeful ghost\u0002: {0}".format(", ".join("{0} ({1}against {2})".format(
                   ghost, team.startswith("!") and "driven away, " or "", team.lstrip("!"))
                   for (ghost, team) in var.VENGEFUL_GHOSTS.items())))

        #show bitten users + days until turning
        if var.BITTEN and next((days for (nickname,days) in var.BITTEN.items() if days > 0 or var.get_role(nickname) not in var.WOLF_ROLES), None) is not None:
            output.append("\u0002bitten\u0002: {0}".format(", ".join("{0} ({1} night{2} until transformation)".format(
                nickname, max(days, 0), "" if days == 1 else "s") for (nickname,days) in var.BITTEN.items() if days > 0 or var.get_role(nickname) not in var.WOLF_ROLES)))

        #show who got immunized
        if var.IMMUNIZED:
            output.append("\u0002immunized\u0002: {0}".format(", ".join(var.IMMUNIZED)))

        # get charmed players
        if var.CHARMED | var.TOBECHARMED:
            output.append("\u0002charmed players\u0002: {0}".format(", ".join(var.CHARMED | var.TOBECHARMED)))

        if chan == nick:
            pm(cli, nick, var.break_long_message(output, " | "))
        else:
            if botconfig.DEBUG_MODE:
                cli.msg(chan, var.break_long_message(output, " | "))
            else:
                cli.notice(nick, var.break_long_message(output, " | "))


    @cmd("fgame", admin_only=True, raw_nick=True, phases=("join",))
    def fgame(cli, nick, chan, rest):
        """Force a certain game mode to be picked. Disable voting for game modes upon use."""
        nick = parse_nick(nick)[0]

        pl = var.list_players()

        if nick not in pl and not is_admin(nick):
            cli.notice(nick, "You're not currently playing.")
            return

        if rest:
            gamemode = rest.strip().lower()
            parts = gamemode.replace("=", " ", 1).split(None, 1)
            if len(parts) > 1:
                gamemode, modeargs = parts
            else:
                gamemode = parts[0]
                modeargs = None

            if gamemode not in var.GAME_MODES.keys():
                gamemode = gamemode.split()[0]
                gamemode, _ = complete_match(gamemode, var.GAME_MODES.keys())
                if not gamemode:
                    cli.notice(nick, "\u0002{0}\u0002 is not a valid game mode.".format(rest))
                    return
                parts[0] = gamemode

            if cgamemode(cli, "=".join(parts)):
                cli.msg(chan, ("\u0002{0}\u0002 has changed the game settings "
                               "successfully.").format(nick))
                var.FGAMED = True
        else:
            cli.notice(nick, fgame.__doc__())

    def fgame_help(args=""):
        args = args.strip()

        if not args:
            return "Available game mode setters: " + ", ".join(var.GAME_MODES.keys())
        elif args in var.GAME_MODES.keys():
            return var.GAME_MODES[args][0].__doc__ or "Game mode {0} has no doc string".format(args)
        else:
            return "Game mode setter \u0002{0}\u0002 not found.".format(args)


    fgame.__doc__ = fgame_help


    # DO NOT MAKE THIS A PMCOMMAND ALSO
    @cmd("force", admin_only=True)
    def force(cli, nick, chan, rest):
        """Force a certain player to use a specific command."""
        rst = re.split(" +",rest)
        if len(rst) < 2:
            cli.msg(chan, "The syntax is incorrect.")
            return
        who = rst.pop(0).strip()
        if not who or who == botconfig.NICK:
            cli.msg(chan, "That won't work.")
            return
        if who == "*":
            who = var.list_players()
        else:
            if not is_fake_nick(who):
                ul = list(var.USERS.keys())
                ull = [u.lower() for u in ul]
                if who.lower() not in ull:
                    cli.msg(chan, "This can only be done on players in the channel or fake nicks.")
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
                if fn.admin_only and nick in var.USERS and not is_admin(nick):
                    # Not a full admin
                    cli.notice(nick, "Only full admins can force an admin-only command.")
                    continue
                for user in who:
                    if fn.chan:
                        fn.caller(cli, user, chan, " ".join(rst))
                    else:
                        fn.caller(cli, user, user, " ".join(rst))
            cli.msg(chan, "Operation successful.")
        else:
            cli.msg(chan, "That command was not found.")


    @cmd("rforce", admin_only=True)
    def rforce(cli, nick, chan, rest):
        """Force all players of a given role to perform a certain action."""
        rst = re.split(" +",rest)
        if len(rst) < 2:
            cli.msg(chan, "The syntax is incorrect.")
            return
        who = rst.pop(0).strip().lower()
        who = who.replace("_", " ")

        if who == "*": # wildcard match
            tgt = var.list_players()
        elif (who not in var.ROLES or not var.ROLES[who]) and (who != "gunner"
            or var.PHASE in ("none", "join")):
            cli.msg(chan, nick+": invalid role")
            return
        elif who == "gunner":
            tgt = list(var.GUNNERS.keys())
        else:
            tgt = var.ROLES[who].copy()

        comm = rst.pop(0).lower().replace(botconfig.CMD_CHAR, "", 1)
        if comm in COMMANDS and not COMMANDS[comm][0].owner_only:
            for fn in COMMANDS[comm]:
                if fn.owner_only:
                    continue
                if fn.admin_only and nick in var.USERS and not is_admin(nick):
                    # Not a full admin
                    cli.notice(nick, "Only full admins can force an admin-only command.")
                    continue
                for user in tgt:
                    if fn.chan:
                        fn.caller(cli, user, chan, " ".join(rst))
                    else:
                        fn.caller(cli, user, user, " ".join(rst))
            cli.msg(chan, "Operation successful.")
        else:
            cli.msg(chan, "That command was not found.")



    @cmd("frole", admin_only=True)
    def frole(cli, nick, chan, rest):
        """Change the role or template of a player."""
        rst = re.split(" +",rest)
        if len(rst) < 2:
            cli.msg(chan, "The syntax is incorrect.")
            return
        who = rst.pop(0).strip()
        rol = " ".join(rst).strip()
        ul = list(var.USERS.keys())
        ull = [u.lower() for u in ul]
        if who.lower() not in ull:
            if not is_fake_nick(who):
                cli.msg(chan, "Could not be done.")
                cli.msg(chan, "The target needs to be in this channel or a fake name.")
                return
        if not is_fake_nick(who):
            who = ul[ull.index(who.lower())]
        if who == botconfig.NICK or not who:
            cli.msg(chan, "No.")
            return
        pl = var.list_players()
        rolargs = re.split("\s*=\s*", rol, 1)
        rol = rolargs[0]
        if rol[1:] in var.TEMPLATE_RESTRICTIONS.keys():
            addrem = rol[0]
            rol = rol[1:]
            is_gunner = (rol == "gunner" or rol == "sharpshooter")
            if addrem == "+" and who not in var.ROLES[rol]:
                if is_gunner:
                    if len(rolargs) == 2 and rolargs[1].isdigit():
                        if len(rolargs[1]) < 7:
                            var.GUNNERS[who] = int(rolargs[1])
                            var.WOLF_GUNNERS[who] = int(rolargs[1])
                        else:
                            var.GUNNERS[who] = 999
                            var.WOLF_GUNNERS[who] = 999
                    elif rol == "gunner":
                        var.GUNNERS[who] = math.ceil(var.SHOTS_MULTIPLIER * len(pl))
                    else:
                        var.GUNNERS[who] = math.ceil(var.SHARPSHOOTER_MULTIPLIER * len(pl))
                if who not in pl:
                    var.ROLES[var.DEFAULT_ROLE].add(who)
                    var.ALL_PLAYERS.append(who)
                    if not is_fake_nick(who):
                        cli.mode(chan, "+v", who)
                    cli.msg(chan, "Added default role ({0}) because only a template was specified for a new player.".format(var.DEFAULT_ROLE))

                var.ROLES[rol].add(who)
            elif addrem == "-" and who in var.ROLES[rol]:
                var.ROLES[rol].remove(who)
                if is_gunner and who in var.GUNNERS:
                    del var.GUNNERS[who]
            else:
                cli.msg(chan, "Improper template modification.")
                return
        elif rol in var.TEMPLATE_RESTRICTIONS.keys():
            cli.msg(chan, "Please specify \u0002+{0}\u0002 or \u0002-{0}\u0002 to add/remove this template.".format(rol))
            return
        elif rol in var.ROLES.keys():
            if who in pl:
                oldrole = var.get_role(who)
                var.ROLES[oldrole].remove(who)
            else:
                var.ALL_PLAYERS.append(who)
            if rol in var.TOTEM_ORDER:
                if len(rolargs) == 2:
                    var.TOTEMS[who] = rolargs[1]
                else:
                    max_totems = defaultdict(int)
                    for ix in range(len(var.TOTEM_ORDER)):
                        for c in var.TOTEM_CHANCES.values():
                            max_totems[var.TOTEM_ORDER[ix]] += c[ix]
                    for shaman in var.list_players(var.TOTEM_ORDER):
                        indx = var.TOTEM_ORDER.index(rol)
                        target = 0
                        rand = random.random() * max_totems[var.TOTEM_ORDER[indx]]
                        for t in var.TOTEM_CHANCES.keys():
                            target += var.TOTEM_CHANCES[t][indx]
                            if rand <= target:
                                var.TOTEMS[shaman] = t
                                break
            var.ROLES[rol].add(who)
            if not is_fake_nick(who):
                cli.mode(chan, "+v", who)
        else:
            cli.msg(chan, "Not a valid role.")
            return
        cli.msg(chan, "Operation successful.")
        if var.PHASE not in ("none", "join"):
            # default stats determination does not work if we're mucking with !frole
            if var.STATS_TYPE == "default":
                var.ORIGINAL_SETTINGS["STATS_TYPE"] = var.STATS_TYPE
                var.STATS_TYPE = "accurate"
                cli.msg(chan, "!stats type changed to accurate due to use of !frole.")
            chk_win(cli)


if botconfig.ALLOWED_NORMAL_MODE_COMMANDS and not botconfig.DEBUG_MODE:
    for comd in list(COMMANDS.keys()):
        if (comd not in before_debug_mode_commands and
            comd not in botconfig.ALLOWED_NORMAL_MODE_COMMANDS):
            del COMMANDS[comd]

# vim: set expandtab:sw=4:ts=4:
