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
import sys
import os

import botconfig

ver = sys.version_info
if ver < (3, 3):
    print("Python 3.3 or newer is required to run the bot.")
    print("You are currently using {0}.{1}.{2}".format(ver[0], ver[1], ver[2]))
    sys.exit(1)

try: # need to manually add dependencies here
    import typing # Python >= 3.5
    import enum # Python >= 3.4
except ImportError:
    command = "python3"
    if os.name == "nt":
        command = "py -3"
    print("\n".join(["*** Missing dependencies! ***".center(80),
          "Please install the missing dependencies by running the following command:",
          "{0} -m pip install --user -r requirements.txt".format(command), "",
          "If you don't have pip and don't know how to install it, follow this link:",
          "https://pip.pypa.io/en/stable/installing/", "",
          "If you need any further help with setting up and/or running the bot,",
          "  we will be happy to help you in #lykos on irc.freenode.net", "",
          "- The lykos developers"]))
    sys.exit(1)

from oyoyo.client import IRCClient

import src
from src import handler
from src.events import Event

def main():
    evt = Event("init", {})
    evt.dispatch()
    src.plog("Connecting to {0}:{1}{2}".format(botconfig.HOST, "+" if botconfig.USE_SSL else "", botconfig.PORT))
    cli = IRCClient(
                      {"privmsg": lambda *s: None,
                       "notice": lambda *s: None,
                       "": handler.unhandled},
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
