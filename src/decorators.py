import traceback
import threading
import string
import random
import json
import re

import urllib.request, urllib.parse

from collections import defaultdict

from oyoyo.client import IRCClient
from oyoyo.parse import parse_nick

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, users, logger, errlog, events
from src.messages import messages

adminlog = logger.logger("audit.log")

COMMANDS = defaultdict(list)
HOOKS = defaultdict(list)

# Error handler decorators and context managers

class _local(threading.local):
    frame_locals = None
    handler = None
    level = 0

_local = _local()

# This is a mapping of stringified tracebacks to (link, uuid) tuples
# That way, we don't have to call in to the website everytime we have
# another error. If you ever need to delete pastes, do the following:
# $ curl -x DELETE https://ptpb.pw/<uuid>

_tracebacks = {}

class chain_exceptions:

    def __init__(self, exc, *, suppress_context=False):
        self.exc = exc
        self.suppress_context = suppress_context

    def __enter__(self):
        return self

    def __exit__(self, exc, value, tb):
        if exc is value is tb is None:
            return False

        value.__context__ = self.exc
        value.__suppress_context__ = self.suppress_context
        self.exc = value
        return True

    @property
    def traceback(self):
        return "".join(traceback.format_exception(type(self.exc), self.exc, self.exc.__traceback__))

class print_traceback:

    def __enter__(self):
        _local.level += 1
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is exc_value is tb is None:
            _local.level -= 1
            return False

        if not issubclass(exc_type, Exception):
            _local.level -= 1
            return False

        if _local.frame_locals is None:
            while tb.tb_next is not None:
                tb = tb.tb_next
            _local.frame_locals = tb.tb_frame.f_locals

        if _local.level > 1:
            _local.level -= 1
            return False # the outermost caller should handle this

        if _local.handler is None:
            _local.handler = chain_exceptions(exc_value)

        variables = ["", None, "Local variables from innermost frame:", ""]

        with _local.handler:
            for name, value in _local.frame_locals.items():
                variables.append("{0} = {1!r}".format(name, value))

        if len(variables) > 4:
            variables.append("\n")
        else:
            variables[2] = "No local variables found in innermost frame."

        variables[1] = _local.handler.traceback

        if not botconfig.PASTEBIN_ERRORS or channels.Main is not channels.Dev:
            channels.Main.send(messages["error_log"])
        if botconfig.PASTEBIN_ERRORS and channels.Dev is not None:
            message = [messages["error_log"]]

            link_uuid = _tracebacks.get("\n".join(variables))
            if link_uuid is None:
                bot_id = re.sub(r"[^A-Za-z0-9-]", "-", users.Bot.nick)
                bot_id = re.sub(r"--+", "-", bot_id).strip("-")

                rand_id = "".join(random.sample(string.ascii_letters + string.digits, 8))

                api_url = "https://ptpb.pw/~{0}-error-{1}".format(bot_id, rand_id)

                data = None
                with _local.handler:
                    req = urllib.request.Request(api_url, urllib.parse.urlencode({
                            "c": "\n".join(variables),  # contents
                        }).encode("utf-8", "replace"))

                    req.add_header("Accept", "application/json")
                    resp = urllib.request.urlopen(req)
                    data = json.loads(resp.read().decode("utf-8"))

                if data is None: # couldn't fetch the link
                    message.append(messages["error_pastebin"])
                    variables[1] = _local.handler.traceback # an error happened; update the stored traceback
                else:
                    link, uuid = _tracebacks["\n".join(variables)] = (data["url"] + "/pytb", data.get("uuid"))
                    message.append(link)
                    if uuid is None: # if there's no uuid, the paste already exists and we don't have it
                        message.append("(Already reported by another instance)")
                    else:
                        message.append("(uuid: {0})".format(uuid))

            else:
                link, uuid = link_uuid
                message.append(link)
                if uuid is None:
                    message.append("(Previously reported)")
                else:
                    message.append("(uuid: {0}-...)".format(uuid[:8]))

            channels.Dev.send(" ".join(message), prefix=botconfig.DEV_PREFIX)

        errlog("\n".join(variables))

        _local.level -= 1
        if not _local.level: # outermost caller; we're done here
            _local.frame_locals = None
            _local.handler = None

        return True # a true return value tells the interpreter to swallow the exception

class handle_error:

    def __new__(cls, func=None, *, instance=None):
        if isinstance(func, cls) and instance is func.instance: # already decorated
            return func

        if isinstance(func, cls):
            func = func.func

        self = super().__new__(cls)
        self.instance = instance
        self.func = func
        return self

    def __get__(self, instance, owner):
        if instance is not self.instance:
            return type(self)(self.func, instance=instance)
        return self

    def __call__(*args, **kwargs):
        self, *args = args
        if self.instance is not None:
            args = [self.instance] + args
        with print_traceback():
            return self.func(*args, **kwargs)

class cmd:
    def __init__(self, *cmds, raw_nick=False, flag=None, owner_only=False,
                 chan=True, pm=False, playing=False, silenced=False,
                 phases=(), roles=(), nicks=None, old_api=True):

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
        self.old_api = old_api # functions using the old API will get (cli, nick, chan, rest) passed in
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
    def caller(self, var, wrapper, message):
        # The wrapper is an object which will know the sender and target
        # It will have methods such as .reply(), taking off the load from the end code
        raise NotImplementedError("The new interface has not been implemented yet")

    @handle_error
    def old_api_caller(self, *args):
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
