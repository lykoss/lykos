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

import sys

if sys.version_info < (3, 2):
    print("Python 3.2 or newer is required to run the bot.")
    sys.exit(1)

if sys.version_info < (3, 3):
    print("*** WARNING ***".center(80),
          "Starting February 2016, Python 3.2 support will be officially dropped.",
          "The minimum requirement will be increased to Python 3.3",
          "Please make sure to upgrade by then, or stick with an older revision.", "",
          "Concerns and questions may be asked on the official development channel",
          "  in ##werewolf-dev over at irc.freenode.net", "",
          "You may also open an issue on the issue tracker in the GitHub repository",
          "  located at https://github.com/lykoss/lykos", "",
          "The lifetime of Python 3.2 support may be extended on request.", "",
          "Thank you for your interest in this IRC bot!", "",
          "- The lykos development team", "", sep="\n", file=sys.stderr)

import traceback

from oyoyo.client import IRCClient

import botconfig
import src
from src import handler

def main():
    cli = IRCClient(
                      {"privmsg": handler.on_privmsg,
                       "notice": lambda a, b, c, d: handler.on_privmsg(a, b, c, d, True),
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
        src.logger("errors.log")(traceback.format_exc())
