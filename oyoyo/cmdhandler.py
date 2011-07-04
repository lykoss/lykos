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

import inspect
import logging
import sys
import traceback

from oyoyo.parse import parse_nick

def protected(func):
    """ decorator to protect functions from being called """
    func.protected = True
    return func


class CommandError(Exception):
    def __init__(self, cmd):
        self.cmd = cmd

class NoSuchCommandError(CommandError):
    def __str__(self):
        return 'No such command "%s"' % ".".join(self.cmd)

class ProtectedCommandError(CommandError):
    def __str__(self):
        return 'Command "%s" is protected' % ".".join(self.cmd)
        

class CommandHandler(object):
    """ The most basic CommandHandler """

    def __init__(self, client):
        self.client = client

    @protected
    def get(self, in_command_parts):
        """ finds a command 
        commands may be dotted. each command part is checked that it does
        not start with and underscore and does not have an attribute 
        "protected". if either of these is true, ProtectedCommandError
        is raised.
        its possible to pass both "command.sub.func" and 
        ["command", "sub", "func"].
        """

        if isinstance(in_command_parts, bytes):
            in_command_parts = in_command_parts.split(b'.')
        else:
            in_command_parts = in_command_parts.split('.')
            
        command_parts = []
        for cmdpart in in_command_parts:
            if isinstance(cmdpart, bytes):
                cmdpart = cmdpart.decode('ascii')    
            command_parts.append(cmdpart)

        p = self
        while command_parts:
            cmd = command_parts.pop(0)
            if cmd.startswith('_'):
                raise ProtectedCommandError(in_command_parts)

            try:
                f = getattr(p, cmd)
            except AttributeError:
                raise NoSuchCommandError(in_command_parts)

            if hasattr(f, 'protected'):
                raise ProtectedCommandError(in_command_parts)

            if isinstance(f, CommandHandler) and command_parts:
                return f.get(command_parts)
            p = f

        return f

    @protected
    def run(self, command, *args):
        """ finds and runs a command """
        logging.debug("processCommand %s(%s)" % (command, args))

        try:
            f = self.get(command)
        except NoSuchCommandError:
            self.__unhandled__(command, *args)
            return

        logging.debug('f %s' % f)

        try:
            largs = list(args)
            for i,arg in enumerate(largs):
                if arg: largs[i] = arg.decode('ascii')
            f(*largs)
        except Exception as e:
            logging.error('command raised %s' % e)
            logging.error(traceback.format_exc())
            raise CommandError(command)

    @protected
    def __unhandled__(self, cmd, *args):
        """The default handler for commands. Override this method to
        apply custom behavior (example, printing) unhandled commands.
        """
        logging.debug('unhandled command %s(%s)' % (cmd, args))


class DefaultCommandHandler(CommandHandler):
    """ CommandHandler that provides methods for the normal operation of IRC.
    If you want your bot to properly respond to pings, etc, you should subclass this.
    """

    def ping(self, prefix, server):
        self.client.send('PONG', server)


class DefaultBotCommandHandler(CommandHandler):
    """ default command handler for bots. methods/attributes are made 
    available as commands """

    @protected
    def getVisibleCommands(self, obj=None):
        test = (lambda x: isinstance(x, CommandHandler) or \
                inspect.ismethod(x) or inspect.isfunction(x))
        members = inspect.getmembers(obj or self, test)          
        return [m for m, _ in members 
            if (not m.startswith('_') and 
                not hasattr(getattr(obj, m), 'protected'))]

