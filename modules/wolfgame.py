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

from oyoyo.parse import parse_nick
import settings.wolfgame as var
import botconfig
from tools.wolfgamelogger import WolfgameLogger
from tools import decorators
from datetime import datetime, timedelta
import threading
import copy
import time
import re
import sys
import os
import imp
import math
import fnmatch
import random
import subprocess
from imp import reload

BOLD = "\u0002"

COMMANDS = {}
PM_COMMANDS = {}
HOOKS = {}

cmd = decorators.generate(COMMANDS)
pmcmd = decorators.generate(PM_COMMANDS)
hook = decorators.generate(HOOKS, raw_nick=True, permissions=False)

# Game Logic Begins:

var.LAST_PING = None  # time of last ping
var.LAST_STATS = None
var.LAST_VOTES = None
var.LAST_ADMINS = None
var.LAST_GSTATS = None
var.LAST_PSTATS = None
var.LAST_TIME = None

var.USERS = {}

var.PINGING = False
var.ADMIN_PINGING = False
var.ROLES = {"person" : []}
var.SPECIAL_ROLES = {}
var.ORIGINAL_ROLES = {}
var.PLAYERS = {}
var.DCED_PLAYERS = {}
var.ADMIN_TO_PING = None
var.AFTER_FLASTGAME = None
var.TIMERS = {}

var.ORIGINAL_SETTINGS = {}

var.LAST_SAID_TIME = {}

var.GAME_START_TIME = datetime.now()  # for idle checker only
var.CAN_START_TIME = 0
var.GRAVEYARD_LOCK = threading.RLock()
var.STARTED_DAY_PLAYERS = 0

var.DISCONNECTED = {}  # players who got disconnected

var.LOGGER = WolfgameLogger(var.LOG_FILENAME, var.BARE_LOG_FILENAME)

var.OPPED = False  # Keeps track of whether the bot is opped

if botconfig.DEBUG_MODE:
    var.NIGHT_TIME_LIMIT = 0 # 120
    var.NIGHT_TIME_WARN = 0 # 90
    var.DAY_TIME_LIMIT = 0 # 720
    var.DAY_TIME_WARN = 0 # 600
    var.SHORT_DAY_LIMIT = 0 # 520
    var.SHORT_DAY_WARN = 0 # 400
    var.KILL_IDLE_TIME = 0 # 300
    var.WARN_IDLE_TIME = 0 # 180
    var.JOIN_TIME_LIMIT = 0
    var.LEAVE_STASIS_PENALTY = 1
    var.IDLE_STASIS_PENALTY = 1
    var.PART_STASIS_PENALTY = 1


def connect_callback(cli):
    to_be_devoiced = []
    cmodes = []

    @hook("quietlist", hookid=294)
    def on_quietlist(cli, server, botnick, channel, q, quieted, by, something):
        if re.match(".+\!\*@\*", quieted):  # only unquiet people quieted by bot
            cmodes.append(("-q", quieted))

    @hook("whospcrpl", hookid=294)
    def on_whoreply(cli, server, nick, ident, cloak, user, status, acc):
        if user in var.USERS: return  # Don't add someone who is already there
        if user == botconfig.NICK:
            cli.nickname = user
            cli.ident = ident
            cli.hostmask = cloak
        if acc == "0":
            acc = "*"
        if "+" in status:
            to_be_devoiced.append(user)
        var.USERS[user] = dict(cloak=cloak,account=acc)

    @hook("endofwho", hookid=294)
    def afterwho(*args):
        for nick in to_be_devoiced:
            cmodes.append(("-v", nick))
        # devoice all on connect

    @hook("mode", hookid=294)
    def on_give_me_ops(cli, blah, blahh, modeaction, target="", *other):
        if modeaction == "+o" and target == botconfig.NICK:
            var.OPPED = True

            if var.PHASE == "none":
                @hook("quietlistend", 294)
                def on_quietlist_end(cli, svr, nick, chan, *etc):
                    if chan == botconfig.CHANNEL:
                        mass_mode(cli, cmodes)

                cli.mode(botconfig.CHANNEL, "q")  # unquiet all
                cli.mode(botconfig.CHANNEL, "-m")  # remove -m mode from channel
        elif modeaction == "-o" and target == botconfig.NICK:
            var.OPPED = False
            cli.msg("ChanServ", "op " + botconfig.CHANNEL)


    cli.who(botconfig.CHANNEL, "%nuhaf")


def mass_mode(cli, md):
    """ Example: mass_mode(cli, (('+v', 'asdf'), ('-v','wobosd'))) """
    lmd = len(md)  # store how many mode changes to do
    for start_i in range(0, lmd, 4):  # 4 mode-changes at a time
        if start_i + 4 > lmd:  # If this is a remainder (mode-changes < 4)
            z = list(zip(*md[start_i:]))  # zip this remainder
            ei = lmd % 4  # len(z)
        else:
            z = list(zip(*md[start_i:start_i+4])) # zip four
            ei = 4 # len(z)
        # Now z equal something like [('+v', '-v'), ('asdf', 'wobosd')]
        arg1 = "".join(z[0])
        arg2 = " ".join(z[1])  # + " " + " ".join([x+"!*@*" for x in z[1]])
        cli.mode(botconfig.CHANNEL, arg1, arg2)

def pm(cli, target, message):  # message either privmsg or notice, depending on user settings
    if is_fake_nick(target) and botconfig.DEBUG_MODE:
        print("[{0}] Would send message to fake nick {1}: {2}".format(
            time.strftime("%d/%b/%Y %H:%M:%S"),
            target,
            message), file=sys.stderr)

        return

    if target in var.USERS and var.USERS[target]["cloak"] in var.PREFER_NOTICE:
        cli.notice(target, message)
    else:
        cli.msg(target, message)

def reset_settings():
    for attr in list(var.ORIGINAL_SETTINGS.keys()):
        setattr(var, attr, var.ORIGINAL_SETTINGS[attr])
    dict.clear(var.ORIGINAL_SETTINGS)

def reset_modes_timers(cli):
    # Reset game timers
    for x, timr in var.TIMERS.items():
        timr[0].cancel()
    var.TIMERS = {}

    # Reset modes
    cli.mode(botconfig.CHANNEL, "-m")
    cmodes = []
    for plr in var.list_players():
        cmodes.append(("-v", plr))
    if var.QUIET_DEAD_PLAYERS:
        for deadguy in var.DEAD:
            if not is_fake_nick(deadguy):
                cmodes.append(("-q", deadguy+"!*@*"))
    mass_mode(cli, cmodes)

def reset():
    var.PHASE = "none" # "join", "day", or "night"
    var.GAME_ID = 0
    var.DEAD = []
    var.ROLES = {"person" : []}
    var.JOINED_THIS_GAME = [] # keeps track of who already joined this game at least once (cloaks)
    var.NO_LYNCH = []
    var.FGAMED = False
    var.CURRENT_GAMEMODE = "default"
    var.GAMEMODE_VOTES = {} #list of players who have used !game

    reset_settings()

    dict.clear(var.LAST_SAID_TIME)
    dict.clear(var.PLAYERS)
    dict.clear(var.DCED_PLAYERS)
    dict.clear(var.DISCONNECTED)
reset()

def make_stasis(nick, penalty):
    try:
        cloak = var.USERS[nick]['cloak']
        if cloak is not None:
            if penalty == 0:
                del var.STASISED[cloak]
                var.set_stasised(cloak, 0)
            else:
                var.STASISED[cloak] += penalty
                var.set_stasis(cloak, var.STASISED[cloak])
    except KeyError:
        pass

@pmcmd("fdie", "fbye", admin_only=True)
@cmd("fdie", "fbye", admin_only=True)
def forced_exit(cli, nick, *rest):  # Admin Only
    """Forces the bot to close."""

    if var.PHASE in ("day", "night"):
        stop_game(cli)
    else:
        reset_modes_timers(cli)
        reset()

    cli.quit("Forced quit from "+nick)



@pmcmd("frestart", admin_only=True)
@cmd("frestart", admin_only=True)
def restart_program(cli, nick, *rest):
    """Restarts the bot."""
    try:
        if var.PHASE in ("day", "night"):
            stop_game(cli)
        else:
            reset_modes_timers(cli)
            reset()

        cli.quit("Forced restart from "+nick)
        raise SystemExit
    finally:
        print("RESTARTING")
        python = sys.executable
        if rest[-1].strip().lower() == "debugmode":
            os.execl(python, python, sys.argv[0], "--debug")
        elif rest[-1].strip().lower() == "normalmode":
            os.execl(python, python, sys.argv[0])
        elif rest[-1].strip().lower() == "verbosemode":
            os.execl(python, python, sys.argv[0], "--verbose")
        else:
            os.execl(python, python, *sys.argv)



@pmcmd("ping")
def pm_ping(cli, nick, rest):
    pm(cli, nick, 'Pong!')


@cmd("ping")
def pinger(cli, nick, chan, rest):
    """Pings the channel to get people's attention. Rate-limited."""

    if var.PHASE in ('night','day'):
        #cli.notice(nick, "You cannot use this command while a game is running.")
        cli.notice(nick, 'Pong!')
        return

    if (var.LAST_PING and
        var.LAST_PING + timedelta(seconds=var.PING_WAIT) > datetime.now()):
        cli.notice(nick, ("This command is rate-limited. " +
                          "Please wait a while before using it again."))
        return

    var.LAST_PING = datetime.now()
    if var.PINGING:
        return
    var.PINGING = True
    TO_PING = []



    @hook("whoreply", hookid=800)
    def on_whoreply(cli, server, dunno, chan, dunno1,
                    cloak, dunno3, user, status, dunno4):
        if not var.PINGING: return
        if user in (botconfig.NICK, nick): return  # Don't ping self.

        if (all((not var.OPT_IN_PING,
                 'G' not in status,  # not /away
                 '+' not in status,  # not already joined (voiced)
                 cloak not in var.STASISED, # not in stasis
                 cloak not in var.AWAY)) or
            all((var.OPT_IN_PING, '+' not in status,
                 cloak in var.PING_IN))):

            TO_PING.append(user)


    @hook("endofwho", hookid=800)
    def do_ping(*args):
        if not var.PINGING: return

        TO_PING.sort(key=lambda x: x.lower())

        cli.msg(botconfig.CHANNEL, "PING! "+" ".join(TO_PING))
        var.PINGING = False

        minimum = datetime.now() + timedelta(seconds=var.PING_MIN_WAIT)
        if not var.CAN_START_TIME or var.CAN_START_TIME < minimum:
           var.CAN_START_TIME = minimum

        decorators.unhook(HOOKS, 800)

    cli.who(botconfig.CHANNEL)


@cmd("simple", raw_nick = True)
@pmcmd("simple", raw_nick = True)
def mark_simple_notify(cli, nick, *rest):
    """Makes the bot give you simple role instructions, in case you are familiar with the roles."""

    nick, _, __, cloak = parse_nick(nick)

    if cloak in var.SIMPLE_NOTIFY:
        var.SIMPLE_NOTIFY.remove(cloak)
        var.remove_simple_rolemsg(cloak)

        cli.notice(nick, "You now no longer receive simple role instructions.")
        return

    var.SIMPLE_NOTIFY.append(cloak)
    var.add_simple_rolemsg(cloak)

    cli.notice(nick, "You now receive simple role instructions.")

@cmd("notice", raw_nick = True)
@pmcmd("notice", raw_nick = True)
def mark_prefer_notice(cli, nick, *rest):
    """Makes the bot NOTICE you for every interaction."""

    nick, _, __, cloak = parse_nick(nick)

    if cloak in var.PREFER_NOTICE:
        var.PREFER_NOTICE.remove(cloak)
        var.remove_prefer_notice(cloak)

        cli.notice(nick, "Gameplay interactions will now use PRIVMSG for you.")
        return

    var.PREFER_NOTICE.append(cloak)
    var.add_prefer_notice(cloak)

    cli.notice(nick, "The bot will now always NOTICE you.")

if not var.OPT_IN_PING:
    @cmd("away", raw_nick=True)
    @pmcmd("away", raw_nick=True)
    def away(cli, nick, *rest):
        """Use this to activate your away status (so you aren't pinged)."""
        nick, _, _, cloak = parse_nick(nick)
        if cloak in var.AWAY:
            prefix = botconfig.CMD_CHAR

            cli.notice(nick, ("You are already marked as away. Use {}back "
                              "to unset your away status.").format(prefix))

            return
        var.AWAY.append(cloak)
        var.add_away(cloak)

        cli.notice(nick, "You are now marked as away.")

    @cmd("back", raw_nick=True)
    @pmcmd("back", raw_nick=True)
    def back_from_away(cli, nick, *rest):
        """Unsets your away status."""
        nick, _, _, cloak = parse_nick(nick)
        if cloak not in var.AWAY:
            cli.notice(nick, "You are not marked as away.")
            return
        var.AWAY.remove(cloak)
        var.remove_away(cloak)

        cli.notice(nick, "You are no longer marked as away.")


else:  # if OPT_IN_PING setting is on
    @cmd("in", raw_nick=True)
    @pmcmd("in", raw_nick=True)
    def get_in(cli, nick, *rest):
        """Puts yourself in the ping list."""
        nick, _, _, cloak = parse_nick(nick)
        if cloak in var.PING_IN:
            cli.notice(nick, "You are already on the list.")
            return
        var.PING_IN.append(cloak)
        var.add_ping(cloak)

        cli.notice(nick, "You are now on the list.")

    @cmd("out", raw_nick=True)
    @pmcmd("out", raw_nick=True)
    def get_out(cli, nick, *rest):
        """Removes yourself from the ping list."""
        nick, _, _, cloak = parse_nick(nick)
        if cloak in var.PING_IN:
            var.PING_IN.remove(cloak)
            var.remove_ping(cloak)

            cli.notice(nick, "You are no longer in the list.")
            return
        cli.notice(nick, "You are not in the list.")


@cmd("fping", admin_only=True)
def fpinger(cli, nick, chan, rest):
    """Pings the channel to get people's attention, ignoring the rate limit."""
    var.LAST_PING = None
    pinger(cli, nick, chan, rest)


@cmd("join", "j")
def join(cli, nick, chann_, rest):
    """Either starts a new game of Werewolf or joins an existing game that has not started yet."""
    join_player(cli, nick)

def join_player(cli, player, who = None, forced = False):
    if who is None:
        who = player

    pl = var.list_players()
    chan = botconfig.CHANNEL

    if not var.OPPED:
        cli.notice(who, "Sorry, I'm not opped in {0}.".format(chan))
        cli.msg("ChanServ", "op " + botconfig.CHANNEL)
        return

    cloak = None
    try:
        cloak = var.USERS[player]['cloak']
        if cloak is not None and cloak in var.STASISED and not forced:
            cli.notice(who, "Sorry, but {0} in stasis for {1} game{2}.".format(
                "you are" if player == who else player + " is", var.STASISED[cloak],
                "s" if var.STASISED[cloak] != 1 else ""))
            return
    except KeyError:
        pass

    if var.PHASE == "none":

        cli.mode(chan, "+v", player)
        var.ROLES["person"].append(player)
        var.PHASE = "join"
        var.WAITED = 0
        var.GAME_ID = time.time()
        var.JOINED_THIS_GAME.append(cloak)
        var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.MINIMUM_WAIT)
        cli.msg(chan, ('\u0002{0}\u0002 has started a game of Werewolf. '+
                      'Type "{1}join" to join. Type "{1}start" to start the game. '+
                      'Type "{1}wait" to increase start wait time.').format(player, botconfig.CMD_CHAR))

        # Set join timer
        if var.JOIN_TIME_LIMIT and not botconfig.DEBUG_MODE:
            t = threading.Timer(var.JOIN_TIME_LIMIT, kill_join, [cli, chan])
            var.TIMERS['join'] = (t, time.time(), var.JOIN_TIME_LIMIT)
            t.daemon = True
            t.start()

    elif player in pl:
        cli.notice(who, "{0}'re already playing!".format("You" if who == player else "They"))
    elif len(pl) >= var.MAX_PLAYERS:
        cli.notice(who, "Too many players! Try again next time.")
    elif var.PHASE != "join":
        cli.notice(who, "Sorry, but the game is already running. Try again next time.")
    else:

        var.ROLES["person"].append(player)
        if not is_fake_nick(player) or not botconfig.DEBUG_MODE:
            cli.mode(chan, "+v", player)
            cli.msg(chan, '\u0002{0}\u0002 has joined the game and raised the number of players to \u0002{1}\u0002.'.format(player, len(pl) + 1))
        if not cloak in var.JOINED_THIS_GAME:
            # make sure this only happens once
            var.JOINED_THIS_GAME.append(cloak)
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


def kill_join(cli, chan):
    pl = var.list_players()
    pl.sort(key=lambda x: x.lower())
    msg = 'PING! {0}'.format(", ".join(pl))
    reset_modes_timers(cli)
    reset()
    cli.msg(chan, msg)
    cli.msg(chan, 'The current game took too long to start and ' +
                  'has been canceled. If you are still active, ' +
                  'please join again to start a new game.')
    var.LOGGER.logMessage('Game canceled.')


@cmd("fjoin", admin_only=True)
def fjoin(cli, nick, chann_, rest):
    """Forces someone to join a game."""
    noticed = False
    fake = False
    chan = botconfig.CHANNEL
    if not rest.strip():
        join_player(cli, nick, forced=True)

    for a in re.split(" +",rest):
        a = a.strip()
        if not a:
            continue
        ul = list(var.USERS.keys())
        ull = [u.lower() for u in ul]
        if a.lower() not in ull:
            if not is_fake_nick(a) or not botconfig.DEBUG_MODE:
                if not noticed:  # important
                    cli.msg(chan, nick+(": You may only fjoin "+
                                        "people who are in this channel."))
                    noticed = True
                continue
        if not is_fake_nick(a):
            a = ul[ull.index(a.lower())]
        elif botconfig.DEBUG_MODE:
            fake = True
        if a != botconfig.NICK:
            join_player(cli, a.strip(), forced=True, who=nick)
        else:
            cli.notice(nick, "No, that won't be allowed.")
    if fake:
        cli.msg(chan, "\u0002{0}\u0002 used fjoin and raised the number of players to \u0002{1}\u0002.".format(nick, len(var.list_players())))

@cmd("fleave", "fquit", admin_only=True)
def fleave(cli, nick, chann_, rest):
    """Forces someone to leave the game."""
    chan = botconfig.CHANNEL

    if var.PHASE == "none":
        cli.notice(nick, "No game is running.")
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
            message += " Say goodbye to the \02{0}\02.".format(var.get_reveal_role(a))
        if var.PHASE == "join":
            message += " New player count: \u0002{0}\u0002".format(len(var.list_players()) - 1)
        if var.PHASE in ("day", "night"):
            var.LOGGER.logMessage("{0} is forcing {1} to leave.".format(nick, a))
            var.LOGGER.logMessage("Say goodbye to the {0}".format(var.get_reveal_role(a)))
        cli.msg(chan, message)

        del_player(cli, a, death_triggers = False)


@cmd("fstart", admin_only=True)
def fstart(cli, nick, chan, rest):
    """Forces the game to start immediately."""
    cli.msg(botconfig.CHANNEL, "\u0002{0}\u0002 has forced the game to start.".format(nick))
    start(cli, nick, forced = True)



@hook("kick")
def on_kicked(cli, nick, chan, victim, reason):
    if victim == botconfig.NICK:
        cli.join(botconfig.CHANNEL)
        cli.msg("ChanServ", "op "+botconfig.CHANNEL)


@hook("account")
def on_account(cli, nick, acc):
    nick, mode, user, cloak = parse_nick(nick)
    if nick in var.USERS.keys():
        var.USERS[nick]["cloak"] = cloak
        var.USERS[nick]["account"] = acc

@cmd("stats")
def stats(cli, nick, chan, rest):
    """Displays the player statistics."""
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return

    pl = var.list_players()
    if var.PHASE in ("night", "day"):
        pl = [x for x in var.ALL_PLAYERS if x in pl]

    if nick != chan and (nick in pl or var.PHASE == "join"):
        # only do this rate-limiting stuff if the person is in game
        if (var.LAST_STATS and
            var.LAST_STATS + timedelta(seconds=var.STATS_RATE_LIMIT) > datetime.now()):
            cli.notice(nick, ("This command is rate-limited. " +
                              "Please wait a while before using it again."))
            return

        var.LAST_STATS = datetime.now()

    if len(pl) > 1:
        msg = '{0}: \u0002{1}\u0002 players: {2}'.format(nick,
            len(pl), ", ".join(pl))
    else:
        msg = '{0}: \u00021\u0002 player: {1}'.format(nick, pl[0])

    if nick == chan:
        pm(cli, nick, msg)
    else:
        if nick in pl or var.PHASE == "join":
            cli.msg(chan, msg)
            var.LOGGER.logMessage(msg.replace("\02", ""))
        else:
            cli.notice(nick, msg)

    if var.PHASE == "join" or not var.ROLE_REVEAL:
        return

    message = []
    l1 = [k for k in var.ROLES.keys()
          if var.ROLES[k]]
    l2 = [k for k in var.ORIGINAL_ROLES.keys()
          if var.ORIGINAL_ROLES[k]]
    rs = list(set(l1+l2))

    # Due to popular demand, picky ordering
    if "wolf" in rs:
        rs.remove("wolf")
        rs.insert(0, "wolf")
    if "augur" in rs:
        rs.remove("augur")
        rs.insert(1, "augur")
    if "oracle" in rs:
        rs.remove("oracle")
        rs.insert(1, "oracle")
    if "seer" in rs:
        rs.remove("seer")
        rs.insert(1, "seer")
    if var.DEFAULT_ROLE in rs:
        rs.remove(var.DEFAULT_ROLE)
    rs.append(var.DEFAULT_ROLE)


    firstcount = len(var.ROLES[rs[0]])
    if firstcount > 1 or not firstcount:
        vb = "are"
    else:
        vb = "is"

    amn_roles = {"amnesiac": 0}
    for amn in var.ORIGINAL_ROLES["amnesiac"]:
        if amn not in pl:
            continue

        amnrole = var.get_role(amn)
        if amnrole in ("village elder", "time lord"):
            amnrole = "villager"
        elif amnrole == "vengeful ghost":
            amnrole = var.DEFAULT_ROLE
        elif amnrole == "traitor" and var.HIDDEN_TRAITOR:
            amnrole = var.DEFAULT_ROLE
        if amnrole != "amnesiac":
            amn_roles["amnesiac"] += 1
            if amnrole in amn_roles:
                amn_roles[amnrole] -= 1
            else:
                amn_roles[amnrole] = -1

    for role in rs:
        # only show actual roles
        if role in ("village elder", "time lord", "vengeful ghost") or role in var.TEMPLATE_RESTRICTIONS.keys():
            continue
        count = len(var.ROLES[role])
        if role == "traitor" and var.HIDDEN_TRAITOR:
            continue
        elif role == var.DEFAULT_ROLE:
            if var.HIDDEN_TRAITOR:
                count += len(var.ROLES["traitor"])
            if var.DEFAULT_ROLE == "villager":
                count += len(var.ROLES["village elder"] + var.ROLES["time lord"] + var.ROLES["vengeful ghost"])
            else:
                count += len(var.ROLES["vengeful ghost"])
        elif role == "villager":
            count += len(var.ROLES["village elder"] + var.ROLES["time lord"])
        if role in amn_roles:
            count += amn_roles[role]

        if count > 1 or count == 0:
            if count == 0 and len(var.ORIGINAL_ROLES[role]) == 0:
                continue
            message.append("\u0002{0}\u0002 {1}".format(count if count else "\u0002no\u0002", var.plural(role)))
        else:
            message.append("\u0002{0}\u0002 {1}".format(count, role))
    stats_mssg =  "{0}: It is currently {4}. There {3} {1}, and {2}.".format(nick,
                                                        ", ".join(message[0:-1]),
                                                        message[-1],
                                                        vb,
                                                        var.PHASE)
    if nick == chan:
        pm(cli, nick, stats_mssg)
    else:
        if nick in pl or var.PHASE == "join":
            cli.msg(chan, stats_mssg)
            var.LOGGER.logMessage(stats_mssg.replace("\02", ""))
        else:
            cli.notice(nick, stats_mssg)

@pmcmd("stats")
def stats_pm(cli, nick, rest):
    stats(cli, nick, nick, rest)



def hurry_up(cli, gameid, change):
    if var.PHASE != "day": return
    if gameid:
        if gameid != var.DAY_ID:
            return

    chan = botconfig.CHANNEL

    if not change:
        cli.msg(chan, ("\02As the sun sinks inexorably toward the horizon, turning the lanky pine " +
                      "trees into fire-edged silhouettes, the villagers are reminded that very little " +
                      "time remains for them to reach a decision; if darkness falls before they have done " +
                      "so, the majority will win the vote. No one will be lynched if there " +
                      "are no votes or an even split.\02"))
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
            imp_count = sum([1 if p == v else 0 for p in var.IMPATIENT])
            pac_count = sum([1 if p == v else 0 for p in var.PACIFISTS])
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
        var.LOGGER.logMessage("The sun sets.")
        chk_decision(cli, force = maxfound[1])  # Induce a lynch
    else:
        cli.msg(chan, ("As the sun sets, the villagers agree to "+
                      "retire to their beds and wait for morning."))
        var.LOGGER.logMessage(("As the sun sets, the villagers agree to "+
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
    chan = botconfig.CHANNEL
    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED) - len(var.ASLEEP)
    votesneeded = avail // 2 + 1
    not_lynching = set(var.NO_LYNCH)
    for p in var.PACIFISTS:
        if p in pl and p not in var.WOUNDED and p not in var.ASLEEP:
            not_lynching.add(p)

    # we only need 50%+ to not lynch, instead of an actual majority, because a tie would time out day anyway
    # don't check for ABSTAIN_ENABLED here since we may have a case where the majority of people have pacifism totems or something
    if len(not_lynching) >= math.ceil(avail / 2):
        cli.msg(botconfig.CHANNEL, "The villagers have agreed to not lynch anybody today.")
        var.ABSTAINED = True
        transition_night(cli)
        return
    aftermessage = None
    votelist = copy.deepcopy(var.VOTES)
    for votee, voters in votelist.items():
        numvotes = 0
        for v in var.IMPATIENT:
            if v in pl and v not in voters and v != votee and v not in var.WOUNDED and v not in var.ASLEEP:
                voters = [v] + voters
        for v in voters:
            weight = 1
            imp_count = sum([1 if p == v else 0 for p in var.IMPATIENT])
            pac_count = sum([1 if p == v else 0 for p in var.PACIFISTS])
            if pac_count > imp_count:
                weight = 0 # more pacifists than impatience totems
            elif imp_count == pac_count and v not in var.VOTES[votee]:
                weight = 0 # impatience and pacifist cancel each other out, so don't count impatience
            if v in var.ROLES["bureaucrat"] or v in var.INFLUENTIAL: # the two do not stack
                weight *= 2
            numvotes += weight

        if numvotes >= votesneeded or votee == force:
            # roles that prevent any lynch from happening
            if votee in var.ROLES["mayor"] and votee not in var.REVEALED_MAYORS:
                lmsg = ("While being dragged to the gallows, \u0002{0}\u0002 reveals that they " +
                        "are the \u0002mayor\u0002. The village agrees to let them live for now.").format(votee)
                var.REVEALED_MAYORS.append(votee)
                var.LOGGER.logBare(votee, "MAYOR REVEALED")
                votee = None
            elif votee in var.REVEALED:
                role = var.get_role(votee)
                if role == "amnesiac":
                    var.ROLES["amnesiac"].remove(votee)
                    role = var.FINAL_ROLES[votee]
                    var.ROLES[role].append(votee)
                    var.AMNESIACS.append(votee)
                    pm(cli, votee, "Your totem clears your amnesia and you now fully remember who you are!")
                    # If wolfteam, don't bother giving list of wolves since night is about to start anyway
                    # Existing wolves also know that someone just joined their team because revealing totem says what they are

                an = "n" if role[0] in ("a", "e", "i", "o", "u") else ""
                lmsg = ("Before the rope is pulled, \u0002{0}\u0002's totem emits a brilliant flash of light. " +
                        "When the villagers are able to see again, they discover that {0} has escaped! " +
                        "The left-behind totem seems to have taken on the shape of a{1} \u0002{2}\u0002.").format(votee, an, role)
                var.LOGGER.logBare(votee, "ACTIVATED REVEALING TOTEM")
                votee = None
            else:
                # roles that end the game upon being lynched
                if votee in var.ROLES["fool"]:
                    # ends game immediately, with fool as only winner
                    lmsg = random.choice(var.LYNCH_MESSAGES).format(votee, "", var.get_reveal_role(votee))
                    cli.msg(botconfig.CHANNEL, lmsg)
                    var.LOGGER.logMessage(lmsg.replace("\02", ""))
                    var.LOGGER.logBare(votee, "LYNCHED")
                    message = "Game over! The fool has been lynched, causing them to win."
                    cli.msg(botconfig.CHANNEL, message)
                    var.LOGGER.logMessage(message)
                    var.LOGGER.logBare(votee, "FOOL WIN")
                    stop_game(cli, "@" + votee)
                    return
                # roles that eliminate other players upon being lynched
                # note that lovers, assassin, clone, and vengeful ghost are handled in del_player() since they trigger on more than just lynch
                if votee in var.DESPERATE:
                    # Also kill the very last person to vote them, unless they voted themselves last in which case nobody else dies
                    target = voters[-1]
                    if target != votee:
                        if var.ROLE_REVEAL:
                            r1 = var.get_reveal_role(target)
                            an1 = "n" if r1[0] in ("a", "e", "i", "o", "u") else ""
                            tmsg = ("As the noose is being fitted, \u0002{0}\u0002's totem emits a brilliant flash of light. " +
                                    "When the villagers are able to see again, they discover that \u0002{1}\u0002, " +
                                    "a{2} \u0002{3}\u0002, has fallen over dead.").format(votee, target, an1, r1)
                        else:
                            tmsg = ("As the noose is being fitted, \u0002{0}\u0002's totem emits a brilliant flash of light. " +
                                    "When the villagers are able to see again, they discover that \u0002{1}\u0002 " +
                                    "has fallen over dead.").format(votee, target)
                        var.LOGGER.logMessage(tmsg.replace("\02", ""))
                        var.LOGGER.logBare(votee, "ACTIVATED DESPERATION TOTEM")
                        var.LOGGER.logBare(target, "DESPERATION TOTEM TARGET")
                        cli.msg(botconfig.CHANNEL, tmsg)
                        del_player(cli, target, True, end_game = False, killer_role = "shaman") # do not end game just yet, we have more killin's to do!
                # Other
                if votee in var.ROLES["jester"]:
                    var.JESTERS.append(votee)

                if var.ROLE_REVEAL:
                    rrole = var.get_reveal_role(votee)
                    an = "n" if rrole[0] in ('a', 'e', 'i', 'o', 'u') else ""
                    lmsg = random.choice(var.LYNCH_MESSAGES).format(votee, an, rrole)
                else:
                    lmsg = random.choice(var.LYNCH_MESSAGES_NO_REVEAL).format(votee)
            cli.msg(botconfig.CHANNEL, lmsg)
            var.LOGGER.logMessage(lmsg.replace("\02", ""))
            if aftermessage != None:
                cli.msg(botconfig.CHANNEL, aftermessage)
                var.LOGGER.logMessage(aftermessage.replace("\02", ""))
            if votee != None:
                var.LOGGER.logBare(votee, "LYNCHED")
            if del_player(cli, votee, True, killer_role = "villager"):
                transition_night(cli)
            break


@cmd('votes')
def show_votes(cli, nick, chan, rest):
    """Displays the voting statistics."""

    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return

    if var.PHASE != 'day':
        cli.notice(nick, "Voting is only during the day.")
        return

    if (chan != nick and var.LAST_VOTES and var.VOTES_RATE_LIMIT and
            var.LAST_VOTES + timedelta(seconds=var.VOTES_RATE_LIMIT) >
            datetime.now()):
        cli.notice(nick, ('This command is rate-limited. Please wait a while '
                          'before using it again.'))
        return
    
    pl = var.list_players()

    if chan != nick and nick in pl:
        var.LAST_VOTES = datetime.now()

    if not var.VOTES.values():
        msg = nick+ ': No votes yet.'

        if nick in pl:
            var.LAST_VOTES = None  # reset
    else:
        votelist = ['{}: {} ({})'.format(votee,
                                         len(var.VOTES[votee]),
                                         ' '.join(var.VOTES[votee]))
                    for votee in var.VOTES.keys()]
        msg = '{}: {}'.format(nick, ', '.join(votelist))

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
    the_message = ('{}: \u0002{}\u0002 players, \u0002{}\u0002 votes '
                   'required to lynch, \u0002{}\u0002 players available to '
                   'vote. \u0002{}\u0002 player{} refrained from voting.').format(nick, len(pl), votesneeded, avail, not_voting, plural)

    if chan == nick:
        pm(cli, nick, the_message)
    elif nick not in pl and var.PHASE not in ("none", "join"):
        cli.notice(nick, the_message)
    else:
        cli.msg(chan, the_message)


@pmcmd('votes')
def show_votes_pm(cli, nick, rest):
    show_votes(cli, nick, nick, rest)


def chk_traitor(cli):
    wcl = copy.copy(var.ROLES["wolf cub"])
    ttl = copy.copy(var.ROLES["traitor"])
    for wc in wcl:
        var.ROLES["wolf"].append(wc)
        var.ROLES["wolf cub"].remove(wc)
        var.LOGGER.logBare(wc, "GROW UP")
        pm(cli, wc, ('You have grown up into a wolf and vowed to take revenge for your dead parents!'))

    if len(var.ROLES["wolf"]) == 0:
        for tt in ttl:
            var.ROLES["wolf"].append(tt)
            var.ROLES["traitor"].remove(tt)
            if tt in var.ROLES["cursed villager"]:
                var.ROLES["cursed villager"].remove(tt)
            var.LOGGER.logBare(tt, "TRANSFORM")
            pm(cli, tt, ('HOOOOOOOOOWL. You have become... a wolf!\n'+
                         'It is up to you to avenge your fallen leaders!'))

        # no message if wolf cub becomes wolf for now, may want to change that in future
        if len(var.ROLES["wolf"]) > 0:
            if var.ROLE_REVEAL:
                cli.msg(botconfig.CHANNEL, ('\u0002The villagers, during their celebrations, are '+
                                            'frightened as they hear a loud howl. The wolves are '+
                                            'not gone!\u0002'))
            var.LOGGER.logMessage(('The villagers, during their celebrations, are '+
                                   'frightened as they hear a loud howl. The wolves are '+
                                   'not gone!'))



def stop_game(cli, winner = ""):
    chan = botconfig.CHANNEL
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
    cli.msg(chan, gameend_msg)
    var.LOGGER.logMessage(gameend_msg.replace("\02", "")+"\n")
    var.LOGGER.logBare("DAY", "TIME", str(var.DAY_TIMEDELTA.seconds))
    var.LOGGER.logBare("NIGHT", "TIME", str(var.NIGHT_TIMEDELTA.seconds))
    var.LOGGER.logBare("GAME", "TIME", str(total.seconds))

    roles_msg = []

    lroles = list(var.ORIGINAL_ROLES.keys())
    lroles.remove("wolf")
    lroles.insert(0, "wolf")   # picky, howl consistency

    for role in lroles:
        if len(var.ORIGINAL_ROLES[role]) == 0 or role == var.DEFAULT_ROLE:
            continue
        playersinrole = copy.copy(var.ORIGINAL_ROLES[role])
        for i in range(0, len(playersinrole)):
            if playersinrole[i].startswith("(dced)"):  # don't care about it here
                playersinrole[i] = playersinrole[i][6:]
        if len(playersinrole) == 2:
            msg = "The {1} were \u0002{0[0]}\u0002 and \u0002{0[1]}\u0002."
            roles_msg.append(msg.format(playersinrole, var.plural(role)))
        elif len(playersinrole) == 1:
            roles_msg.append("The {1} was \u0002{0[0]}\u0002.".format(playersinrole,
                                                                      role))
        else:
            msg = "The {2} were {0}, and \u0002{1}\u0002."
            nickslist = ["\u0002"+x+"\u0002" for x in playersinrole[0:-1]]
            roles_msg.append(msg.format(", ".join(nickslist),
                                                  playersinrole[-1],
                                                  var.plural(role)))
    message = ""
    count = 0
    cli.msg(chan, var.break_long_message(roles_msg))

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
        cli.msg(chan, "The lovers were {0}.".format(" and ".join(lovers)))
    elif len(lovers) > 2:
        cli.msg(chan, "The lovers were {0}, and {1}".format(", ".join(lovers[0:-1]), lovers[-1]))

    # Only update if someone actually won, "" indicates everyone died or abnormal game stop
    if winner != "":
        plrl = {}
        winners = []
        for role,ppl in var.ORIGINAL_ROLES.items():
            if role in var.TEMPLATE_RESTRICTIONS.keys():
                continue
            for x in ppl:
                if x != None:
                    if role == "amnesiac" and x in var.AMNESIACS:
                        plrl[x] = var.FINAL_ROLES[x]
                    elif role != "amnesiac" and x in var.FINAL_ROLES: # role swap
                        plrl[x] = var.FINAL_ROLES[x]
                    else:
                        plrl[x] = role
        for plr, rol in plrl.items():
            orol = rol # original role, since we overwrite rol in case of clone
            splr = plr # plr stripped of the (dced) bit at the front, since other dicts don't have that
            if plr.startswith("(dced)") and plr[6:] in var.DCED_PLAYERS.keys():
                acc = var.DCED_PLAYERS[plr[6:]]["account"]
                splr = plr[6:]
            elif plr in var.PLAYERS.keys():
                acc = var.PLAYERS[plr]["account"]
            else:
                acc = "*"  #probably fjoin'd fake

            if rol == "clone":
                # see if they became a different role
                if splr in var.FINAL_ROLES:
                    rol = var.FINAL_ROLES[splr]

            won = False
            iwon = False
            # determine if this player's team won
            if rol in var.WOLFTEAM_ROLES:  # the player was wolf-aligned
                if winner == "wolves":
                    won = True
            elif rol in var.TRUE_NEUTRAL_ROLES:
                # true neutral roles never have a team win (with exception of monsters), only individual wins
                if winner == "monsters" and rol == "monster":
                    won = True
            elif rol in ("amnesiac", "vengeful ghost"):
                if var.DEFAULT_ROLE == "villager" and winner == "villagers":
                    won = True
                elif var.DEFAULT_ROLE == "cultist" and winner == "wolves":
                    won = True
            else:
                if winner == "villagers":
                    won = True

            survived = var.list_players()
            if plr.startswith("(dced)"):
                # You get NOTHING! You LOSE! Good DAY, sir!
                won = False
                iwon = False
            elif rol == "fool" and "@" + splr == winner:
                iwon = True
            elif rol == "monster" and splr in survived and winner == "monsters":
                iwon = True
            elif splr in var.LOVERS and splr in survived:
                for lvr in var.LOVERS[splr]:
                    lvrrol = "" #somehow lvrrol wasn't set and caused a crash once
                    if lvr in plrl:
                        lvrrol = plrl[lvr]
                    elif ("(dced)" + lvr) in plrl:
                        lvrrol = plrl["(dced)" + lvr]
                    if lvrrol == "clone" and lvr in var.FINAL_ROLES:
                        lvrrol = var.FINAL_ROLES[lvr]

                    if lvr in survived and not winner.startswith("@") and winner != "monsters":
                        iwon = True
                        break
                    elif lvr in survived and winner.startswith("@") and winner == "@" + lvr and var.LOVER_WINS_WITH_FOOL:
                        iwon = True
                        break
                    elif lvr in survived and winner == "monsters" and lvrrol == "monster":
                        iwon = True
                        break

            if plr.startswith("(dced)"):
                won = False
                iwon = False
            elif rol == "crazed shaman" or rol == "clone":
                # For clone, this means they ended game while being clone and not some other role
                if splr in survived and not winner.startswith("@") and winner != "monsters":
                    iwon = True
            elif rol == "vengeful ghost":
                if not winner.startswith("@") and winner != "monsters":
                    if won and splr in survived:
                        iwon = True
                    elif splr in var.VENGEFUL_GHOSTS and var.VENGEFUL_GHOSTS[splr] == "villagers" and winner == "wolves":
                        won = True
                        iwon = True
                    elif splr in var.VENGEFUL_GHOSTS and var.VENGEFUL_GHOSTS[splr] == "wolves" and winner == "villagers":
                        won = True
                        iwon = True
            elif rol == "lycan" or splr in var.LYCANS:
                if splr in var.LYCANS and winner == "wolves":
                    won = True
                elif splr not in var.LYCANS and winner == "villagers":
                    won = True
                else:
                    won = False
                if not iwon:
                    iwon = won and splr in survived
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

        var.update_game_stats(var.CURRENT_GAMEMODE, len(survived) + len(var.DEAD), winner)

        # spit out the list of winners
        winners.sort()
        if len(winners) == 1:
            cli.msg(chan, "The winner is \u0002{0}\u0002.".format(winners[0]))
        elif len(winners) == 2:
            cli.msg(chan, "The winners are \u0002{0}\u0002 and \u0002{1}\u0002.".format(winners[0], winners[1]))
        elif len(winners) > 2:
            nicklist = ["\u0002" + x + "\u0002" for x in winners[0:-1]]
            cli.msg(chan, "The winners are {0}, and \u0002{1}\u0002.".format(", ".join(nicklist), winners[-1]))

    reset_modes_timers(cli)

    # Set temporary phase to deal with disk lag
    var.PHASE = "writing files"

    var.LOGGER.saveToFile()
    reset()

    # This must be after reset()
    if var.AFTER_FLASTGAME:
        var.AFTER_FLASTGAME()
        var.AFTER_FLASTGAME = None
    if var.ADMIN_TO_PING:  # It was an flastgame
        cli.msg(chan, "PING! " + var.ADMIN_TO_PING)
        var.ADMIN_TO_PING = None

    return True

def chk_win(cli, end_game = True):
    """ Returns True if someone won """
    chan = botconfig.CHANNEL
    lpl = len(var.list_players())

    if var.PHASE == "join":
        if lpl == 0:
            #cli.msg(chan, "No more players remaining. Game ended.")
            reset_modes_timers(cli)
            reset()
            return True
        return False

    lwolves = len(var.list_players(var.WOLFCHAT_ROLES))
    lrealwolves = len(var.list_players(var.WOLF_ROLES)) - len(var.ROLES["wolf cub"])
    if var.PHASE == "day":
        for p in var.WOUNDED:
            try:
                role = var.get_role(p)
                if role in var.WOLFCHAT_ROLES:
                    lwolves -= 1
                else:
                    lpl -= 1
            except KeyError:
                pass
        for p in var.ASLEEP:
            try:
                role = var.get_role(p)
                if role in var.WOLFCHAT_ROLES:
                    lwolves -= 1
                else:
                    lpl -= 1
            except KeyError:
                pass

    if lpl < 1:
        message = "Game over! There are no players remaining. Nobody wins."
        winner = "none"
    elif lwolves == lpl / 2:
        if len(var.ROLES["monster"]) > 0:
            plural = "s" if len(var.ROLES["monster"]) > 1 else ""
            message = ("Game over! There are the same number of wolves as uninjured villagers. " +
                       "The wolves overpower the villagers but then get destroyed by the monster{0}, " +
                       "causing the monster{0} to win.").format(plural)
            winner = "monsters"
        else:
            message = ("Game over! There are the same number of wolves as " +
                      "uninjured villagers. The wolves overpower the villagers and win.")
            winner = "wolves"
    elif lwolves > lpl / 2:
        if len(var.ROLES["monster"]) > 0:
            plural = "s" if len(var.ROLES["monster"]) > 1 else ""
            message = ("Game over! There are more wolves than uninjured villagers. " +
                       "The wolves overpower the villagers but then get destroyed by the monster{0}, " +
                       "causing the monster{0} to win.").format(plural)
            winner = "monsters"
        else:
            message = ("Game over! There are more wolves than "+
                      "uninjured villagers. The wolves overpower the villagers and win.")
            winner = "wolves"
    elif lrealwolves == 0 and len(var.ROLES["traitor"]) == 0 and len(var.ROLES["wolf cub"]) == 0:
        if len(var.ROLES["monster"]) > 0:
            plural = "s" if len(var.ROLES["monster"]) > 1 else ""
            message = ("Game over! All the wolves are dead! As the villagers start preparing the BBQ, " +
                       "the monster{0} quickly kill{1} the remaining villagers, " +
                       "causing the monster{0} to win.").format(plural, "" if plural else "s")
            winner = "monsters"
        else:
            message = ("Game over! All the wolves are dead! The villagers " +
                      "chop them up, BBQ them, and have a hearty meal.")
            winner = "villagers"
    elif lrealwolves == 0:
        chk_traitor(cli)
        return chk_win(cli, end_game)
    else:
        return False
    if end_game:
        cli.msg(chan, message)
        var.LOGGER.logMessage(message)
        var.LOGGER.logBare(winner.upper(), "WIN")
        stop_game(cli, winner)
    return True

def del_player(cli, nick, forced_death = False, devoice = True, end_game = True, death_triggers = True, killer_role = "", deadlist = [], original = ""):
    """
    Returns: False if one side won.
    arg: forced_death = True when lynched or when the seer/wolf both don't act
    """

    t = time.time()  #  time

    var.LAST_STATS = None # reset
    var.LAST_VOTES = None

    with var.GRAVEYARD_LOCK:
        if not var.GAME_ID or var.GAME_ID > t:
            #  either game ended, or a new game has started.
            return False
        cmode = []
        ret = True
        pl = var.list_players()
        for dead in deadlist:
            if dead in pl:
                pl.remove(dead)
        if nick != None and (nick == original or nick in pl):
            nickrole = var.get_role(nick)
            nicktpls = var.get_templates(nick)
            var.del_player(nick)
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
                                sayrole = var.FINAL_ROLES[nick]
                                var.FINAL_ROLES[clone] = sayrole
                                var.ROLES[sayrole].append(clone)
                            else:
                                var.ROLES[nickrole].append(clone)
                                var.FINAL_ROLES[clone] = nickrole
                                sayrole = nickrole
                            # if cloning time lord or vengeful ghost, say they are villager instead
                            if sayrole in ("time lord", "village elder"):
                                sayrole = "villager"
                            elif sayrole == "vengeful ghost":
                                sayrole = var.DEFAULT_ROLE
                            an = "n" if sayrole[0] in ("a", "e", "i", "o", "u") else ""
                            pm(cli, clone, "You are now a{0} \u0002{1}\u0002.".format(an, sayrole))
                            # if a clone is cloning a clone, clone who the old clone cloned
                            if nickrole == "clone" and nick in var.CLONED:
                                if var.CLONED[nick] == clone:
                                    pm(cli, clone, "It appears that \u0002{0}\u0002 was cloning you, so you are now stuck as a clone forever. How sad.".format(nick))
                                else:
                                    var.CLONED[clone] = var.CLONED[nick]
                                    pm(cli, clone, "You will now be cloning \u0002{0}\u0002 if they die.".format(var.CLONED[clone]))
                            elif nickrole in var.WOLFCHAT_ROLES:
                                wolves = var.list_players(var.WOLFCHAT_ROLES)
                                wolves.remove(clone) # remove self from list
                                for wolf in wolves:
                                    pm(cli, wolf, "\u0002{}\u0002 cloned \u0002{}\u0002 and has now become a wolf!".format(clone, nick))
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

                if nickrole == "clone" and nick in var.CLONED:
                    del var.CLONED[nick]

            if death_triggers and var.PHASE in ("night", "day"):
                if nick in var.LOVERS:
                    others = copy.copy(var.LOVERS[nick])
                    del var.LOVERS[nick][:]
                    for other in others:
                        if other not in pl:
                            continue # already died somehow
                        if nick not in var.LOVERS[other]:
                            continue
                        var.LOVERS[other].remove(nick)
                        if var.ROLE_REVEAL:
                            role = var.get_reveal_role(other)
                            an = "n" if role[0] in ("a", "e", "i", "o", "u") else ""
                            message = ("Saddened by the loss of their lover, \u0002{0}\u0002, " +
                                       "a{1} \u0002{2}\u0002, commits suicide.").format(other, an, role)
                        else:
                            message = "Saddened by the loss of their lover, \u0002{0}\u0002 commits suicide.".format(other)
                        cli.msg(botconfig.CHANNEL, message)
                        var.LOGGER.logMessage(message.replace("\02", ""))
                        var.LOGGER.logBare(other, "DEAD LOVER")
                        del_player(cli, other, True, end_game = False, killer_role = killer_role, deadlist = deadlist, original = original)
                if "assassin" in nicktpls:
                    if nick in var.TARGETED:
                        target = var.TARGETED[nick]
                        del var.TARGETED[nick]
                        if target != None and target in pl:
                            if target in var.PROTECTED:
                                message = ("Before dying, \u0002{0}\u0002 quickly attempts to slit \u0002{1}\u0002's throat; " +
                                           "however, {1}'s totem emits a brilliant flash of light, causing the attempt to miss.").format(nick, target)
                                cli.msg(botconfig.CHANNEL, message)
                                var.LOGGER.logMessage(message.replace("\02", ""))
                            elif target in var.GUARDED.values() and var.GAMEPHASE == "night":
                                for bg in var.ROLES["guardian angel"]:
                                    if bg in var.GUARDED and var.GUARDED[bg] == target:
                                        message = ("Before dying, \u0002{0}\u0002 quickly attempts to slit \u0002{1}\u0002's throat; " +
                                                   "however, a guardian angel was on duty and able to foil the attempt.").format(nick, target)
                                        cli.msg(botconfig.CHANNEL, message)
                                        var.LOGGER.logMessage(message.replace("\02", ""))
                                        break
                                else:
                                    for ga in var.ROLES["bodyguard"]:
                                        if ga in var.GUARDED and var.GUARDED[ga] == target:
                                            message = ("Before dying, \u0002{0}\u0002 quickly attempts to slit \u0002{1}\u0002's throat; " +
                                                       "however, \u0002{2}\u0002, a bodyguard, sacrificed their life to protect them.").format(nick, target, ga)
                                            cli.msg(botconfig.CHANNEL, message)
                                            var.LOGGER.logMessage(message.replace("\02", ""))
                                            del_player(cli, ga, True, end_game = False, killer_role = nickrole, deadlist = deadlist, original = original)
                                            break
                            else:
                                if var.ROLE_REVEAL:
                                    role = var.get_reveal_role(target)
                                    an = "n" if role[0] in ("a", "e", "i", "o", "u") else ""
                                    message = ("Before dying, \u0002{0}\u0002 quickly slits \u0002{1}\u0002's throat. " +
                                               "The village mourns the loss of a{2} \u0002{3}\u0002.").format(nick, target, an, role)
                                else:
                                    message = "Before dying, \u0002{0}\u0002 quickly slits \u0002{1}\u0002's throat.".format(nick, target)
                                cli.msg(botconfig.CHANNEL, message)
                                var.LOGGER.logMessage(message.replace("\02", ""))
                                var.LOGGER.logBare(target, "ASSASSINATED")
                                del_player(cli, target, True, end_game = False, killer_role = nickrole, deadlist = deadlist, original = original)

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
                if nickrole == "vengeful ghost":
                    if killer_role in var.WOLFTEAM_ROLES:
                        var.VENGEFUL_GHOSTS[nick] = "wolves"
                    else:
                        var.VENGEFUL_GHOSTS[nick] = "villagers"
                    pm(cli, nick, ("OOOooooOOOOooo! You are the \u0002vengeful ghost\u0002. It is now your job " +
                                   "to exact your revenge on the \u0002{0}\u0002 that killed you.").format(var.VENGEFUL_GHOSTS[nick]))
                if nickrole == "wolf cub":
                    var.ANGRY_WOLVES = True
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
                            if var.ROLE_REVEAL:
                                r1 = var.get_reveal_role(target1)
                                an1 = "n" if r1[0] in ("a", "e", "i", "o", "u") else ""
                                r2 = var.get_reveal_role(target2)
                                an2 = "n" if r2[0] in ("a", "e", "i", "o", "u") else ""
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002, " +
                                        "a{2} \u0002{3}\u0002, and \u0002{4}\u0002, a{5} \u0002{6}\u0002, " +
                                        "get hit by the chemicals and die.").format(nick, target1, an1, r1, target2, an2, r2)
                            else:
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002 " +
                                        "and \u0002{2}\u0002 get hit by the chemicals and die.").format(nick, target1, target2)
                            var.LOGGER.logMessage(tmsg.replace("\02", ""))
                            var.LOGGER.logBare(nick, "MAD SCIENTIST")
                            var.LOGGER.logBare(target1, "DIED FROM SCIENTIST")
                            var.LOGGER.logBare(target2, "DIED FROM SCIENTIST")
                            cli.msg(botconfig.CHANNEL, tmsg)
                            deadlist1 = copy.copy(deadlist)
                            deadlist1.append(target2)
                            deadlist2 = copy.copy(deadlist)
                            deadlist2.append(target1)
                            del_player(cli, target1, True, end_game = False, killer_role = "mad scientist", deadlist = deadlist1, original = original)
                            del_player(cli, target2, True, end_game = False, killer_role = "mad scientist", deadlist = deadlist2, original = original)
                        else:
                            if var.ROLE_REVEAL:
                                r1 = var.get_reveal_role(target1)
                                an1 = "n" if r1[0] in ("a", "e", "i", "o", "u") else ""
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002, " +
                                        "a{2} \u0002{3}\u0002, gets hit by the chemicals and dies.").format(nick, target1, an1, r1)
                            else:
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002 " +
                                        "gets hit by the chemicals and dies.").format(nick, target1)
                            var.LOGGER.logMessage(tmsg.replace("\02", ""))
                            var.LOGGER.logBare(nick, "MAD SCIENTIST")
                            var.LOGGER.logBare(target1, "DIED FROM SCIENTIST")
                            cli.msg(botconfig.CHANNEL, tmsg)
                            del_player(cli, target1, True, end_game = False, killer_role = "mad scientist", deadlist = deadlist, original = original)
                    else:
                        if target2 in pl:
                            if var.ROLE_REVEAL:
                                r2 = var.get_reveal_role(target2)
                                an2 = "n" if r2[0] in ("a", "e", "i", "o", "u") else ""
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002, " +
                                        "a{2} \u0002{3}\u0002, gets hit by the chemicals and dies.").format(nick, target2, an2, r2)
                            else:
                                tmsg = ("\u0002{0}\u0002 throws " +
                                        "a potent chemical concoction into the crowd. \u0002{1}\u0002 " +
                                        "gets hit by the chemicals and dies.").format(nick, target2)
                            var.LOGGER.logMessage(tmsg.replace("\02", ""))
                            var.LOGGER.logBare(nick, "MAD SCIENTIST")
                            var.LOGGER.logBare(target2, "DIED FROM SCIENTIST")
                            cli.msg(botconfig.CHANNEL, tmsg)
                            del_player(cli, target2, True, end_game = False, killer_role = "mad scientist", deadlist = deadlist, original = original)
                        else:
                            tmsg = ("\u0002{0}\u0002 throws " +
                                    "a potent chemical concoction into the crowd. Thankfully, " +
                                    "nobody seems to have gotten hit.").format(nick)
                            var.LOGGER.logMessage(tmsg.replace("\02", ""))
                            var.LOGGER.logBare(nick, "MAD SCIENTIST")
                            cli.msg(botconfig.CHANNEL, tmsg)

            if devoice:
                cmode.append(("-v", nick))
            if var.PHASE == "join":
                # Died during the joining process as a person
                mass_mode(cli, cmode)
                return not chk_win(cli)
            if var.PHASE != "join":
                # Died during the game, so quiet!
                if var.QUIET_DEAD_PLAYERS and not is_fake_nick(nick):
                    cmode.append(("+q", nick+"!*@*"))
                mass_mode(cli, cmode)
                if nick not in var.DEAD:
                    var.DEAD.append(nick)
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
                    keys = list(x.keys())
                    for k in keys:
                        if k == nick:
                            del x[k]
                        elif x[k] == nick:
                            del x[k]
                if nick in var.DISCONNECTED:
                    del var.DISCONNECTED[nick]
            if var.PHASE == "day" and not forced_death and ret:  # didn't die from lynching
                if nick in var.VOTES.keys():
                    del var.VOTES[nick]  #  Delete other people's votes on the player
                for k in list(var.VOTES.keys()):
                    if nick in var.VOTES[k]:
                        var.VOTES[k].remove(nick)
                        if not var.VOTES[k]:  # no more votes on that person
                            del var.VOTES[k]
                        break # can only vote once
                if nick in var.NO_LYNCH:
                    var.NO_LYNCH.remove(nick)

                if nick in var.WOUNDED:
                    var.WOUNDED.remove(nick)
                if nick in var.ASLEEP:
                    var.ASLEEP.remove(nick)
                if nick in var.PLAYERS:
                    cloak = var.PLAYERS[nick]["cloak"]
                    if cloak in var.GAMEMODE_VOTES:
                        del var.GAMEMODE_VOTES[cloak]
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
            # Terminate reaper when experiencing disk lag
            if var.PHASE == "writing files":
                return
            if var.WARN_IDLE_TIME or var.PM_WARN_IDLE_TIME or var.KILL_IDLE_TIME:  # only if enabled
                to_warn    = []
                to_warn_pm = []
                to_kill    = []
                for nick in var.list_players():
                    lst = var.LAST_SAID_TIME.get(nick, var.GAME_START_TIME)
                    tdiff = datetime.now() - lst
                    if (tdiff > timedelta(seconds=var.WARN_IDLE_TIME) and
                                            nick not in var.IDLE_WARNED):
                        if var.WARN_IDLE_TIME:
                            to_warn.append(nick)
                        var.IDLE_WARNED.add(nick)
                        var.LAST_SAID_TIME[nick] = (datetime.now() -
                            timedelta(seconds=var.WARN_IDLE_TIME))  # Give them a chance
                    elif (tdiff > timedelta(seconds=var.PM_WARN_IDLE_TIME) and
                                            nick not in var.IDLE_WARNED_PM):
                        if var.PM_WARN_IDLE_TIME:
                            to_warn_pm.append(nick)
                        var.IDLE_WARNED_PM.add(nick)
                        var.LAST_SAID_TIME[nick] = (datetime.now() -
                            timedelta(seconds=var.PM_WARN_IDLE_TIME))
                    elif (tdiff > timedelta(seconds=var.KILL_IDLE_TIME) and
                        nick in var.IDLE_WARNED and nick in var.IDLE_WARNED_PM):
                        if var.KILL_IDLE_TIME:
                            to_kill.append(nick)
                    elif (tdiff < timedelta(seconds=var.WARN_IDLE_TIME) and
                        (nick in var.IDLE_WARNED or nick in var.IDLE_WARNED_PM)):
                        var.IDLE_WARNED.discard(nick)  # player saved themselves from death
                        var.IDLE_WARNED_PM.discard(nick)
                for nck in to_kill:
                    if nck not in var.list_players():
                        continue
                    if var.ROLE_REVEAL:
                        cli.msg(chan, ("\u0002{0}\u0002 didn't get out of bed for a very long "+
                                       "time and has been found dead. The survivors bury "+
                                       "the \u0002{1}\u0002's body.").format(nck, var.get_reveal_role(nck)))
                    else:
                        cli.msg(chan, ("\u0002{0}\u0002 didn't get out of bed for a very long " +
                                       "time and has been found dead.").format(nck))
                    for r,rlist in var.ORIGINAL_ROLES.items():
                        if nck in rlist:
                            var.ORIGINAL_ROLES[r].remove(nck)
                            var.ORIGINAL_ROLES[r].append("(dced)"+nck)
                    make_stasis(nck, var.IDLE_STASIS_PENALTY)
                    del_player(cli, nck, end_game = False, death_triggers = False)
                chk_win(cli)
                pl = var.list_players()
                x = [a for a in to_warn if a in pl]
                if x:
                    cli.msg(chan, ("{0}: \u0002You have been idling for a while. "+
                                   "Please say something soon or you "+
                                   "might be declared dead.\u0002").format(", ".join(x)))
                msg_targets    = [p for p in to_warn_pm if p in pl and var.PLAYERS[p]["cloak"] not in var.PREFER_NOTICE]
                notice_targets = [p for p in to_warn_pm if p in pl and var.PLAYERS[p]["cloak"]     in var.PREFER_NOTICE]
                mass_privmsg(cli, msg_targets, ("\u0002You have been idling in {0} for a while. Please say something in {0} "+
                                                "or you will be declared dead.\u0002").format(chan))
                mass_privmsg(cli, notice_targets, ("\u0002You have been idling in {0} for a while. Please say something in {0} "+
                                                   "or you will be declared dead.\u0002").format(chan), True)
            for dcedplayer in list(var.DISCONNECTED.keys()):
                _, timeofdc, what = var.DISCONNECTED[dcedplayer]
                if what == "quit" and (datetime.now() - timeofdc) > timedelta(seconds=var.QUIT_GRACE_TIME):
                    if var.get_role(dcedplayer) != "person" and var.ROLE_REVEAL:
                        cli.msg(chan, ("\02{0}\02 was mauled by wild animals and has died. It seems that "+
                                       "\02{1}\02 meat is tasty.").format(dcedplayer, var.get_reveal_role(dcedplayer)))
                    else:
                        cli.msg(chan, ("\u0002{0}\u0002 was mauled by wild animals and has died.").format(dcedplayer))
                    if var.PHASE != "join":
                        make_stasis(dcedplayer, var.PART_STASIS_PENALTY)
                    if not del_player(cli, dcedplayer, devoice = False, death_triggers = False):
                        return
                elif what == "part" and (datetime.now() - timeofdc) > timedelta(seconds=var.PART_GRACE_TIME):
                    if var.get_role(dcedplayer) != "person" and var.ROLE_REVEAL:
                        cli.msg(chan, ("\02{0}\02, a \02{1}\02, ate some poisonous berries "+
                                       "and has died.").format(dcedplayer, var.get_reveal_role(dcedplayer)))
                    else:
                        cli.msg(chan, ("\u0002{0}\u0002 ate some poisonous berries and has died.").format(dcedplayer))
                    if var.PHASE != "join":
                        make_stasis(dcedplayer, var.PART_STASIS_PENALTY)
                    if not del_player(cli, dcedplayer, devoice = False, death_triggers = False):
                        return
        time.sleep(10)



@cmd("")  # update last said
def update_last_said(cli, nick, chan, rest):
    if var.PHASE not in ("join", "none"):
        var.LAST_SAID_TIME[nick] = datetime.now()

    if var.PHASE not in ("none", "join"):
        var.LOGGER.logChannelMessage(nick, rest)

    fullstring = "".join(rest)
    if var.CARE_BOLD and BOLD in fullstring:
        if var.KILL_BOLD:
            cli.send("KICK {0} {1} :Using bold is not allowed".format(botconfig.CHANNEL, nick))
        else:
            cli.notice(nick, "Using bold in the channel is not allowed.")
    if var.CARE_COLOR and any(code in fullstring for code in ["\x03", "\x16", "\x1f" ]):
        if var.KILL_COLOR:
            cli.send("KICK {0} {1} :Using color is not allowed".format(botconfig.CHANNEL, nick))
        else:
            cli.notice(nick, "Using color in the channel is not allowed.")

@hook("join")
def on_join(cli, raw_nick, chan, acc="*", rname=""):
    nick,m,u,cloak = parse_nick(raw_nick)
    if nick != botconfig.NICK:
        if nick not in var.USERS.keys():
            var.USERS[nick] = dict(cloak=cloak,account=acc)
        else:
            var.USERS[nick]["cloak"] = cloak
            var.USERS[nick]["account"] = acc
    with var.GRAVEYARD_LOCK:
        if nick in var.DISCONNECTED.keys():
            clk = var.DISCONNECTED[nick][0]
            if cloak == clk:
                cli.mode(chan, "+v", nick, nick+"!*@*")
                del var.DISCONNECTED[nick]
                var.LAST_SAID_TIME[nick] = datetime.now()
                cli.msg(chan, "\02{0}\02 has returned to the village.".format(nick))
                for r,rlist in var.ORIGINAL_ROLES.items():
                    if "(dced)"+nick in rlist:
                        rlist.remove("(dced)"+nick)
                        rlist.append(nick)
                        break
                if nick in var.DCED_PLAYERS.keys():
                    var.PLAYERS[nick] = var.DCED_PLAYERS.pop(nick)
    if nick == botconfig.NICK:
        var.OPPED = False
    if nick == "ChanServ" and not var.OPPED:
        cli.msg("ChanServ", "op " + chan)


@cmd('goat')
def goat(cli, nick, chan, rest):
    """Use a goat to interact with anyone in the channel during the day."""

    if var.PHASE in ('none', 'join'):
        cli.notice(nick, 'No game is currently running.')
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, 'You\'re not currently playing.')
        return

    if var.PHASE != 'day':
        cli.notice(nick, 'You can only do that in the day.')
        return

    if var.GOATED and nick not in var.SPECIAL_ROLES['goat herder']:
        cli.notice(nick, 'This can only be done once per day.')
        return

    ul = list(var.USERS.keys())
    ull = [x.lower() for x in ul]
    rest = rest.split(' ')[0].strip().lower()

    if not rest:
        cli.notice(nick, 'Not enough parameters.')
        return

    matches = 0

    for player in ull:
        if rest == player:
            victim = player
            break

        if player.startswith(rest):
            victim = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, '\x02{}\x02 is not in this channel.'.format(rest))
            return

    victim = ul[ull.index(victim)]
    goatact = random.choice(('kicks', 'headbutts'))

    cli.msg(chan, '\x02{}\x02\'s goat walks by and {} \x02{}\x02.'.format(
        nick, goatact, victim))

    var.LOGGER.logMessage('{}\'s goat walks by and {} {}.'.format(
        nick, goatact, victim))

    var.GOATED = True

@cmd('fgoat', admin_only=True)
def fgoat(cli, nick, chan, rest):
    """Forces a goat to interact with anyone or anything, without limitations."""
    rest = rest.split(' ')[0].strip()
    goatact = random.choice(['kicks', 'headbutts'])

    cli.msg(chan, '\x02{}\x02\'s goat walks by and {} \x02{}\x02.'.format(
        nick, goatact, rest))

    var.LOGGER.logMessage('{}\'s goat walks by and {} {}.'.format(
        nick, goatact, rest))


@hook("nick")
def on_nick(cli, oldnick, nick):
    prefix,u,m,cloak = parse_nick(oldnick)
    chan = botconfig.CHANNEL

    if prefix in var.USERS:
        var.USERS[nick] = var.USERS.pop(prefix)

    if prefix == var.ADMIN_TO_PING:
        var.ADMIN_TO_PING = nick

    # for k,v in list(var.DEAD_USERS.items()):
        # if prefix == k:
            # var.DEAD_USERS[nick] = var.DEAD_USERS[k]
            # del var.DEAD_USERS[k]

    if (nick.startswith("Guest") or nick[0].isdigit() or (nick != "away" and "away" in nick.lower())) and nick not in var.DISCONNECTED.keys() and prefix in var.list_players():
        if var.PHASE != "join":
            cli.mode(chan, "-v", nick)
        leave(cli, "quit", oldnick)
        return

    if prefix in var.list_players() and prefix not in var.DISCONNECTED.keys():
        r = var.ROLES[var.get_role(prefix)]
        r.append(nick)
        r.remove(prefix)
        tpls = var.get_templates(prefix)
        for t in tpls:
            var.ROLES[t].append(nick)
            var.ROLES[t].remove(prefix)

        if var.PHASE in ("night", "day"):
            # ALL_PLAYERS needs to keep its ordering for purposes of mad scientist
            var.ALL_PLAYERS[var.ALL_PLAYERS.index(prefix)] = nick
            for k,v in var.ORIGINAL_ROLES.items():
                if prefix in v:
                    var.ORIGINAL_ROLES[k].remove(prefix)
                    var.ORIGINAL_ROLES[k].append(nick)
                    break
            for k,v in list(var.PLAYERS.items()):
                if prefix == k:
                    var.PLAYERS[nick] = var.PLAYERS[k]
                    del var.PLAYERS[k]
            if prefix in var.GUNNERS.keys():
                var.GUNNERS[nick] = var.GUNNERS.pop(prefix)
            for dictvar in (var.HVISITED, var.OBSERVED, var.GUARDED, var.OTHER_KILLS, var.TARGETED, var.CLONED, var.LASTGUARDED, var.LASTGIVEN, var.LASTHEXED):
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
            for dictvar in (var.VENGEFUL_GHOSTS, var.TOTEMS, var.FINAL_ROLES):
                if prefix in dictvar.keys():
                    dictvar[nick] = dictvar[prefix]
                    del dictvar[prefix]
            for dictvar in (var.KILLS, var.LOVERS, var.ORIGINAL_LOVERS):
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
            if prefix in var.SEEN:
                var.SEEN.remove(prefix)
                var.SEEN.append(nick)
            if prefix in var.HEXED:
                var.HEXED.remove(prefix)
                var.HEXED.append(nick)
            if prefix in var.ASLEEP:
                var.ASLEEP.remove(prefix)
                var.ASLEEP.append(nick)
            if prefix in var.DESPERATE:
                var.DESPERATE.remove(prefix)
                var.DESPERATE.append(nick)
            if prefix in var.PROTECTED:
                var.PROTECTED.remove(prefix)
                var.PROTECTED.append(nick)
            if prefix in var.REVEALED:
                var.REVEALED.remove(prefix)
                var.REVEALED.append(nick)
            if prefix in var.SILENCED:
                var.SILENCED.remove(prefix)
                var.SILENCED.append(nick)
            if prefix in var.TOBESILENCED:
                var.TOBESILENCED.remove(prefix)
                var.TOBESILENCED.append(nick)
            if prefix in var.DYING:
                var.DYING.remove(prefix)
                var.DYING.append(nick)
            if prefix in var.REVEALED_MAYORS:
                var.REVEALED_MAYORS.remove(prefix)
                var.REVEALED_MAYORS.append(nick)
            if prefix in var.MATCHMAKERS:
                var.MATCHMAKERS.remove(prefix)
                var.MATCHMAKERS.append(nick)
            if prefix in var.HUNTERS:
                var.HUNTERS.remove(prefix)
                var.HUNTERS.append(nick)
            if prefix in var.SHAMANS:
                var.SHAMANS.remove(prefix)
                var.SHAMANS.append(nick)
            if prefix in var.LYCANS:
                var.LYCANS.remove(prefix)
                var.LYCANS.append(nick)
            if prefix in var.PASSED:
                var.PASSED.remove(prefix)
                var.PASSED.append(nick)
            if prefix in var.JESTERS:
                var.JESTERS.remove(prefix)
                var.JESTERS.append(nick)
            if prefix in var.AMNESIACS:
                var.AMNESIACS.remove(prefix)
                var.AMNESIACS.append(nick)
            while prefix in var.IMPATIENT:
                var.IMPATIENT.remove(prefix)
                var.IMPATIENT.append(nick)
            while prefix in var.PACIFISTS:
                var.PACIFISTS.remove(prefix)
                var.PACIFISTS.append(nick)
            if prefix in var.INFLUENTIAL:
                var.INFLUENTIAL.remove(prefix)
                var.INFLUENTIAL.append(nick)
            if prefix in var.LYCANTHROPES:
                var.LYCANTHROPES.remove(prefix)
                var.LYCANTHROPES.append(nick)
            if prefix in var.TOBELYCANTHROPES:
                var.TOBELYCANTHROPES.remove(prefix)
                var.TOBELYCANTHROPES.append(nick)
            if prefix in var.LUCKY:
                var.LUCKY.remove(prefix)
                var.LUCKY.append(nick)
            if prefix in var.TOBELUCKY:
                var.TOBELUCKY.remove(prefix)
                var.TOBELUCKY.append(nick)
            if prefix in var.DISEASED:
                var.DISEASED.remove(prefix)
                var.DISEASED.append(nick)
            if prefix in var.TOBEDISEASED:
                var.TOBEDISEASED.remove(prefix)
                var.TOBEDISEASED.append(nick)
            if prefix in var.RETRIBUTION:
                var.RETRIBUTION.remove(prefix)
                var.RETRIBUTION.append(nick)
            if prefix in var.MISDIRECTED:
                var.MISDIRECTED.remove(prefix)
                var.MISDIRECTED.append(nick)
            if prefix in var.TOBEMISDIRECTED:
                var.TOBEMISDIRECTED.remove(prefix)
                var.TOBEMISDIRECTED.append(nick)
            if prefix in var.EXCHANGED:
                var.EXCHANGED.remove(prefix)
                var.EXCHANGED.append(nick)
            if prefix in var.TOBEEXCHANGED:
                var.TOBEEXCHANGED.remove(prefix)
                var.TOBEEXCHANGED.append(nick)
            with var.GRAVEYARD_LOCK:  # to be safe
                if prefix in var.LAST_SAID_TIME.keys():
                    var.LAST_SAID_TIME[nick] = var.LAST_SAID_TIME.pop(prefix)
                if prefix in var.IDLE_WARNED:
                    var.IDLE_WARNED.remove(prefix)
                    var.IDLE_WARNED.add(nick)
                if prefix in var.IDLE_WARNED_PM:
                    var.IDLE_WARNED_PM.remove(prefix)
                    var.IDLE_WARNED_PM.add(nick)

        if var.PHASE == "day":
            if prefix in var.WOUNDED:
                var.WOUNDED.remove(prefix)
                var.WOUNDED.append(nick)
            if prefix in var.INVESTIGATED:
                var.INVESTIGATED.remove(prefix)
                var.INVESTIGATED.append(prefix)
            if prefix in var.VOTES:
                var.VOTES[nick] = var.VOTES.pop(prefix)
            for v in var.VOTES.values():
                if prefix in v:
                    v.remove(prefix)
                    v.append(nick)

    # Check if he was DC'ed
    if var.PHASE in ("night", "day"):
        with var.GRAVEYARD_LOCK:
            if nick in var.DISCONNECTED.keys():
                clk = var.DISCONNECTED[nick][0]
                if cloak == clk:
                    cli.mode(chan, "+v", nick, nick+"!*@*")
                    del var.DISCONNECTED[nick]
                    var.LAST_SAID_TIME[nick] = datetime.now()
                    cli.msg(chan, "\02{0}\02 has returned to the village.".format(nick))
                    for r,rlist in var.ORIGINAL_ROLES.items():
                        if "(dced)"+nick in rlist:
                            rlist.remove("(dced)"+nick)
                            rlist.append(nick)
                            break
                    if nick in var.DCED_PLAYERS.keys():
                        var.PLAYERS[nick] = var.DCED_PLAYERS.pop(nick)

    if prefix in var.NO_LYNCH:
        var.NO_LYNCH.remove(prefix)
        var.NO_LYNCH.append(nick)

def leave(cli, what, nick, why=""):
    nick, _, _, cloak = parse_nick(nick)

    if what == "part" and why != botconfig.CHANNEL: return

    if why and why == botconfig.CHANGING_HOST_QUIT_MESSAGE:
        return
    if var.PHASE == "none":
        return
    # only mark living players as dced, unless they were kicked
    if nick in var.PLAYERS and (what == "kick" or nick in var.list_players()):
        # must prevent double entry in var.ORIGINAL_ROLES
        for r,rlist in var.ORIGINAL_ROLES.items():
            if nick in rlist:
                var.ORIGINAL_ROLES[r].remove(nick)
                var.ORIGINAL_ROLES[r].append("(dced)"+nick)
                break
        var.DCED_PLAYERS[nick] = var.PLAYERS.pop(nick)
    if nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        return

    #  the player who just quit was in the game
    killplayer = True

    population = ""

    if var.PHASE == "join":
        lpl = len(var.list_players()) - 1
        if lpl == 0:
            population = (" No more players remaining.")
        else:
            population = (" New player count: \u0002{0}\u0002").format(lpl)

    if what == "part" and (not var.PART_GRACE_TIME or var.PHASE == "join"):
        if var.get_role(nick) != "person" and var.ROLE_REVEAL:
            msg = ("\02{0}\02, a \02{1}\02, ate some poisonous berries and has "+
                   "died.{2}").format(nick, var.get_reveal_role(nick), population)
        else:
            msg = ("\02{0}\02 ate some poisonous berries and has died.{1}").format(nick, population)
    elif what == "quit" and (not var.QUIT_GRACE_TIME or var.PHASE == "join"):
        if var.get_role(nick) != "person" and var.ROLE_REVEAL:
            msg = ("\02{0}\02 was mauled by wild animals and has died. It seems that "+
                   "\02{1}\02 meat is tasty.{2}").format(nick, var.get_reveal_role(nick), population)
        else:
            msg = ("\02{0}\02 was mauled by wild animals and has died.{1}").format(nick, population)
    elif what != "kick":
        msg = "\u0002{0}\u0002 has gone missing.".format(nick)
        killplayer = False
    else:
        if var.get_role(nick) != "person" and var.ROLE_REVEAL:
            msg = ("\02{0}\02 died due to falling off a cliff. The "+
                   "\02{1}\02 is lost to the ravine forever.{2}").format(nick, var.get_reveal_role(nick), population)
        else:
            msg = ("\02{0}\02 died due to falling off a cliff.{1}").format(nick, population)
        make_stasis(nick, var.LEAVE_STASIS_PENALTY)
    cli.msg(botconfig.CHANNEL, msg)
    var.LOGGER.logMessage(msg.replace("\02", ""))
    if killplayer:
        del_player(cli, nick, death_triggers = False)
    else:
        var.DISCONNECTED[nick] = (cloak, datetime.now(), what)

#Functions decorated with hook do not parse the nick by default
hook("part")(lambda cli, nick, *rest: leave(cli, "part", nick, rest[0]))
hook("quit")(lambda cli, nick, *rest: leave(cli, "quit", nick, rest[0]))
hook("kick")(lambda cli, nick, *rest: leave(cli, "kick", rest[1]))


@cmd("quit", "leave")
def leave_game(cli, nick, chan, rest):
    """Quits the game."""
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    elif var.PHASE == "join":
        lpl = len(var.list_players()) - 1

        if lpl == 0:
            population = (" No more players remaining.")
        else:
            population = (" New player count: \u0002{0}\u0002").format(lpl)
    else:
        population = ""
    if nick not in var.list_players() or nick in var.DISCONNECTED.keys():  # not playing
        cli.notice(nick, "You're not currently playing.")
        return
    if var.get_role(nick) != "person" and var.ROLE_REVEAL:
        cli.msg(botconfig.CHANNEL, ("\02{0}\02, a \02{1}\02, has died of an unknown disease.{2}").format(nick, var.get_reveal_role(nick), population))
        var.LOGGER.logMessage(("{0}, a {1}, has died of an unknown disease.").format(nick, var.get_reveal_role(nick)))
    else:
        cli.msg(botconfig.CHANNEL, ("\02{0}\02 has died of an unknown disease.{1}").format(nick, population))
        var.LOGGER.logMessage(("{0} has died of an unknown disease.").format(nick))
    if var.PHASE != "join":
        for r, rlist in var.ORIGINAL_ROLES.items():
            if nick in rlist:
                var.ORIGINAL_ROLES[r].remove(nick)
                var.ORIGINAL_ROLES[r].append("(dced)"+nick)
        make_stasis(nick, var.LEAVE_STASIS_PENALTY)
        if nick in var.PLAYERS:
            var.DCED_PLAYERS[nick] = var.PLAYERS.pop(nick)

    del_player(cli, nick, death_triggers = False)

def begin_day(cli):
    chan = botconfig.CHANNEL

    # Reset nighttime variables
    var.GAMEPHASE = "day"
    var.KILLS = {}  # nicknames of kill victims (wolves only)
    var.OTHER_KILLS = {} # other kill victims (hunter/vengeful ghost/death totem)
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = []  # list of seers/oracles/augurs that have had visions
    var.HEXED = [] # list of hags that have silenced others
    var.SHAMANS = [] # list of shamans/crazed shamans that have acted
    var.OBSERVED = {}  # those whom werecrows/sorcerers have observed
    var.HVISITED = {} # those whom harlots have visited
    var.GUARDED = {}  # this whom bodyguards/guardian angels have guarded
    var.PASSED = [] # hunters that have opted not to kill
    var.STARTED_DAY_PLAYERS = len(var.list_players())
    var.SILENCED = copy.copy(var.TOBESILENCED)
    var.LYCANTHROPES = copy.copy(var.TOBELYCANTHROPES)
    var.LUCKY = copy.copy(var.TOBELUCKY)
    var.DISEASED = copy.copy(var.TOBEDISEASED)
    var.MISDIRECTED = copy.copy(var.TOBEMISDIRECTED)
    var.EXCHANGED = copy.copy(var.TOBEEXCHANGED)

    msg = ("The villagers must now vote for whom to lynch. "+
           'Use "{0}lynch <nick>" to cast your vote. {1} votes '+
           'are required to lynch.').format(botconfig.CMD_CHAR, len(var.list_players()) // 2 + 1)
    cli.msg(chan, msg)
    var.LOGGER.logMessage(msg)
    var.LOGGER.logBare("DAY", "BEGIN")

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

def night_warn(cli, gameid):
    if gameid != var.NIGHT_ID:
        return

    if var.PHASE == "day":
        return

    cli.msg(botconfig.CHANNEL, ("\02A few villagers awake early and notice it " +
                                "is still dark outside. " +
                                "The night is almost over and there are " +
                                "still whispers heard in the village.\02"))

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

    if not var.START_WITH_DAY or not var.FIRST_DAY:
        # In case people didn't act at night, clear appropriate variables
        if len(var.SHAMANS) < len(var.ROLES["shaman"] + var.ROLES["crazed shaman"]):
            for shaman in var.ROLES["shaman"]:
                if shaman not in var.SHAMANS:
                    var.LASTGIVEN[shaman] = None
            for shaman in var.ROLES["crazed shaman"]:
                if shaman not in var.SHAMANS:
                    var.LASTGIVEN[shaman] = None

        # bodyguard doesn't have restrictions, but being checked anyway since both GA and bodyguard use var.GUARDED
        if len(var.GUARDED.keys()) < len(var.ROLES["bodyguard"] + var.ROLES["guardian angel"]):
            for gangel in var.ROLES["guardian angel"]:
                if gangel not in var.GUARDED:
                    var.LASTGUARDED[gangel] = None

        if len(var.HEXED) < len(var.ROLES["hag"]):
            for hag in var.ROLES["hag"]:
                if hag not in var.HEXED:
                    var.LASTHEXED[hag] = None

        # Select a random target for vengeful ghost if they didn't kill
        wolves = var.list_players(var.WOLFTEAM_ROLES)
        villagers = var.list_players()
        for wolf in wolves:
            villagers.remove(wolf)
        for ghost, target in var.VENGEFUL_GHOSTS.items():
            if ghost not in var.OTHER_KILLS:
                if target == "wolves":
                    var.OTHER_KILLS[ghost] = random.choice(wolves)
                else:
                    var.OTHER_KILLS[ghost] = random.choice(villagers)

    # Reset daytime variables
    var.VOTES = {}
    var.INVESTIGATED = []
    var.WOUNDED = []
    var.DAY_START_TIME = datetime.now()
    var.NO_LYNCH = []
    var.DAY_COUNT += 1
    var.FIRST_DAY = (var.DAY_COUNT == 1)
    havetotem = copy.copy(var.LASTGIVEN)

    if var.START_WITH_DAY and var.FIRST_DAY:
        # TODO: need to message everyone their roles and give a short thing saying "it's daytime"
        # but this is good enough for now to prevent it from crashing
        begin_day(cli)
        return

    if (not len(var.SEEN)+len(var.KILLS)+len(var.OBSERVED) # neither seer nor wolf acted
            and not var.START_WITH_DAY and var.FIRST_NIGHT and (var.ROLES["seer"] or var.ROLES["oracle"] or var.ROLES["augur"]) and not botconfig.DEBUG_MODE):
        cli.msg(botconfig.CHANNEL, "\02The wolves all die of a mysterious plague.\02")
        for x in var.ROLES["traitor"] + var.list_players(var.WOLF_ROLES):
            if not del_player(cli, x, True, death_triggers = False):
                return

    td = var.DAY_START_TIME - var.NIGHT_START_TIME
    var.NIGHT_START_TIME = None
    var.NIGHT_TIMEDELTA += td
    min, sec = td.seconds // 60, td.seconds % 60

    found = {}
    for v in var.KILLS.values():
        for p in v:
            if p in found:
                found[p] += 1
            else:
                found[p] = 1

    maxc = 0
    victims = []
    killers = {} # dict of victim: list of killers (for retribution totem)
    bywolves = set() # wolves targeted, others may have as well (needed for harlot visit and maybe other things)
    onlybywolves = set() # wolves and nobody else targeted (needed for lycan)
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
        if victim in killers:
            killers[victim].append("@wolves") # special key to let us know to randomly select a wolf
        else:
            killers[victim] = ["@wolves"]

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
            if victim in killers:
                killers[victim].append("@wolves") # special key to let us know to randomly select a wolf
            else:
                killers[victim] = ["@wolves"]

    for monster in var.ROLES["monster"]:
        if monster in victims:
            victims.remove(monster)
            bywolves.discard(monster)
            onlybywolves.discard(monster)

    wolfghostvictims = []
    for ghost, target in var.VENGEFUL_GHOSTS.items():
        if target == "villagers":
            victim = var.OTHER_KILLS[ghost]
            if victim in killers:
                killers[victim].append(ghost)
            else:
                killers[victim] = [ghost]
            if victim not in var.DYING: # wolf ghost killing ghost will take precedence over everything except death totem and elder
                wolfghostvictims.append(victim)

    for k, d in var.OTHER_KILLS.items():
        victims.append(d)
        onlybywolves.discard(d)
        if d in killers:
            killers[d].append(k)
        else:
            killers[d] = [k]
    for d in var.DYING:
        victims.append(d)
        onlybywolves.discard(d)
        for s, v in var.LASTGIVEN.items():
            if v == d and var.TOTEMS[s] == "death":
                if d in killers:
                    killers[d].append(s)
                else:
                    killers[d] = [s]
    victims_set = set(victims) # remove duplicates
    victims_set.discard(None) # in the event that ever happens
    victims = []
    vappend = []
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
    if var.FIRST_NIGHT:
        for clone in var.ROLES["clone"]:
            if clone not in var.CLONED:
                ps = pl[:]
                ps.remove(clone)
                for victim in victims:
                    if victim in ps:
                        ps.remove(victim)
                if len(ps) > 0:
                    target = random.choice(ps)
                    var.CLONED[clone] = target
                    pm(cli, clone, "Because you forgot to select someone to clone at night, you are now cloning \u0002{0}\u0002.".format(target))


    message = [("Night lasted \u0002{0:0>2}:{1:0>2}\u0002. It is now daytime. "+
               "The villagers awake, thankful for surviving the night, "+
               "and search the village... ").format(min, sec)]

    # This needs to go down here since having them be their night value matters above
    var.ANGRY_WOLVES = False
    var.DISEASED_WOLVES = False

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
    for victim in vlist:
        if victim in var.PROTECTED and victim not in var.DYING:
            message.append(("\u0002{0}\u0002 was attacked last night, but their totem " +
                            "emitted a brilliant flash of light, blinding the attacker and " +
                            "allowing them to escape.").format(victim))
            novictmsg = False
        elif victim in var.GUARDED.values() and victim not in var.DYING:
            for gangel in var.ROLES["guardian angel"]:
                if var.GUARDED.get(gangel) == victim:
                    message.append(("\u0002{0}\u0002 was attacked last night, but luckily, the guardian angel was on duty.").format(victim))
                    novictmsg = False
                    break
            else:
                for bodyguard in var.ROLES["bodyguard"]:
                    if var.GUARDED.get(bodyguard) == victim:
                        dead.append(bodyguard)
                        message.append(("\u0002{0}\u0002 sacrificed their life to guard that of another.").format(bodyguard))
                        novictmsg = False
                        break
        elif victim in var.ROLES["harlot"] and var.HVISITED.get(victim) and victim not in var.DYING and victim not in dead:
            if victim in onlybywolves:
                message.append("The wolves' selected victim was a harlot, who was not at home last night.")
                novictmsg = False
            bywolves.discard(victim)
            onlybywolves.discard(victim)
        elif (victim in var.ROLES["lycan"] or victim in var.LYCANTHROPES) and victim in onlybywolves:
            message.append("A chilling howl was heard last night. It appears there is another werewolf in our midst!")
            pm(cli, victim, 'HOOOOOOOOOWL. You have become... a wolf!')
            vrole = var.get_role(victim)
            var.ROLES[vrole].remove(victim)
            var.ROLES["wolf"].append(victim)
            var.LYCANS.append(victim)
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
                    if var.ROLE_REVEAL:
                        role = var.get_reveal_role(loser)
                        an = "n" if role[0] in ("a", "e", "i", "o", "u") else ""
                        message.append(("\u0002{0}\u0002's totem emitted a brilliant flash of light last night. " +
                                        "The dead body of \u0002{1}\u0002, a{2} \u0002{3}\u0002, was found at the scene.").format(victim, loser, an, role))
                    else:
                        message.append(("\u0002{0}\u0002's totem emitted a brilliant flash of light last night. " +
                                        "The dead body of \u0002{1}\u0002 was found at the scene.").format(victim, loser))
                var.LOGGER.logBare(loser, "RETRIBUTION")
            if var.ROLE_REVEAL:
                role = var.get_reveal_role(victim)
                an = "n" if role[0] in ("a", "e", "i", "o", "u") else ""
                message.append(("The dead body of \u0002{0}\u0002, a{1} \u0002{2}\u0002, is found. " +
                                "Those remaining mourn the tragedy.").format(victim, an, role))
            else:
                message.append(("The dead body of \u0002{0}\u0002 is found. " +
                                "Those remaining mourn the tragedy.").format(victim))
            dead.append(victim)
            var.LOGGER.logBare(victim, "KILLED")
            if random.random() < 1/50:
                message.append(random.choice(
                    ["https://i.imgur.com/nO8rZ.gif",
                    "https://i.imgur.com/uGVfZ.gif",
                    "https://i.imgur.com/mUcM09n.gif",
                    "https://i.imgur.com/P7TEGyQ.gif",
                    "https://i.imgur.com/b8HAvjL.gif",
                    "https://i.imgur.com/PIIfL15.gif"]
                    ))
            
            if victim in var.HVISITED.values() and victim in bywolves:  #  victim was visited by some harlot and victim was attacked by wolves
                for hlt in var.HVISITED.keys():
                    if var.HVISITED[hlt] == victim:
                        message.append(("\02{0}\02, a \02harlot\02, made the unfortunate mistake of "+
                                        "visiting the victim's house last night and is "+
                                        "now dead.").format(hlt))
                        bywolves.add(hlt)
                        onlybywolves.add(hlt)
                        dead.append(hlt)

    if novictmsg and len(dead) == 0:
        message.append(random.choice(var.NO_VICTIMS_MESSAGES) + " All villagers, however, have survived.")

    for harlot in var.ROLES["harlot"]:
        if var.HVISITED.get(harlot) in var.list_players(var.WOLF_ROLES) and harlot not in dead:
            message.append(("\02{0}\02, a \02harlot\02, made the unfortunate mistake of "+
                            "visiting a wolf's house last night and is "+
                            "now dead.").format(harlot))
            bywolves.add(harlot)
            onlybywolves.add(harlot)
            dead.append(harlot)
    for bodyguard in var.ROLES["bodyguard"]:
        if var.GUARDED.get(bodyguard) in var.list_players(var.WOLF_ROLES) and bodyguard not in dead:
            bywolves.add(bodyguard)
            onlybywolves.add(bodyguard)
            r = random.random()
            if r < var.BODYGUARD_DIES_CHANCE:
                if var.ROLE_REVEAL:
                    message.append(("\02{0}\02, a \02bodyguard\02, "+
                                    "made the unfortunate mistake of guarding a wolf "+
                                    "last night, and is now dead.").format(bodyguard))
                else:
                    message.append(("\02{0}\02 "+
                                    "made the unfortunate mistake of guarding a wolf "+
                                    "last night, and is now dead.").format(bodyguard))
                var.LOGGER.logBare(bodyguard, "KILLEDWHENGUARDINGWOLF")
                dead.append(bodyguard)
    for gangel in var.ROLES["guardian angel"]:
        if var.GUARDED.get(gangel) in var.list_players(var.WOLF_ROLES) and gangel not in dead:
            bywolves.add(gangel)
            onlybywolves.add(gangel)
            r = random.random()
            if r < var.GUARDIAN_ANGEL_DIES_CHANCE:
                if var.ROLE_REVEAL:
                    message.append(("\02{0}\02, a \02guardian angel\02, "+
                                    "made the unfortunate mistake of guarding a wolf "+
                                    "last night, and is now dead.").format(gangel))
                else:
                    message.append(("\02{0}\02 "+
                                    "made the unfortunate mistake of guarding a wolf "+
                                    "last night, and is now dead.").format(gangel))
                var.LOGGER.logBare(gangel, "KILLEDWHENGUARDINGWOLF")
                dead.append(gangel)

    for victim in list(dead):
        if victim in var.GUNNERS.keys() and var.GUNNERS[victim] > 0 and victim in bywolves:
            if random.random() < var.GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE:
                wc = var.ROLES["werecrow"][:]
                for crow in wc:
                    if crow in var.OBSERVED.keys():
                        wc.remove(crow)
                # don't kill off werecrows that observed
                deadwolf = random.choice(var.ROLES["wolf"]+var.ROLES["wolf cub"]+wc)
                if deadwolf not in dead:
                    if var.ROLE_REVEAL:
                        message.append(("Fortunately, \02{0}\02 had bullets and "+
                                        "\02{1}\02, a \02{2}\02, was shot dead.").format(victim, deadwolf, var.get_reveal_role(deadwolf)))
                    else:
                        message.append(("Fortunately, \02{0}\02 had bullets and "+
                                        "\02{1}\02 was shot dead.").format(victim, deadwolf))
                    var.LOGGER.logBare(deadwolf, "KILLEDBYGUNNER")
                    dead.append(deadwolf)
                    var.GUNNERS[victim] -= 1 # deduct the used bullet

    for victim in dead:
        if victim in bywolves and victim in var.DISEASED:
            var.DISEASED_WOLVES = True

        if var.WOLF_STEALS_GUN and victim in bywolves and victim in var.GUNNERS.keys() and var.GUNNERS[victim] > 0:
            # victim has bullets
            try:
                while True:
                    guntaker = random.choice(var.list_players(var.WOLFCHAT_ROLES))  # random looter
                    if guntaker not in dead:
                        break
                numbullets = var.GUNNERS[victim]
                var.WOLF_GUNNERS[guntaker] = 1  # transfer bullets a wolf
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
    for msg in message:
        var.LOGGER.logMessage(msg.replace("\02", ""))

    for deadperson in dead:  # kill each player, but don't end the game if one group outnumbers another
        # take a shortcut for killer_role here since vengeful ghost only cares about team and not particular roles
        # this will have to be modified to track the actual killer if that behavior changes
        # we check if they have already been killed as well since del_player could do chain reactions and we want
        # to avoid sending duplicate messages.
        if deadperson in var.list_players():
            del_player(cli, deadperson, end_game = False, killer_role = "wolf" if deadperson in onlybywolves or deadperson in wolfghostvictims else "villager", deadlist = dead, original = deadperson)

    message = []
    for havetotem in havetotem.values():
        if havetotem:
            message.append("\u0002{0}\u0002 seem{1} to be in possession of a mysterious totem...".format(havetotem, "ed" if havetotem in dead else "s"))
    cli.msg(chan, "\n".join(message))
    for msg in message:
        var.LOGGER.logMessage(msg.replace("\02", ""))
    
    if chk_win(cli):  # if after the last person is killed, one side wins, then actually end the game here
        return

    begin_day(cli)

def chk_nightdone(cli):
    # TODO: alphabetize and/or arrange sensibly
    actedcount  = len(var.SEEN + list(var.HVISITED.keys()) + list(var.GUARDED.keys()) +
                      list(var.KILLS.keys()) + list(var.OTHER_KILLS.keys()) +
                      list(var.OBSERVED.keys()) + var.PASSED + var.HEXED + var.SHAMANS +
                      list(var.TARGETED.keys()))
    nightroles = (var.ROLES["seer"] + var.ROLES["oracle"] + var.ROLES["harlot"] +
                  var.ROLES["bodyguard"] + var.ROLES["guardian angel"] + var.ROLES["wolf"] +
                  var.ROLES["werecrow"] + var.ROLES["sorcerer"] + var.ROLES["hunter"] +
                  list(var.VENGEFUL_GHOSTS.keys()) + var.ROLES["hag"] + var.ROLES["shaman"] +
                  var.ROLES["crazed shaman"] + var.ROLES["assassin"] + var.ROLES["augur"])
    if var.FIRST_NIGHT:
        actedcount += len(var.MATCHMAKERS + list(var.CLONED.keys()))
        nightroles += var.ROLES["matchmaker"] + var.ROLES["clone"]

    if var.DISEASED_WOLVES:
        nightroles = [p for p in nightroles if p not in var.ROLES["wolf"]]

    for p in var.HUNTERS:
        # only remove one instance of their name if they have used hunter ability, in case they have templates
        # the OTHER_KILLS check ensures we only remove them if they acted in a *previous* night
        if p in nightroles and p not in var.OTHER_KILLS:
            nightroles.remove(p)

    # but remove all instances of their name if they are silenced
    nightroles = [p for p in nightroles if p not in var.SILENCED]

    playercount = len(nightroles) + var.ACTED_EXTRA

    if var.PHASE == "night" and actedcount >= playercount:
        if not var.DISEASED_WOLVES:
            # flatten var.KILLS
            kills = set()
            for ls in var.KILLS.values():
                if not isinstance(ls, str):
                    for v in ls:
                        kills.add(v)
                else:
                    kills.add(ls)
            # check if wolves are actually agreeing
            # allow len(kills) == 0 through as that means that crow was dumb and observed instead
            # of killing or something, or weird cases where there are no wolves at night
            if not var.ANGRY_WOLVES and len(kills) > 1:
                return
            elif var.ANGRY_WOLVES and (len(kills) == 1 or len(kills) > 2):
                return

        for x, t in var.TIMERS.items():
            t[0].cancel()

        var.TIMERS = {}
        if var.PHASE == "night":  # Double check
            transition_day(cli)

@cmd("nolynch", "nl", "novote", "nv", "abstain", "abs")
def no_lynch(cli, nick, chan, rest):
    """Allows you to abstain from voting for the day."""
    if chan == botconfig.CHANNEL:
        if var.PHASE in ("none", "join"):
            cli.notice(nick, "No game is currently running.")
            return
        elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
            cli.notice(nick, "You're not currently playing.")
            return
        elif not var.ABSTAIN_ENABLED:
            cli.notice(nick, "This command has been disabled by the admins.")
            return
        elif var.LIMIT_ABSTAIN and var.ABSTAINED:
            cli.notice(nick, "The village has already abstained once this game and may not do so again.")
            return
        elif var.LIMIT_ABSTAIN and var.FIRST_DAY:
            cli.notice(nick, "The village may not abstain on the first day.")
            return
        elif var.PHASE != "day":
            cli.notice(nick, "Lynching is only during the day. Please wait patiently for morning.")
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
        if nick not in var.NO_LYNCH and nick not in var.IMPATIENT:
            var.NO_LYNCH.append(nick)
        cli.msg(chan, "\u0002{0}\u0002 votes to not lynch anyone today.".format(nick))
        
        chk_decision(cli)
        return

@cmd("lynch", "vote", "v")
def vote(cli, nick, chann_, rest):
    """Use this to vote for a candidate to be lynched."""
    chan = botconfig.CHANNEL

    rest = re.split(" +",rest)[0].strip().lower()

    if not rest:
        show_votes(cli, nick, chan, rest)
        return
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    if var.PHASE != "day":
        cli.notice(nick, ("Lynching is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return
    if nick in var.WOUNDED:
        cli.msg(chan, ("{0}: You are wounded and resting, "+
                      "thus you are unable to vote for the day.").format(nick))
        return
    if nick in var.ASLEEP:
        pm(cli, nick, "As you place your vote, your totem emits a brilliant flash of light. " +
                      "After recovering, you notice that you are still in your bed. " +
                      "That entire sequence of events must have just been a dream...")
        return
    if nick in var.NO_LYNCH:
        var.NO_LYNCH.remove(nick)

    pl = var.list_players()
    pl_l = [x.strip().lower() for x in pl]

    matches = 0
    for player in pl_l:
        if rest == player:
            target = player
            break
        if player.startswith(rest):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(rest))
            return

    voted = pl[pl_l.index(target)]

    if not var.SELF_LYNCH_ALLOWED:
        if nick == voted:
            if nick in var.ROLES["fool"] or nick in var.ROLES["jester"]:
                cli.notice(nick, "You may not vote yourself.")
            else:
                cli.notice(nick, "Please try to save yourself.")
            return

    lcandidates = list(var.VOTES.keys())
    for voters in lcandidates:  # remove previous vote
        if nick in var.VOTES[voters]:
            var.VOTES[voters].remove(nick)
            if not var.VOTES.get(voters) and voters != voted:
                del var.VOTES[voters]
            break
    if voted not in var.VOTES.keys():
        var.VOTES[voted] = [nick]
    else:
        var.VOTES[voted].append(nick)
    cli.msg(chan, ("\u0002{0}\u0002 votes for "+
                   "\u0002{1}\u0002.").format(nick, voted))
    var.LOGGER.logMessage("{0} votes for {1}.".format(nick, voted))
    var.LOGGER.logBare(voted, "VOTED", nick)

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
    if nick in var.EXCHANGED:
        var.EXCHANGED.remove(nick)
        actor_role = var.get_role(actor)
        nick_role = var.get_role(nick)
        
        if actor_role == "amnesiac":
            actor_role = var.FINAL_ROLES[actor]
        elif actor_role == "clone":
            if actor in var.CLONED:
                actor_target = var.CLONED[actor]
                del var.CLONED[actor]
        elif actor_role in ("shaman", "crazed shaman"):
            actor_totem = var.TOTEMS[actor]
            del var.TOTEMS[actor]
            if actor in var.SHAMANS:
                var.ACTED_EXTRA += 1
                var.SHAMANS.remove(actor)
            if actor in var.LASTGIVEN:
                del var.LASTGIVEN[actor]
        elif actor_role == "wolf":
            if actor in var.KILLS:
                del var.KILLS[actor]
        elif actor_role == "hunter":
            if actor in var.OTHER_KILLS:
                var.ACTED_EXTRA += 1
            if actor in var.HUNTERS:
                var.HUNTERS.remove(actor)
            if actor in var.PASSED:
                var.PASSED.remove(actor)
        elif actor_role in ("bodyguard", "guardian angel"):
            if actor in var.GUARDED:
                pm(cli, var.GUARDED[actor], "Your protector seems to have disappeared...")
                del var.GUARDED[actor]
            if actor in var.LASTGUARDED:
                del var.LASTGUARDED[actor]
        elif actor_role in ("werecrow", "sorcerer"):
            if actor in var.OBSERVED:
                del var.OBSERVED[actor]
            if actor in var.KILLS:
                del var.KILLS[actor]
        elif actor_role == "harlot":
            if actor in var.HVISITED:
                pm(cli, var.HVISITED[actor], "\u0002{0}\u0002 seems to have disappeared...".format(actor))
                del var.HVISITED[actor]
        elif actor_role in ("seer", "oracle", "augur"):
            if actor in var.SEEN:
                var.SEEN.remove(actor)
        elif actor_role == "hag":
            if actor in var.LASTHEXED:
                if var.LASTHEXED[actor] in var.TOBESILENCED and actor in var.HEXED:
                    var.TOBESILENCED.remove(var.LASTHEXED[actor])
                del var.LASTHEXED[actor]
            if actor in var.HEXED:
                var.HEXED.remove(actor)

        if nick_role == "amnesiac":
            nick_role = var.FINAL_ROLES[nick]
        elif nick_role == "clone":
            if nick in var.CLONED:
                nick_target = var.CLONED[nick]
                del var.CLONED[nick]
        elif nick_role in ("shaman", "crazed shaman"):
            nick_totem = var.TOTEMS[nick]
            del var.TOTEMS[nick]
            if nick in var.SHAMANS:
                var.ACTED_EXTRA += 1
                var.SHAMANS.remove(nick)
            if nick in var.LASTGIVEN:
                del var.LASTGIVEN[nick]
        elif nick_role == "wolf":
            if nick in var.KILLS:
                del var.KILLS[nick]
        elif nick_role == "hunter":
            if nick in var.OTHER_KILLS:
                var.ACTED_EXTRA += 1
            if nick in var.HUNTERS:
                var.HUNTERS.remove(nick)
            if nick in var.PASSED:
                var.PASSED.remove(nick)
        elif nick_role in ("bodyguard", "guardian angel"):
            if nick in var.GUARDED:
                pm(cli, var.GUARDED[nick], "Your protector seems to have disappeared...")
                del var.GUARDED[nick]
            if nick in var.LASTGUARDED:
                del var.LASTGUARDED[nick]
        elif nick_role in ("werecrow", "sorcerer"):
            if nick in var.OBSERVED:
                del var.OBSERVED[nick]
            if nick in var.KILLS:
                del var.KILLS[nick]
        elif nick_role == "harlot":
            if nick in var.HVISITED:
                pm(cli, var.HVISITED[nick], "\u0002{0}\u0002 seems to have disappeared...".format(nick))
                del var.HVISITED[nick]
        elif nick_role in ("seer", "oracle", "augur"):
            if nick in var.SEEN:
                var.SEEN.remove(nick)
        elif nick_role == "hag":
            if nick in var.LASTHEXED:
                if var.LASTHEXED[nick] in var.TOBESILENCED and nick in var.HEXED:
                    var.TOBESILENCED.remove(var.LASTHEXED[nick])
                del var.LASTHEXED[nick]
            if nick in var.HEXED:
                var.HEXED.remove(nick)
            
        var.FINAL_ROLES[actor] = nick_role
        var.FINAL_ROLES[nick] = actor_role
        var.ROLES[actor_role].append(nick)
        var.ROLES[actor_role].remove(actor)
        var.ROLES[nick_role].append(actor)
        var.ROLES[nick_role].remove(nick)

        actor_rev_role = actor_role
        if actor_role == "vengeful ghost":
            actor_rev_role = var.DEFAULT_ROLE
        elif actor_role in ("village elder", "time lord"):
            actor_rev_role = "villager"

        nick_rev_role = nick_role
        if nick_role == "vengeful ghost":
            nick_rev_role = var.DEFAULT_ROLE
        elif actor_role in ("village elder", "time lord"):
            nick_rev_role = "villager"

        # don't say who, since misdirection/luck totem may have switched it
        # and this makes life far more interesting
        pm(cli, actor, "You have exchanged roles with someone! You are now a \u0002{0}\u0002.".format(nick_rev_role))
        pm(cli, nick,  "You have exchanged roles with someone! You are now a \u0002{0}\u0002.".format(actor_rev_role))

        if nick_role == "clone":
            pm(cli, actor, "You are cloning \u0002{0}\u0002.".format(nick_target))
        elif nick_role in ("shaman", "crazed shaman"):
            if nick_role == "shaman":
                pm(cli, actor, "You have a \u0002{0}\u0002 totem.".format(nick_totem))
            var.TOTEMS[actor] = nick_totem
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
            if var.DISEASED_WOLVES:
                pm(cli, actor, 'You are feeling ill tonight, and are unable to kill anyone.')
            elif var.ANGRY_WOLVES and actor_role in ("wolf", "werecrow"):
                pm(cli, actor, 'You are \u0002angry\u0002 tonight, and may kill two targets by using "kill <nick1> and <nick2>".')
        elif nick_role == "minion":
            wolves = var.list_players(var.WOLF_ROLES)
            random.shuffle(wolves)
            pm(cli, actor, "Wolves: " + ", ".join(wolves))

        if actor_role == "clone":
            pm(cli, nick, "You are cloning \u0002{0}\u0002.".format(actor_target))
        elif actor_role in ("shaman", "crazed shaman"):
            if actor_role == "shaman":
                pm(cli, nick, "You have a \u0002{0}\u0002 totem.".format(actor_totem))
            var.TOTEMS[nick] = actor_totem
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
            if var.DISEASED_WOLVES:
                pm(cli, nick, 'You are feeling ill tonight, and are unable to kill anyone.')
            elif var.ANGRY_WOLVES and nick_role in ("wolf", "werecrow"):
                pm(cli, nick, 'You are \u0002angry\u0002 tonight, and may kill two targets by using "kill <nick1> and <nick2>".')
        elif actor_role == "minion":
            wolves = var.list_players(var.WOLF_ROLES)
            random.shuffle(wolves)
            pm(cli, nick, "Wolves: " + ", ".join(wolves))

        return True
    return False

@cmd("retract")
def retract(cli, nick, chann_, rest):
    """Takes back your vote during the day (for whom to lynch)."""

    chan = botconfig.CHANNEL

    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return

    if var.PHASE != "day":
        cli.notice(nick, ("Lynching is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return
    if nick in var.NO_LYNCH:
        var.NO_LYNCH.remove(nick)
        cli.msg(chan, "\u0002{0}\u0002's vote was retracted.".format(nick))
        var.LOGGER.logBare(nick, "RETRACT")
        var.LOGGER.logMessage("{0}'s vote was retracted.".format(nick))
        var.LAST_VOTES = None # reset
        return

    candidates = var.VOTES.keys()
    for voter in list(candidates):
        if nick in var.VOTES[voter]:
            var.VOTES[voter].remove(nick)
            if not var.VOTES[voter]:
                del var.VOTES[voter]
            cli.msg(chan, "\u0002{0}\u0002's vote was retracted.".format(nick))
            var.LOGGER.logBare(voter, "RETRACT", nick)
            var.LOGGER.logMessage("{0}'s vote was retracted.".format(nick))
            var.LAST_VOTES = None # reset
            break
    else:
        cli.notice(nick, "You haven't voted yet.")

@pmcmd("retract")
def wolfretract(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return

    role = var.get_role(nick)
    if role not in ("wolf", "werecrow", "hunter") and nick not in var.VENGEFUL_GHOSTS.keys():
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only retract at night.")
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
    elif role not in var.WOLF_ROLES and nick in var.OTHER_KILLS.keys():
        del var.OTHER_KILLS[nick]
        var.HUNTERS.remove(nick)
    pm(cli, nick, "You have retracted your vote.")
    #var.LOGGER.logBare(nick, "RETRACT", nick)

@cmd("shoot")
def shoot(cli, nick, chann_, rest):
    """Use this to fire off a bullet at someone in the day if you have bullets."""

    chan = botconfig.CHANNEL
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return

    if var.PHASE != "day":
        cli.notice(nick, ("Shooting is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return
    if nick not in var.GUNNERS.keys() and nick not in var.WOLF_GUNNERS.keys():
        pm(cli, nick, "You don't have a gun.")
        return
    elif ((nick in var.GUNNERS.keys() and not var.GUNNERS[nick]) or
          (nick in var.WOLF_GUNNERS.keys() and not var.WOLF_GUNNERS[nick])):
        pm(cli, nick, "You don't have any more bullets.")
        return
    elif nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    if not victim:
        cli.notice(nick, "Not enough parameters")
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]
    if victim == nick:
        cli.notice(nick, "You are holding it the wrong way.")
        return

    # get actual victim
    victim = choose_target(nick, victim)

    wolfshooter = nick in var.list_players(var.WOLFCHAT_ROLES)

    if wolfshooter and nick in var.WOLF_GUNNERS:
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
    if rand <= chances[0] and not (wolfshooter and wolfvictim):  # didn't miss or suicide
        # and it's not a wolf shooting another wolf

        cli.msg(chan, ("\u0002{0}\u0002 shoots \u0002{1}\u0002 with "+
                       "a silver bullet!").format(nick, victim))
        var.LOGGER.logMessage("{0} shoots {1} with a silver bullet!".format(nick, victim))
        realrole = var.get_role(victim)
        victimrole = var.get_reveal_role(victim)
        if realrole in var.WOLF_ROLES:
            if var.ROLE_REVEAL:
                cli.msg(chan, ("\u0002{0}\u0002 is a \u0002{1}\u0002, and is dying from "+
                               "the silver bullet.").format(victim, victimrole))
                var.LOGGER.logMessage(("{0} is a {1}, and is dying from the "+
                                "silver bullet.").format(victim, victimrole))
            else:
                cli.msg(chan, ("\u0002{0}\u0002 is a wolf, and is dying from "+
                               "the silver bullet.").format(victim))
                var.LOGGER.logMessage(("{0} is a wolf, and is dying from the "+
                                "silver bullet.").format(victim))
            if not del_player(cli, victim, killer_role = var.get_role(nick)):
                return
        elif random.random() <= chances[3]:
            accident = "accidentally "
            if nick in var.ROLES["sharpshooter"]:
                accident = "" # it's an accident if the sharpshooter DOESN'T headshot :P
            cli.msg(chan, ("\u0002{0}\u0002 is not a wolf "+
                           "but was {1}fatally injured.").format(victim, accident))
            var.LOGGER.logMessage("{0} is not a wolf but was {1}fatally injured.".format(victim, accident))
            if var.ROLE_REVEAL:
                an = "n" if victimrole[0] in ("a", "e", "i", "o", "u") else ""
                cli.msg(chan, "The village has sacrificed a{0} \u0002{1}\u0002.".format(an, victimrole))
                var.LOGGER.logMessage("The village has sacrificed a {0}.".format(victimrole))
            if not del_player(cli, victim, killer_role = var.get_role(nick)):
                return
        else:
            cli.msg(chan, ("\u0002{0}\u0002 is a villager and was injured. Luckily "+
                          "the injury is minor and will heal after a day of "+
                          "rest.").format(victim))
            var.LOGGER.logMessage(("{0} is a villager and was injured. Luckily "+
                          "the injury is minor and will heal after a day of "+
                          "rest.").format(victim))
            if victim not in var.WOUNDED:
                var.WOUNDED.append(victim)
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
        var.LOGGER.logMessage("{0} is a lousy shooter and missed!".format(nick))
    else:
        if var.ROLE_REVEAL:
            cli.msg(chan, ("Oh no! \u0002{0}\u0002's gun was poorly maintained and has exploded! "+
                           "The village mourns a gunner-\u0002{1}\u0002.").format(nick, var.get_reveal_role(nick)))
            var.LOGGER.logMessage(("Oh no! {0}'s gun was poorly maintained and has exploded! "+
                           "The village mourns a gunner-{1}.").format(nick, var.get_reveal_role(nick)))
        else:
            cli.msg(chan, ("Oh no! \u0002{0}\u0002's gun was poorly maintained and has exploded!").format(nick))
            var.LOGGER.logMessage(("Oh no! {0}'s gun was poorly maintained and has exploded!").format(nick))
        if not del_player(cli, nick, killer_role = "villager"): # blame explosion on villager's shoddy gun construction or something
            return  # Someone won.



@pmcmd("kill")
def kill(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif (nick not in var.VENGEFUL_GHOSTS.keys() and nick not in var.list_players()) or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    try:
        role = var.get_role(nick)
    except KeyError:
        role = None
    if role in var.WOLFCHAT_ROLES and role not in ("wolf", "werecrow"):
        return  # they do this a lot.
    if role not in ("wolf", "werecrow", "hunter") and nick not in var.VENGEFUL_GHOSTS.keys():
        pm(cli, nick, "Only a wolf, hunter, or dead vengeful ghost may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only kill people at night.")
        return
    if role == "hunter" and nick in var.HUNTERS and nick not in var.OTHER_KILLS:
        # they are a hunter and did not kill this night (if they killed this night, this allows them to switch)
        pm(cli, nick, "You have already killed someone this game.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    if role in ("wolf", "werecrow") and var.DISEASED_WOLVES:
        pm(cli, nick, "You are feeling ill, and are unable to kill anyone tonight.")
        return
    pieces = [p.strip().lower() for p in re.split(" +",rest)]
    victim = pieces[0]
    victim2 = None
    if role in ("wolf", "werecrow") and var.ANGRY_WOLVES:
        try:
            if pieces[1] == "and":
                victim2 = pieces[2]
            else:
                victim2 = pieces[1]
        except IndexError:
            victim2 = None
    if not victim:
        pm(cli, nick, "Not enough parameters")
        return
    if role == "werecrow":  # Check if flying to observe
        if var.OBSERVED.get(nick):
            pm(cli, nick, ("You have already transformed into a crow; therefore, "+
                           "you are physically unable to kill a villager."))
            return
    pl = var.list_players()
    allwolves = var.list_players(var.WOLFTEAM_ROLES)
    allvills = []
    for p in pl:
        if p not in allwolves:
            allvills.append(p)
    pll = [x.lower() for x in pl]

    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]

    if victim2 != None:
        matches = 0
        for player in pll:
            if victim2 == player:
                target = player
                break
            if player.startswith(victim2):
                target = player
                matches += 1
        else:
            if matches != 1:
                pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(victim2))
                return
        victim2 = pl[pll.index(target)]

    if victim == nick or victim2 == nick:
        if nick in var.VENGEFUL_GHOSTS.keys():
            pm(cli, nick, "You are already dead.")
        else:
            pm(cli, nick, "Suicide is bad. Don't do it.")
        return

    if nick in var.VENGEFUL_GHOSTS.keys():
        if var.VENGEFUL_GHOSTS[nick] == "wolves" and victim not in allwolves:
            pm(cli, nick, "You must target a wolf.")
            return
        elif var.VENGEFUL_GHOSTS[nick] == "villagers" and victim not in allvills:
            pm(cli, nick, "You must target a villager.")
            return

    if role in ("wolf", "werecrow"):
        if victim in var.list_players(var.WOLFCHAT_ROLES) or victim2 in var.list_players(var.WOLFCHAT_ROLES):
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
            if nick not in var.HUNTERS:
                var.HUNTERS.append(nick)
            if nick in var.PASSED:
                var.PASSED.remove(nick)

    if victim2 != None:
        pm(cli, nick, "You have selected \u0002{0}\u0002 and \u0002{1}\u0002 to be killed.".format(victim, victim2))
        var.LOGGER.logBare(nick, "SELECT", victim)
        var.LOGGER.logBare(nick, "SELECT", victim2)
    else:
        pm(cli, nick, "You have selected \u0002{0}\u0002 to be killed.".format(victim))
        var.LOGGER.logBare(nick, "SELECT", victim)
        if var.ANGRY_WOLVES and role in ("wolf", "werecrow"):
            pm(cli, nick, "You are angry tonight and may kill a second target. Use kill <nick1> and <nick2> to select multiple targets.")
    chk_nightdone(cli)

@pmcmd("guard", "protect", "save")
def guard(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    role = var.get_role(nick)
    if role not in ("bodyguard", "guardian angel"):
        pm(cli, nick, "Only a bodyguard or guardian angel may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only protect people at night.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    if not victim:
        pm(cli, nick, "Not enough parameters")
        return
    if var.GUARDED.get(nick):
        pm(cli, nick, "You are already protecting someone tonight.")
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]
    if role == "guardian angel" and var.LASTGUARDED.get(nick) == victim:
        pm(cli, nick, ("You protected \u0002{0}\u0002 last night. " +
                       "You cannot protect the same person two nights in a row.").format(victim))
        return
    if victim == nick:
        if role == "bodyguard" or not var.GUARDIAN_ANGEL_CAN_GUARD_SELF:
            var.GUARDED[nick] = None
            if nick in var.LASTGUARDED:
                del var.LASTGUARDED[nick]
            pm(cli, nick, "You have chosen not to guard anyone tonight.")
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
        var.LOGGER.logBare(var.GUARDED[nick], "GUARDED", nick)
    chk_nightdone(cli)



@pmcmd("observe")
def observe(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    role = var.get_role(nick)
    if role not in ("werecrow", "sorcerer"):
        pm(cli, nick, "Only a werecrow or sorcerer may use this command.")
        return
    if var.PHASE != "night":
        if role == "werecrow":
            pm(cli, nick, "You may only transform into a crow at night.")
        else:
            pm(cli, nick, "You may only observe at night.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    victim = re.split(" +", rest)[0].strip().lower()
    if not victim:
        pm(cli, nick, "Not enough parameters")
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]
    if victim == nick.lower():
        if role == "werecrow":
            pm(cli, nick, "Instead of doing that, you should probably go kill someone.")
        else:
            pm(cli, nick, "That would be a waste.")
        return
    if nick in var.OBSERVED.keys():
        if role == "werecrow":
            pm(cli, nick, "You are already flying to \02{0}\02's house.".format(var.OBSERVED[nick]))
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
    elif role == "sorcerer":
        vrole = var.get_role(victim)
        if vrole == "amnesiac":
            vrole = var.FINAL_ROLES[victim]
        if vrole in ("seer", "oracle", "augur", "sorcerer"):
            an = "n" if vrole[0] in ("a", "e", "i", "o", "u") else ""
            pm(cli, nick, ("After casting your ritual, you determine that \u0002{0}\u0002 " +
                           "is a{1} \u0002{2}\u0002!").format(victim, an, vrole))
        else:
            pm(cli, nick, ("After casting your ritual, you determine that \u0002{0}\u0002 " +
                           "does not have paranormal senses.").format(victim))
    var.LOGGER.logBare(victim, "OBSERVED", nick)
    chk_nightdone(cli)

@pmcmd("id")
def investigate(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    if not var.is_role(nick, "detective"):
        pm(cli, nick, "Only a detective may use this command.")
        return
    if var.PHASE != "day":
        pm(cli, nick, "You may only investigate people during the day.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    if nick in var.INVESTIGATED:
        pm(cli, nick, "You may only investigate one person per round.")
        return
    victim = re.split(" +", rest)[0].strip().lower()
    if not victim:
        pm(cli, nick, "Not enough parameters")
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]
    if victim == nick:
        pm(cli, nick, "Investigating yourself would be a waste.")
        return

    victim = choose_target(nick, victim)
    var.INVESTIGATED.append(nick)
    vrole = var.get_role(victim)
    if vrole == "amnesiac":
        vrole = var.FINAL_ROLES[victim]
    pm(cli, nick, ("The results of your investigation have returned. \u0002{0}\u0002"+
                   " is a... \u0002{1}\u0002!").format(victim, vrole))
    var.LOGGER.logBare(victim, "INVESTIGATED", nick)
    if random.random() < var.DETECTIVE_REVEALED_CHANCE:  # a 2/5 chance (should be changeable in settings)
        # The detective's identity is compromised!
        for badguy in var.list_players(var.WOLFCHAT_ROLES):
            pm(cli, badguy, ("Someone accidentally drops a paper. The paper reveals "+
                            "that \u0002{0}\u0002 is the detective!").format(nick))
        var.LOGGER.logBare(nick, "PAPERDROP")

@pmcmd("visit")
def hvisit(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    if not var.is_role(nick, "harlot"):
        pm(cli, nick, "Only a harlot may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only visit someone at night.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    if var.HVISITED.get(nick):
        pm(cli, nick, ("You are already spending the night "+
                      "with \u0002{0}\u0002.").format(var.HVISITED[nick]))
        return
    victim = re.split(" +",rest)[0].strip().lower()
    if not victim:
        pm(cli, nick, "Not enough parameters")
        return
    pll = [x.lower() for x in var.list_players()]
    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = var.list_players()[pll.index(target)]
    if nick == victim:  # Staying home
        var.HVISITED[nick] = None
        pm(cli, nick, "You have chosen to stay home for the night.")
    else:
        victim = choose_target(nick, victim)
        if check_exchange(cli, nick, victim):
            return
        var.HVISITED[nick] = victim
        pm(cli, nick, ("You are spending the night with \u0002{0}\u0002. "+
                      "Have a good time!").format(var.HVISITED[nick]))
        pm(cli, var.HVISITED[nick], ("You are spending the night with \u0002{0}"+
                                     "\u0002. Have a good time!").format(nick))
        var.LOGGER.logBare(var.HVISITED[nick], "VISITED", nick)
    chk_nightdone(cli)

def is_fake_nick(who):
    return re.match("[0-9]+", who)

@pmcmd("see")
def see(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    role = var.get_role(nick)
    if role not in ("seer", "oracle", "augur"):
        pm(cli, nick, "Only a seer, oracle, or augur may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only have visions at night.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    if nick in var.SEEN:
        pm(cli, nick, "You may only have one vision per round.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if not victim:
        pm(cli, nick, "Not enough parameters")
        return
    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]
    if victim == nick:
        pm(cli, nick, "Seeing yourself would be a waste.")
        return
    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return
    victimrole = var.get_role(victim)
    if victimrole == "amnesiac":
        victimrole = var.FINAL_ROLES[victim]
    if role in ("seer", "oracle"):
        if victimrole in ("wolf", "werecrow", "monster", "mad scientist", "wolf cub") or victim in var.ROLES["cursed villager"]:
            victimrole = "wolf"
        elif victimrole in ("traitor", "hag", "sorcerer", "village elder", "time lord", "villager", "cultist", "minion", "vengeful ghost", "lycan", "clone", "fool", "jester"):
            victimrole = var.DEFAULT_ROLE
        elif role == "oracle": # Oracles never see specific roles, only generalizations
            victimrole = var.DEFAULT_ROLE
        pm(cli, nick, ("You have a vision; in this vision, "+
                        "you see that \u0002{0}\u0002 is a "+
                        "\u0002{1}\u0002!").format(victim, victimrole))
    elif role == "augur":
        aura = "blue"
        if victimrole in var.WOLFTEAM_ROLES:
            aura = "red"
        elif victimrole in var.TRUE_NEUTRAL_ROLES:
            aura = "grey"
        pm(cli, nick, ("You have a vision; in this vision, " +
                       "you see that \u0002{0}\u0002 exudes " +
                       "a \u0002{1}\u0002 aura!").format(victim, aura))
    var.SEEN.append(nick)
    var.LOGGER.logBare(victim, "SEEN", nick)
    chk_nightdone(cli)

@pmcmd("give", "totem")
def give(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    role = var.get_role(nick)
    if role not in ("shaman", "crazed shaman"):
        pm(cli, nick, "Only a shaman or a crazed shaman may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only give totems at night.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    if nick in var.SHAMANS:
        pm(cli, nick, "You have already given out your totem this round.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if not victim:
        pm(cli, nick, "Not enough parameters")
        return
    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]
    if nick in var.LASTGIVEN and var.LASTGIVEN[nick] == victim:
        pm(cli, nick, "You gave your totem to \u0002{0}\u0002 last time, you must choose someone else.".format(victim))
        return
    type = ""
    if role == "shaman":
        type = " of " + var.TOTEMS[nick]
    victim = choose_target(nick, victim)
    if check_exchange(cli, nick, victim):
        return
    pm(cli, nick, ("You have given a totem{0} to \u0002{1}\u0002.").format(type, victim))
    totem = var.TOTEMS[nick]
    if totem == "death":
        if victim not in var.DYING:
            var.DYING.append(victim)
    elif totem == "protection":
        if victim not in var.PROTECTED:
            var.PROTECTED.append(victim)
    elif totem == "revealing":
        if victim not in var.REVEALED:
            var.REVEALED.append(victim)
    elif totem == "narcolepsy":
        if victim not in var.ASLEEP:
            var.ASLEEP.append(victim)
    elif totem == "silence":
        if victim not in var.TOBESILENCED:
            var.TOBESILENCED.append(victim)
    elif totem == "desperation":
        if victim not in var.DESPERATE:
            var.DESPERATE.append(victim)
    elif totem == "impatience": # this totem stacks
        var.IMPATIENT.append(victim)
    elif totem == "pacifism": # this totem stacks
        var.PACIFISTS.append(victim)
    elif totem == "influence":
        if victim not in var.INFLUENTIAL:
            var.INFLUENTIAL.append(victim)
    elif totem == "exchange":
        if victim not in var.TOBEEXCHANGED:
            var.TOBEEXCHANGED.append(victim)
    elif totem == "lycanthropy":
        if victim not in var.TOBELYCANTHROPES:
            var.TOBELYCANTHROPES.append(victim)
    elif totem == "luck":
        if victim not in var.TOBELUCKY:
            var.TOBELUCKY.append(victim)
    elif totem == "pestilence":
        if victim not in var.TOBEDISEASED:
            var.TOBEDISEASED.append(victim)
    elif totem == "retribution":
        if victim not in var.RETRIBUTION:
            var.RETRIBUTION.append(victim)
    elif totem == "misdirection":
        if victim not in var.TOBEMISDIRECTED:
            var.TOBEMISDIRECTED.append(victim)
    else:
        pm(cli, nick, "I don't know what to do with a '{0}' totem. This is a bug, please report it to the admins.".format(totem))
    var.LASTGIVEN[nick] = victim
    var.SHAMANS.append(nick)
    var.LOGGER.logBare(victim, "GIVEN TOTEM", nick)
    chk_nightdone(cli)

@pmcmd("pass")
def pass_cmd(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return

    role = var.get_role(nick)
    if role != "hunter":
        pm(cli, nick, "Only a hunter may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only pass at night.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return

    if nick in var.OTHER_KILLS.keys():
        del var.OTHER_KILLS[nick]
        var.HUNTERS.remove(nick)

    pm(cli, nick, "You have decided to not kill anyone tonight.")
    if nick not in var.PASSED: # Prevents multiple entries
        var.PASSED.append(nick)
    #var.LOGGER.logBare(nick, "PASS", nick)
    chk_nightdone(cli)

@pmcmd("choose", "match")
def choose(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    try:
        role = var.get_role(nick)
    except KeyError:
        role = None
    if role != "matchmaker":
        pm(cli, nick, "Only a matchmaker may use this command.")
        return
    if var.PHASE != "night" or not var.FIRST_NIGHT:
        pm(cli, nick, "You may only choose lovers during the first night.")
        return
    if nick in var.MATCHMAKERS:
        pm(cli, nick, "You have already chosen lovers.")
        return
    # no var.SILENCED check for night 1 only roles; silence should only apply for the night after
    # but just in case, it also sucks if the one night you're allowed to act is when you are
    # silenced, so we ignore it here anyway.
    pieces = [p.strip().lower() for p in re.split(" +",rest)]
    victim = pieces[0]
    try:
        if pieces[1] == "and":
            victim2 = pieces[2]
        else:
            victim2 = pieces[1]
    except IndexError:
        victim2 = None

    if not victim or not victim2:
        pm(cli, nick, "Not enough parameters")
        return

    pl = var.list_players()
    pll = [x.lower() for x in pl]

    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]

    matches = 0
    for player in pll:
        if victim2 == player:
            target = player
            break
        if player.startswith(victim2):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(victim2))
            return
    victim2 = pl[pll.index(target)]

    if victim == victim2:
        pm(cli, nick, "You must choose two different people.")
        return

    var.MATCHMAKERS.append(nick)
    if victim in var.LOVERS:
        var.LOVERS[victim].append(victim2)
        var.ORIGINAL_LOVERS[victim].append(victim2)
    else:
        var.LOVERS[victim] = [victim2]
        var.ORIGINAL_LOVERS[victim] = [victim2]

    if victim2 in var.LOVERS:
        var.LOVERS[victim2].append(victim)
        var.ORIGINAL_LOVERS[victim2].append(victim)
    else:
        var.LOVERS[victim2] = [victim]
        var.ORIGINAL_LOVERS[victim2] = [victim]
    pm(cli, nick, "You have selected \u0002{0}\u0002 and \u0002{1}\u0002 to be lovers.".format(victim, victim2))

    if victim in var.PLAYERS and var.PLAYERS[victim]["cloak"] not in var.SIMPLE_NOTIFY:
        pm(cli, victim, ("You are \u0002in love\u0002 with {0}. If that player dies for any " +
                         "reason, the pain will be too much for you to bear and you will " +
                         "commit suicide.").format(victim2))
    else:
        pm(cli, victim, "You are \u0002in love\u0002 with {0}.".format(victim2))

    if victim2 in var.PLAYERS and var.PLAYERS[victim2]["cloak"] not in var.SIMPLE_NOTIFY:
        pm(cli, victim2, ("You are \u0002in love\u0002 with {0}. If that player dies for any " +
                         "reason, the pain will be too much for you to bear and you will " +
                         "commit suicide.").format(victim))
    else:
        pm(cli, victim2, "You are \u0002in love\u0002 with {0}.".format(victim))

    var.LOGGER.logBare(victim, "LOVERS", victim2)
    chk_nightdone(cli)

@pmcmd("target")
def target(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    if nick not in var.ROLES["assassin"]:
        pm(cli, nick, "Only an assassin may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only target people at night.")
        return
    if nick in var.TARGETED and var.TARGETED[nick] != None:
        pm(cli, nick, "You have already chosen a target.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    pieces = [p.strip().lower() for p in re.split(" +",rest)]
    victim = pieces[0]

    if not victim:
        pm(cli, nick, "Not enough parameters")
        return

    pl = var.list_players()
    pll = [x.lower() for x in pl]

    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]

    if nick == victim:
        pm(cli, nick, "You may not target yourself.")
        return

    victim = choose_target(nick, victim)
    # assassin is a template so it will never get swapped, so don't check for exchanges with it
    var.TARGETED[nick] = victim
    pm(cli, nick, "You have selected \u0002{0}\u0002 as your target.".format(victim))

    var.LOGGER.logBare(nick, "TARGETED", victim)
    chk_nightdone(cli)

@pmcmd("hex")
def hex(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    if nick not in var.ROLES["hag"]:
        pm(cli, nick, "Only a hag may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only hex at night.")
        return
    if nick in var.HEXED:
        pm(cli, nick, "You have already hexed someone tonight.")
        return
    if nick in var.SILENCED:
        pm(cli, nick, "You have been silenced, and are unable to use any special powers.")
        return
    pieces = [p.strip().lower() for p in re.split(" +",rest)]
    victim = pieces[0]

    if not victim:
        pm(cli, nick, "Not enough parameters")
        return

    pl = var.list_players()
    pll = [x.lower() for x in pl]

    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]

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

    var.HEXED.append(nick)
    var.LASTHEXED[nick] = victim
    var.TOBESILENCED.append(victim)
    pm(cli, nick, "You have cast a hex on \u0002{0}\u0002.".format(victim))

    var.LOGGER.logBare(nick, "HEXED", victim)
    chk_nightdone(cli)

@pmcmd("clone")
def clone(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    if nick not in var.ROLES["clone"]:
        pm(cli, nick, "Only a clone may use this command.")
        return
    if var.PHASE != "night" or not var.FIRST_NIGHT:
        pm(cli, nick, "You may only clone someone during the first night.")
        return
    if nick in var.CLONED.keys():
        pm(cli, nick, "You have already chosen to clone someone.")
        return
    # no var.SILENCED check for night 1 only roles; silence should only apply for the night after
    # but just in case, it also sucks if the one night you're allowed to act is when you are
    # silenced, so we ignore it here anyway.

    pieces = [p.strip().lower() for p in re.split(" +",rest)]
    victim = pieces[0]

    if not victim:
        pm(cli, nick, "Not enough parameters")
        return

    pl = var.list_players()
    pll = [x.lower() for x in pl]

    matches = 0
    for player in pll:
        if victim == player:
            target = player
            break
        if player.startswith(victim):
            target = player
            matches += 1
    else:
        if matches != 1:
            pm(cli, nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
            return
    victim = pl[pll.index(target)]

    if nick == victim:
        pm(cli, nick, "You may not target yourself.")
        return

    var.CLONED[nick] = victim
    pm(cli, nick, "You have chosen to clone \u0002{0}\u0002.".format(victim))

    var.LOGGER.logBare(nick, "CLONED", victim)
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
                break



def mass_privmsg(cli, targets, msg, notice = False):
    while targets:
        if len(targets) <= var.MAX_PRIVMSG_TARGETS:
            bgs = ",".join(targets)
            targets = ()
        else:
            bgs = ",".join(targets[0:var.MAX_PRIVMSG_TARGETS])
            targets = targets[var.MAX_PRIVMSG_TARGETS:]
        if not notice:
            cli.msg(bgs, msg)
        else:
            cli.notice(bgs, msg)



@pmcmd("")
def relay(cli, nick, rest):
    """Let the wolves talk to each other through the bot"""
    if var.PHASE not in ("night", "day"):
        return

    badguys = var.list_players(var.WOLFCHAT_ROLES)
    if len(badguys) > 1:
        if nick in badguys:
            badguys.remove(nick)  #  remove self from list

            if rest.startswith("\01ACTION"):
                rest = rest[7:-1]
                mass_privmsg(cli, [guy for guy in badguys
                    if (guy in var.PLAYERS and
                        var.PLAYERS[guy]["cloak"] not in var.PREFER_NOTICE)], "\02{0}\02{1}".format(nick, rest))
                mass_privmsg(cli, [guy for guy in badguys
                    if (guy in var.PLAYERS and
                        var.PLAYERS[guy]["cloak"] in var.PREFER_NOTICE)], nick+rest, True)
            else:
                mass_privmsg(cli, [guy for guy in badguys
                    if (guy in var.PLAYERS and
                        var.PLAYERS[guy]["cloak"] not in var.PREFER_NOTICE)], "\02{0}\02 says: {1}".format(nick, rest))
                mass_privmsg(cli, [guy for guy in badguys
                    if (guy in var.PLAYERS and
                        var.PLAYERS[guy]["cloak"] in var.PREFER_NOTICE)], "\02{0}\02 says: {1}".format(nick, rest), True)

@pmcmd("")
def ctcp_ping(cli, nick, msg):
    if msg.startswith("\x01PING"):
        cli.notice(nick, msg)

def transition_night(cli):
    if var.PHASE == "night":
        return
    var.PHASE = "night"
    var.GAMEPHASE = "night"

    for x, tmr in var.TIMERS.items():  # cancel daytime timer
        tmr[0].cancel()
    var.TIMERS = {}

    # Reset nighttime variables
    var.KILLS = {}
    var.OTHER_KILLS = {}
    var.GUARDED = {}  # key = by whom, value = the person that is visited
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = []  # list of seers that have had visions
    var.HEXED = [] # list of hags that have hexed
    var.SHAMANS = []
    var.PASSED = [] # list of hunters that have chosen not to kill
    var.OBSERVED = {}  # those whom werecrows have observed
    var.HVISITED = {}
    var.ASLEEP = []
    var.DYING = []
    var.PROTECTED = []
    var.DESPERATE = []
    var.REVEALED = []
    var.TOBESILENCED = []
    var.IMPATIENT = []
    var.PACIFISTS = []
    var.INFLUENTIAL = []
    var.TOBELYCANTHROPES = []
    var.TOBELUCKY = []
    var.TOBEDISEASED = []
    var.RETRIBUTION = []
    var.TOBEMISDIRECTED = []
    var.TOBEEXCHANGED = []
    var.NIGHT_START_TIME = datetime.now()
    var.NIGHT_COUNT += 1
    var.FIRST_NIGHT = (var.NIGHT_COUNT == 1)
    var.TOTEMS = {}
    var.ACTED_EXTRA = 0

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

    # convert amnesiac and kill village elder if necessary
    if var.NIGHT_COUNT == var.AMNESIAC_NIGHTS:
        amns = copy.copy(var.ROLES["amnesiac"])
        for amn in amns:
            amnrole = var.FINAL_ROLES[amn]
            var.ROLES["amnesiac"].remove(amn)
            var.ROLES[amnrole].append(amn)
            var.AMNESIACS.append(amn)
            showrole = amnrole
            if showrole in ("village elder", "time lord"):
                showrole = "villager"
            elif showrole == "vengeful ghost":
                showrole = var.DEFAULT_ROLE
            pm(cli, amn, "Your amnesia clears and you now remember that you are a \u0002{0}\u0002!".format(showrole))
            if amnrole in var.WOLFCHAT_ROLES:
                for wolf in var.list_players(var.WOLFCHAT_ROLES):
                    pm(cli, wolf, "\u0002{0}\u0002 is now a \u0002{1}\u0002!".format(amn, showrole))

    numwolves = len(var.list_players(var.WOLF_ROLES))
    if var.NIGHT_COUNT >= numwolves + 1:
        for elder in var.ROLES["village elder"]:
            var.DYING.append(elder)

    # send PMs
    ps = var.list_players()
    wolves = var.list_players(var.WOLFCHAT_ROLES)
    for wolf in wolves:
        normal_notify = wolf in var.PLAYERS and var.PLAYERS[wolf]["cloak"] not in var.SIMPLE_NOTIFY
        role = var.get_role(wolf)
        cursed = "cursed " if wolf in var.ROLES["cursed villager"] else ""

        if normal_notify:
            if role == "wolf":
                pm(cli, wolf, ('You are a \u0002wolf\u0002. It is your job to kill all the '+
                               'villagers. Use "kill <nick>" to kill a villager.'))
            elif role == "traitor":
                pm(cli, wolf, ('You are a \u0002{0}traitor\u0002. You are exactly like a '+
                               'villager and not even a seer can see your true identity, '+
                               'only detectives can.').format(cursed))
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
            else:
                # catchall in case we forgot something above
                pm(cli, wolf, ('You are a \u0002{0}\u0002. There would normally be instructions ' +
                               'here, but someone forgot to add them in. Please report this to ' +
                               'the admins, you can PM me "admins" for a list of available ones.').format(role))

            if len(wolves) > 1:
                pm(cli, wolf, 'Also, if you PM me, your message will be relayed to other wolves.')
        else:
            pm(cli, wolf, "You are a \02{0}{1}\02.".format(cursed, role))  # !simple

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
        if wolf in var.WOLF_GUNNERS.keys() and var.WOLF_GUNNERS[wolf] > 0:
            pm(cli, wolf, "You have a \u0002gun\u0002 with {0} bullet{1}.".format(var.WOLF_GUNNERS[wolf], "s" if var.WOLF_GUNNERS[wolf] > 1 else ""))
        if var.DISEASED_WOLVES:
            pm(cli, wolf, 'You are feeling ill tonight, and are unable to kill anyone.')
        elif var.ANGRY_WOLVES and role in ("wolf", "werecrow"):
            pm(cli, wolf, 'You are \u0002angry\u0002 tonight, and may kill two targets by using "kill <nick1> and <nick2>".')

    for seer in var.list_players(["seer", "oracle", "augur"]):
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

        if seer in var.PLAYERS and var.PLAYERS[seer]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, seer, ('You are {0} \u0002{1}\u0002. '+
                          'It is your job to detect the wolves, you '+
                          'may have a vision once per night. '+
                          'Use "see <nick>" to see {2}.').format(a, role, what))
        else:
            pm(cli, seer, "You are {0} \02{1}\02.".format(a, role))  # !simple
        pm(cli, seer, "Players: " + ", ".join(pl))

    for harlot in var.ROLES["harlot"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(harlot)
        if harlot in var.PLAYERS and var.PLAYERS[harlot]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, harlot, ('You are a \u0002harlot\u0002. '+
                             'You may spend the night with one person per round. '+
                             'If you visit a victim of a wolf, or visit a wolf, '+
                             'you will die. Use visit to visit a player.'))
        else:
            pm(cli, harlot, "You are a \02harlot\02.")  # !simple
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

        if g_angel in var.PLAYERS and var.PLAYERS[g_angel]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, g_angel, ('You are a \u0002bodyguard\u0002. '+
                              'It is your job to protect the villagers. {0}If you guard '+
                              'a victim, you will sacrifice yourself to save them. ' +
                              'Use "guard <nick>" to guard a player.').format(warning))
        else:
            pm(cli, g_angel, "You are a \02bodyguard\02.")  # !simple
        pm(cli, g_angel, "Players: " + ", ".join(pl))

    for gangel in var.ROLES["guardian angel"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(gangel)
        chance = math.floor(var.GUARDIAN_ANGEL_DIES_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = "If you guard a wolf, there is a {0}% chance of you dying. ".format(chance)

        if gangel in var.PLAYERS and var.PLAYERS[gangel]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, gangel, ('You are a \u0002guardian angel\u0002. '+
                              'It is your job to protect the villagers. {0}If you guard '+
                              'a victim, they will live. You may not guard the same person two nights in a row. ' +
                              'Use "guard <nick>" to guard a player.').format(warning))
        else:
            pm(cli, gangel, "You are a \02guardian angel\02.")  # !simple
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
        if dttv in var.PLAYERS and var.PLAYERS[dttv]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, dttv, ("You are a \u0002detective\u0002.\n"+
                          "It is your job to determine all the wolves and traitors. "+
                          "Your job is during the day, and you can see the true "+
                          "identity of all players, even traitors.\n"+
                          '{0}Use "id <nick>" in PM to identify any player during the day.').format(warning))
        else:
            pm(cli, dttv, "You are a \02detective\02.")  # !simple
        pm(cli, dttv, "Players: " + ", ".join(pl))

    for drunk in var.ROLES["village drunk"]:
        if drunk in var.PLAYERS and var.PLAYERS[drunk]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, drunk, "You have been drinking too much! You are the \u0002village drunk\u0002.")
        else:
            pm(cli, drunk, "You are the \u0002village drunk\u0002.")

    for shaman in var.list_players(["shaman", "crazed shaman"]):
        pl = ps[:]
        random.shuffle(pl)
        role = var.get_role(shaman)
        rand = random.random()
        target = 0
        for t, c in var.TOTEM_CHANCES.items():
            target += var.TOTEM_CHANCES[t][0 if role == "shaman" else 1]
            if rand <= target:
                var.TOTEMS[shaman] = t
                break
        else:
            # some sort of error (floating point issues so the %ages didn't sum to 1 or something)
            # just give them death because I'm lazy
            var.TOTEMS[shaman] = 'death'
        if shaman in var.PLAYERS and var.PLAYERS[shaman]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, shaman, ('You are a \u0002{0}\u0002. You can select a player to receive ' +
                             'a {1}totem each night by using "give <nick>". You may give yourself a totem, but you ' +
                             'may not give the same player a totem two nights in a row.').format(role, "random " if shaman in var.ROLES["crazed shaman"] else ""))
            if shaman in var.ROLES["shaman"]:
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
            if shaman in var.ROLES["shaman"]:
                pm(cli, shaman, "You have the \u0002{0}\u0002 totem.".format(var.TOTEMS[shaman]))
        pm(cli, shaman, "Players: " + ", ".join(pl))

    for hunter in var.ROLES["hunter"]:
        if hunter in var.HUNTERS:
            continue #already killed
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(hunter)
        if hunter in var.PLAYERS and var.PLAYERS[hunter]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, hunter, ('You are a \u0002hunter\u0002. Once per game, you may kill another ' +
                             'player with "kill <nick>". If you do not wish to kill anyone tonight, ' +
                             'use "pass" instead.'))
        else:
            pm(cli, hunter, "You are a \u0002hunter\u0002.")
        pm(cli, hunter, "Players: " + ", ".join(pl))

    for fool in var.ROLES["fool"]:
        if fool in var.PLAYERS and var.PLAYERS[fool]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, fool, ('You are a \u0002fool\u0002. The game immediately ends with you ' +
                           'being the only winner if you are lynched during the day. You cannot ' +
                           'otherwise win this game.'))
        else:
            pm(cli, fool, "You are a \u0002fool\u0002.")

    for jester in var.ROLES["jester"]:
        if jester in var.PLAYERS and var.PLAYERS[jester]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, jester, ('You are a \u0002jester\u0002. You will win alongside the normal winners ' +
                             'if you are lynched during the day. You cannot otherwise win this game.'))
        else:
            pm(cli, jester, "You are a \u0002jester\u0002.")

    for monster in var.ROLES["monster"]:
        if monster in var.PLAYERS and var.PLAYERS[monster]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, monster, ('You are a \u0002monster\u0002. You cannot be killed by the wolves. ' +
                              'If you survive until the end of the game, you win instead of the ' +
                              'normal winners.'))
        else:
            pm(cli, monster, "You are a \u0002monster\u0002.")

    for lycan in var.ROLES["lycan"]:
        if lycan in var.PLAYERS and var.PLAYERS[lycan]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, lycan, ('You are a \u0002lycan\u0002. You are currently on the side of the ' +
                            'villagers, but will turn into a wolf if you are targeted by them ' +
                            'during the night.'))
        else:
            pm(cli, lycan, "You are a \u0002lycan\u0002.")

    for v_ghost, who in var.VENGEFUL_GHOSTS.items():
        wolves = var.list_players(var.WOLFTEAM_ROLES)
        if who == "wolves":
            pl = wolves
        else:
            pl = ps[:]
            for wolf in wolves:
                pl.remove(wolf)

        random.shuffle(pl)

        if v_ghost in var.PLAYERS and var.PLAYERS[v_ghost]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, v_ghost, ('You are a \u0002vengeful ghost\u0002, sworn to take revenge on the ' +
                              '{0} that you believe killed you. You must kill one of them with ' +
                              '"kill <nick>" tonight. If you do not, one of them will be selected ' +
                              'at random.').format(who))
        else:
            pm(cli, v_ghost, "You are a \u0002vengeful ghost\u0002.")
        pm(cli, v_ghost, who.capitalize() + ": " + ", ".join(pl))

    for ass in var.ROLES["assassin"]:
        if ass in var.TARGETED and var.TARGETED[ass] != None:
            continue # someone already targeted
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(ass)
        if ass in var.PLAYERS and var.PLAYERS[ass]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, ass, ('You are an \u0002assassin\u0002. Choose a target with ' +
                          '"target <nick>". If you die you will take out your target with you. ' +
                          'If your target dies you may choose another one.'))
        else:
            pm(cli, ass, "You are an \u0002assassin\u0002.")
        pm(cli, ass, "Players: " + ", ".join(pl))

    if var.FIRST_NIGHT:
        for mm in var.ROLES["matchmaker"]:
            pl = ps[:]
            random.shuffle(pl)
            if mm in var.PLAYERS and var.PLAYERS[mm]["cloak"] not in var.SIMPLE_NOTIFY:
                pm(cli, mm, ('You are a \u0002matchmaker\u0002. You can select two players ' +
                             'to be lovers with "choose <nick1> and <nick2>". If one lover ' +
                             'dies, the other will as well. You may select yourself as one ' +
                             'of the lovers. You may only select lovers during the first night.'))
            else:
                pm(cli, mm, "You are a \u0002matchmaker\u0002.")
            pm(cli, mm, "Players: " + ", ".join(pl))

        for clone in var.ROLES["clone"]:
            pl = ps[:]
            random.shuffle(pl)
            pl.remove(clone)
            if clone in var.PLAYERS and var.PLAYERS[clone]["cloak"] not in var.SIMPLE_NOTIFY:
                pm(cli, clone, ('You are a \u0002clone\u0002. You can select someone to clone ' +
                                'with "clone <nick>". If that player dies, you become their ' +
                                'role(s). You may only clone someone during the first night.'))
            else:
                pm(cli, clone, "You are a \u0002clone\u0002")
            pm(cli, clone, "Players: "+", ".join(pl))

        for ms in var.ROLES["mad scientist"]:
            if ms in var.PLAYERS and var.PLAYERS[ms]["cloak"] not in var.SIMPLE_NOTIFY:
                pm(cli, ms, ("You are the \u0002mad scientist\u0002. If you die for any reason " +
                             "other than idling out or quitting, you will let loose a potent " +
                             "chemical concoction that will kill the players that joined " +
                             "immediately before and after you if they are still alive."))
            else:
                pm(cli, ms, "You are the \u0002mad scientist\u0002.")

        for minion in var.ROLES["minion"]:
            wolves = var.list_players(var.WOLF_ROLES)
            random.shuffle(wolves)
            if minion in var.PLAYERS and var.PLAYERS[minion]["cloak"] not in var.SIMPLE_NOTIFY:
                pm(cli, minion, "You are a \u0002minion\u0002. It is your job to help the wolves kill all of the villagers.")
            else:
                pm(cli, minion, "You are a \u0002minion\u0002.")
            pm(cli, minion, "Wolves: " + ", ".join(wolves))

        villagers = copy.copy(var.ROLES["villager"])
        villagers += var.ROLES["time lord"] + var.ROLES["village elder"]
        if var.DEFAULT_ROLE == "villager":
            villagers += var.ROLES["vengeful ghost"] + var.ROLES["amnesiac"]
        for villager in villagers:
            if villager in var.PLAYERS and var.PLAYERS[villager]["cloak"] not in var.SIMPLE_NOTIFY:
                pm(cli, villager, "You are a \u0002villager\u0002. It is your job to lynch all of the wolves.")
            else:
                pm(cli, villager, "You are a \u0002villager\u0002.")

        cultists = copy.copy(var.ROLES["cultist"])
        if var.DEFAULT_ROLE == "cultist":
            cultists += var.ROLES["vengeful ghost"] + var.ROLES["amnesiac"]
        for cultist in cultists:
            if cultist in var.PLAYERS and var.PLAYERS[cultist]["cloak"] not in var.SIMPLE_NOTIFY:
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
        norm_notify = g in var.PLAYERS and var.PLAYERS[g]["cloak"] not in var.SIMPLE_NOTIFY
        role = "gunner"
        if g in var.ROLES["sharpshooter"]:
            role = "sharpshooter"
        if norm_notify:
            if role == "gunner":
                gun_msg = ('You are a \02{0}\02 and hold a gun that shoots special silver bullets. ' +
                           'You may only use it during the day by typing "{0}shoot <nick>" in channel. '.format(botconfig.CMD_CHAR) +
                           'Wolves and the crow will die instantly when shot, but anyone else will ' +
                           'likely survive. You have {1}.')
            elif role == "sharpshooter":
                gun_msg = ('You are a \02{0}\02 and hold a gun that shoots special silver bullets. ' +
                           'You may only use it during the day by typing "{0}shoot <nick>" in channel. '.format(botconfig.CMD_CHAR) +
                           'Wolves and the crow will die instantly when shot, and anyone else will ' +
                           'likely die as well due to your skill with the gun. You have {1}.')
        else:
            gun_msg = ("You are a \02{0}\02 and have a gun with {1}.")
        if var.GUNNERS[g] == 1:
            gun_msg = gun_msg.format(role, "1 bullet")
        elif var.GUNNERS[g] > 1:
            gun_msg = gun_msg.format(role, str(var.GUNNERS[g]) + " bullets")
        else:
            continue

        pm(cli, g, gun_msg)

    dmsg = (daydur_msg + "It is now nighttime. All players "+
                   "check for PMs from me for instructions. "+
                   "If you did not receive one, simply sit back, "+
                   "relax, and wait patiently for morning.")
    cli.msg(chan, dmsg)
    var.LOGGER.logMessage(dmsg.replace("\02", ""))
    var.LOGGER.logBare("NIGHT", "BEGIN")

    # cli.msg(chan, "DEBUG: "+str(var.ROLES))
    if len(var.ROLES["wolf"] + var.ROLES["werecrow"]) == 0 or var.DISEASED_WOLVES:  # Probably something interesting going on.
        chk_nightdone(cli)
        chk_traitor(cli)



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
            for attr in dir(gm):
                val = getattr(gm, attr)
                if (hasattr(var, attr) and not callable(val)
                                        and not attr.startswith("_")):
                    var.ORIGINAL_SETTINGS[attr] = getattr(var, attr)
                    setattr(var, attr, val)
            var.CURRENT_GAMEMODE = md
            return True
        except var.InvalidModeException as e:
            cli.msg(botconfig.CHANNEL, "Invalid mode: "+str(e))
            return False
    else:
        cli.msg(chan, "Mode \u0002{0}\u0002 not found.".format(modeargs[0]))


@cmd("start")
def fstart(cli, nick, chan, rest):
    """Starts a game of Werewolf."""
    start(cli, nick)

def start(cli, nick, forced = False):
    chan = botconfig.CHANNEL

    villagers = var.list_players()
    pl = villagers[:]

    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in villagers and nick != chan and not forced:
        cli.notice(nick, "You're currently not playing.")
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

    if not var.FGAMED:
        votes = {} #key = gamemode, not cloak
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

    for index in range(len(var.ROLE_INDEX) - 1, -1, -1):
        if var.ROLE_INDEX[index] <= len(villagers):
            addroles = {k:v[index] for k,v in var.ROLE_GUIDE.items()}
            break
    else:
        cli.msg(chan, "{0}: No game settings are defined for \u0002{1}\u0002 player games.".format(nick, len(villagers)))
        return

    # Cancel join timer
    if 'join' in var.TIMERS:
        var.TIMERS['join'][0].cancel()
        del var.TIMERS['join']

    if var.ORIGINAL_SETTINGS:  # Custom settings
        while True:
            wvs = sum(addroles[r] for r in var.WOLFCHAT_ROLES)
            if len(villagers) < (sum(addroles.values()) - sum([addroles[r] for r in var.TEMPLATE_RESTRICTIONS.keys()])):
                cli.msg(chan, "There are too few players in the "+
                              "game to use the custom roles.")
            elif not wvs:
                cli.msg(chan, "There has to be at least one wolf!")
            elif wvs > (len(villagers) / 2):
                cli.msg(chan, "Too many wolves.")
            else:
                break
            reset_settings()
            cli.msg(chan, "The default settings have been restored. Please !start again.")
            var.PHASE = "join"
            return


    if var.ADMIN_TO_PING:
        if "join" in COMMANDS.keys():
            COMMANDS["join"] = [lambda *spam: cli.msg(chan, "This command has been disabled by an admin.")]
        if "j" in COMMANDS.keys():
            COMMANDS["j"] = [lambda *spam: cli.msg(chan, "This command has been disabled by an admin.")]
        if "start" in COMMANDS.keys():
            COMMANDS["start"] = [lambda *spam: cli.msg(chan, "This command has been disabled by an admin.")]

    var.ALL_PLAYERS = copy.copy(var.ROLES["person"])
    var.ROLES = {}
    var.GUNNERS = {}
    var.WOLF_GUNNERS = {}
    var.SEEN = []
    var.OBSERVED = {}
    var.KILLS = {}
    var.GUARDED = {}
    var.HVISITED = {}
    var.HUNTERS = []
    var.LYCANS = []
    var.VENGEFUL_GHOSTS = {}
    var.CLONED = {}
    var.TARGETED = {}
    var.LASTGUARDED = {}
    var.LASTHEXED = {}
    var.LASTGIVEN = {}
    var.LOVERS = {}
    var.MATCHMAKERS = []
    var.REVEALED_MAYORS = []
    var.SILENCED = []
    var.TOBESILENCED = []
    var.DESPERATE = []
    var.REVEALED = []
    var.ASLEEP = []
    var.PROTECTED = []
    var.DYING = []
    var.JESTERS = []
    var.AMNESIACS = []
    var.NIGHT_COUNT = 0
    var.DAY_COUNT = 0
    var.ANGRY_WOLVES = False
    var.DISEASED_WOLVES = False
    var.FINAL_ROLES = {}
    var.ORIGINAL_LOVERS = {}
    var.IMPATIENT = []
    var.PACIFISTS = []
    var.INFLUENTIAL = []
    var.LYCANTHROPES = []
    var.TOBELYCANTHROPES = []
    var.LUCKY = []
    var.TOBELUCKY = []
    var.DISEASED = []
    var.TOBEDISEASED = []
    var.RETRIBUTION = []
    var.MISDIRECTED = []
    var.TOBEMISDIRECTED = []
    var.EXCHANGED = []
    var.TOBEEXCHANGED = []
    var.SHAMANS = []
    var.HEXED = []
    var.OTHER_KILLS = {}
    var.ACTED_EXTRA = 0
    var.ABSTAINED = False

    for role, count in addroles.items():
        if role in var.TEMPLATE_RESTRICTIONS.keys():
            var.ROLES[role] = [None] * count
            continue # We deal with those later, see below
        selected = random.sample(villagers, count)
        var.ROLES[role] = selected
        for x in selected:
            villagers.remove(x)

    for v in villagers:
        var.ROLES[var.DEFAULT_ROLE].append(v)

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
                continue

        var.ROLES[template] = random.sample(possible, len(var.ROLES[template]))

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

    while True:
        try:
            var.ROLES["sharpshooter"].remove(None)
        except ValueError:
            break

    var.SPECIAL_ROLES["goat herder"] = []
    if var.GOAT_HERDER:
       var.SPECIAL_ROLES["goat herder"] = [ nick ]

    cli.msg(chan, ("{0}: Welcome to Werewolf, the popular detective/social party "+
                   "game (a theme of Mafia). Using the \002{1}\002 game mode.").format(", ".join(pl), var.CURRENT_GAMEMODE))
    cli.mode(chan, "+m")

    var.ORIGINAL_ROLES = copy.deepcopy(var.ROLES)  # Make a copy

    # Handle amnesiac
    amnroles = list(var.ROLE_GUIDE.keys())
    for nope in var.AMNESIAC_BLACKLIST:
        amnroles.remove(nope)
    for nope in var.TEMPLATE_RESTRICTIONS.keys():
        if nope in amnroles:
            amnroles.remove(nope)
    for amnesiac in var.ROLES["amnesiac"]:
        var.FINAL_ROLES[amnesiac] = random.choice(amnroles)

    var.DAY_TIMEDELTA = timedelta(0)
    var.NIGHT_TIMEDELTA = timedelta(0)
    var.DAY_START_TIME = datetime.now()
    var.NIGHT_START_TIME = datetime.now()

    var.LAST_PING = None

    var.LOGGER.log("Game Start")
    var.LOGGER.logBare("GAME", "BEGIN", nick)
    var.LOGGER.logBare(str(len(pl)), "PLAYERCOUNT")

    var.LOGGER.log("***")
    var.LOGGER.log("ROLES: ")
    roles = copy.copy(var.ROLES)
    for rol in roles:
        r = []
        for rw in var.plural(rol).split(" "):
            rwu = rw[0].upper()
            if len(rw) > 1:
                rwu += rw[1:]
            r.append(rwu)
        r = " ".join(r)
        try:
            var.LOGGER.log("{0}: {1}".format(r, ", ".join(var.ROLES[rol])))
            for plr in var.ROLES[rol]:
                var.LOGGER.logBare(plr, "ROLE", rol)
        except TypeError:
            var.ROLES[rol] = []

    if var.GUNNERS:
        var.LOGGER.log("Villagers With Bullets: "+", ".join([x+"("+str(y)+")" for x,y in var.GUNNERS.items()]))

    var.LOGGER.log("***")

    var.PLAYERS = {plr:dict(var.USERS[plr]) for plr in pl if plr in var.USERS}

    var.FIRST_NIGHT = True
    if not var.START_WITH_DAY:
        var.GAMEPHASE = "night"
        transition_night(cli)
    else:
        var.FIRST_DAY = True
        var.GAMEPHASE = "day"
        transition_day(cli)

    for cloak in list(var.STASISED.keys()):
        var.STASISED[cloak] -= 1
        var.set_stasis(cloak, var.STASISED[cloak])
        if var.STASISED[cloak] <= 0:
            del var.STASISED[cloak]

    if not botconfig.DEBUG_MODE:
        # DEATH TO IDLERS!
        reapertimer = threading.Thread(None, reaper, args=(cli,var.GAME_ID))
        reapertimer.daemon = True
        reapertimer.start()



@hook("error")
def on_error(cli, pfx, msg):
    if msg.endswith("(Excess Flood)"):
        restart_program(cli, "excess flood", "")
    elif msg.startswith("Closing Link:"):
        raise SystemExit

@cmd("fstasis", admin_only=True)
def fstasis(cli, nick, chan, rest):
    """Removes or sets stasis penalties."""

    data = rest.split()
    msg = None

    if data:
        lusers = {k.lower(): v for k, v in var.USERS.items()}
        user = data[0]

        if user.lower() in lusers:
            cloak = lusers[user.lower()]["cloak"]
        else:
            cloak = user

        if len(data) == 1:
            if cloak in var.STASISED:
                plural = "" if var.STASISED[cloak] == 1 else "s"
                msg = "\u0002{0}\u0002 ({1}) is in stasis for \u0002{2}\u0002 game{3}.".format(data[0], cloak, var.STASISED[cloak], plural)
            else:
                msg = "\u0002{0}\u0002 ({1}) is not in stasis.".format(data[0], cloak)
        else:
            try:
                amt = int(data[1])
            except ValueError:
                if chan == nick:
                    pm(cli, nick, "The amount of stasis has to be a non-negative integer.")
                else:
                    cli.notice(nick, "The amount of stasis has to be a non-negative integer.")

                return

            if amt < 0:
                if chan == nick:
                    pm(cli, nick, "The amount of stasis has to be a non-negative integer.")
                else:
                    cli.notice(nick, "The amount of stasis has to be a non-negative integer.")

                return

            if amt > 0:
                var.STASISED[cloak] = amt
                var.set_stasis(cloak, amt)
                plural = "" if amt == 1 else "s"
                msg = "\u0002{0}\u0002 ({1}) is now in stasis for \u0002{2}\u0002 game{3}.".format(data[0], cloak, amt, plural)
            elif amt == 0:
                if cloak in var.STASISED:
                    del var.STASISED[cloak]
                    var.set_stasis(cloak, 0)
                    msg = "\u0002{0}\u0002 ({1}) is no longer in stasis.".format(data[0], cloak)
                else:
                    msg = "\u0002{0}\u0002 ({1}) is not in stasis.".format(data[0], cloak)
    elif var.STASISED:
        msg = "Currently stasised: {0}".format(", ".join(
            "\u0002{0}\u0002 ({1})".format(cloak, number)
            for cloak, number in var.STASISED.items()))
    else:
        msg = "Nobody is currently stasised."

    if msg:
        if data:
            tokens = msg.split()

            if data[0] == cloak and tokens[1] == "({0})".format(cloak):
                # Don't show the cloak twice.
                msg = " ".join((tokens[0], " ".join(tokens[2:])))

        if chan == nick:
            pm(cli, nick, msg)
        else:
            cli.msg(chan, msg)


@pmcmd("fstasis", admin_only=True)
def fstasis_pm(cli, nick, rest):
    fstasis(cli, nick, nick, rest)


def allow_deny(cli, nick, chan, rest, mode):
    data = rest.split()
    msg = None

    modes = ("allow", "deny")
    assert mode in modes, "mode not in {!r}".format(modes)

    if mode == "allow":
        variable = botconfig.ALLOW
    else:
        variable = botconfig.DENY

    if data:
        lusers = {k.lower(): v for k, v in var.USERS.items()}
        user = data[0]

        if user.lower() in lusers:
            cloak = lusers[user.lower()]["cloak"]
        else:
            cloak = user

        if len(data) == 1: #list commands for a specific hostmask
            if cloak in variable:
                msg = "\u0002{0}\u0002 ({1}) is {2} the following {3}commands: {4}.".format(
                    data[0], cloak, "allowed" if mode == 'allow' else "denied", "special " if mode == 'allow' else "", ", ".join(variable[cloak]))
            else:
                msg = "\u0002{0}\u0002 ({1}) is not {2} commands.".format(data[0], cloak, "allowed any special" if mode == 'allow' else "denied any")
        else:
            if cloak not in variable:
                variable[cloak] = []
            commands = data[1:]
            for command in commands: #add or remove commands one at a time to a specific hostmask
                if command[0] == '-': #starting with - removes
                    rem = True
                    command = command[1:]
                else:
                    rem = False
                if command.startswith(botconfig.CMD_CHAR): #ignore command prefix
                    command = command[len(botconfig.CMD_CHAR):]

                if not rem:
                    if (command in COMMANDS or command in PM_COMMANDS) and command not in ["fdeny", "fallow", "exec", "eval"]:
                        variable[cloak].append(command)
                        if mode == "allow":
                            var.add_allow(cloak, command)
                        else:
                            var.add_deny(cloak, command)
                elif command in variable[cloak]:
                    variable[cloak].remove(command)
                    if mode == "allow":
                        var.remove_allow(cloak, command)
                    else:
                        var.remove_deny(cloak, command)
            if len(variable[cloak]):
                msg = "\u0002{0}\u0002 ({1}) is now {2} the following {3}commands: {4}{5}.".format(
                    data[0], cloak, "allowed" if mode == 'allow' else "denied", "special " if mode == 'allow' else "", botconfig.CMD_CHAR, ", {0}".format(botconfig.CMD_CHAR).join(variable[cloak]))
            else:
                del variable[cloak]
                msg = "\u0002{0}\u0002 ({1}) is no longer {2} commands.".format(data[0], cloak, "allowed any special" if mode == 'allow' else "denied any")
    elif variable: #list allowed / denied commands for all hostmasks
        msg = "{0}: {1}".format("Allowed" if mode == 'allow' else "Denied", ", ".join(
            "\u0002{0}\u0002 ({1}{2})".format(cloak, botconfig.CMD_CHAR, ", {0}".format(botconfig.CMD_CHAR).join(denied))
            for cloak, denied in variable.items()))
    else: #deny / allow is empty
        msg = "Nobody is {0} commands.".format("allowed any special" if mode == 'allow' else "denied any")

    if msg:
        if data:
            tokens = msg.split()

            if data[0] == cloak and tokens[1] == "({0})".format(cloak):
                # Don't show the cloak twice.
                msg = " ".join((tokens[0], " ".join(tokens[2:])))

        if chan == nick:
            pm(cli, nick, msg)
        else:
            cli.msg(chan, msg)


def allow(cli, nick, chan, rest):
    allow_deny(cli, nick, chan, rest, "allow")


def deny(cli, nick, chan, rest):
    allow_deny(cli, nick, chan, rest, "deny")


@cmd("fallow", admin_only=True)
def fallow(cli, nick, chan, rest):
    """Allow someone to use an admin command."""
    allow(cli, nick, chan, rest)


@pmcmd("fallow", admin_only=True)
def fallow_pm(cli, nick, rest):
    fallow(cli, nick, nick, rest)


@cmd("fdeny", admin_only=True)
def fdeny(cli, nick, chan, rest):
    """Deny someone from using a command."""
    deny(cli, nick, chan, rest)


@pmcmd("fdeny", admin_only=True)
def fdeny_pm(cli, nick, rest):
    fdeny(cli, nick, nick, rest)


@cmd("wait", "w")
def wait(cli, nick, chann_, rest):
    """Increases the wait time until !start can be used."""
    pl = var.list_players()

    chan = botconfig.CHANNEL


    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in pl:
        cli.notice(nick, "You're currently not playing.")
        return
    if var.WAITED >= var.MAXIMUM_WAITED:
        cli.msg(chan, "Limit has already been reached for extending the wait time.")
        return

    now = datetime.now()
    if now > var.CAN_START_TIME:
        var.CAN_START_TIME = now + timedelta(seconds=var.EXTRA_WAIT)
    else:
        var.CAN_START_TIME += timedelta(seconds=var.EXTRA_WAIT)
    var.WAITED += 1
    cli.msg(chan, ("\u0002{0}\u0002 increased the wait time by "+
                  "{1} seconds.").format(nick, var.EXTRA_WAIT))


@cmd("fwait", admin_only=True)
def fwait(cli, nick, chan, rest):
    """Forces an increase (or decrease) in wait time. Can be used with a number of seconds to wait."""

    pl = var.list_players()

    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return

    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return

    rest = re.split(" +", rest.strip(), 1)[0]

    if rest and (rest.isdigit() or (rest[0] == "-" and rest[1:].isdigit())):
        extra = int(rest)
    else:
        extra = var.EXTRA_WAIT

    now = datetime.now()

    if now > var.CAN_START_TIME:
        var.CAN_START_TIME = now + timedelta(seconds=extra)
    else:
        var.CAN_START_TIME += timedelta(seconds=extra)

    var.WAITED += 1

    cli.msg(chan, ("\u0002{0}\u0002 forcibly {2}creased the wait time by {1} "
                   "second{3}.").format(nick,
                                        abs(extra),
                                        "in" if extra >= 0 else "de",
                                        "s" if extra != 1 else ""))


@cmd("fstop",admin_only=True)
def reset_game(cli, nick, chan, rest):
    """Forces the game to stop."""
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    cli.msg(botconfig.CHANNEL, "\u0002{0}\u0002 has forced the game to stop.".format(nick))
    var.LOGGER.logMessage("{0} has forced the game to stop.".format(nick))
    if var.PHASE != "join":
        stop_game(cli)
    else:
        reset_modes_timers(cli)
        reset()


@pmcmd("rules")
def pm_rules(cli, nick, rest):
    cli.notice(nick, var.RULES)

@cmd("rules")
def show_rules(cli, nick, chan, rest):
    """Displays the rules."""
    if var.PHASE in ("day", "night") and nick not in var.list_players():
        cli.notice(nick, var.RULES)
        return
    cli.msg(botconfig.CHANNEL, var.RULES)
    var.LOGGER.logMessage(var.RULES)


@pmcmd("help", raw_nick = True)
def get_help(cli, rnick, rest):
    """Gets help."""
    nick, mode, user, cloak = parse_nick(rnick)
    fns = []

    rest = rest.strip().replace(botconfig.CMD_CHAR, "", 1).lower()
    splitted = re.split(" +", rest, 1)
    cname = splitted.pop(0)
    rest = splitted[0] if splitted else ""
    found = False
    if cname:
        for c in (COMMANDS,PM_COMMANDS):
            if cname in c.keys():
                found = True
                for fn in c[cname]:
                    if fn.__doc__:
                        if callable(fn.__doc__):
                            pm(cli, nick, botconfig.CMD_CHAR+cname+": "+fn.__doc__(rest))
                            if nick == botconfig.CHANNEL:
                                var.LOGGER.logMessage(botconfig.CMD_CHAR+cname+": "+fn.__doc__(rest))
                        else:
                            pm(cli, nick, botconfig.CMD_CHAR+cname+": "+fn.__doc__)
                            if nick == botconfig.CHANNEL:
                                var.LOGGER.logMessage(botconfig.CMD_CHAR+cname+": "+fn.__doc__)
                        return
                    else:
                        continue
                else:
                    continue
        else:
            if not found:
                pm(cli, nick, "Command not found.")
            else:
                pm(cli, nick, "Documentation for this command is not available.")
            return
    # if command was not found, or if no command was given:
    for name, fn in COMMANDS.items():
        if (name and not fn[0].admin_only and
            not fn[0].owner_only and name not in fn[0].aliases):
            fns.append("\u0002"+name+"\u0002")
    afns = []
    if is_admin(cloak) or cloak in botconfig.OWNERS: # todo - is_owner
        for name, fn in COMMANDS.items():
            if fn[0].admin_only and name not in fn[0].aliases:
                afns.append("\u0002"+name+"\u0002")
    cli.notice(nick, "Commands: "+", ".join(fns))
    if afns:
        cli.notice(nick, "Admin Commands: "+", ".join(afns))



@cmd("help", raw_nick = True)
def help2(cli, nick, chan, rest):
    """Gets help."""
    get_help(cli, nick, rest)


@hook("invite", raw_nick = False, admin_only = True)
def on_invite(cli, nick, something, chan):
    if chan == botconfig.CHANNEL:
        cli.join(chan)


def is_admin(cloak):
    return bool([ptn for ptn in botconfig.OWNERS+botconfig.ADMINS if fnmatch.fnmatch(cloak.lower(), ptn.lower())])


@cmd("admins", "ops")
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
    def on_whoreply(cli, server, _, chan, __, cloak, ___, user, status, ____):
        if not var.ADMIN_PINGING:
            return

        if is_admin(cloak) and "G" not in status and user != botconfig.NICK:
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

        decorators.unhook(HOOKS, 4)
        var.ADMIN_PINGING = False

    cli.who(botconfig.CHANNEL)


@pmcmd("admins", "ops")
def show_admins_pm(cli, nick, rest):
    show_admins(cli, nick, nick, rest)


@cmd("coin")
def coin(cli, nick, chan, rest):
    """It's a bad idea to base any decisions on this command."""

    if var.PHASE in ("day", "night") and nick not in var.list_players():
        cli.notice(nick, "You may not use this command right now.")
        return

    cli.msg(chan, "\2{0}\2 tosses a coin into the air...".format(nick))
    var.LOGGER.logMessage("{0} tosses a coin into the air...".format(nick))
    coin = random.choice(["heads", "tails"])
    specialty = random.randrange(0,10)
    if specialty == 0:
        coin = "its side"
    if specialty == 1:
        coin = botconfig.NICK
    cmsg = "The coin lands on \2{0}\2.".format(coin)
    cli.msg(chan, cmsg)
    var.LOGGER.logMessage(cmsg)

@cmd("pony")
def pony(cli, nick, chan, rest):
    """For entertaining bronies."""

    if var.PHASE in ("day", "night") and nick not in var.list_players():
        cli.notice(nick, "You may not use this command right now.")
        return

    cli.msg(chan, "\2{0}\2 tosses a pony into the air...".format(nick))
    var.LOGGER.logMessage("{0} tosses a pony into the air...".format(nick))
    pony = random.choice(["hoof", "plot"])
    cmsg = "The pony lands on \2{0}\2.".format(pony)
    cli.msg(chan, cmsg)
    var.LOGGER.logMessage(cmsg)

@cmd("time")
def timeleft(cli, nick, chan, rest):
    """Returns the time left until the next day/night transition."""

    if var.PHASE not in ("day", "night"):
        cli.notice(nick, "No game is currently running.")
        return

    if (chan != nick and var.LAST_TIME and
            var.LAST_TIME + timedelta(seconds=var.TIME_RATE_LIMIT) > datetime.now()):
        cli.notice(nick, ("This command is rate-limited. Please wait a while "
                          "before using it again."))
        return

    if chan != nick:
        var.LAST_TIME = datetime.now()

    if var.PHASE in var.TIMERS:
        t = var.TIMERS[var.PHASE]
        remaining = int((t[1] + t[2]) - time.time())
        if var.PHASE == "day":
            what = "sunset"
        elif var.PHASE == "night":
            what = "sunrise"
        elif var.PHASE == "join":
            what = "game is canceled"
        msg = "There is \u0002{0[0]:0>2}:{0[1]:0>2}\u0002 remaining until {1}.".format(divmod(remaining, 60), what)
    else:
        msg = "{0} timers are currently disabled.".format(var.PHASE.capitalize())

    if nick == chan:
        pm(cli, nick, msg)
    elif nick not in var.list_players() and var.PHASE not in ("none", "join"):
        cli.notice(nick, msg)
    else:
        cli.msg(chan, msg)

@pmcmd("time")
def timeleft_pm(cli, nick, rest):
    timeleft(cli, nick, nick, rest)

@cmd("roles")
def listroles(cli, nick, chan, rest):
    """Displays which roles are enabled at a certain number of players."""

    old = {}
    txt = ""
    index = 0
    pl = len(var.list_players()) + len(var.DEAD)
    roleindex = var.ROLE_INDEX
    roleguide = var.ROLE_GUIDE

    for r in var.ROLE_GUIDE.keys():
        old[r] = 0
    rest = re.split(" +", rest.strip(), 1)
    #prepend player count if called without any arguments
    if not len(rest[0]) and pl > 0:
        txt += " {0}: There {1} \u0002{2}\u0002 playing.".format(nick, "is" if pl == 1 else "are", pl)
        if var.PHASE in ["night", "day"]:
            txt += " Using the {0} game mode.".format(var.CURRENT_GAMEMODE)

    #read game mode to get roles for
    if len(rest[0]) and not rest[0].isdigit():
        #check for valid game mode ("roles" gamemode is treated as invalid)
        if rest[0] != "roles" and rest[0] in var.GAME_MODES.keys():
            mode = var.GAME_MODES[rest[0]][0]()
            if hasattr(mode, "ROLE_INDEX"):
                roleindex = getattr(mode, "ROLE_INDEX")
            if hasattr(mode, "ROLE_GUIDE"):
                roleguide = getattr(mode, "ROLE_GUIDE")
            rest.pop(0)
        else:
            txt += " {0}: {1} is not a valid game mode.".format(nick, rest[0])
            rest = []
            roleindex = {}
            
    #number of players to print the game mode for
    if len(rest) and rest[0].isdigit():
        index = int(rest[0])
        for i in range(len(roleindex)-1, -1, -1):
            if roleindex[i] <= index:
                index = roleindex[i]
                break

    for i in range(0, len(roleindex)):
        #getting the roles at a specific player count
        if index:
            if roleindex[i] < index:
                continue
            elif roleindex[i] > index:
                break
        txt += " {0}[{1}]{0} ".format(BOLD if roleindex[i] <= pl else "", str(roleindex[i]))
        roles = []
        for role, amount in roleguide.items():
            direction = 1 if amount[i] > old[role] else -1
            for j in range(old[role], amount[i], direction):
                temp = "{0}{1}".format("-" if direction == -1 else "", role)
                if direction == 1 and j+1 > 1:
                    temp += "({0})".format(j+1)
                elif j > 1:
                    temp += "({0})".format(j)
                roles.append(temp)
            old[role] = amount[i]
        txt += ", ".join(roles)
    txt = txt[1:]

    if chan == nick:
        pm(cli, nick, txt)
    elif nick not in var.list_players() and var.PHASE not in ("none", "join"):
        cli.notice(nick, txt)
    else:
        cli.msg(chan, txt)

@pmcmd("roles")
def listroles_pm(cli, nick, rest):
    listroles(cli, nick, nick, rest)

@cmd("myrole")
def myrole(cli, nick, chan, rest):
    """Reminds you of your current role."""
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return

    ps = var.list_players()
    if nick not in ps and nick not in var.VENGEFUL_GHOSTS.keys():
        cli.notice(nick, "You're currently not playing.")
        return

    role = var.get_role(nick)
    if role in ("time lord", "village elder", "amnesiac"):
        role = var.DEFAULT_ROLE
    elif role == "vengeful ghost" and nick not in var.VENGEFUL_GHOSTS.keys():
        role = var.DEFAULT_ROLE
    an = "n" if role[0] in ("a", "e", "i", "o", "u") else ""
    pm(cli, nick, "You are a{0} \02{1}{2}\02.".format(an, role, " assassin" if nick in var.ROLES["assassin"] and nick not in var.ROLES["amnesiac"] else ""))

    if role == "shaman" and var.PHASE == "night" and nick not in var.SHAMANS:
        pm(cli, nick, "You have the \u0002{0}\u0002 totem.".format(var.TOTEMS[nick]))

    # Check for gun/bullets
    if nick not in ps:
        return
    if nick not in var.ROLES["amnesiac"] and nick in var.GUNNERS and var.GUNNERS[nick]:
        role = "gunner"
        if nick in var.ROLES["sharpshooter"]:
            role = "sharpshooter"
        if var.GUNNERS[nick] == 1:
            pm(cli, nick, "You are a {0} and have a \02gun\02 with {1} {2}.".format(role, var.GUNNERS[nick], "bullet"))
        else:
            pm(cli, nick, "You are a {0} and have a \02gun\02 with {1} {2}.".format(role, var.GUNNERS[nick], "bullets"))
    elif nick in var.WOLF_GUNNERS and var.WOLF_GUNNERS[nick]:
        if var.WOLF_GUNNERS[nick] == 1:
            pm(cli, nick, "You have a \02gun\02 with {0} {1}.".format(var.WOLF_GUNNERS[nick], "bullet"))
        else:
            pm(cli, nick, "You have a \02gun\02 with {0} {1}.".format(var.WOLF_GUNNERS[nick], "bullets"))

    # Remind lovers of each other
    if nick in ps and nick in var.LOVERS:
        message = "You are \02in love\02 with "
        lovers = sorted(list(set(var.LOVERS[nick])))
        if len(lovers) == 1:
            message += lovers[0]
        elif len(lovers) == 2:
            message += lovers[0] + " and " + lovers[1]
        else:
            message += ", ".join(lovers[:-1]) + ", and " + lovers[-1]
        message += "."
        pm(cli, nick, message)

@pmcmd("myrole")
def myrole_pm(cli, nick, rest):
    myrole(cli, nick, "", rest)

def aftergame(cli, rawnick, rest):
    """Schedule a command to be run after the game by someone."""
    chan = botconfig.CHANNEL
    nick = parse_nick(rawnick)[0]

    rst = re.split(" +", rest)
    cmd = rst.pop(0).lower().replace(botconfig.CMD_CHAR, "", 1).strip()

    if cmd in PM_COMMANDS.keys():
        def do_action():
            for fn in PM_COMMANDS[cmd]:
                fn(cli, rawnick, " ".join(rst))
    elif cmd in COMMANDS.keys():
        def do_action():
            for fn in COMMANDS[cmd]:
                fn(cli, rawnick, botconfig.CHANNEL, " ".join(rst))
    else:
        cli.notice(nick, "That command was not found.")
        return

    if var.PHASE == "none":
        do_action()
        return

    cli.msg(chan, ("The command \02{0}\02 has been scheduled to run "+
                  "after this game by \02{1}\02.").format(cmd, nick))
    var.AFTER_FLASTGAME = do_action



@cmd("faftergame", admin_only=True, raw_nick=True)
def _faftergame(cli, nick, chan, rest):
    """Schedules a command to run after the current game."""
    if not rest.strip():
        cli.notice(parse_nick(nick)[0], "Incorrect syntax for this command.")
        return
    aftergame(cli, nick, rest)



@pmcmd("faftergame", admin_only=True, raw_nick=True)
def faftergame(cli, nick, rest):
    _faftergame(cli, nick, botconfig.CHANNEL, rest)


@cmd('fghost', admin_only=True)
@pmcmd('fghost', admin_only=True)
def fghost(cli, nick, *rest):
    """Voices you, allowing you to haunt the remaining players after your death."""
    cli.mode(botconfig.CHANNEL, '+v', nick)


@cmd('funghost', admin_only=True)
@pmcmd('funghost', admin_only=True)
def funghost(cli, nick, *rest):
    """Devoices you."""
    cli.mode(botconfig.CHANNEL, "-v", nick)

@pmcmd("flastgame", admin_only=True, raw_nick=True)
def flastgame(cli, nick, rest):
    rawnick = nick
    nick, _, __, cloak = parse_nick(rawnick)

    chan = botconfig.CHANNEL
    if var.PHASE != "join":
        if "join" in COMMANDS.keys():
            del COMMANDS["join"]
            cmd("join")(lambda *spam: cli.msg(chan, "This command has been disabled by an admin."))
            # manually recreate the command by calling the decorator function
        if "j" in COMMANDS.keys():
            del COMMANDS["j"]
            cmd("j")(lambda *spam: cli.msg(chan, "This command has been disabled by an admin."))
        if "start" in COMMANDS.keys():
            del COMMANDS["start"]
            cmd("start")(lambda *spam: cli.msg(chan, "This command has been disabled by an admin."))

    cli.msg(chan, "Starting a new game has now been disabled by \02{0}\02.".format(nick))
    var.ADMIN_TO_PING = nick

    if rest.strip():
        aftergame(cli, rawnick, rest)

@cmd("flastgame", admin_only=True, raw_nick=True)
def _flastgame(cli, nick, chan, rest):
    """Disables starting or joining a game, and optionally schedules a command to run after the current game ends."""
    flastgame(cli, nick, rest)


@cmd('gamestats', 'gstats')
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

    if var.PHASE not in ('none', 'join'):
        cli.notice(nick, "Wait until the game is over to view stats.")
        return

    gamemode = var.CURRENT_GAMEMODE
    rest = rest.strip().split()
    # Check for gamemode
    if len(rest) and not rest[0].isdigit():
        gamemode = rest[0]
        if gamemode not in var.GAME_MODES.keys():
            cli.notice(nick, "{0} is not a valid game mode".format(gamemode))
            return
        rest.pop(0)
    # Check for invalid input
    if len(rest) and rest[0].isdigit() and (
       int(rest[0]) > var.GAME_MODES[gamemode][2] or int(rest[0]) < var.GAME_MODES[gamemode][1]):
        cli.notice(nick, "Please enter an integer between "+\
                         "{0} and {1}.".format(var.GAME_MODES[gamemode][1], var.GAME_MODES[gamemode][2]))
        return

    # List all games sizes and totals if no size is given
    if not len(rest):
        if chan == nick:
            pm(cli, nick, var.get_game_totals(gamemode))
        else:
            cli.msg(chan, var.get_game_totals(gamemode))
    else:
        # Attempt to find game stats for the given game size
        if chan == nick:
            pm(cli, nick, var.get_game_stats(gamemode, int(rest[0])))
        else:
            cli.msg(chan, var.get_game_stats(gamemode, int(rest[0])))


@pmcmd('gamestats', 'gstats')
def game_stats_pm(cli, nick, rest):
    game_stats(cli, nick, nick, rest)


@cmd('playerstats', 'pstats', 'player', 'p')
def player_stats(cli, nick, chan, rest):
    """Gets the stats for the given player and role or a list of role totals if no role is given."""
    if (chan != nick and var.LAST_PSTATS and var.PSTATS_RATE_LIMIT and
            var.LAST_PSTATS + timedelta(seconds=var.PSTATS_RATE_LIMIT) >
            datetime.now()):
        cli.notice(nick, ('This command is rate-limited. Please wait a while '
                          'before using it again.'))
        return

    if chan != nick:
        var.LAST_PSTATS = datetime.now()

    if var.PHASE not in ('none', 'join'):
        cli.notice(nick, 'Wait until the game is over to view stats.')
        return

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
        acc = lusers[luser]['account']
        if acc == '*':
            if luser == nick.lower():
                cli.notice(nick, 'You are not identified with NickServ.')
            else:
                cli.notice(nick, user + ' is not identified with NickServ.')

            return
    else:
        acc = user

    # List the player's total games for all roles if no role is given
    if len(params) < 2:
        if chan == nick:
            pm(cli, nick, var.get_player_totals(acc))
        else:
            cli.msg(chan, var.get_player_totals(acc))
    else:
        role = ' '.join(params[1:])

        # Attempt to find the player's stats
        if chan == nick:
            pm(cli, nick, var.get_player_stats(acc, role))
        else:
            cli.msg(chan, var.get_player_stats(acc, role))


@pmcmd('playerstats', 'pstats', 'player', 'p')
def player_stats_pm(cli, nick, rest):
    player_stats(cli, nick, nick, rest)

@cmd('game', raw_nick = True)
def game(cli, nick, chan, rest):
    nick, _, __, cloak = parse_nick(nick)
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in var.list_players():
        cli.notice(nick, "You're currently not playing.")
        return

    if rest:
        gamemode = rest.lower().split()[0]
    else:
        gamemodes = ", ".join(["\002{}\002".format(gamemode) if len(var.list_players()) in range(var.GAME_MODES[gamemode][1], 
        var.GAME_MODES[gamemode][2]+1) else gamemode for gamemode in var.GAME_MODES.keys() if gamemode != "roles"])
        cli.notice(nick, "No game mode specified. Available game modes: " + gamemodes)
        return

    if gamemode not in var.GAME_MODES.keys():
        #players can vote by only using partial name
        matches = 0
        possiblegamemode = gamemode
        for mode in var.GAME_MODES.keys():
            if mode.startswith(gamemode) and mode != "roles":
                possiblegamemode = mode
                matches += 1
        if matches != 1:
            cli.notice(nick, "\002{0}\002 is not a valid game mode.".format(gamemode))
            return
        else:
            gamemode = possiblegamemode
    
    if gamemode != "roles":
        var.GAMEMODE_VOTES[cloak] = gamemode
        cli.msg(chan, "\002{0}\002 votes for the \002{1}\002 game mode.".format(nick, gamemode))
    else:
        cli.notice(nick, "You can't vote for that game mode.")

def game_help(args=''):
    return "Votes to make a specific game mode more likely. Available game mode setters: " +\
        ", ".join(["\002{}\002".format(gamemode) if len(var.list_players()) in range(var.GAME_MODES[gamemode][1], var.GAME_MODES[gamemode][2]+1)
        else gamemode for gamemode in var.GAME_MODES.keys() if gamemode != "roles"])
game.__doc__ = game_help

@cmd("fpull", admin_only=True)
def fpull(cli, nick, chan, rest):
    """Pulls from the repository to update the bot."""

    args = ["git", "pull", "--rebase=preserve"]

    if rest:
        args += rest.split(" ")

    child = subprocess.Popen(args,
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
            cli.msg(nick, "Process %s exited with %s %d" % (args, cause, ret))
        else:
            pm(cli, nick, "Process %s exited with %s %d" % (args, cause, ret))


@pmcmd('fpull', admin_only=True)
def fpull_pm(cli, nick, rest):
    fpull(cli, nick, nick, rest)


@pmcmd('fsend', admin_only=True)
def fsend(cli, nick, rest):
    print('[%s] %s fsend: %s' %
          (time.strftime('%Y-%m-%dT%H:%M:%S%z'), nick, rest))

    cli.send(rest)


def _say(cli, raw_nick, rest, command, action=False):
    (nick, _, user, host) = parse_nick(raw_nick)
    rest = rest.split(" ", 1)

    if len(rest) < 2:
        pm(cli, nick, "Usage: {0}{1} <target> <message>".format(
            command, botconfig.CMD_CHAR))

        return

    (target, message) = rest

    if not is_admin(host):
        if nick not in var.USERS:
            pm(cli, nick, "You have to be in {0} to use this command.".format(
                botconfig.CHANNEL))

            return

        if rest[0] != botconfig.CHANNEL:
            pm(cli, nick, ("You do not have permission to message this user "
                           "or channel."))

            return

    print("[{0}] {1} ({2}@{3}) {4} {5}: {6}".format(
        time.strftime("%Y-%m-%d %H:%M:%S%z"), nick, user, host, command,
        target, message))

    if action:
        message = "\x01ACTION {0}\x01".format(message)

    cli.send("PRIVMSG {0} :{1}".format(target, message))


@pmcmd("fsay", admin_only=True, raw_nick=True)
def fsay(cli, raw_nick, rest):
    _say(cli, raw_nick, rest, "fsay")


@pmcmd("fact", "fdo", "fme", admin_only=True, raw_nick=True)
def fact(cli, raw_nick, rest):
    _say(cli, raw_nick, rest, "fact", action=True)


before_debug_mode_commands = list(COMMANDS.keys())
before_debug_mode_pmcommands = list(PM_COMMANDS.keys())

if botconfig.DEBUG_MODE or botconfig.ALLOWED_NORMAL_MODE_COMMANDS:

    @cmd("eval", owner_only = True)
    @pmcmd("eval", owner_only = True)
    def pyeval(cli, nick, *rest):
        rest = list(rest)
        if len(rest) == 2:
            chan = rest.pop(0)
        else:
            chan = nick
        try:
            a = str(eval(rest[0]))
            if len(a) < 500:
                cli.msg(chan, a)
            else:
                cli.msg(chan, a[0:500])
        except Exception as e:
            cli.msg(chan, str(type(e))+":"+str(e))



    @cmd("exec", owner_only = True)
    @pmcmd("exec", owner_only = True)
    def py(cli, nick, *rest):
        rest = list(rest)
        if len(rest) == 2:
            chan = rest.pop(0)
        else:
            chan = nick
        try:
            exec(rest[0])
        except Exception as e:
            cli.msg(chan, str(type(e))+":"+str(e))


    @cmd('revealroles', admin_only=True)
    def revealroles(cli, nick, chan, rest):
        if var.PHASE == 'none':
            cli.notice(nick, 'No game is currently running.')
            return

        s = ' | '.join('\u0002{}\u0002: {}'.format(role,', '.join(players))
                for (role, players) in sorted(var.ROLES.items()) if players)

        if chan == nick:
            pm(cli, nick, s)
        else:
            cli.msg(chan, s)


    @cmd("fgame", admin_only=True, raw_nick=True)
    def fgame(cli, nick, chan, rest):
        (nick, _, __, cloak) = parse_nick(nick)

        pl = var.list_players()

        if var.PHASE == 'none':
            cli.notice(nick, 'No game is currently running.')
            return

        if var.PHASE != 'join':
            cli.notice(nick, 'Werewolf is already in play.')
            return

        if nick not in pl and cloak not in botconfig.ADMINS + botconfig.OWNERS:
            cli.notice(nick, 'You\'re currently not playing.')
            return

        if rest:
            rest = mode = rest.strip().lower()
            if rest not in var.GAME_MODES.keys() and not rest.startswith("roles"):
                rest = rest.split()[0]
                #players can vote by only using partial name
                matches = 0
                for gamemode in var.GAME_MODES.keys():
                    if gamemode.startswith(rest):
                        mode = gamemode
                        matches += 1
                if matches != 1:
                    cli.notice(nick, "\002{0}\002 is not a valid game mode.".format(rest))
                    return

            if cgamemode(cli, mode):
                cli.msg(chan, ('\u0002{}\u0002 has changed the game settings '
                                'successfully.').format(nick))
                var.FGAMED = True
        else:
            cli.notice(nick, fgame.__doc__())

    def fgame_help(args=''):
        args = args.strip()

        if not args:
            return 'Available game mode setters: ' + ', '.join(var.GAME_MODES.keys())
        elif args in var.GAME_MODES.keys():
            if hasattr(var.GAME_MODES[args][0], "__doc__"):
                return var.GAME_MODES[args][0].__doc__
            else:
                return "Game mode {0} has no doc string".format(args)
        else:
            return 'Game mode setter \u0002{}\u0002 not found.'.format(args)


    fgame.__doc__ = fgame_help


    # DO NOT MAKE THIS A PMCOMMAND ALSO
    @cmd("force", admin_only=True)
    def forcepm(cli, nick, chan, rest):
        rst = re.split(" +",rest)
        if len(rst) < 2:
            cli.msg(chan, "The syntax is incorrect.")
            return
        who = rst.pop(0).strip()
        if not who or who == botconfig.NICK:
            cli.msg(chan, "That won't work.")
            return
        if not is_fake_nick(who):
            ul = list(var.USERS.keys())
            ull = [u.lower() for u in ul]
            if who.lower() not in ull:
                cli.msg(chan, "This can only be done on fake nicks.")
                return
            else:
                who = ul[ull.index(who.lower())]
        cmd = rst.pop(0).lower().replace(botconfig.CMD_CHAR, "", 1)
        did = False
        if PM_COMMANDS.get(cmd) and not PM_COMMANDS[cmd][0].owner_only:
            if (PM_COMMANDS[cmd][0].admin_only and nick in var.USERS and
                not is_admin(var.USERS[nick]["cloak"])):
                # Not a full admin
                cli.notice(nick, "Only full admins can force an admin-only command.")
                return

            for fn in PM_COMMANDS[cmd]:
                if fn.raw_nick:
                    continue
                fn(cli, who, " ".join(rst))
                did = True
            if did:
                cli.msg(chan, "Operation successful.")
            else:
                cli.msg(chan, "Not possible with this command.")
            #if var.PHASE == "night":   <-  Causes problems with night starting twice.
            #    chk_nightdone(cli)
        elif COMMANDS.get(cmd) and not COMMANDS[cmd][0].owner_only:
            if (COMMANDS[cmd][0].admin_only and nick in var.USERS and
                not is_admin(var.USERS[nick]["cloak"])):
                # Not a full admin
                cli.notice(nick, "Only full admins can force an admin-only command.")
                return

            for fn in COMMANDS[cmd]:
                if fn.raw_nick:
                    continue
                fn(cli, who, chan, " ".join(rst))
                did = True
            if did:
                cli.msg(chan, "Operation successful.")
            else:
                cli.msg(chan, "Not possible with this command.")
        else:
            cli.msg(chan, "That command was not found.")


    @cmd("rforce", admin_only=True)
    def rforcepm(cli, nick, chan, rest):
        rst = re.split(" +",rest)
        if len(rst) < 2:
            cli.msg(chan, "The syntax is incorrect.")
            return
        who = rst.pop(0).strip().lower()
        who = who.replace("_", " ")

        if (who not in var.ROLES or not var.ROLES[who]) and (who != "gunner"
            or var.PHASE in ("none", "join")):
            cli.msg(chan, nick+": invalid role")
            return
        elif who == "gunner":
            tgt = list(var.GUNNERS.keys())
        else:
            tgt = var.ROLES[who]

        cmd = rst.pop(0).lower().replace(botconfig.CMD_CHAR, "", 1)
        if PM_COMMANDS.get(cmd) and not PM_COMMANDS[cmd][0].owner_only:
            if (PM_COMMANDS[cmd][0].admin_only and nick in var.USERS and
                not is_admin(var.USERS[nick]["cloak"])):
                # Not a full admin
                cli.notice(nick, "Only full admins can force an admin-only command.")
                return

            for fn in PM_COMMANDS[cmd]:
                for guy in tgt[:]:
                    fn(cli, guy, " ".join(rst))
            cli.msg(chan, "Operation successful.")
            #if var.PHASE == "night":   <-  Causes problems with night starting twice.
            #    chk_nightdone(cli)
        elif cmd.lower() in COMMANDS.keys() and not COMMANDS[cmd][0].owner_only:
            if (COMMANDS[cmd][0].admin_only and nick in var.USERS and
                not is_admin(var.USERS[nick]["cloak"])):
                # Not a full admin
                cli.notice(nick, "Only full admins can force an admin-only command.")
                return

            for fn in COMMANDS[cmd]:
                for guy in tgt[:]:
                    fn(cli, guy, chan, " ".join(rst))
            cli.msg(chan, "Operation successful.")
        else:
            cli.msg(chan, "That command was not found.")



    @cmd("frole", admin_only=True)
    def frole(cli, nick, chan, rest):
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
                var.ROLES[rol].append(who)
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
            if rol == "shaman" or rol == "crazed shaman":
                if len(rolargs) == 2:
                    var.TOTEMS[who] = rolargs[1]
                else:
                    rand = random.random()
                    target = 0
                    for t, c in var.TOTEM_CHANCES.items():
                        target += var.TOTEM_CHANCES[t][0 if rol == "shaman" else 1]
                        if rand <= target:
                            var.TOTEMS[who] = t
                            break
                    else:
                        var.TOTEMS[who] = 'death'
            var.ROLES[rol].append(who)
        else:
            cli.msg(chan, "Not a valid role.")
            return
        cli.msg(chan, "Operation successful.")
        if var.PHASE not in ('none','join'):
            chk_win(cli)


if botconfig.ALLOWED_NORMAL_MODE_COMMANDS and not botconfig.DEBUG_MODE:
    for comd in list(COMMANDS.keys()):
        if (comd not in before_debug_mode_commands and
            comd not in botconfig.ALLOWED_NORMAL_MODE_COMMANDS):
            del COMMANDS[comd]
    for pmcomd in list(PM_COMMANDS.keys()):
        if (pmcomd not in before_debug_mode_pmcommands and
            pmcomd not in botconfig.ALLOWED_NORMAL_MODE_COMMANDS):
            del PM_COMMANDS[pmcomd]

# vim: set expandtab:sw=4:ts=4:
