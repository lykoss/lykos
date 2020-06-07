import functools
import logging
from typing import Optional, Iterable, Callable

from collections import defaultdict

import src
from src.functions import get_players
from src.messages import messages
from src import config, channels
from src.users import User
from src.dispatcher import MessageDispatcher
from src.debug import handle_error

COMMANDS = defaultdict(list)
HOOKS = defaultdict(list)

class command:
    def __init__(self, command: str, *, flag: Optional[str] = None, owner_only: bool = False,
                 chan: bool = True, pm: bool = False, playing: bool = False, silenced: bool = False,
                 phases: Iterable[str] = (), roles: Iterable[str] = (), users: Iterable[User] = None,
                 allow_alt: Optional[bool] = None):

        # the "d" flag indicates it should only be enabled in debug mode
        if flag == "d" and not config.Main.get("debug.enabled"):
            return

        # handle command localizations
        commands = messages.raw("_commands")[command]

        self.commands = frozenset(commands)
        self.flag = flag
        self.owner_only = owner_only
        self.chan = chan
        self.pm = pm
        self.playing = playing
        self.silenced = silenced
        self.phases = phases
        self.roles = roles
        self.users = users # iterable of users that can use the command at any time (should be a mutable object)
        self.func = None
        self.aftergame = False
        self.name = commands[0]
        self.key = command
        if allow_alt is not None:
            self.alt_allowed = allow_alt
        else:
            self.alt_allowed = bool(flag or owner_only or not phases)

        alias = False
        self.aliases = []

        if self.commands.intersection(config.Main.get("gameplay.disable.commands")):
            return # command is disabled, do not add to COMMANDS

        for name in commands:
            for func in COMMANDS[name]:
                if func.owner_only != owner_only or func.flag != flag:
                    raise ValueError("mismatched access levels for {0}".format(func.name))

            COMMANDS[name].append(self)
            if alias:
                self.aliases.append(name)
            alias = True

        if playing: # Don't restrict to owners or allow in alt channels
            self.owner_only = False
            self.alt_allowed = False

    def __call__(self, func):
        if isinstance(func, command):
            func = func.func
        self.func = func
        self.__doc__ = func.__doc__
        return self

    @handle_error
    def caller(self, var, wrapper: MessageDispatcher, message: str):
        _ignore_locals_ = True
        if (not self.pm and wrapper.private) or (not self.chan and wrapper.public):
            return # channel or PM command that we don't allow

        if wrapper.public and wrapper.target is not channels.Main and not (self.flag or self.owner_only):
            if "" in self.commands or not self.alt_allowed:
                return # commands not allowed in alt channels

        if "" in self.commands:
            self.func(var, wrapper, message)
            return

        if self.phases and var.PHASE not in self.phases:
            return

        wrapper.source.update_account_data(self.key, functools.partial(self._thunk, var, wrapper, message))

    @handle_error
    def _thunk(self, var, wrapper: MessageDispatcher, message: str, user: User):
        _ignore_locals_ = True
        wrapper.source = user
        self._caller(var, wrapper, message)

    @handle_error
    def _caller(self, var, wrapper: MessageDispatcher, message: str):
        _ignore_locals_ = True
        if self.playing and (wrapper.source not in get_players() or wrapper.source in var.DISCONNECTED):
            return

        logger = logging.getLogger("command.{}".format(self.key))

        for role in self.roles:
            if wrapper.source in var.ROLES[role]:
                break
        else:
            if (self.users is not None and wrapper.source not in self.users) or self.roles:
                return

        if self.silenced and src.status.is_silent(var, wrapper.source):
            wrapper.pm(messages["silenced"])
            return

        if self.playing or self.roles or self.users:
            self.func(var, wrapper, message) # don't check restrictions for game commands
            # Role commands might end the night if it's nighttime
            if var.PHASE == "night":
                from src.wolfgame import chk_nightdone
                chk_nightdone()
            return

        if self.owner_only:
            if wrapper.source.is_owner():
                logger.info("{0} {1} {2} {3}", wrapper.target.name, wrapper.source.rawnick, self.name, message)
                self.func(var, wrapper, message)
                return

            wrapper.pm(messages["not_owner"])
            return

        temp = wrapper.source.lower()

        flags = var.FLAGS_ACCS[temp.account] # TODO: add flags handling to User

        if self.flag and (wrapper.source.is_admin() or wrapper.source.is_owner()):
            logger.info("{0} {1} {2} {3}", wrapper.target.name, wrapper.source.rawnick, self.name, message)
            return self.func(var, wrapper, message)

        denied_commands = var.DENY_ACCS[temp.account] # TODO: add denied commands handling to User

        if self.commands & denied_commands:
            wrapper.pm(messages["invalid_permissions"])
            return

        if self.flag:
            if self.flag in flags:
                logger.info("{0} {1} {2} {3}", wrapper.target.name, wrapper.source.rawnick, self.name, message)
                self.func(var, wrapper, message)
                return

            wrapper.pm(messages["not_an_admin"])
            return

        self.func(var, wrapper, message)

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
        _ignore_locals_ = True
        return self.func(*args, **kwargs)

    @staticmethod
    def unhook(hookid):
        for each in list(HOOKS):
            for inner in list(HOOKS[each]):
                if inner.hookid == hookid:
                    HOOKS[each].remove(inner)
            if not HOOKS[each]:
                del HOOKS[each]
