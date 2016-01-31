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

import botconfig

if sys.version_info < (3, 2):
    print("Python 3.2 or newer is required to run the bot.")
    sys.exit(1)

if sys.version_info < (3, 3):
    allow_unsup = getattr(botconfig, "allow_unsupported_Python", None)
    # add an "allow_unsupported_Python" attribute in botconfig
    # set it to the tuple (3, 2) to prevent the bot from exiting
    # this backwards-compatibility fix will not remain for long
    # please update to 3.3 if you can. if you can't, you will need
    # to stick with an older revision, and new bugfixes/features
    # will not be applied to the 3.2-supported versions
    # we will also not provide any more support
    print("As of the 1st of February 2016, support for Python 3.2 is gone.",
          "You need Python 3.3 or above to run the bot from this point onwards.",
          "Please upgrade your installed Python version to run the bot.",
          "", "Thank you for your interest!", "- The lykos development team",
          sep="\n", file=sys.stderr)

    if allow_unsup != (3, 2):
        sys.exit(1)
    else:
        print("\n...\nFine, fine, I'll run anyway", file=sys.stderr)

from oyoyo.client import IRCClient

import src
from src import handler

def main():
    src.logger(None)("Connecting to {0}:{1}{2}".format(botconfig.HOST, "+" if botconfig.USE_SSL else "", botconfig.PORT))
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
