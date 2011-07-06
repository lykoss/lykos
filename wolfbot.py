from oyoyo.client import IRCClient
from oyoyo.cmdhandler import DefaultCommandHandler, protected
from oyoyo.parse import parse_nick
import logging
import botconfig
import wolfgame

class WolfBotHandler(DefaultCommandHandler):
    def __init__(self, client):
        super().__init__(client)

    def privmsg(self, rawnick, chan, msg):         
        if chan != botconfig.NICK:  #not a PM
            for x in wolfgame.COMMANDS.keys():
                if msg.lower().startswith(x):
                    h = msg[len(x):]
                    if not h or h[0] == " " or not x:
                        wolfgame.COMMANDS[x](self.client, rawnick, chan, h.lstrip())
        else:
            for x in wolfgame.PM_COMMANDS.keys():
                if msg.lower().startswith(x):
                    h = msg[len(x):]
                    if not h or h[0] == " " or not x:
                        wolfgame.PM_COMMANDS[x](self.client, rawnick, h.lstrip())
        
    @protected
    def __unhandled__(self, cmd, *args):
        if cmd in wolfgame.HOOKS.keys():
            largs = list(args)
            for i,arg in enumerate(largs):
                if arg: largs[i] = arg.decode('ascii')
            wolfgame.HOOKS[cmd](self.client, *largs)
        else:
            logging.debug('unhandled command %s(%s)' % (cmd, args))

def main():
    logging.basicConfig(level=logging.INFO)
    cli = IRCClient(WolfBotHandler, host=botconfig.HOST, port=botconfig.PORT, nickname=botconfig.NICK,
                    connect_cb=wolfgame.connect_callback)

    conn = cli.connect()
    while True:
        next(conn)


if __name__ == "__main__":
    main()