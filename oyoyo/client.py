# Copyright (c) 2011 Duncan Fordyce, Jimmy Cao
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

import socket
import ssl
import sys
import threading
import time
import traceback
import os

from oyoyo.parse import parse_raw_irc_command


# Adapted from http://code.activestate.com/recipes/511490-implementation-of-the-token-bucket-algorithm/
class TokenBucket(object):
    """An implementation of the token bucket algorithm.

    >>> bucket = TokenBucket(80, 0.5)
    >>> bucket.consume(1)
    """
    def __init__(self, tokens, fill_rate):
        """tokens is the total tokens in the bucket. fill_rate is the
        rate in tokens/second that the bucket will be refilled."""
        self.capacity = float(tokens)
        self._tokens = float(tokens)
        self.fill_rate = float(fill_rate)
        self.timestamp = time.time()

    def consume(self, tokens):
        """Consume tokens from the bucket. Returns True if there were
        sufficient tokens otherwise False."""
        if tokens <= self.tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def tokens(self):
        now = time.time()
        if self._tokens < self.capacity:
            delta = self.fill_rate * (now - self.timestamp)
            self._tokens = min(self.capacity, self._tokens + delta)
        self.timestamp = now
        return self._tokens

    def __repr__(self):
        return "{self.__class__.__name__}(capacity={self.capacity}, fill rate={self.fill_rate}, tokens={self.tokens})".format(self=self)

class IRCClient:
    """ IRC Client class. This handles one connection to a server.
    This can be used either with or without IRCApp ( see connect() docs )
    """

    def __init__(self, cmd_handler, **kwargs):
        """ the first argument should be an object with attributes/methods named
        as the irc commands. You may subclass from one of the classes in
        oyoyo.cmdhandler for convenience but it is not required. The
        methods should have arguments (prefix, args). prefix is
        normally the sender of the command. args is a list of arguments.
        Its recommened you subclass oyoyo.cmdhandler.DefaultCommandHandler,
        this class provides defaults for callbacks that are required for
        normal IRC operation.

        all other arguments should be keyword arguments. The most commonly
        used will be nick, host and port. You can also specify an "on connect"
        callback. ( check the source for others )

        Warning: By default this class will not block on socket operations, this
        means if you use a plain while loop your app will consume 100% cpu.
        To enable blocking pass blocking=True.
        """

        self.socket = None
        self.nickname = ""
        self.hostmask = ""
        self.ident = ""
        self.real_name = ""
        self.host = None
        self.port = None
        self.password = ""
        self.authname = ""
        self.connect_cb = None
        self.blocking = True
        self.sasl_auth = False
        self.use_ssl = False
        self.server_pass = None
        self.lock = threading.RLock()
        self.stream_handler = lambda output, level=None: print(output)

        self.tokenbucket = TokenBucket(23, 1.73)

        self.__dict__.update(kwargs)
        self.command_handler = cmd_handler
        self._end = 0

    def __enter__(self):
        return self

    def __exit__(self, exc, value, tb):
        return False # TODO: make this into a proper context manager

    def send(self, *args, **kwargs):
        """ send a message to the connected server. all arguments are joined
        with a space for convenience, for example the following are identical

        >>> cli.send("JOIN " + some_room)
        >>> cli.send("JOIN", some_room)

        In python 2, all args must be of type str or unicode, *BUT* if they are
          unicode they will be converted to str with the encoding specified by
          the 'encoding' keyword argument (default 'utf8').
        In python 3, all args must be of type str or bytes, *BUT* if they are
          str they will be converted to bytes with the encoding specified by the
          'encoding' keyword argument (default 'utf8').
        """
        with self.lock:
            # Convert all args to bytes if not already
            encoding = kwargs.get('encoding') or 'utf_8'
            bargs = []
            for i,arg in enumerate(args):
                if isinstance(arg, str):
                    bargs.append(bytes(arg, encoding))
                elif isinstance(arg, bytes):
                    bargs.append(arg)
                elif arg is None:
                    continue
                else:
                    raise Exception(('Refusing to send arg at index {1} of the args from '+
                                     'provided: {0}').format(repr([(type(arg), arg)
                                                                   for arg in args]), i))

            msg = bytes(" ", "utf_8").join(bargs)
            self.stream_handler('---> send {0}'.format(str(msg)[1:]))

            while not self.tokenbucket.consume(1):
                time.sleep(0.3)
            self.socket.send(msg + bytes("\r\n", "utf_8"))

    def connect(self):
        """ initiates the connection to the server set in self.host:self.port
        and returns a generator object.

        >>> cli = IRCClient(my_handler, host="irc.freenode.net", port=6667)
        >>> g = cli.connect()
        >>> while 1:
        ...     next(g)

        """
        try:
            retries = 0
            while True:
                try:
                    self.socket = socket.create_connection(("{0}".format(self.host), self.port))
                    break
                except socket.error as e:
                    retries += 1
                    self.stream_handler('Error: {0}'.format(e), level="warning")
                    if retries > 3:
                        sys.exit(1)

            if self.use_ssl:
                self.socket = ssl.wrap_socket(self.socket)

            if not self.blocking:
                self.socket.setblocking(0)

            self.send("CAP LS 302")

            if (self.server_pass and "{password}" in self.server_pass
                    and self.password and not self.sasl_auth):
                message = "PASS :{0}".format(self.server_pass).format(
                    account=self.authname if self.authname else self.nickname,
                    password=self.password)
                self.send(message)

            self.send("NICK", self.nickname)
            self.user(self.ident, self.real_name)

            if self.connect_cb:
                try:
                    self.connect_cb(self)
                except Exception as e:
                    sys.stderr.write(traceback.format_exc())
                    raise e

            buffer = bytes()
            while not self._end:
                try:
                    buffer += self.socket.recv(1024)
                except socket.error as e:
                    if False and not self.blocking and e.errno == 11:
                        pass
                    else:
                        sys.stderr.write(traceback.format_exc())
                        raise e
                else:
                    data = buffer.split(bytes("\n", "utf_8"))
                    buffer = data.pop()

                    for el in data:
                        prefix, command, args = parse_raw_irc_command(el)

                        try:
                            enc = "utf8"
                            fargs = [arg.decode(enc) for arg in args if isinstance(arg,bytes)]
                        except UnicodeDecodeError:
                            enc = "latin1"
                            fargs = [arg.decode(enc) for arg in args if isinstance(arg,bytes)]

                        try:
                            largs = list(args)
                            if prefix is not None:
                                prefix = prefix.decode(enc)
                            self.stream_handler("<--- receive {0} {1} ({2})".format(prefix, command, ", ".join(fargs)), level="debug")
                            # for i,arg in enumerate(largs):
                                # if arg is not None: largs[i] = arg.decode(enc)
                            if command in self.command_handler:
                                self.command_handler[command](self, prefix,*fargs)
                            elif "" in self.command_handler:
                                self.command_handler[""](self, prefix, command, *fargs)
                        except Exception as e:
                            sys.stderr.write(traceback.format_exc())
                            raise e  # ?
                yield True
        finally:
            if self.socket:
                self.stream_handler('closing socket')
                self.socket.close()
                yield False
    def msg(self, user, msg):
        for line in msg.split('\n'):
            maxchars = 494 - len(self.nickname+self.ident+self.hostmask+user)
            while line:
                extra = ""
                if len(line) > maxchars:
                    extra = line[maxchars:]
                    line = line[:maxchars]
                self.send("PRIVMSG", user, ":{0}".format(line))
                line = extra
    privmsg = msg  # Same thing
    def notice(self, user, msg):
        for line in msg.split('\n'):
            maxchars = 495 - len(self.nickname+self.ident+self.hostmask+user)
            while line:
                extra = ""
                if len(line) > maxchars:
                    extra = line[maxchars:]
                    line = line[:maxchars]
                self.send("NOTICE", user, ":{0}".format(line))
                line = extra
    def join(self, channel):
        self.send("JOIN {0}".format(channel))
    def quit(self, msg=""):
        self.send("QUIT :{0}".format(msg))
    def part(self, chan, msg=""):
        self.send("PART {0} :{1}".format(chan, msg))
    def mode(self, *args):
        self.send("MODE {0}".format(" ".join(args)))
    def kick(self, chan, nick, msg=""):
        self.send("KICK", chan, nick, ":"+msg)
    def who(self, *args):
        self.send("WHO {0}".format(" ".join(args)))
    def ns_identify(self, account, passwd, nickserv, command):
        if command:
            self.msg(nickserv, command.format(account=account, password=passwd))
    def ns_ghost(self, nick, password, nickserv, command):
        if command:
            self.msg(nickserv, command.format(nick=nick, password=password))
    def ns_release(self, nick, password, nickserv="NickServ", command="RELEASE {nick}"):
        if command:
            self.msg(nickserv, command.format(nick=nick, password=password))
    def ns_regain(self, nick, password, nickserv="NickServ", command="REGAIN {nick}"):
        if command:
            self.msg(nickserv, command.format(nick=nick, password=password))
    def user(self, ident, rname):
        self.send("USER", ident, self.host, self.host, ":{0}".format(rname or ident))
    def mainLoop(self):
        conn = self.connect()
        while True:
            if not next(conn):
                self.stream_handler("Calling sys.exit()...", level="warning")
                sys.exit()
