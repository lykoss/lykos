import time

from enum import Enum

from src.context import IRCContext, Features, lower
from src.events import Event
from src import settings as var
from src import users

Main = None # main channel
Dummy = None # fake channel
Dev = None # dev channel

_channels = {}

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
    return not name.startswith(tuple(Features["CHANTYPES"]))

def get(name, *, allow_none=False):
    try:
        return _channels[lower(name)]
    except KeyError:
        if allow_none:
            return None
        raise

def add(name, cli, key=""):
    """Add and return a new channel, or an existing one if it exists."""

    # We use add() in a bunch of places where the channel probably (but
    # not surely) already exists. If it does, obviously we want to use
    # that one. However, if the client is *not* the same, that means we
    # would be trying to send something from one connection over to
    # another one (or some other weird stuff like that). Instead of
    # jumping through hoops, we just disallow it here.

    if lower(name) in _channels:
        if cli is not _channels[lower(name)].client:
            raise RuntimeError("different IRC client for channel {0}".format(name))
        return _channels[lower(name)]

    cls = Channel
    if predicate(name):
        cls = FakeChannel

    chan = _channels[lower(name)] = cls(name, cli)
    chan._key = key
    chan.join()
    return chan

def exists(name):
    """Return True if a channel by the name exists, False otherwise."""
    return lower(name) in _channels

def channels():
    """Iterate over all the current channels."""
    yield from _channels.values()

class Channel(IRCContext):

    is_channel = True

    def __init__(self, name, client):
        super().__init__(name, client)
        self.users = set()
        self.modes = {}
        self.timestamp = None
        self.state = _States.NotJoined
        self._pending = []

    def __del__(self):
        self.users.clear()
        self.modes.clear()
        self.state = None
        self.client = None
        self.timestamp = None

    def __str__(self):
        return "{self.__class__.__name__}: {self.name} ({self.state.value})".format(self=self)

    def __repr__(self):
        return "{self.__class__.__name__}({self.name!r})".format(self=self)

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

    def join(self, key=None):
        if self.state in (_States.NotJoined, _States.Left):
            if key is None:
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
        list_modes, all_set, only_set, no_set = Features["CHANMODES"]
        status_modes = Features["PREFIX"].values()

        i = 0
        for c in mode:
            if c in ("+", "-"):
                prefix = c
                continue

            if prefix == "+":
                if c in status_modes: # op/voice status; keep it here and update the user's registry too
                    if c not in self.modes:
                        self.modes[c] = set()
                    user = users._get(targets[i], allow_bot=True) # FIXME
                    self.modes[c].add(user)
                    user.channels[self].add(c)
                    if user in var.OLD_MODES:
                        var.OLD_MODES[user].discard(c)
                    i += 1

                elif c in list_modes: # stuff like bans, quiets, and ban and invite exempts
                    if c not in self.modes:
                        self.modes[c] = {}
                    self.modes[c][targets[i]] = (actor.rawnick, set_time)
                    i += 1

                else:
                    if c in no_set: # everything else; e.g. +m, +i, +f, etc.
                        targ = None
                    else:
                        targ = targets[i]
                        i += 1
                    if c in only_set and targ.isdigit(): # +l/+j
                        targ = int(targ)
                    self.modes[c] = targ

            else:
                if c in status_modes:
                    if c in self.modes:
                        user = users._get(targets[i], allow_bot=True) # FIXME
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
        if len(user.channels) == 0:
            event = Event("cleanup_user", {})
            event.dispatch(var, user)

    def _clear(self):
        for user in self.users:
            del user.channels[self]
        self.users.clear()
        self.modes.clear()
        self.state = _States.Cleared
        self.timestamp = None
        del _channels[self.name]

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

        self.update_modes(users.Bot.rawnick, "".join(modes), targets)
