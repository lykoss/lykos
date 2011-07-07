from oyoyo.client import IRCClient
from oyoyo.cmdhandler import CommandHandler, protected
from oyoyo.parse import parse_nick
import logging
import botconfig
import wolfgame

class WolfBotHandler(CommandHandler):
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
                if isinstance(arg, bytes): largs[i] = arg.decode('ascii')
            wolfgame.HOOKS[cmd](self.client, *largs)
        else:
            logging.debug('Unhandled command {0}({1})'.format(cmd, [arg.decode('utf_8')
                                                                  for arg in args
                                                                  if isinstance(arg, bytes)]))

def main():
    logging.basicConfig(level=logging.DEBUG)
    cli = IRCClient(WolfBotHandler, host=botconfig.HOST, port=botconfig.PORT, nickname=botconfig.NICK,
                    connect_cb=wolfgame.connect_callback)

    cli.mainLoop()


if __name__ == "__main__":
    main()