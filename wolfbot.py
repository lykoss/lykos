#!/usr/bin/env python3.2

# Copyright (c) 2011 Jimmy Cao
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.



from oyoyo.client import IRCClient
from oyoyo.parse import parse_nick
import logging
import botconfig
import wolfgame
import traceback

def on_privmsg(cli, rawnick, chan, msg):         
    if chan != botconfig.NICK:  #not a PM
        if "" in wolfgame.COMMANDS.keys():
            for fn in wolfgame.COMMANDS[""]:
                try:
                    fn(cli, rawnick, chan, msg)
                except Exception as e:
                    if botconfig.DEBUG_MODE:
                        raise e
                    else:
                        logging.error(traceback.format_exc())
                        cli.msg(chan, "An error has occurred and has been logged.")
            # Now that is always called first.
        for x in wolfgame.COMMANDS.keys():
            if x and msg.lower().startswith(botconfig.CMD_CHAR+x):
                h = msg[len(x)+1:]
                if not h or h[0] == " " or not x:
                    for fn in wolfgame.COMMANDS[x]:
                        try:
                            fn(cli, rawnick, chan, h.lstrip())
                        except Exception as e:
                            if botconfig.DEBUG_MODE:
                                raise e
                            else:
                                logging.error(traceback.format_exc())
                                cli.msg(chan, "An error has occurred and has been logged.")
    else:
        for x in wolfgame.PM_COMMANDS.keys():
            if msg.lower().startswith(botconfig.CMD_CHAR+x):
                h = msg[len(x)+1:]
            elif not x or msg.lower().startswith(x):
                h = msg[len(x):]
            else:
                continue
            if not h or h[0] == " " or not x:
                for fn in wolfgame.PM_COMMANDS[x]:
                    try:
                        fn(cli, rawnick, h.lstrip())
                    except Exception as e:
                        if botconfig.DEBUG_MODE:
                            raise e
                        else:
                            logging.error(traceback.format_exc())
                            cli.msg(chan, "An error has occurred and has been logged.")
    
def __unhandled__(cli, prefix, cmd, *args):
    if cmd in wolfgame.HOOKS.keys():
        largs = list(args)
        for i,arg in enumerate(largs):
            if isinstance(arg, bytes): largs[i] = arg.decode('ascii')
        for fn in wolfgame.HOOKS[cmd]:
            try:
                fn(cli, prefix, *largs)
            except Exception as e:
                if botconfig.DEBUG_MODE:
                    raise e
                else:
                    logging.error(traceback.format_exc())
                    cli.msg(botconfig.CHANNEL, "An error has occured and has been logged.")
    else:
        logging.debug('Unhandled command {0}({1})'.format(cmd, [arg.decode('utf_8')
                                                              for arg in args
                                                              if isinstance(arg, bytes)]))

def main():
    if not botconfig.DEBUG_MODE:
        logging.basicConfig(filename='errors.log', filemode='a', level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.DEBUG)
    
    cli = IRCClient(
                      {"privmsg":on_privmsg,
                       "":__unhandled__},
                     host=botconfig.HOST, 
                     port=botconfig.PORT,
                     authname=botconfig.USERNAME,
                     password=botconfig.PASS,
                     nickname=botconfig.NICK,
                     connect_cb=wolfgame.connect_callback
                    )
    cli.mainLoop()


if __name__ == "__main__":
    try:
        main()
    except:
        logging.error(traceback.format_exc())
