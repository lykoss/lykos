import fnmatch
import time
import re
from typing import Callable, Optional, Set

from src.context import IRCContext, Features, lower, equals
from src import settings as var
from src import db
from src.events import EventListener
from src.debug import CheckedDict, CheckedSet
from src.match import Match

import botconfig

__all__ = ["Bot", "predicate", "get", "add", "users", "disconnected", "complete_match",
           "parse_rawnick", "parse_rawnick_as_dict", "User", "FakeUser", "BotUser"]

Bot = None # bot instance

_users = CheckedSet("users._users") # type: CheckedSet[User]
_ghosts = CheckedSet("users._ghosts") # type: CheckedSet[User]
_pending_account_updates = CheckedDict("users._pending_account_updates") # type: CheckedDict[User, CheckedDict[str, Callable]]

_arg_msg = "(nick={0!r}, ident={1!r}, host={2!r}, account={3!r}, allow_bot={4})"

# This is used to tell if this is a fake nick or not. If this function
# returns a true value, then it's a fake nick. This is useful for
# testing, where we might want everyone to be fake nicks.
predicate = re.compile(r"^[0-9]+$").search

def get(nick=None, ident=None, host=None, account=None, *, allow_multiple=False, allow_none=False, allow_bot=False, allow_ghosts=False):
    """Return the matching user(s) from the user list.

    :param nick: Nickname or raw nick (nick!ident@host) to match.
        If a raw nick is passed, the `ident` and `host` args must be None.
    :param ident: Ident to match.
    :param host: Host to match.
    :param account: Account to match.
    :param allow_multiple: Allow multiple matches, returning a list (even if only one match).
    :param allow_none: Allow no matches, returning None if nothing found. Otherwise raises KeyError.
    :param allow_bot: Allow the BotUser to be matched and returned.
    :param allow_ghosts: Allow disconnected users to be matched and returned.
    :returns: The matched user(s), if any.
    :raises KeyError: If no users match and allow_none is False.
    :raises ValueError: If multiple users match and allow_multiple is False.
    """

    if ident is None and host is None and nick is not None:
        nick, ident, host = parse_rawnick(nick)

    sentinel = object()

    temp = User(sentinel, nick, ident, host, account)
    if temp.client is not sentinel:  # actual client
        return [temp] if allow_multiple else temp

    potential = []
    users = set(_users)
    if not allow_ghosts:
        users.difference_update(_ghosts)
    if allow_bot:
        try:
            users.add(Bot)
        except ValueError:
            pass # Bot may not be hashable in early init; this is fine and User.__new__ handles this gracefully

    for user in users:
        if user.partial_match(temp):
            potential.append(user)

    if allow_multiple:
        return potential

    if len(potential) == 1:
        return potential[0]

    if len(potential) > 1:
        raise ValueError("More than one user matches: " +
              _arg_msg.format(nick, ident, host, account, allow_bot))

    if not allow_none:
        raise KeyError(_arg_msg.format(nick, ident, host, account, allow_bot))

    return None

def add(cli, *, nick, ident=None, host=None, account=None):
    """Create a new user, add it to the user list and return it.

    This function takes up to 4 keyword-only arguments (and one positional
    argument, cli): nick, ident, host, and account.
    With the exception of the first one, any parameter can be omitted.

    """

    if ident is None and host is None and nick is not None:
        nick, ident, host = parse_rawnick(nick)

    cls = User
    if predicate(nick):
        cls = FakeUser

    new = cls(cli, nick, ident, host, account)

    if new is not Bot:
        try:
            hash(new)
        except ValueError:
            pass
        else:
            _users.add(new)

    return new

def users():
    """Iterate over the users in the registry."""
    yield from _users

def disconnected():
    """Iterate over the users who are in-game but disconnected."""
    yield from _ghosts

def complete_match(pattern: str, scope=None):
    """ Find a user or users who match the given pattern.

    :param pattern: Pattern to match on. The format is "[nick][:account]",
        with [] denoting an optional field. Exact matches are tried, and then
        prefix matches (stripping special characters as needed). If both a nick
        and an account are specified, both must match.
    :param Optional[Iterable[User]] scope: Users to match pattern against. If None,
        search against all users.
    :returns: A Match object describing whether or not the match succeeded.
    :rtype: Match[User]
    """
    if scope is None:
        scope = _users
    matches = []
    nick_search, _, acct_search = lower(pattern).partition(":")
    if not nick_search and not acct_search:
        return Match([])

    direct_match = False
    for user in scope:
        nick = lower(user.nick)
        stripped_nick = nick.lstrip("[{\\^_`|}]")
        if nick_search:
            if nick == nick_search:
                if not direct_match:
                    matches.clear()
                    direct_match = True
                matches.append(user)
            elif not direct_match and (nick.startswith(nick_search) or stripped_nick.startswith(nick_search)):
                matches.append(user)
        else:
            matches.append(user)

    if acct_search:
        scope = list(matches)
        matches.clear()
        direct_match = False
        for user in scope:
            if not user.account:
                continue # fakes don't have accounts, so this search won't be able to find them
            acct = lower(user.account)
            stripped_acct = acct.lstrip("[{\\^_`|}]")
            if acct == acct_search:
                if not direct_match:
                    matches.clear()
                    direct_match = True
                matches.append(user)
            elif not direct_match and (acct.startswith(acct_search) or stripped_acct.startswith(acct_search)):
                matches.append(user)

    return Match(matches)

_raw_nick_pattern = re.compile(r"^(?P<nick>.+?)(?:!(?P<ident>.+?)@(?P<host>.+))?$")

def parse_rawnick(rawnick, *, default=None):
    """Return a tuple of (nick, ident, host) from rawnick."""

    return _raw_nick_pattern.search(rawnick).groups(default)

def parse_rawnick_as_dict(rawnick, *, default=None):
    """Return a dict of {"nick": nick, "ident": ident, "host": host}."""

    return _raw_nick_pattern.search(rawnick).groupdict(default)

def _cleanup_user(evt, var, user):
    """Removes a user from our global tracking set once it has left all channels."""
    if var.PHASE in var.GAME_PHASES and user in var.ALL_PLAYERS:
        _ghosts.add(user)
    else:
        _users.discard(user)

def _reset(evt, var):
    """Cleans up users that left during game during game end."""
    for user in _ghosts:
        if not user.channels:
            _users.discard(user)
    _ghosts.clear()

def _update_account(evt, user):
    """Updates account data of a user for networks which don't support certain features."""
    from src.decorators import handle_error
    user.account_timestamp = time.time()
    if user in _pending_account_updates:
        updates = list(_pending_account_updates[user].items())
        _pending_account_updates[user].clear()
        for command, callback in updates:
            # handle_error swallows exceptions so that a callback raising an exception
            # does not prevent other registered callbacks from running
            handle_error(callback)()

# Can't use @event_listener decorator since src/decorators.py imports us
# (meaning decorator isn't defined at the point in time we are run)
EventListener(_cleanup_user).install("cleanup_user")
EventListener(_reset).install("reset")
EventListener(_update_account).install("who_end")

class User(IRCContext):

    is_user = True

    def __new__(cls, cli, nick, ident, host, account):
        self = super().__new__(cls)
        super(__class__, self).__init__(nick, cli)

        self._ident = ident
        self._host = host
        self._account = account
        self.channels = CheckedDict("users.User.channels")
        self.timestamp = time.time()
        self.sets = []
        self.lists = []
        self.dict_keys = []
        self.dict_values = []
        self.account_timestamp = time.time()

        if Bot is not None and Bot.nick.rstrip("_") == nick.rstrip("_") and None in {Bot.ident, Bot.host}:
            # Bot ident/host being None means that this user isn't hashable, so it cannot be in any containers
            # which store by hash. As such, mutating the properties is safe.
            self = Bot
            self.name = nick
            if ident is not None:
                self._ident = ident
            if host is not None:
                self._host = host
            self._account = account
            self.timestamp = time.time()
            self.account_timestamp = time.time()

        elif (cls.__name__ == "User" and Bot is not None
              and Bot.nick == nick and ident is not None and host is not None
              and Bot.ident != ident and Bot.host == host and Bot.account == account):
            # Messages sent in early init may give us an incorrect ident (such as because we're waiting for
            # a response from identd, or there is some *line which overrides the ident for the bot).
            # Since Bot.ident attempts to create a new BotUser, we guard against recursion by only following this
            # branch if we're constructing a top-level User object (such as via users.get)
            Bot.ident = ident
            self = Bot

        elif nick is not None and ident is not None and host is not None:
            users = set(_users)
            users.add(Bot)
            if self in users:
                for user in users:
                    if self == user:
                        self = user
                        break

        else:
            # This takes a different code path because of slightly different
            # conditions; in the above case, the ident and host are both known,
            # and so the instance is hashable. Being hashable, it can be checked
            # for set containment, and exactly one instance in that set will be
            # equal (since the hash is based off of the ident and host, and the
            # comparisons check for all those two attributes among others, two
            # instances cannot possibly be equal while having a different hash).
            #
            # In this case, however, at least the ident or the host is missing,
            # and so the hash cannot be calculated. This means that two instances
            # may compare equal and hash to different values (since only non-None
            # attributes are compared), so we need to run through the entire set
            # no matter what to make sure that one - and only one - instance in
            # the set compares equal with the new one. We can't know in advance
            # whether or not there is an instance that compares equal to this one
            # in the set, or if multiple instances are going to compare equal to
            # this one.
            #
            # The code paths, while similar in functionality, fulfill two distinct
            # purposes; the first path is usually for when new users are created
            # from a WHO reply, with all the information. This is the most common
            # case. This path, on the other hand, is for the less common cases,
            # where only the nick is known (for example, a KICK target), and where
            # the user may or may not already exist. In that case, it's easier and
            # better to just try to create a new user, which this code can then
            # implicitly replace with the equivalent user (instead of trying to get
            # an existing user or creating a new one if that fails). This is also
            # used as a short-circuit for get().
            #
            # Please don't merge these two code paths for the sake of simplicity,
            # and instead opt for the sake of clarity that this separation provides.

            potential = None
            users = set(_users)
            users.add(Bot)
            for user in users:
                if self.partial_match(user):
                    if potential is None:
                        potential = user
                    else:
                        break # too many possibilities
            else:
                if potential is not None:
                    self = potential

        return self

    def __init__(self, *args, **kwargs):
        pass # everything that needed to be done was done in __new__

    def __str__(self):
        return "{self.__class__.__name__}: {self.nick}!{self.ident}@{self.host}:{self.account}".format(self=self)

    def __repr__(self):
        return "{self.__class__.__name__}({self.nick!r}, {self.ident!r}, {self.host!r}, {self.account!r}, {self.channels!r})".format(self=self)

    def __format__(self, format_spec):
        if format_spec == "@":
            return "\u0002{0}\u0002".format(self.name)
        elif format_spec == "for_tb":
            if var.USER_DATA_LEVEL == 0:
                return "{self.__class__.__name__}({0:x})".format(id(self), self=self)
            elif var.USER_DATA_LEVEL == 1:
                return "{self.__class__.__name__}({self.nick!r})".format(self=self)
            else:
                return repr(self)
        return super().__format__(format_spec)

    def __hash__(self):
        # check intentionally omits account: account may be None for normal operation for any user.
        if self.nick is None or self.ident is None or self.host is None:
            raise ValueError("cannot hash a User with no nick, ident, or host")
        return hash((self.nick, self.ident, self.host, self.account))

    def __eq__(self, other):
        return (isinstance(other, User)
                and self.nick == other.nick
                and self.ident == other.ident
                and self.host == other.host
                and self.account == other.account)

    def partial_match(self, other):
        """Test if our non-None properties match the non-None properties on the other object.

        :param other: Object to compare with
        :returns: True if `other` is a User object and the non-None properties match our non-None properties.
        """
        return self._compare(other, __class__, "nick", "ident", "host", "account")

    # User objects are not copyable - this is a deliberate design decision
    # Therefore, those two functions here only return the object itself
    # Even if we tried to create new instances, the logic in __new__ would
    # just fetch back the same instance, so we save ourselves the trouble

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def swap(self, new, *, same_user=False):
        """Swap yourself out with the new user everywhere.

        :param new: New user to replace current one with.
        :param same_user: If True, indicates `new` is the same user instance as `self`, just
            with updated values. This performs some additional work to ensure that the hand-off
            does not lose any data.
        """
        if self is new:
            return # as far as the caller is aware, we've swapped

        _ghosts.discard(self)
        if not self.channels or same_user:
            _users.discard(self) # Goodbye, my old friend

        for l in self.lists[:]:
            while self in l:
                l[l.index(self)] = new

        for s in self.sets[:]:
            s.remove(self)
            s.add(new)

        for dk in self.dict_keys[:]:
            dk[new] = dk.pop(self)

        for dv in self.dict_values[:]:
            for key in dv:
                if dv[key] is self:
                    dv[key] = new

        if same_user:
            global Bot
            new.channels = self.channels
            for channel in self.channels:
                channel.users.discard(self)
                channel.users.add(new)
                for mode in Features["PREFIX"].values():
                    if self in channel.modes.get(mode, ()):
                        channel.modes[mode].discard(self)
                        channel.modes[mode].add(self)
            if not isinstance(new, BotUser):
                _users.add(new)
            elif self is Bot:
                Bot = new

        # It is the containers' responsibility to properly remove themselves from the users
        # So if any list is non-empty, something went terribly wrong
        assert not self.lists + self.sets + self.dict_keys + self.dict_values

    def lower(self):
        temp = type(self)(self.client, lower(self.nick), lower(self.ident), lower(self.host, casemapping="ascii"), lower(self.account))
        if temp is not self: # If everything is already lowercase, we'll get back the same instance
            temp.channels = self.channels
            temp.ref = self.ref or self
        return temp

    def is_owner(self):
        if self.is_fake:
            return False

        accounts = set(botconfig.OWNERS_ACCOUNTS)

        if self.account is not None and self.account in accounts:
            return True

        return False

    def is_admin(self):
        if self.is_fake:
            return False

        flags = var.FLAGS_ACCS[self.account]

        if "F" not in flags:
            try:
                accounts = set(botconfig.ADMINS_ACCOUNTS)
                if self.account is not None and self.account in accounts:
                    return True
            except AttributeError:
                pass

            return self.is_owner()

        return True

    def get_send_type(self, *, is_notice=False, is_privmsg=False):
        if is_privmsg:
            return "PRIVMSG"
        if is_notice:
            return "NOTICE"
        if self.prefers_notice():
            return "NOTICE"
        return "PRIVMSG"

    def match_hostmask(self, hostmask):
        """Match n!u@h, u@h, or just h by itself."""
        nick, ident, host = re.match("(?:(?:(.*?)!)?(.*?)@)?(.*)", hostmask).groups("")
        temp = self.lower()

        return ((not nick or fnmatch.fnmatch(temp.nick, lower(nick))) and
                (not ident or fnmatch.fnmatch(temp.ident, lower(ident))) and
                fnmatch.fnmatch(temp.host, lower(host, casemapping="ascii")))

    def prefers_notice(self):
        return self.lower().account in var.PREFER_NOTICE_ACCS

    def get_pingif_count(self):
        temp = self.lower()
        if temp.account in var.PING_IF_PREFS_ACCS:
            return var.PING_IF_PREFS_ACCS[temp.account]
        return 0

    def set_pingif_count(self, value, old=None):
        temp = self.lower()

        if not value:
            if temp.account in var.PING_IF_PREFS_ACCS:
                del var.PING_IF_PREFS_ACCS[temp.account]
                db.set_pingif(0, temp.account)
                if old is not None:
                    with var.WARNING_LOCK:
                        if old in var.PING_IF_NUMS_ACCS:
                            var.PING_IF_NUMS_ACCS[old].discard(temp.account)
        else:
            if temp.account is not None:
                var.PING_IF_PREFS_ACCS[temp.account] = value
                db.set_pingif(value, temp.account)
                with var.WARNING_LOCK:
                    if value not in var.PING_IF_NUMS_ACCS:
                        var.PING_IF_NUMS_ACCS[value] = set()
                    var.PING_IF_NUMS_ACCS[value].add(temp.account)
                    if old is not None:
                        if old in var.PING_IF_NUMS_ACCS:
                            var.PING_IF_NUMS_ACCS[old].discard(temp.account)

    def wants_deadchat(self):
        return self.lower().account not in var.DEADCHAT_PREFS_ACCS

    def stasis_count(self):
        """Return the number of games the user is in stasis for."""
        return var.STASISED_ACCS.get(self.lower().account, 0)

    def update_account_data(self, command: str, callback: Callable):
        """Refresh stale account data on networks that don't support certain features.

        :param command: Command name that prompted the call to update_account_data.
            Used to handle cases where the user executes multiple commands before
            account data can be updated, so they can all be queued. If the same command
            is given multiple times, we honor the most recent one given.
        :param callback: Callback to execute when account data is fully updated
        """

        # Nothing to update for fake nicks
        if self.is_fake:
            callback()
            return

        if self.account is not None and Features.get("account-notify", False):
            # account-notify is enabled, so we're already up to date on our account name
            callback()
            return

        if self.account is not None and self.account_timestamp > time.time() - 900:
            # account data is less than 15 minutes old, use existing data instead of refreshing
            callback()
            return

        if self not in _pending_account_updates:
            _pending_account_updates[self] = CheckedDict("users.User.update_account_data")

        _pending_account_updates[self][command] = callback

        if len(_pending_account_updates[self].keys()) > 1:
            # already have a pending WHO/WHOIS for this user, don't send multiple to the server to avoid hitting
            # rate limits (if we are ratelimited, that can be handled by re-sending the request at a lower layer)
            return

        if Features.get("WHOX", False):
            # A WHOX query performs less network noise than WHOIS, so use that if available
            self.who()
        else:
            # Fallback to WHOIS
            self.client.send("WHOIS {0}".format(self))

    @property
    def nick(self): # name should be the same as nick (for length calculation)
        return self.name

    @nick.setter
    def nick(self, value):
        new = User(self.client, value, self.ident, self.host, self.account)
        self.swap(new, same_user=True)

    @property
    def ident(self):
        return self._ident

    @ident.setter
    def ident(self, value):
        new = User(self.client, self.nick, value, self.host, self.account)
        self.swap(new, same_user=True)

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, value):
        new = User(self.client, self.nick, self.ident, value, self.account)
        self.swap(new, same_user=True)

    @property
    def account(self): # automatically converts "0" and "*" to None
        return self._account

    @account.setter
    def account(self, value):
        if value in ("0", "*"):
            value = None
        new = User(self.client, self.nick, self.ident, self.host, value)
        new.account_timestamp = time.time()
        self.swap(new, same_user=True)

    @property
    def rawnick(self):
        if self.nick is None or self.ident is None or self.host is None:
            return None
        return "{self.nick}!{self.ident}@{self.host}".format(self=self)

    @rawnick.setter
    def rawnick(self, value):
        nick, ident, host = parse_rawnick(value)
        new = User(self.client, nick, ident, host, self.account)
        self.swap(new, same_user=True)

    @property
    def disconnected(self):
        return self in _ghosts

    @disconnected.setter
    def disconnected(self, value):
        if value:
            _ghosts.add(self)
        else:
            _ghosts.discard(self)
            # ensure dangling users aren't left around in our tracking var
            if not self.channels:
                _users.discard(self)

class FakeUser(User):

    is_fake = True

    def __hash__(self):
        return hash(self.nick)

    def __format__(self, format_spec):
        if format_spec == "for_tb" and self.nick.startswith("@"):
            # fakes starting with @ are used internally for various purposes (such as @WolvesAgree@)
            # so it'd be good to keep that around when debugging in tracebacks
            return "{self.__class__.__name__}({self.nick!r})".format(self=self)
        return super().__format__(format_spec)

    @classmethod
    def from_nick(cls, nick):
        return FakeUser(None, nick, None, None, None)

    @property
    def nick(self):
        return self.name

    @nick.setter
    def nick(self, value):
        raise ValueError("may not change the nick of a fake user")

    @property
    def rawnick(self):
        return self.nick # we don't have a raw nick

    @rawnick.setter
    def rawnick(self, value):
        raise ValueError("may not change the raw nick of a fake user")

class BotUser(User): # TODO: change all the 'if x is Bot' for 'if isinstance(x, BotUser)'

    def __new__(cls, cli, nick, ident=None, host=None, account=None):
        self = super().__new__(cls, cli, nick, ident, host, account)
        self.modes = set()
        return self

    def change_nick(self, nick=None):
        if nick is None:
            nick = self.nick
        self.client.send("NICK", nick)

    @property
    def nick(self): # name should be the same as nick (for length calculation)
        return self.name

    @nick.setter
    def nick(self, value):
        self.client.nickname = value
        new = BotUser(self.client, value, self.ident, self.host, self.account)
        self.swap(new, same_user=True)

    @property
    def ident(self):
        return self._ident

    @ident.setter
    def ident(self, value):
        self.client.ident = value
        new = BotUser(self.client, self.nick, value, self.host, self.account)
        self.swap(new, same_user=True)

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, value):
        self.client.hostmask = value
        new = BotUser(self.client, self.nick, self.ident, value, self.account)
        self.swap(new, same_user=True)

    @property
    def account(self): # automatically converts "0" and "*" to None
        return self._account

    @account.setter
    def account(self, value):
        if value in ("0", "*"):
            value = None
        new = BotUser(self.client, self.nick, self.ident, self.host, value)
        self.swap(new, same_user=True)

    @property
    def rawnick(self):
        if self.nick is None or self.ident is None or self.host is None:
            return None
        return "{self.nick}!{self.ident}@{self.host}".format(self=self)

    @rawnick.setter
    def rawnick(self, value):
        nick, ident, host = parse_rawnick(value)
        self.client.nickname = nick
        self.client.ident = ident
        self.client.hostmask = host
        new = BotUser(self.client, nick, ident, host, self.account)
        self.swap(new, same_user=True)

    @property
    def disconnected(self):
        return False

    @disconnected.setter
    def disconnected(self, value):
        pass # no-op
