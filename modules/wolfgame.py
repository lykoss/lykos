# Copyright (c) 2011, Jimmy Cao
# All rights reserved.

# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

# Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from oyoyo.parse import parse_nick
import settings.wolfgame as var
import botconfig
from tools.wolfgamelogger import WolfgameLogger
from tools import decorators
from datetime import datetime, timedelta
from collections import defaultdict
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
var.PHASE = "none"  # "join", "day", or "night"
var.TIMERS = {}
var.DEAD = []

var.ORIGINAL_SETTINGS = {}

var.LAST_SAID_TIME = {}

var.GAME_START_TIME = datetime.now()  # for idle checker only
var.CAN_START_TIME = 0
var.GRAVEYARD_LOCK = threading.RLock()
var.GAME_ID = 0

var.DISCONNECTED = {}  # players who got disconnected

var.STASISED = defaultdict(int)

var.LOGGER = WolfgameLogger(var.LOG_FILENAME, var.BARE_LOG_FILENAME)

var.JOINED_THIS_GAME = [] # keeps track of who already joined this game at least once (cloaks)

if botconfig.DEBUG_MODE:
    var.NIGHT_TIME_LIMIT = 0  # 90
    var.NIGHT_TIME_WARN = 0
    var.DAY_TIME_LIMIT_WARN = 0
    var.DAY_TIME_LIMIT_CHANGE = 0
    var.KILL_IDLE_TIME = 0 #300
    var.WARN_IDLE_TIME = 0 #180

        
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
            if modeaction == "+o" and target == botconfig.NICK and var.PHASE == "none":
                
                @hook("quietlistend", 294)
                def on_quietlist_end(cli, svr, nick, chan, *etc):
                    if chan == botconfig.CHANNEL:
                        decorators.unhook(HOOKS, 294)
                        mass_mode(cli, cmodes)
                
                cli.mode(botconfig.CHANNEL, "q")  # unquiet all

                cli.mode(botconfig.CHANNEL, "-m")  # remove -m mode from channel
            elif modeaction == "+o" and target == botconfig.NICK and var.PHASE != "none":
                decorators.unhook(HOOKS, 294)  # forget about it


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
    if target in var.USERS and var.USERS[target]["cloak"] in var.SIMPLE_NOTIFY:
        cli.notice(target, message)
    else:
        cli.msg(target, message)

def reset_settings():
    for attr in list(var.ORIGINAL_SETTINGS.keys()):
        setattr(var, attr, var.ORIGINAL_SETTINGS[attr])
    dict.clear(var.ORIGINAL_SETTINGS)

def reset_modes(cli):
    cli.mode(botconfig.CHANNEL, "-m")
    cmodes = []
    for plr in var.list_players():
        cmodes.append(("-v", plr))
    for deadguy in var.DEAD:
        cmodes.append(("-q", deadguy+"!*@*"))
    mass_mode(cli, cmodes)

def reset(cli):
    var.PHASE = "none"

    for x, timr in var.TIMERS.items():
        timr.cancel()
    var.TIMERS = {}
    
    var.GAME_ID = 0

    var.DEAD = []

    var.ROLES = {"person" : []}

    var.JOINED_THIS_GAME = []

    reset_settings()

    dict.clear(var.LAST_SAID_TIME)
    dict.clear(var.PLAYERS)
    dict.clear(var.DCED_PLAYERS)
    dict.clear(var.DISCONNECTED)

def make_stasis(nick, penalty):
    try:
        cloak = var.USERS[nick]['cloak']
        if cloak is not None:
            var.STASISED[cloak] += penalty
    except KeyError:
        pass

@pmcmd("fdie", "fbye", admin_only=True)
@cmd("fdie", "fbye", admin_only=True)
def forced_exit(cli, nick, *rest):  # Admin Only
    """Forces the bot to close"""
    
    if var.PHASE in ("day", "night"):
        stop_game(cli)
    else:
        reset_modes(cli)
        reset(cli)

    cli.quit("Forced quit from "+nick)



@pmcmd("frestart", admin_only=True)
@cmd("frestart", admin_only=True)
def restart_program(cli, nick, *rest):
    """Restarts the bot."""
    try:
        if var.PHASE in ("day", "night"):
            stop_game(cli)
        else:
            reset_modes(cli)
            reset(cli)

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
    
            

@cmd("ping")
def pinger(cli, nick, chan, rest):
    """Pings the channel to get people's attention.  Rate-Limited."""
    if (var.LAST_PING and
        var.LAST_PING + timedelta(seconds=var.PING_WAIT) > datetime.now()):
        cli.notice(nick, ("This command is rate-limited. " +
                          "Please wait a while before using it again."))
        return
        
    if var.PHASE in ('night','day'):
        cli.notice(nick, "You cannot use this command while a game is running.")
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
    """If you want the bot to NOTICE you for every interaction"""
    
    nick, _, __, cloak = parse_nick(nick)
    
    if cloak in var.SIMPLE_NOTIFY:
        var.SIMPLE_NOTIFY.remove(cloak)
        var.remove_simple_rolemsg(cloak)
        
        cli.notice(nick, "You now no longer receive simple role instructions.")
        return
        
    var.SIMPLE_NOTIFY.append(cloak)
    var.add_simple_rolemsg(cloak)
    
    cli.notice(nick, "You now receive simple role instructions.")

if not var.OPT_IN_PING:
    @cmd("away", raw_nick=True)
    @pmcmd("away", raw_nick=True)
    def away(cli, nick, *rest):
        """Use this to activate your away status (so you aren't pinged)."""
        nick, _, _, cloak = parse_nick(nick)
        if cloak in var.AWAY:
            var.AWAY.remove(cloak)
            var.remove_away(cloak)

            cli.notice(nick, "You are no longer marked as away.")
            return
        var.AWAY.append(cloak)
        var.add_away(cloak)

        cli.notice(nick, "You are now marked as away.")

    @cmd("back", raw_nick=True)
    @pmcmd("back", raw_nick=True)
    def back_from_away(cli, nick, *rest):
        """Unmarks away status"""
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
        """Get yourself in the ping list"""
        nick, _, _, cloak = parse_nick(nick)
        if cloak in var.PING_IN:
            cli.notice(nick, "You are already on the list")
            return
        var.PING_IN.append(cloak)
        var.add_ping(cloak)

        cli.notice(nick, "You are now on the list.")

    @cmd("out", raw_nick=True)
    @pmcmd("out", raw_nick=True)
    def get_out(cli, nick, *rest):
        """Removes yourself from the ping list"""
        nick, _, _, cloak = parse_nick(nick)
        if cloak in var.PING_IN:
            var.PING_IN.remove(cloak)
            var.remove_ping(cloak)

            cli.notice(nick, "You are no longer in the list.")
            return
        cli.notice(nick, "You are not in the list.")


@cmd("fping", admin_only=True)
def fpinger(cli, nick, chan, rest):
    var.LAST_PING = None
    pinger(cli, nick, chan, rest)



@cmd("join", raw_nick=True)
def join(cli, nick, chann_, rest):
    """Either starts a new game of Werewolf or joins an existing game that has not started yet."""
    pl = var.list_players()
    
    chan = botconfig.CHANNEL
    
    nick, _, __, cloak = parse_nick(nick)

    try:
        cloak = var.USERS[nick]['cloak']
        if cloak is not None and cloak in var.STASISED and var.STASISED[cloak] > 0:
            cli.notice(nick, "Sorry, but you are in stasis for {0} games.".format(var.STASISED[cloak]))
            return
    except KeyError:
        cloak = None
    

    if var.PHASE == "none":
    
        cli.mode(chan, "+v", nick)
        var.ROLES["person"].append(nick)
        var.PHASE = "join"
        var.WAITED = 0
        var.GAME_ID = time.time()
        var.JOINED_THIS_GAME.append(cloak)
        var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.MINIMUM_WAIT)
        cli.msg(chan, ('\u0002{0}\u0002 has started a game of Werewolf. '+
                      'Type "{1}join" to join. Type "{1}start" to start the game. '+
                      'Type "{1}wait" to increase start wait time.').format(nick, botconfig.CMD_CHAR))
    elif nick in pl:
        cli.notice(nick, "You're already playing!")
    elif len(pl) >= var.MAX_PLAYERS:
        cli.notice(nick, "Too many players!  Try again next time.")
    elif var.PHASE != "join":
        cli.notice(nick, "Sorry but the game is already running.  Try again next time.")
    else:
    
        cli.mode(chan, "+v", nick)
        var.ROLES["person"].append(nick)
        cli.msg(chan, '\u0002{0}\u0002 has joined the game and raised the number of players to \u0002{1}\u0002.'.format(nick, len(pl) + 1))
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


@cmd("fjoin", admin_only=True)
def fjoin(cli, nick, chann_, rest):
    noticed = False
    chan = botconfig.CHANNEL
    if not rest.strip():
        join(cli, nick, chan, "")

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
        if a != botconfig.NICK:
            join(cli, a.strip(), chan, "")
        else:
            cli.notice(nick, "No, that won't be allowed.")

@cmd("fleave","fquit","fdel", admin_only=True)
def fleave(cli, nick, chann_, rest):
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
        cli.msg(chan, ("\u0002{0}\u0002 is forcing"+
                       " \u0002{1}\u0002 to leave.").format(nick, a))
        cli.msg(chan, "Say goodbye to the \02{0}\02.".format(var.get_role(a)))
        if var.PHASE == "join":
            cli.msg(chan, ("New player count: \u0002{0}\u0002").format(len(var.list_players()) - 1))
        if var.PHASE in ("day", "night"):
            var.LOGGER.logMessage("{0} is forcing {1} to leave.".format(nick, a))
            var.LOGGER.logMessage("Say goodbye to the {0}".format(var.get_role(a)))
        del_player(cli, a)


@cmd("fstart", admin_only=True)
def fstart(cli, nick, chan, rest):
    var.CAN_START_TIME = datetime.now()
    cli.msg(botconfig.CHANNEL, "\u0002{0}\u0002 has forced the game to start.".format(nick))
    start(cli, nick, chan, rest)



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
@pmcmd("stats")
def stats(cli, nick, chan, rest):
    """Display the player statistics"""
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
        
    pl = var.list_players()
    
    if nick in pl or var.PHASE == "join":
        # only do this rate-limiting stuff if the person is in game
        if (var.LAST_STATS and
            var.LAST_STATS + timedelta(seconds=var.STATS_RATE_LIMIT) > datetime.now()):
            cli.notice(nick, ("This command is rate-limited. " +
                              "Please wait a while before using it again."))
            return
            
        var.LAST_STATS = datetime.now()
    
    pl.sort(key=lambda x: x.lower())
    if len(pl) > 1:
        msg = '{0}: \u0002{1}\u0002 players: {2}'.format(nick,
            len(pl), ", ".join(pl))
    else:
        msg = '{0}: \u00021\u0002 player: {1}'.format(nick, pl[0])
    
    if nick in pl or var.PHASE == "join":
        cli.msg(chan, msg)
        var.LOGGER.logMessage(msg.replace("\02", ""))
    else:
   
        cli.notice(nick, msg)
        
    if var.PHASE == "join":
        return

    message = []
    f = False  # set to true after the is/are verb is decided
    l1 = [k for k in var.ROLES.keys()
          if var.ROLES[k]]
    l2 = [k for k in var.ORIGINAL_ROLES.keys()
          if var.ORIGINAL_ROLES[k]]
    rs = list(set(l1+l2))
        
    # Due to popular demand, picky ordering
    if "wolf" in rs:
        rs.remove("wolf")
        rs.insert(0, "wolf")
    if "seer" in rs:
        rs.remove("seer")
        rs.insert(1, "seer")
    if "villager" in rs:
        rs.remove("villager")
        rs.append("villager")
        
        
    firstcount = len(var.ROLES[rs[0]])
    if firstcount > 1 or not firstcount:
        vb = "are"
    else:
        vb = "is"
    for role in rs:
        count = len(var.ROLES[role])
        if role == "traitor" and var.HIDDEN_TRAITOR:
            continue
        elif role == "villager" and var.HIDDEN_TRAITOR:
            count += len(var.ROLES["traitor"])
                
        if count > 1 or count == 0:
            message.append("\u0002{0}\u0002 {1}".format(count if count else "\u0002no\u0002", var.plural(role)))
        else:
            message.append("\u0002{0}\u0002 {1}".format(count, role))
    stats_mssg =  "{0}: It is currently {4}. There {3} {1}, and {2}.".format(nick,
                                                        ", ".join(message[0:-1]),
                                                        message[-1],
                                                        vb,
                                                        var.PHASE)
    if nick in pl or var.PHASE == "join":
        cli.msg(chan, stats_mssg)
        var.LOGGER.logMessage(stats_mssg.replace("\02", ""))
    else:
        cli.notice(nick, stats_mssg)



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
        if not var.DAY_TIME_LIMIT_CHANGE:
            return
        if (len(var.list_players()) <= var.SHORT_DAY_PLAYERS):
            tmr = threading.Timer(var.SHORT_DAY_LIMIT_CHANGE, hurry_up, [cli, var.DAY_ID, True])
        else:
            tmr = threading.Timer(var.DAY_TIME_LIMIT_CHANGE, hurry_up, [cli, var.DAY_ID, True])
        tmr.daemon = True
        var.TIMERS["day"] = tmr
        tmr.start()
        return
        
    
    var.DAY_ID = 0
    
    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED)
    votesneeded = avail // 2 + 1

    found_dup = False
    maxfound = (0, "")
    for votee, voters in iter(var.VOTES.items()):
        if len(voters) > maxfound[0]:
            maxfound = (len(voters), votee)
            found_dup = False
        elif len(voters) == maxfound[0]:
            found_dup = True
    if maxfound[0] > 0 and not found_dup:
        cli.msg(chan, "The sun sets.")
        var.LOGGER.logMessage("The sun sets.")
        var.VOTES[maxfound[1]] = [None] * votesneeded
        chk_decision(cli)  # Induce a lynch
    else:
        cli.msg(chan, ("As the sun sets, the villagers agree to "+
                      "retire to their beds and wait for morning."))
        var.LOGGER.logMessage(("As the sun sets, the villagers agree to "+
                               "retire to their beds and wait for morning."))
        transition_night(cli)
        



@cmd("fnight", admin_only=True)
def fnight(cli, nick, chan, rest):
    if var.PHASE != "day":
        cli.notice(nick, "It is not daytime.")
    else:
        hurry_up(cli, 0, True)


@cmd("fday", admin_only=True)
def fday(cli, nick, chan, rest):
    if var.PHASE != "night":
        cli.notice(nick, "It is not nighttime.")
    else:
        transition_day(cli)



def chk_decision(cli):
    chan = botconfig.CHANNEL
    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED)
    votesneeded = avail // 2 + 1
    for votee, voters in iter(var.VOTES.items()):
        if len(voters) >= votesneeded:
            lmsg = random.choice(var.LYNCH_MESSAGES).format(votee, var.get_reveal_role(votee))
            cli.msg(botconfig.CHANNEL, lmsg)
            var.LOGGER.logMessage(lmsg.replace("\02", ""))
            var.LOGGER.logBare(votee, "LYNCHED")
            if del_player(cli, votee, True):
                transition_night(cli)



@cmd("votes")
def show_votes(cli, nick, chan, rest):
    """Displays the voting statistics."""
    
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "day":
        cli.notice(nick, "Voting is only during the day.")
        return
    
    if (var.LAST_VOTES and
        var.LAST_VOTES + timedelta(seconds=var.VOTES_RATE_LIMIT) > datetime.now()):
        cli.notice(nick, ("This command is rate-limited." +
                          "Please wait a while before using it again."))
        return    
    
    pl = var.list_players()
    
    if nick in pl:
        var.LAST_VOTES = datetime.now()    
        
    if not var.VOTES.values():
        msg = nick+": No votes yet."
        if nick in pl:
            var.LAST_VOTES = None # reset
    else:
        votelist = ["{0}: {1} ({2})".format(votee,
                                            len(var.VOTES[votee]),
                                            " ".join(var.VOTES[votee]))
                    for votee in var.VOTES.keys()]
        msg = "{0}: {1}".format(nick, ", ".join(votelist))
        
    if nick in pl:
        cli.msg(chan, msg)
    else:
        cli.notice(nick, msg)

    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED)
    votesneeded = avail // 2 + 1
    the_message = ("{0}: \u0002{1}\u0002 players, \u0002{2}\u0002 votes "+
                   "required to lynch, \u0002{3}\u0002 players available " +
                   "to vote.").format(nick, len(pl), votesneeded, avail)
    if nick in pl:
        cli.msg(chan, the_message)
    else:
        cli.notice(nick, the_message)



def chk_traitor(cli):
    for tt in var.ROLES["traitor"]:
        var.ROLES["wolf"].append(tt)
        var.ROLES["traitor"].remove(tt)
        pm(cli, tt, ('HOOOOOOOOOWL. You have become... a wolf!\n'+
                     'It is up to you to avenge your fallen leaders!'))



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
    
    var.ORIGINAL_ROLES["cursed villager"] = var.CURSED  # A hack
    var.ORIGINAL_ROLES["gunner"] = list(var.GUNNERS.keys())

    lroles = list(var.ORIGINAL_ROLES.keys())
    lroles.remove("wolf")
    lroles.insert(0, "wolf")   # picky, howl consistency
    
    for role in lroles:
        if len(var.ORIGINAL_ROLES[role]) == 0 or role == "villager":
            continue
        playersinrole = list(var.ORIGINAL_ROLES[role])
        for i,plr in enumerate(playersinrole):
            if plr.startswith("(dced)"):  # don't care about it here
                playersinrole[i] = plr[6:]
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
    cli.msg(chan, " ".join(roles_msg))

    reset_modes(cli)
    
    plrl = []
    for role,ppl in var.ORIGINAL_ROLES.items():
        for x in ppl:
            plrl.append((x, role))
    
    var.LOGGER.saveToFile()
    
    for plr, rol in plrl:
        #if plr not in var.USERS.keys():  # they died TODO: when a player leaves, count the game as lost for them
        #    if plr in var.DEAD_USERS.keys():
        #        acc = var.DEAD_USERS[plr]["account"]
        #    else:
        #        continue  # something wrong happened
        #else:
        if plr.startswith("(dced)") and plr[6:] in var.DCED_PLAYERS.keys():
            acc = var.DCED_PLAYERS[plr[6:]]["account"]
        elif plr in var.PLAYERS.keys():
            acc = var.PLAYERS[plr]["account"]
        else:
            continue  #probably fjoin'd fake

        if acc == "*":
            continue  # not logged in during game start
        # determine if this player's team won
        if plr in (var.ORIGINAL_ROLES["wolf"] + var.ORIGINAL_ROLES["traitor"] +
                   var.ORIGINAL_ROLES["werecrow"]):  # the player was wolf-aligned
            if winner == "wolves":
                won = True
            elif winner == "villagers":
                won = False
            else:
                break  # abnormal game stop
        else:
            if winner == "wolves":
                won = False
            elif winner == "villagers":
                won = True
            else:
                break
                
        iwon = won and plr in var.list_players()  # survived, team won = individual win
                
        var.update_role_stats(acc, rol, won, iwon)
    
    size = len(var.list_players()) + len(var.DEAD)
    if winner != "": # Only update if not an abnormal game stop
        var.update_game_stats(size, winner)
    
    reset(cli)
    
    # This must be after reset(cli)
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
    
    if lpl == 0:
        #cli.msg(chan, "No more players remaining. Game ended.")
        reset_modes(cli)
        reset(cli)
        return True
        
    if var.PHASE == "join":
        return False
        
        
    lwolves = (len(var.ROLES["wolf"])+
               len(var.ROLES["traitor"])+
               len(var.ROLES["werecrow"]))
    if var.PHASE == "day":
        lpl -= len([x for x in var.WOUNDED if x not in var.ROLES["traitor"]])
        lwolves -= len([x for x in var.WOUNDED if x in var.ROLES["traitor"]])
    
    if lwolves == lpl / 2:
        message = ("Game over! There are the same number of wolves as " +
                  "uninjured villagers. The wolves overpower the villagers and win.")
        village_win = False
    elif lwolves > lpl / 2:
        message = ("Game over! There are more wolves than "+
                  "uninjured villagers. The wolves overpower the villagers and win.")
        village_win = False
    elif (not var.ROLES["wolf"] and
          not var.ROLES["traitor"] and
          not var.ROLES["werecrow"]):
        message = ("Game over! All the wolves are dead! The villagers " +
                  "chop them up, BBQ them, and have a hearty meal.")
        village_win = True
    elif (not var.ROLES["wolf"] and not 
          var.ROLES["werecrow"] and var.ROLES["traitor"]):
        for t in var.ROLES["traitor"]:
            var.LOGGER.logBare(t, "TRANSFORM")
        chk_traitor(cli)
        cli.msg(chan, ('\u0002The villagers, during their celebrations, are '+
                       'frightened as they hear a loud howl. The wolves are '+
                       'not gone!\u0002'))
        var.LOGGER.logMessage(('The villagers, during their celebrations, are '+
                               'frightened as they hear a loud howl. The wolves are '+
                               'not gone!'))
        return chk_win(cli, end_game)
    else:
        return False
    if end_game:
        cli.msg(chan, message)
        var.LOGGER.logMessage(message)
        var.LOGGER.logBare("VILLAGERS" if village_win else "WOLVES", "WIN")
        stop_game(cli, "villagers" if village_win else "wolves")
    return True





def del_player(cli, nick, forced_death = False, devoice = True, end_game = True):
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
        if devoice:
            cmode.append(("-v", nick))
        var.del_player(nick)
        ret = True
        if var.PHASE == "join":
            # Died during the joining process as a person
            mass_mode(cli, cmode)
            return not chk_win(cli)
        if var.PHASE != "join":
            # Died during the game, so quiet!
            if not is_fake_nick(nick):
                cmode.append(("+q", nick+"!*@*"))
            mass_mode(cli, cmode)
            if nick not in var.DEAD:
                var.DEAD.append(nick)
            ret = not chk_win(cli, end_game)
        if var.PHASE in ("night", "day") and ret:
            # remove the player from variables if they're in there
            for a,b in list(var.KILLS.items()):
                if b == nick:
                    del var.KILLS[a]
                elif a == nick:
                    del var.KILLS[a]
            for x in (var.OBSERVED, var.HVISITED, var.GUARDED):
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
                    
            if nick in var.WOUNDED:
                var.WOUNDED.remove(nick)
            chk_decision(cli)
        elif var.PHASE == "night" and ret:
            chk_nightdone(cli)
        return ret  


def reaper(cli, gameid):
    # check to see if idlers need to be killed.
    var.IDLE_WARNED = []
    chan = botconfig.CHANNEL
    
    while gameid == var.GAME_ID:
        with var.GRAVEYARD_LOCK:
            if var.WARN_IDLE_TIME or var.KILL_IDLE_TIME:  # only if enabled
                to_warn = []
                to_kill = []
                for nick in var.list_players():
                    lst = var.LAST_SAID_TIME.get(nick, var.GAME_START_TIME)
                    tdiff = datetime.now() - lst
                    if (tdiff > timedelta(seconds=var.WARN_IDLE_TIME) and
                                            nick not in var.IDLE_WARNED):
                        if var.WARN_IDLE_TIME:
                            to_warn.append(nick)
                        var.IDLE_WARNED.append(nick)
                        var.LAST_SAID_TIME[nick] = (datetime.now() -
                            timedelta(seconds=var.WARN_IDLE_TIME))  # Give them a chance
                    elif (tdiff > timedelta(seconds=var.KILL_IDLE_TIME) and
                        nick in var.IDLE_WARNED):
                        if var.KILL_IDLE_TIME:
                            to_kill.append(nick)
                    elif (tdiff < timedelta(seconds=var.WARN_IDLE_TIME) and
                        nick in var.IDLE_WARNED):
                        var.IDLE_WARNED.remove(nick)  # player saved himself from death
                for nck in to_kill:
                    if nck not in var.list_players():
                        continue
                    cli.msg(chan, ("\u0002{0}\u0002 didn't get out of bed for a very long "+
                                   "time and has been found dead. The survivors bury "+
                                   "the \u0002{1}\u0002's body.").format(nck, var.get_reveal_role(nck)))
                    make_stasis(nck, var.IDLE_STASIS_PENALTY)
                    if not del_player(cli, nck):
                        return
                pl = var.list_players()
                x = [a for a in to_warn if a in pl]
                if x:
                    cli.msg(chan, ("{0}: \u0002You have been idling for a while. "+
                                   "Please say something soon or you "+
                                   "might be declared dead.\u0002").format(", ".join(x)))
            for dcedplayer in list(var.DISCONNECTED.keys()):
                _, timeofdc, what = var.DISCONNECTED[dcedplayer]
                if what == "quit" and (datetime.now() - timeofdc) > timedelta(seconds=var.QUIT_GRACE_TIME):
                    cli.msg(chan, ("\02{0}\02 was mauled by wild animals and has died. It seems that "+
                                   "\02{1}\02 meat is tasty.").format(dcedplayer, var.get_reveal_role(dcedplayer)))
                    if var.PHASE != "join":
                        make_stasis(dcedplayer, var.PART_STASIS_PENALTY)
                    if not del_player(cli, dcedplayer, devoice = False):
                        return
                elif what == "part" and (datetime.now() - timeofdc) > timedelta(seconds=var.PART_GRACE_TIME):
                    cli.msg(chan, ("\02{0}\02, a \02{1}\02, ate some poisonous berries "+
                                   "and has died.").format(dcedplayer, var.get_reveal_role(dcedplayer)))
                    if var.PHASE != "join":
                        make_stasis(dcedplayer, var.PART_STASIS_PENALTY)
                    if not del_player(cli, dcedplayer, devoice = False):
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

@cmd("goat")
def goat(cli, nick, chan, rest):
    """Use a goat to interact with anyone in the channel during the day"""
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    if var.PHASE != "day":
        cli.notice(nick, "You can only do that in the day.")
        return
    if var.GOATED and nick not in var.SPECIAL_ROLES["goat herder"]:
        cli.notice(nick, "You can only do that once per day.")
        return
    ul = list(var.USERS.keys())
    ull = [x.lower() for x in ul]
    rest = re.split(" +",rest)[0].strip().lower()
    if not rest:
        cli.notice(nick, "Not enough parameters.")
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
            pm(cli, nick,"\u0002{0}\u0002 is not in this channel.".format(rest))
            return
    victim = ul[ull.index(victim)]
    cli.msg(botconfig.CHANNEL, ("\u0002{0}\u0002's goat walks by "+
                                "and kicks \u0002{1}\u0002.").format(nick,
                                                                     victim))
    var.LOGGER.logMessage("{0}'s goat walks by and kicks {1}.".format(nick, victim))
    var.GOATED = True
    
    

@hook("nick")
def on_nick(cli, prefix, nick):
    prefix,u,m,cloak = parse_nick(prefix)
    chan = botconfig.CHANNEL

    if prefix in var.USERS:
        var.USERS[nick] = var.USERS.pop(prefix)
        
    if prefix == var.ADMIN_TO_PING:
        var.ADMIN_TO_PING = nick

    # for k,v in list(var.DEAD_USERS.items()):
        # if prefix == k:
            # var.DEAD_USERS[nick] = var.DEAD_USERS[k]
            # del var.DEAD_USERS[k]

    if prefix in var.list_players() and prefix not in var.DISCONNECTED.keys():
        r = var.ROLES[var.get_role(prefix)]
        r.append(nick)
        r.remove(prefix)

        if var.PHASE in ("night", "day"):
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
            if prefix in var.CURSED:
                var.CURSED.append(nick)
                var.CURSED.remove(prefix)
            for dictvar in (var.HVISITED, var.OBSERVED, var.GUARDED, var.KILLS):
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
            if prefix in var.SEEN:
                var.SEEN.remove(prefix)
                var.SEEN.append(nick)
            with var.GRAVEYARD_LOCK:  # to be safe
                if prefix in var.LAST_SAID_TIME.keys():
                    var.LAST_SAID_TIME[nick] = var.LAST_SAID_TIME.pop(prefix)
                if prefix in var.IDLE_WARNED:
                    var.IDLE_WARNED.remove(prefix)
                    var.IDLE_WARNED.append(nick)

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
                    
                    cli.msg(chan, ("\02{0}\02 has returned to "+
                                   "the village.").format(nick))

def leave(cli, what, nick, why=""):
    nick, _, _, cloak = parse_nick(nick)

    if what == "part" and why != botconfig.CHANNEL: return
        
    if why and why == botconfig.CHANGING_HOST_QUIT_MESSAGE:
        return
    if var.PHASE == "none":
        return
    if nick in var.PLAYERS:
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
    if what == "part" and (not var.PART_GRACE_TIME or var.PHASE == "join"):
        msg = ("\02{0}\02, a \02{1}\02, ate some poisonous berries and has "+
               "died.").format(nick, var.get_reveal_role(nick))
    elif what == "quit" and (not var.QUIT_GRACE_TIME or var.PHASE == "join"):
        msg = ("\02{0}\02 was mauled by wild animals and has died. It seems that "+
               "\02{1}\02 meat is tasty.").format(nick, var.get_reveal_role(nick))
    elif what != "kick":
        msg = "\u0002{0}\u0002 has gone missing.".format(nick)
        killplayer = False
    else:
        msg = ("\02{0}\02 died due to falling off a cliff. The "+
               "\02{1}\02 is lost to the ravine forever.").format(nick, var.get_reveal_role(nick))
    cli.msg(botconfig.CHANNEL, msg)
    var.LOGGER.logMessage(msg.replace("\02", ""))
    if killplayer:
        del_player(cli, nick)
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
    cli.msg(botconfig.CHANNEL, ("\02{0}\02, a \02{1}\02, has died of an unknown disease.{2}").format(nick, var.get_reveal_role(nick), population))
    var.LOGGER.logMessage(("{0}, a {1}, has died of an unknown disease.").format(nick, var.get_reveal_role(nick)))
    if var.PHASE != "join":
        make_stasis(nick, var.LEAVE_STASIS_PENALTY)

    del_player(cli, nick)
    



def begin_day(cli):
    chan = botconfig.CHANNEL

    # Reset nighttime variables
    var.KILLS = {}  # nicknames of kill victim
    var.GUARDED = ""
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = []  # list of seers that have had visions
    var.OBSERVED = {}  # those whom werecrows have observed
    var.HVISITED = {}
    var.GUARDED = {}

    msg = ("The villagers must now vote for whom to lynch. "+
           'Use "{0}lynch <nick>" to cast your vote. {1} votes '+
           'are required to lynch.').format(botconfig.CMD_CHAR, len(var.list_players()) // 2 + 1)
    cli.msg(chan, msg)
    var.LOGGER.logMessage(msg)
    var.LOGGER.logBare("DAY", "BEGIN")

    if var.DAY_TIME_LIMIT_WARN > 0:  # Time limit enabled
        var.DAY_ID = time.time()
        if len(var.list_players()) <= var.SHORT_DAY_PLAYERS:
            t = threading.Timer(var.SHORT_DAY_LIMIT_WARN, hurry_up, [cli, var.DAY_ID, False])
        else:
            t = threading.Timer(var.DAY_TIME_LIMIT_WARN, hurry_up, [cli, var.DAY_ID, False])
        var.TIMERS["day_warn"] = t
        t.daemon = True
        t.start()

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
    
    # Reset daytime variables
    var.VOTES = {}
    var.INVESTIGATED = []
    var.WOUNDED = []
    var.DAY_START_TIME = datetime.now()

    if (not len(var.SEEN)+len(var.KILLS)+len(var.OBSERVED) # neither seer nor wolf acted
            and not var.START_WITH_DAY and var.FIRST_NIGHT and var.ROLES["seer"] and not botconfig.DEBUG_MODE):
        cli.msg(botconfig.CHANNEL, "\02The wolves all die of a mysterious plague.\02")
        for x in var.ROLES["wolf"]+var.ROLES["werecrow"]+var.ROLES["traitor"]:
            if not del_player(cli, x, True):
                return
    
    var.FIRST_NIGHT = False

    td = var.DAY_START_TIME - var.NIGHT_START_TIME
    var.NIGHT_START_TIME = None
    var.NIGHT_TIMEDELTA += td
    min, sec = td.seconds // 60, td.seconds % 60

    found = {}
    for v in var.KILLS.values():
        if v in found:
            found[v] += 1
        else:
            found[v] = 1
    
    maxc = 0
    victim = ""
    dups = []
    for v, c in found.items():
        if c > maxc:
            maxc = c
            victim = v
            dups = []
        elif c == maxc:
            dups.append(v)

    if maxc:
        if dups:
            dups.append(victim)
            victim = random.choice(dups)
    
    message = [("Night lasted \u0002{0:0>2}:{1:0>2}\u0002. It is now daytime. "+
               "The villagers awake, thankful for surviving the night, "+
               "and search the village... ").format(min, sec)]
    dead = []
    crowonly = var.ROLES["werecrow"] and not var.ROLES["wolf"]
    if victim:
        var.LOGGER.logBare(victim, "WOLVESVICTIM", *[y for x,y in var.KILLS.items() if x == victim])
    for crow, target in iter(var.OBSERVED.items()):
        if ((target in list(var.HVISITED.keys()) and var.HVISITED[target]) or  # if var.HVISITED[target] is None, harlot visited self
            target in var.SEEN+list(var.GUARDED.keys())):
            pm(cli, crow, ("As the sun rises, you conclude that \u0002{0}\u0002 was not in "+
                          "bed all night, and you fly back to your house.").format(target))
        else:
            pm(cli, crow, ("As the sun rises, you conclude that \u0002{0}\u0002 was sleeping "+
                          "all night long, and you fly back to your house.").format(target))
    if victim in var.GUARDED.values():
        message.append(("\u0002{0}\u0002 was attacked by the wolves last night, but luckily, the "+
                        "guardian angel was on duty.").format(victim))
        victim = ""
    elif not victim:
        message.append(random.choice(var.NO_VICTIMS_MESSAGES) +
                    " All villagers, however, have survived.")
    elif victim in var.ROLES["harlot"]:  # Attacked harlot, yay no kill
        if var.HVISITED.get(victim):
            message.append("The wolves' selected victim was a harlot, "+
                           "who was not at home last night.")
            victim = ""
    if victim and (victim not in var.ROLES["harlot"] or   # not a harlot
                          not var.HVISITED.get(victim)):   # harlot stayed home
        message.append(("The dead body of \u0002{0}\u0002, a "+
                        "\u0002{1}\u0002, is found. Those remaining mourn the "+
                        "tragedy.").format(victim, var.get_role(victim)))
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
            
    if victim in var.GUNNERS.keys() and var.GUNNERS[victim]:  # victim had bullets!
        if random.random() < var.GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE:
            wc = var.ROLES["werecrow"][:]
            for crow in wc:
                if crow in var.OBSERVED.keys():
                    wc.remove(crow)
            # don't kill off werecrows that observed
            deadwolf = random.choice(var.ROLES["wolf"]+wc)
            message.append(("Fortunately, the victim, \02{0}\02, had bullets, and "+
                            "\02{1}\02, a \02{2}\02, was shot dead.").format(victim, deadwolf, var.get_role(deadwolf)))
            var.LOGGER.logBare(deadwolf, "KILLEDBYGUNNER")
            dead.append(deadwolf)
    if victim in var.HVISITED.values():  #  victim was visited by some harlot
        for hlt in var.HVISITED.keys():
            if var.HVISITED[hlt] == victim:
                message.append(("\02{0}\02, a \02harlot\02, made the unfortunate mistake of "+
                                "visiting the victim's house last night and is "+
                                "now dead.").format(hlt))
                dead.append(hlt)
    for harlot in var.ROLES["harlot"]:
        if var.HVISITED.get(harlot) in var.ROLES["wolf"]+var.ROLES["werecrow"]:
            message.append(("\02{0}\02, a \02harlot\02, made the unfortunate mistake of "+
                            "visiting a wolf's house last night and is "+
                            "now dead.").format(harlot))
            dead.append(harlot)
    for gangel in var.ROLES["guardian angel"]:
        if var.GUARDED.get(gangel) in var.ROLES["wolf"]+var.ROLES["werecrow"]:
            if victim == gangel:
                continue # already dead.
            r = random.random()
            if r < var.GUARDIAN_ANGEL_DIES_CHANCE:
                message.append(("\02{0}\02, a \02guardian angel\02, "+
                                "made the unfortunate mistake of guarding a wolf "+
                                "last night, and is now dead.").format(gangel))
                var.LOGGER.logBare(gangel, "KILLEDWHENGUARDINGWOLF")
                dead.append(gangel)
    cli.msg(chan, "\n".join(message))
    for msg in message:
        var.LOGGER.logMessage(msg.replace("\02", ""))
    
    for deadperson in dead:  # kill each player, but don't end the game if one group outnumbers another
        del_player(cli, deadperson, end_game = False)
    if chk_win(cli):  # if after the last person is killed, one side wins, then actually end the game here
        return
    
    if (var.WOLF_STEALS_GUN and victim in dead and 
        victim in var.GUNNERS.keys() and var.GUNNERS[victim] > 0):
        # victim has bullets
        guntaker = random.choice(var.ROLES["wolf"] + var.ROLES["werecrow"] 
                                 + var.ROLES["traitor"])  # random looter
        numbullets = var.GUNNERS[victim]
        var.WOLF_GUNNERS[guntaker] = 1  # transfer bullets a wolf
        mmsg = ("While searching {0}'s belongings, You found " + 
                "a gun loaded with 1 silver bullet! " + 
                "You may only use it during the day. " +
                "If you shoot at a wolf, you will intentionally miss. " +
                "If you shoot a villager, it is likely that they will be injured.")
        mmsg = mmsg.format(victim)
        pm(cli, guntaker, mmsg)
        var.GUNNERS[victim] = 0  # just in case

            
    begin_day(cli)


def chk_nightdone(cli):
    if (len(var.SEEN) >= len(var.ROLES["seer"]) and  # Seers have seen.
        len(var.HVISITED.keys()) >= len(var.ROLES["harlot"]) and  # harlots have visited.
        len(var.GUARDED.keys()) >= len(var.ROLES["guardian angel"]) and  # guardians have guarded
        len(var.KILLS)+len(var.OBSERVED) >= len(var.ROLES["werecrow"]+var.ROLES["wolf"]) and
        var.PHASE == "night"):
        
        # check if wolves are actually agreeing
        if len(set(var.KILLS.values())) > 1:
            return
        
        for x, t in var.TIMERS.items():
            t.cancel()
        
        var.TIMERS = {}
        if var.PHASE == "night":  # Double check
            transition_day(cli)



@cmd("lynch", "vote")
def vote(cli, nick, chann_, rest):
    """Use this to vote for a candidate to be lynched"""
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
    if nick in var.WOUNDED:
        cli.msg(chan, ("{0}: You are wounded and resting, "+
                      "thus you are unable to vote for the day.").format(nick))
        return

    pl = var.list_players()
    pl_l = [x.strip().lower() for x in pl]
    rest = re.split(" +",rest)[0].strip().lower()
    
    if not rest:
        cli.notice(nick, "Not enough parameters.")
        return
    
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



@cmd("retract")
def retract(cli, nick, chann_, rest):
    """Takes back your vote during the day (for whom to lynch)"""
    
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



@cmd("shoot")
def shoot(cli, nick, chann_, rest):
    """Use this to fire off a bullet at someone in the day if you have bullets"""
    
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
    if not (nick in var.GUNNERS.keys() or nick in var.WOLF_GUNNERS.keys()):
        pm(cli, nick, "You don't have a gun.")
        return
    elif ((nick in var.GUNNERS.keys() and not var.GUNNERS[nick]) or
          (nick in var.WOLF_GUNNERS.keys() and not var.WOLF_GUNNERS[nick])):
        pm(cli, nick, "You don't have any more bullets.")
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
    
    wolfshooter = nick in var.ROLES["wolf"]+var.ROLES["werecrow"]+var.ROLES["traitor"]
    
    if wolfshooter and nick in var.WOLF_GUNNERS:
        var.WOLF_GUNNERS[nick] -= 1
    else:
        var.GUNNERS[nick] -= 1
    
    rand = random.random()
    if nick in var.ROLES["village drunk"]:
        chances = var.DRUNK_GUN_CHANCES
    else:
        chances = var.GUN_CHANCES
    
    wolfvictim = victim in var.ROLES["wolf"]+var.ROLES["werecrow"]
    if rand <= chances[0] and not (wolfshooter and wolfvictim):  # didn't miss or suicide
        # and it's not a wolf shooting another wolf
        
        cli.msg(chan, ("\u0002{0}\u0002 shoots \u0002{1}\u0002 with "+
                       "a silver bullet!").format(nick, victim))
        var.LOGGER.logMessage("{0} shoots {1} with a silver bullet!".format(nick, victim))
        victimrole = var.get_reveal_role(victim)
        if victimrole in ("wolf", "werecrow"):
            cli.msg(chan, ("\u0002{0}\u0002 is a {1}, and is dying from "+
                           "the silver bullet.").format(victim, victimrole))
            var.LOGGER.logMessage(("{0} is a {1}, and is dying from the "+
                            "silver bullet.").format(victim, victimrole))
            if not del_player(cli, victim):
                return
        elif random.random() <= var.MANSLAUGHTER_CHANCE:
            cli.msg(chan, ("\u0002{0}\u0002 is a not a wolf "+
                           "but was accidentally fatally injured.").format(victim))
            cli.msg(chan, "The village has sacrificed a \u0002{0}\u0002.".format(victimrole))
            var.LOGGER.logMessage("{0} is not a wolf but was accidentally fatally injured.".format(victim))
            var.LOGGER.logMessage("The village has sacrificed a {0}.".format(victimrole))
            if not del_player(cli, victim):
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
        cli.msg(chan, ("Oh no! \u0002{0}\u0002's gun was poorly maintained and has exploded! "+
                       "The village mourns a gunner-\u0002{1}\u0002.").format(nick, var.get_reveal_role(nick)))
        var.LOGGER.logMessage(("Oh no! {0}'s gun was poorly maintained and has exploded! "+
                       "The village mourns a gunner-{1}.").format(nick, var.get_reveal_role(nick)))
        if not del_player(cli, nick):
            return  # Someone won.



@pmcmd("kill")
def kill(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    role = var.get_role(nick)
    if role == "traitor":
        return  # they do this a lot.
    if role not in ('wolf', 'werecrow'):
        pm(cli, nick, "Only a wolf may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only kill people at night.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    if not victim:
        pm(cli, nick, "Not enough parameters")
        return
    if role == "werecrow":  # Check if flying to observe
        if var.OBSERVED.get(nick):
            pm(cli, nick, ("You have already transformed into a crow; therefore, "+
                           "you are physically unable to kill a villager."))
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
        pm(cli, nick, "Suicide is bad.  Don't do it.")
        return
    if victim in var.ROLES["wolf"]+var.ROLES["werecrow"]+var.ROLES["traitor"]:
        pm(cli, nick, "You may only kill villagers, not other wolves.")
        return
    var.KILLS[nick] = victim
    pm(cli, nick, "You have selected \u0002{0}\u0002 to be killed.".format(victim))
    var.LOGGER.logBare(nick, "SELECT", victim)
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
    if role != 'guardian angel':
        pm(cli, nick, "Only a guardian angel may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only protect people at night.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    if not victim:
        pm(cli, nick, "Not enough parameters")
        return
    if var.GUARDED.get(nick):
        pm(cli, nick, ("You are already protecting "+
                      "\u0002{0}\u0002.").format(var.GUARDED[nick]))
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
        pm(cli, nick, "You may not guard yourself.")
        return
    var.GUARDED[nick] = victim
    pm(cli, nick, "You are protecting \u0002{0}\u0002 tonight. Farewell!".format(var.GUARDED[nick]))
    pm(cli, var.GUARDED[nick], "You can sleep well tonight, for a guardian angel is protecting you.")
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
    if not var.is_role(nick, "werecrow"):
        pm(cli, nick, "Only a werecrow may use this command.")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only transform into a crow at night.")
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
        pm(cli, nick, "Instead of doing that, you should probably go kill someone.")
        return
    if nick in var.OBSERVED.keys():
        pm(cli, nick, "You are already flying to \02{0}\02's house.".format(var.OBSERVED[nick]))
        return
    if var.get_role(victim) in ("werecrow", "traitor", "wolf"):
        pm(cli, nick, "Flying to another wolf's house is a waste of time.")
        return
    var.OBSERVED[nick] = victim
    if nick in var.KILLS.keys():
        del var.KILLS[nick]
    pm(cli, nick, ("You transform into a large crow and start your flight "+
                   "to \u0002{0}'s\u0002 house. You will return after "+
                  "collecting your observations when day begins.").format(victim))
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

    var.INVESTIGATED.append(nick)
    pm(cli, nick, ("The results of your investigation have returned. \u0002{0}\u0002"+
                   " is a... \u0002{1}\u0002!").format(victim, var.get_role(victim)))
    var.LOGGER.logBare(victim, "INVESTIGATED", nick)
    if random.random() < var.DETECTIVE_REVEALED_CHANCE:  # a 2/5 chance (should be changeable in settings)
        # The detective's identity is compromised!
        for badguy in var.ROLES["wolf"] + var.ROLES["werecrow"] + var.ROLES["traitor"]:
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
        var.HVISITED[nick] = victim
        pm(cli, nick, ("You are spending the night with \u0002{0}\u0002. "+
                      "Have a good time!").format(var.HVISITED[nick]))
        pm(cli, var.HVISITED[nick], ("You are spending the night with \u0002{0}"+
                                     "\u0002. Have a good time!").format(nick))
        var.LOGGER.logBare(var.HVISITED[nick], "VISITED", nick)
    chk_nightdone(cli)


def is_fake_nick(who):
    return not(re.search("^[a-zA-Z\\\_\]\[`]([a-zA-Z0-9\\\_\]\[`]+)?", who)) or who.lower().endswith("serv")



@pmcmd("see")
def see(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players() or nick in var.DISCONNECTED.keys():
        cli.notice(nick, "You're not currently playing.")
        return
    if not var.is_role(nick, "seer"):
        pm(cli, nick, "Only a seer may use this command")
        return
    if var.PHASE != "night":
        pm(cli, nick, "You may only have visions at night.")
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
    if victim in var.CURSED or var.get_role(victim) == "werecrow":
        role = "wolf"
    elif var.get_role(victim) == "traitor":
        role = "villager"
    else:
        role = var.get_role(victim)
    pm(cli, nick, ("You have a vision; in this vision, "+
                    "you see that \u0002{0}\u0002 is a "+
                    "\u0002{1}\u0002!").format(victim, role))
    var.SEEN.append(nick)
    var.LOGGER.logBare(victim, "SEEN", nick)
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

    badguys = var.ROLES["wolf"] + var.ROLES["traitor"] + var.ROLES["werecrow"]
    if len(badguys) > 1:
        if nick in badguys:
            badguys.remove(nick)  #  remove self from list
        
            if rest.startswith("\01ACTION"):
                rest = rest[7:-1]
                mass_privmsg(cli, [guy for guy in badguys 
                    if (guy in var.PLAYERS and
                        var.PLAYERS[guy]["cloak"] not in var.SIMPLE_NOTIFY)], "\02{0}\02{1}".format(nick, rest))
                mass_privmsg(cli, [guy for guy in badguys 
                    if (guy in var.PLAYERS and
                        var.PLAYERS[guy]["cloak"] in var.SIMPLE_NOTIFY)], nick+rest, True)
            else:
                mass_privmsg(cli, [guy for guy in badguys 
                    if (guy in var.PLAYERS and
                        var.PLAYERS[guy]["cloak"] not in var.SIMPLE_NOTIFY)], "\02{0}\02 says: {1}".format(nick, rest))
                mass_privmsg(cli, [guy for guy in badguys 
                    if (guy in var.PLAYERS and
                        var.PLAYERS[guy]["cloak"] in var.SIMPLE_NOTIFY)], "\02{0}\02 says: {1}".format(nick, rest), True)



def transition_night(cli):
    if var.PHASE == "night":
        return
    var.PHASE = "night"

    for x, tmr in var.TIMERS.items():  # cancel daytime timer
        tmr.cancel()
    var.TIMERS = {}

    # Reset nighttime variables
    var.KILLS = {}
    var.GUARDED = {}  # key = by whom, value = the person that is visited
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = []  # list of seers that have had visions
    var.OBSERVED = {}  # those whom werecrows have observed
    var.HVISITED = {}
    var.NIGHT_START_TIME = datetime.now()

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
        var.TIMERS["night"] = t
        var.TIMERS["night"].daemon = True
        t.start()
        
    if var.NIGHT_TIME_WARN > 0:
        t2 = threading.Timer(var.NIGHT_TIME_WARN, night_warn, [cli, var.NIGHT_ID])
        var.TIMERS["night_warn"] = t2
        var.TIMERS["night_warn"].daemon = True
        t2.start()

    # send PMs
    ps = var.list_players()
    wolves = var.ROLES["wolf"]+var.ROLES["traitor"]+var.ROLES["werecrow"]
    for wolf in wolves:
        normal_notify = wolf in var.PLAYERS and var.PLAYERS[wolf]["cloak"] not in var.SIMPLE_NOTIFY
    
        if normal_notify:
            if wolf in var.ROLES["wolf"]:
                pm(cli, wolf, ('You are a \u0002wolf\u0002. It is your job to kill all the '+
                               'villagers. Use "kill <nick>" to kill a villager.'))
            elif wolf in var.ROLES["traitor"]:
                pm(cli, wolf, ('You are a \u0002traitor\u0002. You are exactly like a '+
                               'villager and not even a seer can see your true identity. '+
                               'Only detectives can. '))
            else:
                pm(cli, wolf, ('You are a \u0002werecrow\u0002.  You are able to fly at night. '+
                               'Use "kill <nick>" to kill a a villager.  Alternatively, you can '+
                               'use "observe <nick>" to check if someone is in bed or not. '+
                               'Observing will prevent you from participating in a killing.'))
            if len(wolves) > 1:
                pm(cli, wolf, 'Also, if you PM me, your message will be relayed to other wolves.')
        else:
            pm(cli, wolf, "You are a \02{0}\02.".format(var.get_role(wolf)))  # !simple
            
        
        pl = ps[:]
        pl.sort(key=lambda x: x.lower())
        pl.remove(wolf)  # remove self from list
        for i, player in enumerate(pl):
            if player in var.ROLES["wolf"]:
                pl[i] = player + " (wolf)"
            elif player in var.ROLES["traitor"]:
                pl[i] = player + " (traitor)"
            elif player in var.ROLES["werecrow"]:
                pl[i] = player + " (werecrow)"
        pm(cli, wolf, "\u0002Players:\u0002 "+", ".join(pl))

    for seer in var.ROLES["seer"]:
        pl = ps[:]
        pl.sort(key=lambda x: x.lower())
        pl.remove(seer)  # remove self from list
        
        if seer in var.PLAYERS and var.PLAYERS[seer]["cloak"] not in var.SIMPLE_NOTIFY:
            pm(cli, seer, ('You are a \u0002seer\u0002. '+
                          'It is your job to detect the wolves, you '+
                          'may have a vision once per night. '+
                          'Use "see <nick>" to see the role of a player.'))
        else:
            pm(cli, seer, "You are a \02seer\02.")  # !simple
        pm(cli, seer, "Players: "+", ".join(pl))

    for harlot in var.ROLES["harlot"]:
        pl = ps[:]
        pl.sort(key=lambda x: x.lower())
        pl.remove(harlot)
        if harlot in var.PLAYERS and var.PLAYERS[harlot]["cloak"] not in var.SIMPLE_NOTIFY:
            cli.msg(harlot, ('You are a \u0002harlot\u0002. '+
                             'You may spend the night with one person per round. '+
                             'If you visit a victim of a wolf, or visit a wolf, '+
                             'you will die. Use visit to visit a player.'))
        else:
            cli.notice(harlot, "You are a \02harlot\02.")  # !simple
        pm(cli, harlot, "Players: "+", ".join(pl))

    for g_angel in var.ROLES["guardian angel"]:
        pl = ps[:]
        pl.sort(key=lambda x: x.lower())
        pl.remove(g_angel)
        if g_angel in var.PLAYERS and var.PLAYERS[g_angel]["cloak"] not in var.SIMPLE_NOTIFY:
            cli.msg(g_angel, ('You are a \u0002guardian angel\u0002. '+
                              'It is your job to protect the villagers. If you guard a'+
                              ' wolf, there is a 50/50 chance of you dying, if you guard '+
                              'a victim, they will live. Use guard to guard a player.'))
        else:
            cli.notice(g_angel, "You are a \02guardian angel\02.")  # !simple
        pm(cli, g_angel, "Players: " + ", ".join(pl))
    
    for dttv in var.ROLES["detective"]:
        pl = ps[:]
        pl.sort(key=lambda x: x.lower())
        pl.remove(dttv)
        if dttv in var.PLAYERS and var.PLAYERS[dttv]["cloak"] not in var.SIMPLE_NOTIFY:
            cli.msg(dttv, ("You are a \u0002detective\u0002.\n"+
                          "It is your job to determine all the wolves and traitors. "+
                          "Your job is during the day, and you can see the true "+
                          "identity of all users, even traitors.\n"+
                          "But, each time you use your ability, you risk a 2/5 "+
                          "chance of having your identity revealed to the wolves. So be "+
                          "careful. Use \"{0}id\" to identify any player during the day.").format(botconfig.CMD_CHAR))
        else:
            cli.notice(dttv, "You are a \02detective\02.")  # !simple
        pm(cli, dttv, "Players: " + ", ".join(pl))
    for drunk in var.ROLES["village drunk"]:
        if drunk in var.PLAYERS and var.PLAYERS[drunk]["cloak"] not in var.SIMPLE_NOTIFY:
            cli.msg(drunk, "You have been drinking too much! You are the \u0002village drunk\u0002.")
        else:
            cli.notice(drunk, "You are the \u0002village drunk\u0002.")

    for g in tuple(var.GUNNERS.keys()):
        if g not in ps:
            continue
        elif not var.GUNNERS[g]:
            continue
        norm_notify = g in var.PLAYERS and var.PLAYERS[g]["cloak"] not in var.SIMPLE_NOTIFY
        if norm_notify:
            gun_msg =  ("You hold a gun that shoots special silver bullets. You may only use it "+
                        "during the day. Wolves and the crow will die instantly when shot, but "+
                        "a villager or traitor will likely survive. You get {0}.")
        else:
            gun_msg = ("You have a \02gun\02 with {0}.")
        if var.GUNNERS[g] == 1:
            gun_msg = gun_msg.format("1 bullet")
        elif var.GUNNERS[g] > 1:
            gun_msg = gun_msg.format(str(var.GUNNERS[g]) + " bullets")
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
    if not var.ROLES["wolf"] + var.ROLES["werecrow"]:  # Probably something interesting going on.
        chk_nightdone(cli)
        chk_traitor(cli)



def cgamemode(cli, *args):
    chan = botconfig.CHANNEL
    if var.ORIGINAL_SETTINGS:  # needs reset
        reset_settings()
    
    for arg in args:
        modeargs = arg.split("=", 1)
        
        if len(modeargs) < 2:  # no equal sign in the middle of the arg
            cli.msg(botconfig.CHANNEL, "Invalid syntax.")
            return False
        
        modeargs[0] = modeargs[0].strip()
        if modeargs[0] in var.GAME_MODES.keys():
            md = modeargs.pop(0)
            modeargs[0] = modeargs[0].strip()
            try:
                gm = var.GAME_MODES[md](modeargs[0])
                for attr in dir(gm):
                    val = getattr(gm, attr)
                    if (hasattr(var, attr) and not callable(val)
                                            and not attr.startswith("_")):
                        var.ORIGINAL_SETTINGS[attr] = getattr(var, attr)
                        setattr(var, attr, val)
                return True
            except var.InvalidModeException as e:
                cli.msg(botconfig.CHANNEL, "Invalid mode: "+str(e))
                return False
        else:
            cli.msg(chan, "Mode \u0002{0}\u0002 not found.".format(modeargs[0]))


@cmd("start")
def start(cli, nick, chann_, rest):
    """Starts a game of Werewolf"""
    
    chan = botconfig.CHANNEL
    
    villagers = var.list_players()
    pl = villagers[:]

    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in villagers and nick != chan:
        cli.notice(nick, "You're currently not playing.")
        return
        
    now = datetime.now()
    var.GAME_START_TIME = now  # Only used for the idler checker
    dur = int((var.CAN_START_TIME - now).total_seconds())
    if dur > 0:
        cli.msg(chan, "Please wait at least {0} more seconds.".format(dur))
        return

    if len(villagers) < var.MIN_PLAYERS:
        cli.msg(chan, "{0}: \u0002{1}\u0002 or more players are required to play.".format(nick, var.MIN_PLAYERS))
        return

    for pcount in range(len(villagers), var.MIN_PLAYERS - 1, -1):
        addroles = var.ROLES_GUIDE.get(pcount)
        if addroles:
            break
    else:
        cli.msg(chan, "{0}: No game settings are defined for \u0002{1}\u0002 player games.".format(nick, len(villagers)))
        return

    if var.ORIGINAL_SETTINGS:  # Custom settings
        while True:
            wvs = (addroles[var.INDEX_OF_ROLE["wolf"]] +
                  addroles[var.INDEX_OF_ROLE["traitor"]])
            if len(villagers) < (sum(addroles) - addroles[var.INDEX_OF_ROLE["gunner"]] -
                    addroles[var.INDEX_OF_ROLE["cursed villager"]]):
                cli.msg(chan, "There are too few players in the "+
                              "game to use the custom roles.")
            elif not wvs:
                cli.msg(chan, "There has to be at least one wolf!")
            elif wvs > (len(villagers) / 2):
                cli.msg(chan, "Too many wolves.")
            else:
                break
            reset_settings()
            cli.msg(chan, "The default settings have been restored.  Please !start again.")
            var.PHASE = "join"
            return

            
    if var.ADMIN_TO_PING:
        if "join" in COMMANDS.keys():
            COMMANDS["join"] = [lambda *spam: cli.msg(chan, "This command has been disabled by an admin.")]
        if "start" in COMMANDS.keys():
            COMMANDS["start"] = [lambda *spam: cli.msg(chan, "This command has been disabled by an admin.")]

    var.ROLES = {}
    var.CURSED = []
    var.GUNNERS = {}
    var.WOLF_GUNNERS = {}
    var.SEEN = []
    var.OBSERVED = {}
    var.KILLS = {}
    var.GUARDED = {}
    var.HVISITED = {}

    villager_roles = ("gunner", "cursed villager")
    for i, count in enumerate(addroles):
        role = var.ROLE_INDICES[i]
        if role in villager_roles:
            var.ROLES[role] = [None] * count
            continue # We deal with those later, see below
        selected = random.sample(villagers, count)
        var.ROLES[role] = selected
        for x in selected:
            villagers.remove(x)

    # Now for the villager roles
    # Select cursed (just a villager)
    if var.ROLES["cursed villager"]:
        possiblecursed = pl[:]
        for cannotbe in (var.ROLES["wolf"] + var.ROLES["werecrow"] +
                         var.ROLES["seer"] + var.ROLES["village drunk"]):
                                              # traitor can be cursed
            possiblecursed.remove(cannotbe)
        
        var.CURSED = random.sample(possiblecursed, len(var.ROLES["cursed villager"]))
    del var.ROLES["cursed villager"]
    
    # Select gunner (also a villager)
    if var.ROLES["gunner"]:
                   
        possible = pl[:]
        for cannotbe in (var.ROLES["wolf"] + var.ROLES["werecrow"] +
                         var.ROLES["traitor"]):
            possible.remove(cannotbe)
            
        for csd in var.CURSED:  # cursed cannot be gunner
            if csd in possible:
                possible.remove(csd)
                
        for gnr in random.sample(possible, len(var.ROLES["gunner"])):
            if gnr in var.ROLES["village drunk"]:
                var.GUNNERS[gnr] = (var.DRUNK_SHOTS_MULTIPLIER * 
                                    math.ceil(var.SHOTS_MULTIPLIER * len(pl)))
            else:
                var.GUNNERS[gnr] = math.ceil(var.SHOTS_MULTIPLIER * len(pl))
    del var.ROLES["gunner"]

    var.SPECIAL_ROLES["goat herder"] = []
    if var.GOAT_HERDER:
       var.SPECIAL_ROLES["goat herder"] = [ nick ]

    var.ROLES["villager"] = villagers

    cli.msg(chan, ("{0}: Welcome to Werewolf, the popular detective/social party "+
                   "game (a theme of Mafia).").format(", ".join(pl)))
    cli.mode(chan, "+m")

    var.ORIGINAL_ROLES = copy.deepcopy(var.ROLES)  # Make a copy
    
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
    for rol in var.ROLES:
        r = []
        for rw in var.plural(rol).split(" "):
            rwu = rw[0].upper()
            if len(rw) > 1:
                rwu += rw[1:]
            r.append(rwu)
        r = " ".join(r)
        var.LOGGER.log("{0}: {1}".format(r, ", ".join(var.ROLES[rol])))
        
        for plr in var.ROLES[rol]:
            var.LOGGER.logBare(plr, "ROLE", rol)
    
    if var.CURSED:
        var.LOGGER.log("Cursed Villagers: "+", ".join(var.CURSED))
        
        for plr in var.CURSED:
            var.LOGGER.logBare(plr+" ROLE cursed villager")
    if var.GUNNERS:
        var.LOGGER.log("Villagers With Bullets: "+", ".join([x+"("+str(y)+")" for x,y in var.GUNNERS.items()]))
        for plr in var.GUNNERS:
            var.LOGGER.logBare(plr, "ROLE gunner")
    
    var.LOGGER.log("***")        
        
    var.PLAYERS = {plr:dict(var.USERS[plr]) for plr in pl if plr in var.USERS}    

    if not var.START_WITH_DAY:
        var.FIRST_NIGHT = True
        transition_night(cli)
    else:
        transition_day(cli)

    for cloak in list(var.STASISED.keys()):
        if var.STASISED[cloak] != 0:
            var.STASISED[cloak] -= 1
        else:
            del var.STASISED[cloak]

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


@pmcmd("fstasis", admin_only=True)
def fstasis(cli, nick, *rest):
    data = rest[0].split()
    if data and len(data) < 3:
        lusers = {k.lower(): v for k, v in var.USERS.items()}
        user = data[0].lower()
        if user in lusers:
            cloak = lusers[user]['cloak']
        else:
            cloak = None
        if cloak is None:
            cli.msg(nick, "Sorry, that user cannot be found.")
            return
        if len(data) == 2:
            amt = int(data[1])
            if amt < 0 and cloak in var.STASISED:
                var.STASISED[cloak] += amt
                if var.STASISED[cloak] == 0:
                    cli.msg(nick, "{0} ({1}) is no longer in stasis.".format(data[0], cloak))
                else:
                    cli.msg(nick, "{0} ({1}) is now in stasis for {2} games.".format(data[0], cloak, var.STASISED[cloak]))
            elif amt <= 0:
                if cloak in var.STASISED:
                    var.STASISED.pop(cloak)
                    cli.msg(nick, "{0} ({1}) is no longer in stasis.".format(data[0], cloak))
                else:
                    cli.msg(nick, "{0} ({1}) is not in stasis.".format(data[0], cloak))
            else:
                var.STASISED[cloak] = amt
                cli.msg(nick, "{0} ({1}) is now in stasis for {2} games.".format(data[0], cloak, amt))
        elif len(data) == 1:
            if cloak in var.STASISED:
                cli.msg(nick, "{0} ({1}) is in stasis for {2} games.".format(data[0], cloak, var.STASISED[cloak]))
            else:
                cli.msg(nick, "{0} ({1}) is not in stasis.".format(data[0], cloak))
    elif not data:
        if var.STASISED:
            cli.msg(nick, "Currently stasised: {0}".format(
                ", ".join("{0}: {1}".format(cloak, number) for cloak, number in var.STASISED.items())))
        else:
            cli.msg(nick, "Nobody is currently stasised.")



@cmd("wait")
def wait(cli, nick, chann_, rest):
    """Increase the wait time (before !start can be used)"""
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
def fwait(cli, nick, chann_, rest):

    pl = var.list_players()
    
    chan = botconfig.CHANNEL
    
    
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return

    rest = re.split(" +", rest.strip(), 1)[0]
    if rest and (rest.isdigit() or (rest[0] == '-' and rest[1:].isdigit())):
        if len(rest) < 4:
            extra = int(rest)
        else:
            cli.msg(chan, "{0}: We don't have all day!".format(nick))
            return
    else:
        extra = var.EXTRA_WAIT
        
    now = datetime.now()
    if now > var.CAN_START_TIME:
        var.CAN_START_TIME = now + timedelta(seconds=extra)
    else:
        var.CAN_START_TIME += timedelta(seconds=extra)
    var.WAITED += 1
    cli.msg(chan, ("\u0002{0}\u0002 forcibly increased the wait time by "+
                  "{1} seconds.").format(nick, extra))


@cmd("fstop",admin_only=True)
def reset_game(cli, nick, chan, rest):
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    cli.msg(botconfig.CHANNEL, "\u0002{0}\u0002 has forced the game to stop.".format(nick))
    var.LOGGER.logMessage("{0} has forced the game to stop.".format(nick))
    if var.PHASE != "join":
        stop_game(cli)
    else:
        reset_modes(cli)
        reset(cli)


@pmcmd("rules")
def pm_rules(cli, nick, rest):
    cli.notice(nick, var.RULES)

@cmd("rules")
def show_rules(cli, nick, chan, rest):
    """Displays the rules"""
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
    """Gets help"""
    get_help(cli, nick, rest)


@hook("invite", raw_nick = False, admin_only = True)
def on_invite(cli, nick, something, chan):
    if chan == botconfig.CHANNEL:
        cli.join(chan)

      
def is_admin(cloak):
    return bool([ptn for ptn in botconfig.OWNERS+botconfig.ADMINS if fnmatch.fnmatch(cloak.lower(), ptn.lower())])


@cmd("admins")
def show_admins(cli, nick, chan, rest):
    """Pings the admins that are available."""
    admins = []
    pl = var.list_players()
    
    if (var.LAST_ADMINS and
        var.LAST_ADMINS + timedelta(seconds=var.ADMINS_RATE_LIMIT) > datetime.now()):
        cli.notice(nick, ("This command is rate-limited. " +
                          "Please wait a while before using it again."))
        return
        
    if not (var.PHASE in ("day", "night") and nick not in pl):
        var.LAST_ADMINS = datetime.now()
    
    if var.ADMIN_PINGING:
        return
    var.ADMIN_PINGING = True

    @hook("whoreply", hookid = 4)
    def on_whoreply(cli, server, dunno, chan, dunno1,
                    cloak, dunno3, user, status, dunno4):
        if not var.ADMIN_PINGING:
            return
        if (is_admin(cloak) and 'G' not in status and
            user != botconfig.NICK):
            admins.append(user)

    @hook("endofwho", hookid = 4)
    def show(*args):
        if not var.ADMIN_PINGING:
            return
        admins.sort(key=lambda x: x.lower())
        
        if var.PHASE in ("day", "night") and nick not in pl:
            cli.notice(nick, "Available admins: "+" ".join(admins))
        else:
            cli.msg(chan, "Available admins: "+" ".join(admins))

        decorators.unhook(HOOKS, 4)
        var.ADMIN_PINGING = False

    cli.who(chan)



@cmd("coin")
def coin(cli, nick, chan, rest):
    """It's a bad idea to base any decisions on this command."""
    
    if var.PHASE in ("day", "night") and nick not in var.list_players():
        cli.notice(nick, "You may not use this command right now.")
        return
    
    cli.msg(chan, "\2{0}\2 tosses a coin into the air...".format(nick))
    var.LOGGER.logMessage("{0} tosses a coin into the air...".format(nick))
    coin = random.choice(["heads", "tails"])
    specialty = random.randrange(0,20)
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

@cmd("roles")
def listroles(cli, nick, chan, rest):
    """Display which roles are enabled and when"""

    old = var.ROLES_GUIDE.get(None)

    txt = ""

    pl = len(var.list_players()) + len(var.DEAD)
    if pl > 0:
        txt += '{0}: There are \u0002{1}\u0002 playing. '.format(nick, pl)

    for i,v in sorted({i:var.ROLES_GUIDE[i] for i in var.ROLES_GUIDE if i is not None}.items()):
        if (i <= pl):
            txt += BOLD
        txt += "[" + str(i) + "] "
        if (i <= pl):
            txt += BOLD
        for index, amt in enumerate(v):
            if amt - old[index] != 0:
                if amt > 1:
                    txt = txt + var.ROLE_INDICES[index] + "({0}), ".format(amt)
                else:
                    txt = txt + var.ROLE_INDICES[index] + ", "
        txt = txt[:-2] + " "
        old = v
    cli.msg(botconfig.CHANNEL, txt)

@cmd("myrole")
def myrole(cli, nick, chan, rest):
    """Reminds you of which role you have."""
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    
    ps = var.list_players()
    if nick not in ps:
        cli.notice(nick, "You're currently not playing.")
        return
    
    pm(cli, nick, "You are a \02{0}\02.".format(var.get_role(nick)))
    
    # Check for gun/bullets
    if nick in var.GUNNERS and var.GUNNERS[nick]:
        if var.GUNNERS[nick] == 1:
            pm(cli, nick, "You have a \02gun\02 with {0} {1}.".format(var.GUNNERS[nick], "bullet"))
        else:
            pm(cli, nick, "You have a \02gun\02 with {0} {1}.".format(var.GUNNERS[nick], "bullets"))
    elif nick in var.WOLF_GUNNERS and var.WOLF_GUNNERS[nick]:
        if var.WOLF_GUNNERS[nick] == 1:
            pm(cli, nick, "You have a \02gun\02 with {0} {1}.".format(var.WOLF_GUNNERS[nick], "bullet"))
        else:
            pm(cli, nick, "You have a \02gun\02 with {0} {1}.".format(var.WOLF_GUNNERS[nick], "bullets"))

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
    if not rest.strip():
        cli.notice(parse_nick(nick)[0], "Incorrect syntax for this command.")
        return
    aftergame(cli, nick, rest)
        
    
    
@pmcmd("faftergame", admin_only=True, raw_nick=True)
def faftergame(cli, nick, rest):
    _faftergame(cli, nick, botconfig.CHANNEL, rest)

@pmcmd("fghost", owner_only=True)
@cmd("fghost", owner_only=True)
def fghost(cli, nick, *rest):
    cli.msg(botconfig.CHANNEL, nick + " is the ghost!")
    cli.mode(botconfig.CHANNEL, "+v", nick)

@pmcmd("funghost", owner_only=True)
@cmd("funghost", owner_only=True)
def funghost(cli, nick, *rest):
    cli.mode(botconfig.CHANNEL, "-v", nick)
    
@pmcmd("flastgame", admin_only=True, raw_nick=True)
def flastgame(cli, nick, rest):
    """This command may be used in the channel or in a PM, and it disables starting or joining a game. !flastgame <optional-command-after-game-ends>"""
    rawnick = nick
    nick, _, __, cloak = parse_nick(rawnick)
    
    chan = botconfig.CHANNEL
    if var.PHASE != "join":
        if "join" in COMMANDS.keys():
            del COMMANDS["join"]
            cmd("join")(lambda *spam: cli.msg(chan, "This command has been disabled by an admin."))
            # manually recreate the command by calling the decorator function
        if "start" in COMMANDS.keys():
            del COMMANDS["start"]
            cmd("join")(lambda *spam: cli.msg(chan, "This command has been disabled by an admin."))
        
    cli.msg(chan, "Starting a new game has now been disabled by \02{0}\02.".format(nick))
    var.ADMIN_TO_PING = nick
    
    if rest.strip():
        aftergame(cli, rawnick, rest)
    
@cmd("flastgame", admin_only=True, raw_nick=True)
def _flastgame(cli, nick, chan, rest):
    flastgame(cli, nick, rest)
   
   
@cmd("gamestats", "gstats")
def game_stats(cli, nick, chan, rest):
    """Gets the game stats for a given game size or lists game totals for all game sizes if no game size is given."""
    if (chan != nick and var.LAST_GSTATS and
        var.LAST_GSTATS + timedelta(seconds=var.GSTATS_RATE_LIMIT) > datetime.now()):
        cli.notice(nick, ("This command is rate-limited. " +
                          "Please wait a while before using it again."))
        return

    if chan != nick:
        var.LAST_GSTATS = datetime.now()

    if var.PHASE not in ("none", "join"):
        cli.notice(nick, "Wait until the game is over to view stats.")
        return
    
    # List all games sizes and totals if no size is given.
    if rest == "":
        if chan == nick:
            pm(cli, nick, var.get_game_totals())
        else:
            cli.msg(chan, var.get_game_totals())
        return
    
    # Check for invalid input
    rest = rest.strip()
    if not rest.isdigit() or int(rest) > var.MAX_PLAYERS or int(rest) < var.MIN_PLAYERS:
        cli.notice(nick, "Please enter an integer between {0} and {1}.".format(var.MIN_PLAYERS, var.MAX_PLAYERS))
        return
    
    # Attempt to find game stats for the given game size.
    if chan == nick:
        pm(cli, nick, var.get_game_stats(int(rest)))
    else:
        cli.msg(chan, var.get_game_stats(int(rest)))

@pmcmd("gamestats", "gstats")
def game_stats_pm(cli, nick, rest):
    game_stats(cli, nick, nick, rest)
    
@cmd("playerstats", "pstats", "player", "p")
def player_stats(cli, nick, chan, rest):
    """Gets the stats for the given player and role or a list of role totals if no role is given."""
    if (chan != nick and var.LAST_PSTATS and
        var.LAST_PSTATS + timedelta(seconds=var.PSTATS_RATE_LIMIT) > datetime.now()):
        cli.notice(nick, ("This command is rate-limited. " +
                          "Please wait a while before using it again."))
        return

    if chan != nick:
        var.LAST_PSTATS = datetime.now()

    if var.PHASE not in ("none", "join"):
        cli.notice(nick, "Wait until the game is over to view stats.")
        return
    
    # Check if we have enough parameters.
    params = rest.split()
    if len(params) < 1:
        user = nick
    else:
        user = params[0]

    # Find the player's account if possible.
    if user in var.USERS:
        acc = var.USERS[user]["account"]
        if acc == "*":
            cli.notice(nick, "{0} is not identified with NickServ.".format(user))
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
        role = " ".join(params[1:]).lower()    
        # Attempt to find the player's stats.
        if chan == nick:
            pm(cli, nick, var.get_player_stats(acc, role))
        else:
            cli.msg(chan, var.get_player_stats(acc, role))
    
@pmcmd("playerstats", "pstats", "player", "p")
def player_stats_pm(cli, nick, rest):
    player_stats(cli, nick, nick, rest)
    
@cmd("pull", admin_only=True)
def git_pull(cli, nick, chan, rest):
    try:
        output = subprocess.check_output(('git', 'pull'))
    except Exception as e:
        cli.msg(chan, '{0}:{1}'.format(type(e), e))
        raise

    if output:
        for line in output.splitlines():
            cli.msg(chan, line.decode('utf-8'))

@pmcmd("pull", admin_only=True)
def git_pull_pm(cli, nick, rest):
    git_pull(cli, nick, nick, rest)

@pmcmd("fsend", admin_only=True)
def fsend(cli, nick, rest):
    print('fsend ({0}): {1}'.format(nick, rest))
    cli.send(rest)
    
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

            

    @cmd("revealroles", admin_only=True)
    def revroles(cli, nick, chan, rest):
        if var.PHASE != "none":
            cli.msg(chan, str(var.ROLES))
        if var.PHASE in ('night','day'):
            cli.msg(chan, "Cursed: "+str(var.CURSED))
            cli.msg(chan, "Gunners: "+str(list(var.GUNNERS.keys())))
        
        
    @cmd("fgame", admin_only=True)
    def game(cli, nick, chan, rest):
        pl = var.list_players()
        if var.PHASE == "none":
            cli.notice(nick, "No game is currently running.")
            return
        if var.PHASE != "join":
            cli.notice(nick, "Werewolf is already in play.")
            return
        if nick not in pl:
            cli.notice(nick, "You're currently not playing.")
            return
        rest = rest.strip().lower()
        if rest:
            if cgamemode(cli, *re.split(" +",rest)):
                cli.msg(chan, ("\u0002{0}\u0002 has changed the "+
                                "game settings successfully.").format(nick))
    
    def fgame_help(args = ""):
        args = args.strip()
        if not args:
            return "Available game mode setters: "+ ", ".join(var.GAME_MODES.keys())
        elif args in var.GAME_MODES.keys():
            return var.GAME_MODES[args].__doc__
        else:
            return "Game mode setter {0} not found.".format(args)

    game.__doc__ = fgame_help


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
        if rol not in var.ROLES.keys():
            pl = var.list_players()
            if var.PHASE not in ("night", "day"):
                cli.msg(chan, "This is only allowed in game.")
                return
            if rol.startswith("gunner"):
                rolargs = re.split(" +",rol, 1)
                if len(rolargs) == 2 and rolargs[1].isdigit():
                    if len(rolargs[1]) < 7:
                        var.GUNNERS[who] = int(rolargs[1])
                        var.WOLF_GUNNERS[who] = int(rolargs[1])
                    else:
                        var.GUNNERS[who] = 999
                        var.WOLF_GUNNERS[who] = 999
                else:
                    var.GUNNERS[who] = math.ceil(var.SHOTS_MULTIPLIER * len(pl))
                if who not in pl:
                    var.ROLES["villager"].append(who)
            elif rol == "cursed villager":
                if who not in var.CURSED:
                    var.CURSED.append(who)
                if who not in pl:
                    var.ROLES["villager"].append(who)
            else:
                cli.msg(chan, "Not a valid role.")
                return
            cli.msg(chan, "Operation successful.")
            return
        if who in var.list_players():
            var.del_player(who)
        var.ROLES[rol].append(who)
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
