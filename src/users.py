from collections import defaultdict
from weakref import WeakSet
import fnmatch
import re

from src.context import IRCContext, Features, lower
from src.logger import debuglog
from src import settings as var
from src import db

import botconfig

Bot = None # bot instance

_users = WeakSet()

_arg_msg = "(nick={0}, ident={1}, host={2}, realname={3}, account={4}, allow_bot={5})"

# This is used to tell if this is a fake nick or not. If this function
# returns a true value, then it's a fake nick. This is useful for
# testing, where we might want everyone to be fake nicks.
predicate = re.compile(r"^[0-9]+$").search

def get(nick=None, ident=None, host=None, realname=None, account=None, *, allow_multiple=False, allow_none=False, allow_bot=False):
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

    for user in users:
        if nick is not None and user.nick != nick:
            continue
        if ident is not None and user.ident != ident:
            continue
        if host is not None and user.host != host:
            continue
        if realname is not None and user.realname != realname:
            continue
        if account is not None and user.account != account:
            continue

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

def add(cli, *, nick, ident=None, host=None, realname=None, account=None, channels=None):
    """Create a new user, add it to the user list and return it.

    This function takes up to 6 keyword-only arguments (and no positional
    arguments): nick, ident, host, realname, account and channels.
    With the exception of the first one, any parameter can be omitted.
    If a matching user already exists, a ValueError will be raised.

    """

    if ident is None and host is None and nick is not None:
        nick, ident, host = parse_rawnick(nick)

    if exists(nick, ident, host, realname, account, allow_multiple=True, allow_bot=True):
        raise ValueError("User already exists: " + _arg_msg.format(nick, ident, host, realname, account, True))

    if channels is None:
        channels = {}
    else:
        channels = dict(channels)

    cls = User
    if predicate(nick):
        cls = FakeUser

    new = cls(cli, nick, ident, host, realname, account, channels)
    _users.add(new)
    return new

def exists(nick=None, ident=None, host=None, realname=None, account=None, *, allow_multiple=False, allow_bot=False):
    """Return True if a matching user exists.

    Positional and keyword arguments are the same as get(), with the
    exception that allow_none may not be used (a RuntimeError will be
    raised in that case).

    """

    try:
        get(nick, ident, host, realname, account, allow_multiple=allow_multiple, allow_bot=allow_bot)
    except (KeyError, ValueError):
        return False

    return True

def users():
    """Iterate over the users in the registry."""
    yield from _users

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

    def __init__(self, cli, nick, ident, host, realname, account, channels, **kwargs):
        super().__init__(nick, cli, **kwargs)
        self.nick = nick
        self.ident = ident
        self.host = host
        self.realname = realname
        self.account = account
        self.channels = channels

    def __str__(self):
        return "{self.__class__.__name__}: {self.nick}!{self.ident}@{self.host}#{self.realname}:{self.account}".format(self=self)

    def __repr__(self):
        return "{self.__class__.__name__}({self.nick!r}, {self.ident!r}, {self.host!r}, {self.realname!r}, {self.account!r}, {self.channels!r})".format(self=self)

    def lower(self):
        return type(self)(self.client, lower(self.nick), lower(self.ident), lower(self.host), lower(self.realname), lower(self.account), channels, ref=(self.ref or self))

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
                    cls._send(message, targets[0].client, send_type, ",".join([t.nick for t in using]))

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

    def queue_message(self, message):
        self.send(message) # don't actually queue it

    def send(self, data, *, notice=False, privmsg=False):
        debuglog("Would message fake user {0}: {1!r}".format(self.nick, data))

    @property
    def rawnick(self):
        return self.nick # we don't have a raw nick

    @rawnick.setter
    def rawnick(self, rawnick):
        self.nick = parse_rawnick_as_dict(rawnick)["nick"]
