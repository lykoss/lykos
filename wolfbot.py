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

import asyncio
import traceback
import sys
import os
import argparse
import logging
from pathlib import Path

ver = sys.version_info
if ver < (3, 9):
    print("Python 3.9 or newer is required to run the bot.", file=sys.stderr)
    print("You are currently using {0}.{1}.{2}".format(ver[0], ver[1], ver[2]), file=sys.stderr)
    sys.exit(1)

try: # need to manually add dependencies here
    import antlr4
    import requests
    import ruamel.yaml
    from ircrobots import ircrobots # TODO: figure out how to make it install the deps
except ImportError:
    command = "python3"
    if os.name == "nt":
        command = "py -3"
    print("\n".join(["*** Missing dependencies! ***".center(80),
                     "Please install the missing dependencies by running the following command:",
                     "{0} -m pip install --user -r requirements.txt".format(command),
                     "",
                     "If you don't have pip and don't know how to install it, follow this link:",
                     "https://pip.pypa.io/en/stable/installing/",
                     "",
                     "If you need any further help with setting up and/or running the bot,",
                     "  we will be happy to help you in #lykos on irc.libera.chat",
                     "",
                     "- The lykos developers"]), file=sys.stderr)
    sys.exit(1)

# Parse command line args
# Argument --debug means start in debug mode (loads botconfig.debug.yml)
#          --config <name> Means to load settings from the configuration file botconfig.name.yml, overriding
#              whatever is present in botconfig.yml. If specified alongside --debug, configuration in
#              botconfig.debug.yml takes precedence over configuration defined here.
parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true', help="Run bot in debug mode. Loads botconfig.debug.yml.")
parser.add_argument('--config', help="Path to file to load in addition to botconfig.yml.")

args = parser.parse_args()
if args.debug:
    os.environ["DEBUG"] = "1"
if args.config:
    p = Path(args.config)
    if not p.is_file():
        print("File specified by --config does not exist or is not a file", file=sys.stderr)
        sys.exit(1)
    os.environ["BOTCONFIG"] = str(p.resolve())

from oyoyo.client import IRCClient, TokenBucket

from src import handler, config

async def main():
    # fetch IRC transport
    irc = config.Main.get("transports[0].type", None)
    if irc != "irc":
        print("\n".join([
            "botconfig.yml is not configured. If you have an old botconfig.py file,",
            "it will no longer be loaded. Please copy all relevant configuration to botconfig.yml.",
            "Please see comments in botconfig.yml or check https://ww.chat/config for help",
            "on how to configure lykos."]))
        sys.exit(1)

    general_logger = logging.getLogger("general")
    general_logger.info("Loading Werewolf IRC bot")

    host = config.Main.get("transports[0].connection.host")
    port = config.Main.get("transports[0].connection.port")
    bindhost = config.Main.get("transports[0].connection.source")
    use_ssl = config.Main.get("transports[0].connection.ssl.use_ssl")
    nick = config.Main.get("transports[0].user.nick")
    ident = config.Main.get("transports[0].user.ident")
    if not ident:
        ident = nick
    real_name = config.Main.get("transports[0].user.realname")
    if not real_name:
        real_name = nick
    username = config.Main.get("transports[0].authentication.services.username")
    if not username:
        username = nick

    transport_name = config.Main.get("transports[0].name")
    transport_logger = logging.getLogger("transport.{}".format(transport_name))
    # this uses %-style formatting to ensure that our logger is capable of handling both styles
    transport_logger.info("Connecting to %s:%s%d", host, "+" if use_ssl else "", port)
    cmd_handler = {
        "privmsg": lambda *s: None,
        "notice": lambda *s: None,
        "": handler.unhandled
    }

    def stream_handler(msg, level="info"):
        level_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR
        }
        transport_logger.log(level_map[level], msg)

    params = ircrobots.ConnectionParams(
        nickname=nick,
        host=host,
        port=port,
        username=ident,
        realname=real_name,
        password=config.Main.get("transports[0].authentication.services.password"),
    )

    cli = IRCClient(
        cmd_handler,
        #host=host,
        #port=port,
        bindhost=bindhost,
        authname=username,
        #password=config.Main.get("transports[0].authentication.services.password"),
        #nickname=nick,
        #ident=ident,
        #real_name=real_name,
        sasl_auth=config.Main.get("transports[0].authentication.services.use_sasl"),
        server_pass=config.Main.get("transports[0].authentication.server.password"),
        use_ssl=use_ssl,
        cert_verify=config.Main.get("transports[0].connection.ssl.verify_peer"),
        cert_fp=config.Main.get("transports[0].connection.ssl.trusted_fingerprints"),
        client_certfile=config.Main.get("transports[0].authentication.services.client_certificate"),
        client_keyfile=config.Main.get("transports[0].authentication.services.client_key"),
        cipher_list=config.Main.get("ssl.ciphers"),
        tokenbucket=TokenBucket(
            config.Main.get("transports[0].flood.max_burst"),
            config.Main.get("transports[0].flood.sustained_rate"),
            init=config.Main.get("transports[0].flood.initial_burst")),
        connect_cb=handler.connect_callback,
        stream_handler=stream_handler,
    )
    cli.mainLoop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        # can't rely on logging utilities here, they might be broken or closed already
        traceback.print_exc()
