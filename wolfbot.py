from oyoyo.client import IRCClient
from oyoyo.cmdhandler import DefaultCommandHandler, protected
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
        
    @protected
    def __unhandled__(self, cmd, *args):
        if cmd in HOOKS.keys():
            largs = list(args)
            for i,arg in enumerate(largs):
                if arg: largs[i] = arg.decode('ascii')
            HOOKS[cmd](*largs)
        else:
            logging.debug('unhandled command %s(%s)' % (cmd, args))

def main():
    logging.basicConfig(level=logging.DEBUG)
    cli = IRCClient(WolfBotHandler, host="irc.freenode.net", port=6667, nickname=botconfig.NICK,
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
        
@cmd("!exec", pm=False)
def py(cli, rawnick, chan, rest):
    if parse_nick(rawnick)[0] in botconfig.ADMINS:
        exec(rest)

@cmd("!ping", pm=False)
def pinger(cli, rawnick, chan, rest):
    vars.PINGING = True
    TO_PING = []

    @hook("whoreply")
    def on_whoreply(server, dunno, chan, dunno1, dunno2, dunno3, user, status, dunno4):
        if not vars.PINGING: return
        if user in (botconfig.NICK, parse_nick(rawnick)[0]): return  # Don't ping self.
        
        if vars.PINGING and 'G' not in status and '+' not in status:
            # TODO: check if the user has AWAY'D himself
            TO_PING.append(user)

    @hook("endofwho")
    def do_ping(*args):
        if not vars.PINGING: return
        
        chan = args[2]
        cli.msg(chan, "PING! "+" ".join(TO_PING))
        vars.PINGING = False
        
        HOOKS.pop("whoreply")
        HOOKS.pop("endofwho")
    
    cli.send("WHO "+chan)

        
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
    if len(pl) > 1:
        cli.msg(chan, '{0}: {1} players: {2}'.format(nick,
            len(pl), ", ".join(pl)))
    else:
        cli.msg(chan, '{0}: 1 player: {1}'.format(nick, pl[0]))
    
    msg = []
    for role in vars.ROLES.keys():
        num = len(vars.ROLES[role])
        if num > 1:
            msg.append("{0} {1}".format(num, plural(role)))
        else:
            msg.append("{0} {1}".format(num, role))
    if len(msg) > 2:  # More than 2 roles to say
        msg[-1] = "and "+msg[-1]+"."
        msg[0] = "{0}: There are ".format(nick) + msg[0]
        cli.msg(chan, ", ".join(msg))
    elif len(msg) == 2:  # 2 roles to say
        cli.msg(chan, "{0}: There are ".format(nick) + msg[0],
                "and", msg[1] + ".")
    elif len(msg) == 1:
        cli.msg(chan, "{0}: There is ".format(nick) + msg[0] + ".")        

# Game Logic Ends


if __name__ == "__main__":
    main()