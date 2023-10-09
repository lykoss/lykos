from __future__ import annotations

import time
from enum import Enum
from typing import Optional, TYPE_CHECKING
from collections import defaultdict
import logging

from src.context import IRCContext, Features, lower
from src.events import Event, EventListener
from src import users, config
from src.debug import CheckedSet, CheckedDict
from src.users import User, BotUser

if TYPE_CHECKING:
    # gamestate depends on channels; can't turn this into a top-level import
    from src.gamestate import GameState

Main: Channel = None # type: ignore[assignment]
Dummy: Channel = None # type: ignore[assignment]

_channels: CheckedDict[str, Channel] = CheckedDict("channels._channels")

class _States(Enum):
    NotJoined = "not yet joined"
    PendingJoin = "pending join"
    Joined = "joined"
    PendingLeave = "pending leave"
    Left = "left channel"

    Cleared = "cleared"

# This is used to tell if this is a fake channel or not. If this
# function returns a true value, then it's a fake channel. This is
# useful for testing, where we might want the users in fake channels.
def predicate(name):
    return not name.startswith(tuple(Features.CHANTYPES))

def _normalize(x: str):
    return lower(x.lstrip("".join(Features.STATUSMSG)))

def get(name: str, *, allow_none: bool = False) -> Optional[Channel]:
    try:
        return _channels[_normalize(name)]
    except KeyError:
        if allow_none:
            return None
        raise

def add(name, cli, key="", prefix=""):
    """Add and return a new channel, or an existing one if it exists."""

    # We use add() in a bunch of places where the channel probably (but
    # not surely) already exists. If it does, obviously we want to use
    # that one. However, if the client is *not* the same, that means we
    # would be trying to send something from one connection over to
    # another one (or some other weird stuff like that). Instead of
    # jumping through hoops, we just disallow it here.

    if _normalize(name) in _channels:
        if cli is not _channels[_normalize(name)].client:
            raise RuntimeError("different IRC client for channel {0}".format(name))
        return _channels[_normalize(name)]

    cls = Channel
    if predicate(name):
        cls = FakeChannel

    chan = _channels[_normalize(name)] = cls(name, cli, prefix=prefix)
    chan.join(key=key)
    return chan

def exists(name):
    """Return True if a channel by the name exists, False otherwise."""
    return _normalize(name) in _channels

def channels():
    """Iterate over all the current channels."""
    yield from _channels.values()

def _chan_join(evt, channel: Channel, user: User):
    if isinstance(user, BotUser):
        channel.state = _States.Joined

EventListener(_chan_join).install("chan_join")

class Channel(IRCContext):

    is_channel = True

    def __init__(self, name, client, prefix=""):
        super().__init__(name, client, prefix=prefix)
        self.users: CheckedSet[User] = CheckedSet("channels.Channel.users")
        self.modes: dict[str, set[User]] = {}
        self.old_modes = defaultdict(set)
        self.timestamp = None
        self.state = _States.NotJoined
        self.game_state: Optional[GameState] = None
        self._pending = []
        self._key = ""

    def __del__(self):
        self.users.clear()
        self.modes.clear()

    def __str__(self):
        return "{self.__class__.__name__}: {self.name} ({self.state.value})".format(self=self)

    def __repr__(self):
        return "{self.__class__.__name__}({self.name!r})".format(self=self)

    def __format__(self, format_spec):
        if format_spec == "#":
            return self.name
        elif format_spec in ("for_tb", "for_tb_verbose"):
            channel_data_level = config.Main.get("telemetry.errors.channel_data_level")
            if channel_data_level == 0:
                if self is Main:
                    value = "Main"
                elif self is Dummy:
                    value = "Dummy"
                else:
                    value = format(id(self), "x")
                return "{self.__class__.__name__}({0})".format(value, self=self)
            else:
                return repr(self)

        return super().__format__(format_spec)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self._compare(other, __class__, "name", "key", "client", "state", "modes", "timestamp")

    @property
    def key(self):
        return self._key

    def queue(self, name, params, args):
        if self._pending is None:
            Event(name, params).dispatch(*args)
        else:
            self._pending.append((name, params, args))

    def dispatch_queue(self):
        if self._pending is not None:
            for name, params, args in self._pending:
                Event(name, params).dispatch(*args)
            self._pending = None

    def join(self, key=""):
        if self.state in (_States.NotJoined, _States.Left):
            if not key:
                key = self.key
            self.state = _States.PendingJoin
            self.client.send("JOIN {0} :{1}".format(self.name, key))

    def part(self, message=""):
        if self.state is _States.Joined:
            self.state = _States.PendingLeave
            self.client.send("PART {0} :{1}".format(self.name, message))

    def kick(self, target, message=""):
        if self.state is _States.Joined:
            self.client.send("KICK {0} {1} :{2}".format(self.name, target, message))

    def mode(self, *changes):
        """Perform a mode change on the channel.

        Usage:

            chan.mode() # Will get back the modes on the channel
            chan.mode("b") # Will get the banlist back
            chan.mode("-m")
            chan.mode(["-v", "woffle"], ["+o", "Vgr"])
            chan.mode("-m", ("+v", "jacob1"), ("-o", "nyuszika7h"))

        This performs both single and complex mode changes.

        Note: Not giving a prefix with the mode is the same as giving a
        '+' prefix. For instance, the following are identical:

            chan.mode(("+o", "woffle"))
            chan.mode(("o", "woffle"))

        """

        if not changes: # bare call; get channel modes
            self.client.send("MODE", self.name)
            return

        max_modes = Features["MODES"]
        params = []
        for change in changes:
            if isinstance(change, str):
                change = (change, None)
            mode, target = change
            if len(mode) < 2:
                mode = "+" + mode
            params.append((mode, target))
        params.sort(key=lambda x: x[0][0]) # sort by prefix

        while params:
            cur, params = params[:max_modes], params[max_modes:]
            modes, targets = zip(*cur)
            prefix = ""
            final = []
            for mode in modes:
                if mode[0] == prefix:
                    mode = mode[1:]
                elif mode.startswith(("+", "-")):
                    prefix = mode[0]

                final.append(mode)

            for target in targets:
                if target is not None: # target will be None if the mode is parameter-less
                    final.append(" ")
                    final.append("{0}".format(target))

            self.client.send("MODE", self.name, "".join(final))

    def update_modes(self, actor, mode, targets):
        """Update the channel's mode registry with the new modes.

        This is called whenever a MODE event is received. All of the
        modes are kept up-to-date in the channel, even if we don't need
        it. For instance, banlists are updated properly when the bot
        receives them. We don't need all the mode information, but it's
        better to have everything stored than only some parts.

        """

        set_time = int(time.time()) # for list modes timestamp
        list_modes, all_set, only_set, no_set = Features.CHANMODES
        status_modes = Features.PREFIX.values()
        all_modes = list_modes + all_set + only_set + no_set + "".join(status_modes)
        if self.state is not _States.Joined: # not joined, modes won't have the value
            no_set += all_set + only_set
            only_set = ""
            all_set = ""

        i = 0
        prefix = None
        for c in mode:
            if c in ("+", "-"):
                prefix = c
                continue
            elif c not in all_modes:
                # some broken ircds have modes without telling us about them in ISUPPORT
                # ignore such modes but emit a warning
                transport_name = config.Main.get("transports[0].name")
                logger = logging.getLogger("transport.{}".format(transport_name))
                logger.warning("Broken ircd detected: unrecognized channel mode +{0}", c)
                continue

            if prefix == "+":
                if c in status_modes: # op/voice status; keep it here and update the user's registry too
                    if c not in self.modes:
                        self.modes[c] = set()
                    user = users.get(targets[i], allow_bot=True)
                    self.modes[c].add(user)
                    user.channels[self].add(c)
                    if user in self.old_modes:
                        self.old_modes[user].discard(c)
                    i += 1

                elif c in list_modes: # stuff like bans, quiets, and ban and invite exempts
                    if c not in self.modes:
                        self.modes[c] = {}
                    self.modes[c][targets[i]] = ((actor.rawnick if actor is not None else None), set_time)
                    i += 1

                else:
                    if c in no_set: # everything else; e.g. +m, +i, etc.
                        targ = None
                    else: # +f, +l, +j, +k
                        targ = targets[i]
                        i += 1
                    if c in only_set and targ.isdigit(): # +l/+j
                        targ = int(targ)
                    self.modes[c] = targ

            elif prefix == "-":
                if c in status_modes:
                    if c in self.modes:
                        user = users.get(targets[i], allow_bot=True)
                        self.modes[c].discard(user)
                        user.channels[self].discard(c)
                        if not self.modes[c]:
                            del self.modes[c]
                    i += 1

                elif c in list_modes:
                    if c in self.modes:
                        self.modes[c].pop(targets[i], None)
                        if not self.modes[c]:
                            del self.modes[c]
                    i += 1

                else:
                    if c in all_set:
                        i += 1 # -k needs a target, but we don't care about it
                    del self.modes[c]

        if "k" in mode:
            self._key = self.modes.get("k", "")

    def remove_user(self, user):
        self.users.remove(user)
        for mode in Features["PREFIX"].values():
            if mode in self.modes:
                self.modes[mode].discard(user)
                if not self.modes[mode]:
                    del self.modes[mode]
        del user.channels[self]
        if not user.channels: # Only fire if the user left all channels
            event = Event("cleanup_user", {})
            event.dispatch(self.game_state, user)

    def clear(self):
        for user in self.users:
            del user.channels[self]
        self.users.clear()
        self.modes.clear()
        self.state = _States.Cleared
        self.timestamp = None
        del _channels[lower(self.name)]

class FakeChannel(Channel):

    is_fake = True

    def join(self, key=""):
        self.state = _States.Joined

    def part(self, message=""):
        self.state = _States.Left

    def mode(self, *changes):
        if not changes:
            return

        modes = []
        targets = []

        for change in changes:
            if isinstance(change, str):
                if change.startswith(("+", "-")): # we're probably asking for the list modes otherwise
                    modes.append(change)
            else:
                mode, target = change
                modes.append(mode)
                if target is not None:
                    targets.append(target)

        self.update_modes(users.Bot, "".join(modes), targets)
