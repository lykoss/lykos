from oyoyo.client import IRCClient
from oyoyo.cmdhandler import DefaultCommandHandler
from oyoyo import helpers
from oyoyo.parse import parse_nick
import logging
import botconfig

def connect_callback(cli):
    helpers.identify(cli, botconfig.PASS)
    helpers.join(cli, botconfig.CHANNEL)
    helpers.msg(cli, "ChanServ", "op "+botconfig.CHANNEL)
    helpers.msg(cli, botconfig.CHANNEL, "\u0002Wolfbot2 is here.\u0002")

G_PM_COMMANDS = []
G_COMMANDS = []
COMMANDS = {}
PM_COMMANDS = {}

HOOKS = {}

def cmd(s, pmOnly = False):
    def dec(f):
        if s is None and pmOnly:
            G_PM_COMMANDS.append(f)
        elif s is None and not pmOnly:
            G_COMMANDS.append(f)
        elif pmOnly:
            if s in PM_COMMANDS:
                PM_COMMANDS[s].append(f)
            else: PM_COMMANDS[s] = [f]
        else:
            if s in COMMANDS:
                COMMANDS[s].append(f)
            else: COMMANDS[s] = [f]
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
        print("{0} in {1} said: {2}".format(rawnick, chan, msg))
            
        if chan != botconfig.NICK:  #not a PM
            for x in COMMANDS:
                if msg.startswith(x):
                    msg = msg.replace(x, "", 1)
                    for f in COMMANDS[x]:
                        f(self.client, rawnick, chan, msg.lstrip())
        else:
            for x in PM_COMMANDS:
                if msg.startswith(x):
                    msg = msg.replace(x, "", 1)
                    for f in PM_COMMANDS[x]:
                        f(self.client, rawnick, msg.lstrip())
        
    def nick(self, fro, to):
        print(fro, to)

def main():
    logging.basicConfig(level=logging.DEBUG)
    cli = IRCClient(WolfBotHandler, host="irc.freenode.net", port=6667, nick="wolfbot2-alpha",
                    connect_cb=connect_callback)

    conn = cli.connect()
    while True:
        next(conn)        

#Game Logic Begins:

@cmd("!say", True)
def join(cli, rawnick, rest):
    cli.msg(botconfig.CHANNEL, "{0} says: {1}".format(parse_nick(rawnick)[0], rest))
    
@cmd("!bye", True)
@cmd("!bye", False)
def forced_exit(cli, rawnick, *rest):
    if parse_nick(rawnick)[0] in botconfig.ADMINS:
        cli.quit("Forced quit from admin")
        raise SystemExit

#Game Logic Ends

if __name__ == "__main__":
    main()