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
        return 'No such command "{0}"'.format(".".join(self.cmd))

class ProtectedCommandError(CommandError):
    def __str__(self):
        return 'Command "{0}" is protected'.format(".".join(self.cmd))
        

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
                cmdpart = cmdpart.decode('utf_8')    
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
        logging.debug("processCommand {0}({1})".format(command,
                                                       [arg.decode('utf_8')
                                                        for arg in args
                                                        if isinstance(arg, bytes)]))

        try:
            f = self.get(command)
        except NoSuchCommandError:
            self.__unhandled__(command, *args)
            return

        logging.debug('f {0}'.format(f))
        try:
            largs = list(args)
            for i,arg in enumerate(largs):
                if arg: largs[i] = arg.decode('utf_8')
            f(*largs)
            self.__unhandled__(command, *args)
        except Exception as e:
            logging.error('command raised {0}'.format(e))
            logging.error(traceback.format_exc())
            raise CommandError(command)

    @protected
    def __unhandled__(self, cmd, *args):
        """The default handler for commands. Override this method to
        apply custom behavior (example, printing) unhandled commands.
        """
        logging.debug('Unhandled command {0}({1})'.format(cmd, [arg.decode('utf_8')
                                                                for arg in args
                                                                if isinstance(arg, bytes)]))
