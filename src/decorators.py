import traceback
import fnmatch
import socket
from collections import defaultdict

from oyoyo.client import IRCClient
from oyoyo.parse import parse_nick

import botconfig
import src.settings as var
from src.utilities import *
from src import logger
from src.messages import messages

adminlog = logger("audit.log")
errlog = logger("errors.log")

COMMANDS = defaultdict(list)
HOOKS = defaultdict(list)

# Error handler decorators

class handle_error:

    instance = None
    owner = object

    def __new__(cls, func):
        if isinstance(func, cls): # already decorated
            return func

        self = super().__new__(cls)
        self.func = func
        return self

    def __get__(self, instance, owner):
        self.instance = instance
        self.owner = owner
        return self

    def __call__(self, *args, **kwargs):
        try:
            return self.func.__get__(self.instance, self.owner)(*args, **kwargs)
        except Exception:
            traceback.print_exc() # no matter what, we want it to print
            if kwargs.get("cli"): # client
                cli = kwargs["cli"]
            else:
                for cli in args:
                    if isinstance(cli, IRCClient):
                        break
                else:
                    cli = None

            if cli is not None:
                msg = "An error has occurred and has been logged."
                if not botconfig.PASTEBIN_ERRORS or botconfig.CHANNEL != botconfig.DEV_CHANNEL:
                    cli.msg(botconfig.CHANNEL, msg)
                if botconfig.PASTEBIN_ERRORS and botconfig.DEV_CHANNEL:
                    try:
                        with socket.socket() as sock:
                            sock.connect(("termbin.com", 9999))
                            sock.send(traceback.format_exc().encode("utf-8", "replace") + b"\n")
                            url = sock.recv(1024).decode("utf-8")
                    except socket.error:
                        pass
                    else:
                        cli.msg(botconfig.DEV_CHANNEL, " ".join((msg, url)))

class cmd:
    def __init__(self, *cmds, raw_nick=False, admin_only=False, owner_only=False,
                 chan=True, pm=False, playing=False, silenced=False, phases=(), roles=()):

        self.cmds = cmds
        self.raw_nick = raw_nick
        self.admin_only = admin_only
        self.owner_only = owner_only
        self.chan = chan
        self.pm = pm
        self.playing = playing
        self.silenced = silenced
        self.phases = phases
        self.roles = roles
        self.func = None
        self.aftergame = False
        self.name = cmds[0]

        alias = False
        self.aliases = []
        for name in cmds:
            for func in COMMANDS[name]:
                if (func.owner_only != owner_only or
                    func.admin_only != admin_only):
                    raise ValueError("unmatching protection levels for " + func.name)

            COMMANDS[name].append(self)
            if alias:
                self.aliases.append(name)
            alias = True

    def __call__(self, func):
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

        if chan.startswith("#") and chan != botconfig.CHANNEL and not (self.admin_only or self.owner_only):
            if "" in self.cmds:
                return # don't have empty commands triggering in other channels
            for command in self.cmds:
                if command in botconfig.ALLOWED_ALT_CHANNELS_COMMANDS:
                    break
            else:
                return

        if nick in var.USERS and var.USERS[nick]["account"] != "*":
            acc = var.USERS[nick]["account"]
        else:
            acc = None

        if "" in self.cmds:
            return self.func(*largs)

        if self.phases and var.PHASE not in self.phases:
            return

        if self.playing and (nick not in var.list_players() or nick in var.DISCONNECTED):
            if chan == nick:
                pm(cli, nick, messages["player_not_playing"])
            else:
                cli.notice(nick, messages["player_not_playing"])
            return

        if self.silenced and nick in var.SILENCED:
            if chan == nick:
                pm(cli, nick, messages["silenced"])
            else:
                cli.notice(nick, messages["silenced"])
            return

        if self.roles:
            for role in self.roles:
                if nick in var.ROLES[role]:
                    break
            else:
                return

            return self.func(*largs) # don't check restrictions for role commands

        forced_owner_only = False
        if hasattr(botconfig, "OWNERS_ONLY_COMMANDS"):
            for command in self.cmds:
                if command in botconfig.OWNERS_ONLY_COMMANDS:
                    forced_owner_only = True
                    break

        if self.owner_only or forced_owner_only:
            if var.is_owner(nick, ident, host):
                adminlog(chan, rawnick, self.name, rest)
                return self.func(*largs)

            if chan == nick:
                pm(cli, nick, messages["not_owner"])
            else:
                cli.notice(nick, messages["not_owner"])
            return

        if var.is_admin(nick, ident, host):
            if self.admin_only:
                adminlog(chan, rawnick, self.name, rest)
            return self.func(*largs)

        if not var.DISABLE_ACCOUNTS and acc:
            if acc in var.DENY_ACCOUNTS:
                for command in self.cmds:
                    if command in var.DENY_ACCOUNTS[acc]:
                        if chan == nick:
                            pm(cli, nick, messages["invalid_permissions"])
                        else:
                            cli.notice(nick, messages["invalid_permissions"])
                        return

            if acc in var.ALLOW_ACCOUNTS:
                for command in self.cmds:
                    if command in var.ALLOW_ACCOUNTS[acc]:
                        if self.admin_only:
                            adminlog(chan, rawnick, self.name, rest)
                        return self.func(*largs)

        if host:
            for pattern in var.DENY:
                if var.match_hostmask(pattern, nick, ident, host):
                    for command in self.cmds:
                        if command in var.DENY[pattern]:
                            if chan == nick:
                                pm(cli, nick, messages["invalid_permissions"])
                            else:
                                cli.notice(nick, messages["invalid_permissions"])
                            return

            for pattern in var.ALLOW:
                if var.match_hostmask(pattern, nick, ident, host):
                    for command in self.cmds:
                        if command in var.ALLOW[pattern]:
                            if self.admin_only:
                                adminlog(chan, rawnick, self.name, rest)
                            return self.func(*largs)

        if self.admin_only:
            if chan == nick:
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
