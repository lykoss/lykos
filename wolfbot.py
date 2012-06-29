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
import time
import traceback
import modules.common

class UTCFormatter(logging.Formatter):
    converter = time.gmtime

def main():
    if not botconfig.DEBUG_MODE:
        logging.basicConfig(filename='errors.log', filemode='a', level=logging.WARNING)
        formatter = UTCFormatter('[%(asctime)s] %(message)s', '%d/%b/%Y %H:%M:%S')
        for handler in logging.getLogger().handlers:
            handler.setFormatter(formatter)
    else:
        logging.basicConfig(level=logging.DEBUG)
        formatter = UTCFormatter('[%(asctime)s] %(message)s', '%H:%M:%S')
        for handler in logging.getLogger().handlers:
            handler.setFormatter(formatter)
    
    cli = IRCClient(
                      {"privmsg":modules.common.on_privmsg,
                       "notice":lambda a, b, c, d: modules.common.on_privmsg(a, b, c, d, True),
                       "":modules.common.__unhandled__},
                     host=botconfig.HOST, 
                     port=botconfig.PORT,
                     authname=botconfig.USERNAME,
                     password=botconfig.PASS,
                     nickname=botconfig.NICK,
                     sasl_auth=botconfig.SASL_AUTHENTICATION,
                     use_ssl=botconfig.USE_SSL,
                     connect_cb=modules.common.connect_callback
                    )
    cli.mainLoop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.error(traceback.format_exc())
