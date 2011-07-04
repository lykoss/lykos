from oyoyo.client import IRCClient
from oyoyo.cmdhandler import DefaultCommandHandler
from oyoyo import helpers
from oyoyo.parse import parse_nick
import logging
import botconfig

def connect_callback(cli):
    cli.identify(botconfig.PASS)
    cli.join(botconfig.CHANNEL)
    cli.msg("ChanServ", "op "+botconfig.CHANNEL)
    cli.msg(botconfig.CHANNEL, "\u0002Wolfbot2 is here.\u0002")

G_PM_COMMAND = []
G_COMMAND = []
COMMANDS = {}
PM_COMMANDS = {}

HOOKS = {}

def cmd(s, pm = False):
    def dec(f):
        if s is None and pm:
            G_PM_COMMAND = f
        elif s is None and not pm:
            G_COMMAND = f
        elif pm:
            PM_COMMANDS[s] = f
        else:
            COMMANDS[s] = f
        return f
    return dec

def hook(s):
    def dec(f):
        HOOKS[s] = f
        return f
    return dec

class WolfBotHandler(DefaultCommandHandler):
    def __init__(self, client):
        super().__init__(client)

    def privmsg(self, rawnick, chan, msg):         
        if chan != botconfig.NICK:  #not a PM
            for x in COMMANDS.keys():
                if msg.startswith(x):
                    msg = msg.replace(x, "", 1)
                    COMMANDS[x](self.client, rawnick, chan, msg.lstrip())
        else:
            for x in PM_COMMANDS.keys():
                if msg.startswith(x):
                    msg = msg.replace(x, "", 1)
                    PM_COMMANDS[x](self.client, rawnick, msg.lstrip())
        
    def nick(self, fro, to):
        print(fro, to)

def main():
    logging.basicConfig(level=logging.DEBUG)
    cli = IRCClient(WolfBotHandler, host="irc.freenode.net", port=6667, nick="wolfbot2-alpha",
                    connect_cb=connect_callback)

    conn = cli.connect()
    while True:
        next(conn)        

        
# Game Logic Begins:

import vars

def reset_game():
    vars.GAME_STARTED = False
    vars.ROLES = {"person" : []}
    vars.PHASE = "none"

# Command Handlers:
@cmd("!say", pm=True)
def say(cli, rawnick, rest):  # To be removed later
    cli.msg(botconfig.CHANNEL, "{0} says: {1}".format(parse_nick(rawnick)[0], rest))
    
@cmd("!bye", pm=True)
@cmd("!bye", pm=False)
def forced_exit(cli, rawnick, *rest):  # Admin Only
    if parse_nick(rawnick)[0] in botconfig.ADMINS:
        cli.quit("Forced quit from admin")
        raise SystemExit

@cmd("!join", pm=False)
def join(cli, rawnick, chan, rest):
    if vars.PHASE != "none":
        return

    vars.GAME_STARTED = True
    
    nick = parse_nick(rawnick)[0]
    cli.msg(chan, '{0} has started a game of Werewolf. \
Type "!join" to join. Type "!start" to start the game. \
Type "!wait" to increase join wait time.'.format(nick))

    vars.ROLES["person"].append(nick)
    vars.PHASE = "join"



@cmd("!stats", pm=False)
def stats(cli, rawnick, chan, rest):
    if vars.PHASE == "none":
        return
    nick = parse_nick(rawnick)[0]
    pl = []
    for x in vars.ROLES.values(): pl.extend(x)
    cli.msg(chan, '{0}: {1} players: {2}'.format(nick,
        len(pl), ", ".join(pl)))
    

# Game Logic Ends


if __name__ == "__main__":
    main()