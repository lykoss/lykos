import fnmatch
import socket
import traceback
import threading
import types
import sys
from collections import defaultdict

from oyoyo.client import IRCClient
from oyoyo.parse import parse_nick

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, logger, errlog, events
from src.messages import messages

adminlog = logger.logger("audit.log")

COMMANDS = defaultdict(list)
HOOKS = defaultdict(list)

# Error handler decorators

_do_nothing = lambda: None

class _local(threading.local):
    level = 0
    frame_locals = None

_local = _local()

class handle_error:

    def __new__(cls, func):
        if isinstance(func, cls): # already decorated
            return func

        self = super().__new__(cls)
        self.func = func
        return self

    def __get__(self, instance, owner):
        if instance is not None:
            return types.MethodType(self, instance)
        return self

    def __call__(self, *args, **kwargs):
        fn = _do_nothing
        _local.level += 1
        try:
            return self.func(*args, **kwargs)
        except Exception:
            if _local.frame_locals is None:
                exc_type, exc_value, tb = sys.exc_info()
                while tb.tb_next is not None:
                    tb = tb.tb_next
                _local.frame_locals = tb.tb_frame.f_locals

            if _local.level > 1:
                raise # the outermost caller should handle this

            fn = lambda: errlog("\n{0}\n\n".format(data))
            data = traceback.format_exc()
            variables = ["\nLocal variables from innermost frame:"]
            for name, value in _local.frame_locals.items():
                variables.append("{0} = {1!r}".format(name, value))

            data += "\n".join(variables)

            if not botconfig.PASTEBIN_ERRORS or channels.Main is not channels.Dev:
                channels.Main.send(messages["error_log"])
            if botconfig.PASTEBIN_ERRORS and channels.Dev is not None:
                pastebin_tb(channels.Dev, messages["error_log"], data, prefix=botconfig.DEV_PREFIX)

        finally:
            fn()
            _local.level -= 1
            if not _local.level: # outermost caller; we're done here
                _local.frame_locals = None

class cmd:
    def __init__(self, *cmds, raw_nick=False, flag=None, owner_only=False,
                 chan=True, pm=False, playing=False, silenced=False,
                 phases=(), roles=(), nicks=None):

        self.cmds = cmds
        self.raw_nick = raw_nick
        self.flag = flag
        self.owner_only = owner_only
        self.chan = chan
        self.pm = pm
        self.playing = playing
        self.silenced = silenced
        self.phases = phases
        self.roles = roles
        self.nicks = nicks # iterable of nicks that can use the command at any time (should be a mutable object)
        self.func = None
        self.aftergame = False
        self.name = cmds[0]

        alias = False
        self.aliases = []
        for name in cmds:
            for func in COMMANDS[name]:
                if (func.owner_only != owner_only or
                    func.flag != flag):
                    raise ValueError("unmatching protection levels for " + func.name)

            COMMANDS[name].append(self)
            if alias:
                self.aliases.append(name)
            alias = True

    def __call__(self, func):
        if isinstance(func, cmd):
            func = func.func
        self.func = func
        self.__doc__ = self.func.__doc__
        return self

    @handle_error
    def caller(self, *args):
        largs = list(args)

        cli, rawnick, chan, rest = largs
        nick, mode, ident, host = parse_nick(rawnick)

        if ident is None:
            ident = ""

        if host is None:
            host = ""

        if not self.raw_nick:
            largs[1] = nick

        if not self.pm and chan == nick:
            return # PM command, not allowed

        if not self.chan and chan != nick:
            return # channel command, not allowed

        if chan.startswith("#") and chan != botconfig.CHANNEL and not (self.flag or self.owner_only):
            if "" in self.cmds:
                return # don't have empty commands triggering in other channels
            for command in self.cmds:
                if command in botconfig.ALLOWED_ALT_CHANNELS_COMMANDS:
                    break
            else:
                return

        if nick not in var.USERS and not is_fake_nick(nick):
            return

        if nick in var.USERS and var.USERS[nick]["account"] != "*":
            acc = irc_lower(var.USERS[nick]["account"])
        else:
            acc = None
        ident = irc_lower(ident)
        host = host.lower()
        hostmask = nick + "!" + ident + "@" + host

        if "" in self.cmds:
            return self.func(*largs)

        if self.phases and var.PHASE not in self.phases:
            return

        if self.playing and (nick not in list_players() or nick in var.DISCONNECTED):
            return

        for role in self.roles:
            if nick in var.ROLES[role]:
                break
        else:
            if (self.nicks is not None and nick not in self.nicks) or self.roles:
                return

        if self.silenced and nick in var.SILENCED:
            if chan == nick:
                pm(cli, nick, messages["silenced"])
            else:
                cli.notice(nick, messages["silenced"])
            return

        if self.roles or (self.nicks is not None and nick in self.nicks):
            return self.func(*largs) # don't check restrictions for role commands

        forced_owner_only = False
        if hasattr(botconfig, "OWNERS_ONLY_COMMANDS"):
            for command in self.cmds:
                if command in botconfig.OWNERS_ONLY_COMMANDS:
                    forced_owner_only = True
                    break

        owner = is_owner(nick, ident, host)
        if self.owner_only or forced_owner_only:
            if owner:
                adminlog(chan, rawnick, self.name, rest)
                return self.func(*largs)

            if chan == nick:
                pm(cli, nick, messages["not_owner"])
            else:
                cli.notice(nick, messages["not_owner"])
            return

        flags = var.FLAGS[hostmask] + var.FLAGS_ACCS[acc]
        admin = is_admin(nick, ident, host)
        if self.flag and (admin or owner):
            adminlog(chan, rawnick, self.name, rest)
            return self.func(*largs)

        denied_cmds = var.DENY[hostmask] | var.DENY_ACCS[acc]
        for command in self.cmds:
            if command in denied_cmds:
                if chan == nick:
                    pm(cli, nick, messages["invalid_permissions"])
                else:
                    cli.notice(nick, messages["invalid_permissions"])
                return

        if self.flag:
            if self.flag in flags:
                adminlog(chan, rawnick, self.name, rest)
                return self.func(*largs)
            elif chan == nick:
                pm(cli, nick, messages["not_an_admin"])
            else:
                cli.notice(nick, messages["not_an_admin"])
            return

        return self.func(*largs)

class hook:
    def __init__(self, name, hookid=-1):
        self.name = name
        self.hookid = hookid
        self.func = None

        HOOKS[name].append(self)

    def __call__(self, func):
        if isinstance(func, hook):
            self.func = func.func
        else:
            self.func = func
        self.__doc__ = self.func.__doc__
        return self

    @handle_error
    def caller(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    @staticmethod
    def unhook(hookid):
        for each in list(HOOKS):
            for inner in list(HOOKS[each]):
                if inner.hookid == hookid:
                    HOOKS[each].remove(inner)
            if not HOOKS[each]:
                del HOOKS[each]

class event_listener:
    def __init__(self, event, priority=5):
        self.event = event
        self.priority = priority
        self.func = None

    def __call__(self, *args, **kwargs):
        if self.func is None:
            func = args[0]
            if isinstance(func, event_listener):
                func = func.func
            self.func = handle_error(func)
            events.add_listener(self.event, self.func, self.priority)
            self.__doc__ = self.func.__doc__
            return self
        else:
            return self.func(*args, **kwargs)

    def remove(self):
        events.remove_listener(self.event, self.func, self.priority)

# vim: set sw=4 expandtab:
