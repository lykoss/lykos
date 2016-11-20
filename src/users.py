from collections import defaultdict
from weakref import WeakSet
import fnmatch
import re

from src.context import IRCContext, Features, lower
from src import settings as var
from src import db

import botconfig

Bot = None # bot instance

_users = WeakSet()

_arg_msg = "(nick={0!r}, ident={1!r}, host={2!r}, realname={3!r}, account={4!r}, allow_bot={5})"

class _user:
    def __init__(self, nick):
        self.nick = nick

    for name in ("ident", "host", "account", "inchan", "modes", "moded"):
        locals()[name] = property(lambda self, name=name: var.USERS[self.nick][name], lambda self, value, name=name: var.USERS[self.nick].__setitem__(name, value))

# This is used to tell if this is a fake nick or not. If this function
# returns a true value, then it's a fake nick. This is useful for
# testing, where we might want everyone to be fake nicks.
predicate = re.compile(r"^[0-9]+$").search

def _get(nick=None, ident=None, host=None, realname=None, account=None, *, allow_multiple=False, allow_none=False, allow_bot=False):
    """Return the matching user(s) from the user list.

    This takes up to 5 positional arguments (nick, ident, host, realname,
    account) and may take up to three keyword-only arguments:

    - allow_multiple (defaulting to False) allows multiple matches,
      and returns a list, even if there's only one match;

    - allow_none (defaulting to False) allows no match at all, and
      returns None instead of raising an error; an empty list will be
      returned if this is used with allow_multiple;

    - allow_bot (defaulting to False) allows the bot to be matched and
      returned;

    If allow_multiple is not set and multiple users match, a ValueError
    will be raised. If allow_none is not set and no users match, a KeyError
    will be raised.

    """

    if ident is None and host is None and nick is not None:
        nick, ident, host = parse_rawnick(nick)

    potential = []
    users = set(_users)
    if allow_bot:
        users.add(Bot)

    sentinel = object()

    temp = User(sentinel, nick, ident, host, realname, account)
    if temp.client is not sentinel:
        return temp # actual client

    for user in users:
        if user == temp:
            if not potential or allow_multiple:
                potential.append(user)
            else:
                raise ValueError("More than one user matches: " +
                                 _arg_msg.format(nick, ident, host, realname, account, allow_bot))

    if not potential and not allow_none:
        raise KeyError(_arg_msg.format(nick, ident, host, realname, account, allow_bot))

    if allow_multiple:
        return potential

    if not potential: # allow_none
        return None

    return potential[0]

def get(nick, *stuff, **morestuff): # backwards-compatible API - kill this as soon as possible!
    var.USERS[nick] # _user(nick) evaluates lazily, so check eagerly if the nick exists
    return _user(nick)

def _add(cli, *, nick, ident=None, host=None, realname=None, account=None):
    """Create a new user, add it to the user list and return it.

    This function takes up to 5 keyword-only arguments (and no positional
    arguments): nick, ident, host, realname and account.
    With the exception of the first one, any parameter can be omitted.
    If a matching user already exists, a ValueError will be raised.

    """

    if ident is None and host is None and nick is not None:
        nick, ident, host = parse_rawnick(nick)

    cls = User
    if predicate(nick):
        cls = FakeUser

    new = cls(cli, nick, ident, host, realname, account)
    if new is not Bot:
        _users.add(new)
    return new

def add(nick, **blah): # backwards-compatible API
    var.USERS[nick] = blah
    return _user(nick)

def _exists(nick=None, ident=None, host=None, realname=None, account=None, *, allow_multiple=False, allow_bot=False):
    """Return True if a matching user exists.

    Positional and keyword arguments are the same as get(), with the
    exception that allow_none may not be used (a RuntimeError will be
    raised in that case).

    """

    sentinel = object()

    if ident is None and host is None and nick is not None:
        nick, ident, host = parse_rawnick(nick)

    cls = User
    if predicate(nick):
        cls = FakeUser

    temp = cls(sentinel, nick, ident, host, realname, account)

    if temp.client is sentinel: # doesn't exist; if it did, the client would be an actual client
        return False

    return temp is not Bot or allow_bot

def exists(nick, *stuff, **morestuff): # backwards-compatible API
    return nick in var.USERS

def users_():
    """Iterate over the users in the registry."""
    yield from _users

class users: # backwards-compatible API
    def __iter__(self):
        yield from var.USERS
    def items(self):
        yield from var.USERS.items()

_raw_nick_pattern = re.compile(r"^(?P<nick>.+?)(?:!(?P<ident>.+?)@(?P<host>.+))?$")

def parse_rawnick(rawnick, *, default=None):
    """Return a tuple of (nick, ident, host) from rawnick."""

    return _raw_nick_pattern.search(rawnick).groups(default)

def parse_rawnick_as_dict(rawnick, *, default=None):
    """Return a dict of {"nick": nick, "ident": ident, "host": host}."""

    return _raw_nick_pattern.search(rawnick).groupdict(default)

def equals(nick1, nick2):
    return lower(nick1) == lower(nick2)

class User(IRCContext):

    is_user = True

    _messages = defaultdict(list)

    def __new__(cls, cli, nick, ident, host, realname, account):
        self = super().__new__(cls)
        super(User, self).__init__(nick, cli)

        self._ident = ident
        self._host = host
        self.realname = realname
        self.account = account
        self.channels = {}

        if Bot is not None and Bot.nick == nick and {Bot.ident, Bot.host, Bot.realname, Bot.account} == {None}:
            self = Bot
            self.ident = ident
            self.host = host
            self.realname = realname
            self.account = account

        # check the set to see if this already exists
        elif ident is not None and host is not None:
            users = set(_users)
            users.add(Bot)
            if self in users: # quirk: this actually checks for the hash first (also, this is O(1))
                for user in users:
                    if self == user:
                        self = user
                        break # this may only happen once

        return self

    def __init__(*args, **kwargs):
        pass # everything that needed to be done was done in __new__

    def __str__(self):
        return "{self.__class__.__name__}: {self.nick}!{self.ident}@{self.host}#{self.realname}:{self.account}".format(self=self)

    def __repr__(self):
        return "{self.__class__.__name__}({self.nick!r}, {self.ident!r}, {self.host!r}, {self.realname!r}, {self.account!r}, {self.channels!r})".format(self=self)

    def __hash__(self):
        if self.ident is None or self.host is None:
            raise ValueError("cannot hash a User with no ident or host")
        return hash((self.ident, self.host))

    def __eq__(self, other):
        if not isinstance(other, User):
            return NotImplemented

        done = False
        for a, b in ((self.nick, other.nick), (self.ident, other.ident), (self.host, other.host), (self.realname, other.realname), (self.account, other.account)):
            if a is None or b is None:
                continue
            done = True
            if a != b:
                return False

        return done

    def lower(self):
        temp = type(self)(self.client, lower(self.nick), lower(self.ident), lower(self.host), lower(self.realname), lower(self.account))
        temp.channels = self.channels
        temp.ref = self.ref or self
        return temp

    def is_owner(self):
        if self.is_fake:
            return False

        hosts = set(botconfig.OWNERS)
        accounts = set(botconfig.OWNERS_ACCOUNTS)

        if not var.DISABLE_ACCOUNTS and self.account is not None:
            for pattern in accounts:
                if fnmatch.fnmatch(lower(self.account), lower(pattern)):
                    return True

        for hostmask in hosts:
            if match_hostmask(hostmask, self.nick, self.ident, self.host):
                return True

        return False

    def is_admin(self):
        if self.is_fake:
            return False

        flags = var.FLAGS[self.rawnick] + var.FLAGS_ACCS[self.account]

        if "F" not in flags:
            try:
                hosts = set(botconfig.ADMINS)
                accounts = set(botconfig.ADMINS_ACCOUNTS)

                if not var.DISABLE_ACCOUNTS and self.account is not None:
                    for pattern in accounts:
                        if fnmatch.fnmatch(lower(self.account), lower(pattern)):
                            return True

                for hostmask in hosts:
                    if match_hostmask(hostmask, self.nick, self.ident, self.host):
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

        return (fnmatch.fnmatch(temp.nick, lower(nick)) and
                fnmatch.fnmatch(temp.ident, lower(ident)) and
                fnmatch.fnmatch(temp.host, lower(host)))

    def prefers_notice(self):
        temp = self.lower()

        if temp.account in var.PREFER_NOTICE_ACCS:
            return True

        if not var.ACCOUNTS_ONLY:
            for hostmask in var.PREFER_NOTICE:
                if temp.match_hostmask(hostmask):
                    return True

        return False

    def prefers_simple(self):
        temp = self.lower()

        if temp.account in var.SIMPLE_NOTIFY_ACCS:
            return True

        if not var.ACCOUNTS_ONLY:
            for hostmask in var.SIMPLE_NOTIFY:
                if temp.match_hostmask(hostmask):
                    return True

        return False

    def get_pingif_count(self):
        temp = self.lower()

        if not var.DISABLE_ACCOUNTS and temp.account is not None:
            if temp.account in var.PING_IF_PREFS_ACCS:
                return var.PING_IF_PREFS_ACCS[temp.account]

        elif not var.ACCOUNTS_ONLY:
            for hostmask, pref in var.PING_IF_PREFS.items():
                if temp.match_hostmask(hostmask):
                    return pref

        return 0

    def set_pingif_count(self, value, old=None):
        temp = self.lower()

        if not value:
            if not var.DISABLE_ACCOUNTS and temp.account:
                if temp.account in var.PING_IF_PREFS_ACCS:
                    del var.PING_IF_PREFS_ACCS[temp.account]
                    db.set_pingif(0, temp.account, None)
                    if old is not None:
                        with var.WARNING_LOCK:
                            if old in var.PING_IF_NUMS_ACCS:
                                var.PING_IF_NUMS_ACCS[old].discard(temp.account)

            if not var.ACCOUNTS_ONLY:
                for hostmask in list(var.PING_IF_PREFS):
                    if temp.match_hostmask(hostmask):
                        del var.PING_IF_PREFS[hostmask]
                        db.set_pingif(0, None, hostmask)
                        if old is not None:
                            with var.WARNING_LOCK:
                                if old in var.PING_IF_NUMS:
                                    var.PING_IF_NUMS[old].discard(hostmask)
                                    var.PING_IF_NUMS[old].discard(temp.host)

        else:
            if not var.DISABLE_ACCOUNTS and temp.account:
                var.PING_IF_PREFS[temp.account] = value
                db.set_pingif(value, temp.account, None)
                with var.WARNING_LOCK:
                    if value not in var.PING_IF_NUMS_ACCS:
                        var.PING_IF_NUMS_ACCS[value] = set()
                    var.PING_IF_NUMS_ACCS[value].add(temp.account)
                    if old is not None:
                        if old in var.PING_IF_NUMS_ACCS:
                            var.PING_IF_NUMS_ACCS[old].discard(temp.account)

            elif not var.ACCOUNTS_ONLY:
                var.PING_IF_PREFS[temp.userhost] = value
                db.set_pingif(value, None, temp.userhost)
                with var.WARNING_LOCK:
                    if value not in var.PING_IF_NUMS:
                        var.PING_IF_NUMS[value] = set()
                    var.PING_IF_NUMS[value].add(temp.userhost)
                    if old is not None:
                        if old in var.PING_IF_NUMS:
                            var.PING_IF_NUMS[old].discard(temp.host)
                            var.PING_IF_NUMS[old].discard(temp.userhost)

    def wants_deadchat(self):
        temp = self.lower()

        if temp.account in var.DEADCHAT_PREFS_ACCS:
            return False
        elif var.ACCOUNTS_ONLY:
            return True
        elif temp.host in var.DEADCHAT_PREFS:
            return False

        return True

    def stasis_count(self):
        """Return the number of games the user is in stasis for."""
        temp = self.lower()
        amount = 0

        if not var.DISABLE_ACCOUNTS:
            amount = var.STASISED_ACCS.get(temp.account, 0)

        amount = max(amount, var.STASISED.get(temp.userhost, 0))

        return amount

    def queue_message(self, message):
        self._messages[message].append(self)

    @classmethod
    def send_messages(cls, *, notice=False, privmsg=False):
        for message, targets in cls._messages.items():
            send_types = defaultdict(list)
            for target in targets:
                send_types[target.get_send_type(is_notice=notice, is_privmsg=privmsg)].append(target)
            for send_type, targets in send_types.items():
                max_targets = Features["TARGMAX"][send_type]
                while targets:
                    using, targets = targets[:max_targets], targets[max_targets:]
                    cls._send([message], "", " ", targets[0].client, send_type, ",".join([t.nick for t in using]))

        cls._messages.clear()

    @property
    def nick(self): # name should be the same as nick (for length calculation)
        return self.name

    @nick.setter
    def nick(self, nick):
        self.name = nick
        if self is Bot: # update the client's nickname as well
            self.client.nickname = nick

    @property
    def ident(self): # prevent changing ident and host after they were set (so hash remains the same)
        return self._ident

    @ident.setter
    def ident(self, ident):
        if self._ident is None:
            self._ident = ident
            if self is Bot:
                self.client.ident = ident
        elif self._ident != ident:
            raise ValueError("may not change the ident of a live user")

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, host):
        if self._host is None:
            self._host = host
            if self is Bot:
                self.client.hostmask = host
        elif self._host != host:
            raise ValueError("may not change the host of a live user")

    @property
    def realname(self):
        return self._realname

    @realname.setter
    def realname(self, realname):
        self._realname = realname
        if self is Bot:
            self.client.real_name = realname

    @property
    def account(self): # automatically converts "0" and "*" to None
        return self._account

    @account.setter
    def account(self, account):
        if account in ("0", "*"):
            account = None
        self._account = account

    @property
    def rawnick(self):
        if self.nick is None or self.ident is None or self.host is None:
            return None
        return "{self.nick}!{self.ident}@{self.host}".format(self=self)

    @rawnick.setter
    def rawnick(self, rawnick):
        self.nick, self.ident, self.host = parse_rawnick(rawnick)

    @property
    def userhost(self):
        if self.ident is None or self.host is None:
            return None
        return "{self.ident}@{self.host}".format(self=self)

    @userhost.setter
    def userhost(self, userhost):
        nick, self.ident, self.host = parse_rawnick(userhost)

class FakeUser(User):

    is_fake = True

    def __hash__(self):
        return hash(self.nick)

    def queue_message(self, message):
        self.send(message) # don't actually queue it

    @property
    def nick(self):
        return self.name

    @nick.setter
    def nick(self, nick):
        raise ValueError("may not change the nick of a fake user")

    @property
    def rawnick(self):
        return self.nick # we don't have a raw nick

    @rawnick.setter
    def rawnick(self, rawnick):
        self.nick = parse_rawnick_as_dict(rawnick)["nick"]

class BotUser(User): # TODO: change all the 'if x is Bot' for 'if isinstance(x, BotUser)'

    def __new__(cls, cli, nick):
        self = super().__new__(cls, cli, nick, None, None, None, None)
        self.modes = set()
        return self

    def change_nick(self, nick=None):
        if nick is None:
            nick = self.nick
        self.client.send("NICK", nick)
