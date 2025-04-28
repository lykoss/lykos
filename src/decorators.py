from __future__ import annotations
import functools
import logging
from typing import Callable, Optional, Iterable
from collections import defaultdict

import src
from src.functions import get_players
from src.messages import messages
from src import config, channels, db
from src.users import User
from src.dispatcher import MessageDispatcher
from src.debug import handle_error

COMMANDS: dict[str, list[command]] = defaultdict(list)
HOOKS: dict[str, list[hook]] = defaultdict(list)

class command:
    def __init__(self, cmd: str, *, flag: Optional[str] = None, owner_only: bool = False,
                 chan: bool = True, pm: bool = False, playing: bool = False, silenced: bool = False,
                 phases: Iterable[str] = (), roles: Iterable[str] = (), users: Iterable[User] = None,
                 in_game_only: bool = False, allow_alt: Optional[bool] = None, register: bool = True):

        # the "d" flag indicates it should only be enabled in debug mode
        if flag == "d" and not config.Main.get("debug.enabled"):
            return

        # handle command localizations
        commands = messages.raw("_commands")[cmd]

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
        self.in_game_only = in_game_only
        self.func: Callable[[MessageDispatcher, str], None] = None # type: ignore[assignment]
        self.aftergame = False
        self.name: str = commands[0]
        self.internal_name = cmd
        self.key = "{0}_{1}".format(cmd, id(self))
        self.alt_allowed = allow_alt if allow_alt is not None else bool(flag or owner_only)
        self._disabled = False

        alias = False
        self.aliases = []

        if self.commands.intersection(config.Main.get("gameplay.disable.commands")):
            self._disabled = True
            return # command is disabled, do not add to COMMANDS

        for name in commands:
            for func in COMMANDS[name]:
                if func.owner_only != owner_only or func.flag != flag:
                    raise ValueError("mismatched access levels for {0}".format(func.name))

            if register:
                COMMANDS[name].append(self)
            if alias:
                self.aliases.append(name)
            alias = True

        self._registered = register

        if playing: # Don't restrict to owners or allow in alt channels
            self.owner_only = False
            self.alt_allowed = False

    def __call__(self, func):
        if isinstance(func, command):
            func = func.func
        self.func = func
        self.__doc__ = func.__doc__
        return self

    def register(self):
        if not self._registered and not self._disabled:
            COMMANDS[self.name].append(self)
            for alias in self.aliases:
                COMMANDS[alias].append(self)
            self._registered = True

    def remove(self):
        if self._registered:
            COMMANDS[self.name].remove(self)
            for alias in self.aliases:
                COMMANDS[alias].remove(self)
            self._registered = False

    @handle_error
    def caller(self, wrapper: MessageDispatcher, message: str):
        _ignore_locals_ = True
        if (not self.pm and wrapper.private) or (not self.chan and wrapper.public):
            return # channel or PM command that we don't allow

        if wrapper.public and wrapper.target is not channels.Main and not (self.flag or self.owner_only):
            if "" in self.commands or not self.alt_allowed:
                return # commands not allowed in alt channels

        if "" in self.commands:
            self.func(wrapper, message)
            return

        if self.phases and (wrapper.game_state is None or wrapper.game_state.current_phase not in self.phases):
            return

        if self.in_game_only and (wrapper.game_state is None or not wrapper.game_state.in_game):
            return

        wrapper.source.update_account_data(self.key, functools.partial(self._thunk, wrapper, message))

    @handle_error
    def _thunk(self, wrapper: MessageDispatcher, message: str, user: User):
        _ignore_locals_ = True
        wrapper.source = user
        self._caller(wrapper, message)

    @handle_error
    def _caller(self, wrapper: MessageDispatcher, message: str):
        _ignore_locals_ = True
        var = wrapper.game_state # FIXME
        from src import reaper
        if self.playing and (wrapper.source not in get_players(wrapper.game_state) or wrapper.source in reaper.DISCONNECTED):
            return

        logger = logging.getLogger("command.{}".format(self.name))
        command_log_args = {
            "target": wrapper.target.name,
            "account": wrapper.source.account,
            "rawnick": wrapper.source.rawnick,
            "command": self.name.upper()
        }

        if message:
            command_log_line = "[{target}] {account} ({rawnick}) {command}: {message}"
            command_log_args["message"] = message
        else:
            command_log_line = "[{target}] {account} ({rawnick}) {command}"

        for role in self.roles:
            if wrapper.source in var.roles[role]:
                break
        else:
            if (self.users is not None and wrapper.source not in self.users) or self.roles:
                return

        if self.silenced and src.status.is_silent(var, wrapper.source):
            wrapper.pm(messages["silenced"])
            return

        if self.playing or self.roles or self.users:
            self.func(wrapper, message) # don't check restrictions for game commands
            # Role commands might end the night if it's nighttime
            if var.current_phase == "night":
                from src.wolfgame import chk_nightdone
                chk_nightdone(var)
            return

        if self.owner_only:
            if wrapper.source.is_owner():
                logger.info(command_log_line, command_log_args)
                self.func(wrapper, message)
                return

            wrapper.pm(messages["not_owner"])
            return

        temp = wrapper.source.lower()

        flags = db.FLAGS[temp.account]

        if self.flag and (wrapper.source.is_admin() or wrapper.source.is_owner()):
            logger.info(command_log_line, command_log_args)
            return self.func(wrapper, message)

        denied_commands = db.DENY[temp.account]

        if self.internal_name in denied_commands:
            wrapper.pm(messages["invalid_permissions"])
            return

        if self.flag:
            if self.flag in flags:
                logger.info(command_log_line, command_log_args)
                self.func(wrapper, message)
                return

            wrapper.pm(messages["not_an_admin"])
            return

        self.func(wrapper, message)

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
