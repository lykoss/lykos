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

ver = sys.version_info
if ver < (3, 6):
    print("Python 3.6 or newer is required to run the bot.")
    print("You are currently using {0}.{1}.{2}".format(ver[0], ver[1], ver[2]))
    sys.exit(1)

try: # need to manually add dependencies here
    import antlr4
    import yaml
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

from oyoyo.client import IRCClient, TokenBucket

import src
from src import handler
from src.events import Event
import src.settings as var

def main():
    with open("botconfig.yml") as f:
        config = yaml.safe_load(f)

    if not config["transports"]:
        print("\n".join([
            "botconfig.yml is not configured. If you have an old botconfig.py file,",
            "it will no longer be loaded. Please copy all relevant configuration to botconfig.yml.",
            "Please see comments in botconfig.yml or check https://ww.chat/config for help",
            "on how to configure lykos."]))
        sys.exit(1)

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
                     cert_verify=var.SSL_VERIFY,
                     cert_fp=var.SSL_CERTFP,
                     client_certfile=var.SSL_CERTFILE,
                     client_keyfile=var.SSL_KEYFILE,
                     cipher_list=var.SSL_CIPHERS,
                     tokenbucket=TokenBucket(var.IRC_TB_BURST, var.IRC_TB_DELAY, init=var.IRC_TB_INIT),
                     connect_cb=handler.connect_callback,
                     stream_handler=src.stream,
    )
    cli.mainLoop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        src.errlog(traceback.format_exc())
