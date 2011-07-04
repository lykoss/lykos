from oyoyo.client import IRCClient
from oyoyo.cmdhandler import DefaultCommandHandler, protected
from oyoyo.parse import parse_nick
import logging
import botconfig
import wolfgame

def cmd(s, pm = False):
    def dec(f):
        if s is None and pm:
            G_PM_COMMAND.append(f)
        elif s is None and not pm:
            G_COMMAND.append(f)
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
            for x in wolfgame.COMMANDS.keys():
                if msg.startswith(x):
                    msg = msg.replace(x, "", 1)
                    wolfgame.COMMANDS[x](self.client, rawnick, chan, msg.lstrip())
        else:
            for x in wolfgame.PM_COMMANDS.keys():
                if msg.startswith(x):
                    msg = msg.replace(x, "", 1)
                    wolfgame.PM_COMMANDS[x](self.client, rawnick, msg.lstrip())
        print(wolfgame.COMMANDS)
        
    @protected
    def __unhandled__(self, cmd, *args):
        if cmd in wolfgame.HOOKS.keys():
            largs = list(args)
            for i,arg in enumerate(largs):
                if arg: largs[i] = arg.decode('ascii')
            wolfgame.HOOKS[cmd](*largs)
        else:
            logging.debug('unhandled command %s(%s)' % (cmd, args))

def main():
    logging.basicConfig(level=logging.DEBUG)
    cli = IRCClient(WolfBotHandler, host=botconfig.HOST, port=botconfig.PORT, nickname=botconfig.NICK,
                    connect_cb=wolfgame.connect_callback)

    conn = cli.connect()
    while True:
        next(conn)


if __name__ == "__main__":
    main()