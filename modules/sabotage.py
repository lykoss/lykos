from tools import decorators
import settings.sabotage as var
import time
from datetime import datetime, timedelta
import botconfig

COMMANDS = {}
PM_COMMANDS = {}
HOOKS = {}

cmd = decorators.generate(COMMANDS)
pmcmd = decorators.generate(PM_COMMANDS)
hook = decorators.generate(HOOKS, raw_nick=True, permissions=False)

def connect_callback(cli):
    var.PHASE = "none"
    var.PLAYERS = []
    
    var.LAST_STATS = None


@cmd("join")
def join(cli, nick, chan, rest):
    """Either starts a new game of Werewolf or joins an existing game that has not started yet."""
    
    if var.PHASE == "none":
    
        cli.mode(chan, "+v", nick, nick+"!*@*")
        var.PLAYERS.append(nick)
        var.PHASE = "join"
        var.WAITED = 0
        var.GAME_ID = time.time()
        var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.MINIMUM_WAIT)
        cli.msg(chan, ('\u0002{0}\u0002 has started a game of Sabotage. '+
                      'Type "{1}join" to join. Type "{1}start" to start the game. '+
                      'Type "{1}wait" to increase join wait time.').format(nick, botconfig.CMD_CHAR))
    elif nick in var.PLAYERS:
        cli.notice(nick, "You're already playing!")
    elif len(pl) >= var.MAX_PLAYERS:
        cli.notice(nick, "Too many players!  Try again next time.")
    elif var.PHASE != "join":
        cli.notice(nick, "Sorry but the game is already running.  Try again next time.")
    else:
    
        cli.mode(chan, "+v", nick, nick+"!*@*")
        var.PLAYERS.append(nick)
        cli.msg(chan, '\u0002{0}\u0002 has joined the game.'.format(nick))
        
        var.LAST_STATS = None # reset
