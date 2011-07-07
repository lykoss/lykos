# Copyright (c) 2008 Duncan Fordyce
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

import logging
import socket

from oyoyo.parse import parse_raw_irc_command
from oyoyo.cmdhandler import CommandError

class IRCClientError(Exception):
    pass
    
def add_commands(d):
    def dec(cls):
        for c in d:
            def func(x):
                def gen(self, *a):
                    self.send(x.upper(), *a)
                return gen
            setattr(cls, c, func(c))
        return cls
    return dec
@add_commands(("join",
               "mode",
               "nick",
               "part"))
class IRCClient(object):
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
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.nickname = ""
        self.real_name = ""
        self.host = None
        self.port = None
        self.connect_cb = None
        self.blocking = True

        self.__dict__.update(kwargs)
        self.command_handler = cmd_handler(self)

        self._end = 0

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
        logging.info('---> send "{0}"'.format(msg))

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
            logging.info('connecting to {0}:{1}'.format(self.host, self.port))
            self.socket.connect(("{0}".format(self.host), self.port))
            if not self.blocking:
                self.socket.setblocking(0)
            
            self.nick(self.nickname)
            self.user(self.nickname, self.real_name)

            if self.connect_cb:
                self.connect_cb(self)
            
            buffer = bytes()
            while not self._end:
                try:
                    buffer += self.socket.recv(1024)
                except socket.error as e:                
                    if not self.blocking and e.errno == 11:
                        pass
                    else:
                        raise e
                else:
                    data = buffer.split(bytes("\n", "utf_8"))
                    buffer = data.pop()

                    for el in data:
                        prefix, command, args = parse_raw_irc_command(el)

                        try:
                            self.command_handler.run(command, prefix, *args)
                        except CommandError:
                            # error will of already been logged by the handler
                            pass 

                yield True
        finally:
            if self.socket: 
                logging.info('closing socket')
                self.socket.close()
    def msg(self, user, msg):
        for line in msg.split('\n'):
            self.send("PRIVMSG", user, ":{0}".format(line))
    privmsg = msg  # Same thing
    def notice(self, user, msg):
        for line in msg.split('\n'):
            self.send("NOTICE", user, ":{0}".format(line))
    def quit(self, msg):
        self.send("QUIT :{0}".format(msg))
    def identify(self, passwd, authuser="NickServ"):
        self.msg(authuser, "IDENTIFY {0}".format(passwd))
    def user(self, uname, rname):
        self.send("USER", uname, self.host, self.host, 
                 rname or uname)
    def mainLoop(self):
        conn = self.connect()
        while True:
            next(conn)
