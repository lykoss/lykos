import fnmatch
import time
import re
from typing import Callable, Optional

from src.context import IRCContext, Features, lower, equals
from src import settings as var
from src import db
from src.events import EventListener
from src.decorators import hook

import botconfig

Bot = None # bot instance

_users = set()
_ghosts = set()

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
    if temp.client is not sentinel: # actual client
        return [temp] if allow_multiple else temp

    for user in users:
        if user == temp:
            potential.append(user)

    if allow_multiple:
        return potential

    if len(potential) == 1:
        return potential[0]

    if len(potential) > 1:
        raise ValueError("More than one user matches: " +
              _arg_msg.format(nick, ident, host, realname, account, allow_bot))

    if not allow_none:
        raise KeyError(_arg_msg.format(nick, ident, host, realname, account, allow_bot))

    return None

def get(nick, *stuff, **morestuff): # backwards-compatible API - kill this as soon as possible!
    var.USERS[nick] # _user(nick) evaluates lazily, so check eagerly if the nick exists
    return _user(nick)

def _add(cli, *, nick, ident=None, host=None, realname=None, account=None):
    """Create a new user, add it to the user list and return it.

    This function takes up to 5 keyword-only arguments (and one positional
    argument, cli): nick, ident, host, realname and account.
    With the exception of the first one, any parameter can be omitted.

    """

    if ident is None and host is None and nick is not None:
        nick, ident, host = parse_rawnick(nick)

    cls = User
    if predicate(nick):
        cls = FakeUser

    new = cls(cli, nick, ident, host, realname, account)

    if new is not Bot:
        try:
            hash(new)
        except ValueError:
            pass
        else:
            _users.add(new)

    return new

def add(nick, **blah): # backwards-compatible API
    var.USERS[nick] = blah
    return _user(nick)

def exists(nick, *stuff, **morestuff): # backwards-compatible API
    return nick in var.USERS

def users():
    """Iterate over the users in the registry."""
    yield from _users

def disconnected():
    """Iterate over the users who are in-game but disconnected."""
    yield from _ghosts

def complete_match(string, users):
    matches = []
    string = lower(string)
    for user in users:
        nick = lower(user.nick)
        if nick == string:
            return user, 1
        elif nick.startswith(string) or nick.lstrip("[{\\^_`|}]").startswith(string):
            matches.append(user)

    if len(matches) != 1:
        return None, len(matches)

    return matches[0], 1

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

# Can't use @event_listener decorator since src/decorators.py imports us
# (meaning decorator isn't defined at the point in time we are run)
EventListener(_cleanup_user).install("cleanup_user")
EventListener(_reset).install("reset")

class User(IRCContext):

    is_user = True

    def __new__(cls, cli, nick, ident, host, realname, account):
        self = super().__new__(cls)
        super(__class__, self).__init__(nick, cli)

        self._ident = ident
        self._host = host
        self.realname = realname
        self.account = account
        self.channels = {}
        self.timestamp = time.time()
        self.sets = []
        self.lists = []
        self.dict_keys = []
        self.dict_values = []

        if Bot is not None and Bot.nick == nick and {Bot.ident, Bot.host, Bot.realname, Bot.account} == {None}:
            self = Bot
            self.ident = ident
            self.host = host
            self.realname = realname
            self.account = account
            self.timestamp = time.time()

        elif ident is not None and host is not None:
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
            # comparisons check for all non-None attributes, two instances cannot
            # possibly be equal while having a different hash).
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
                if self == user:
                    if potential is None:
                        potential = user
                    else:
                        break # too many possibilities
            else:
                if potential is not None:
                    self = potential

        return self

    def __init__(*args, **kwargs):
        pass # everything that needed to be done was done in __new__

    def __str__(self):
        return "{self.__class__.__name__}: {self.nick}!{self.ident}@{self.host}#{self.realname}:{self.account}".format(self=self)

    def __repr__(self):
        return "{self.__class__.__name__}({self.nick!r}, {self.ident!r}, {self.host!r}, {self.realname!r}, {self.account!r}, {self.channels!r})".format(self=self)

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
        if self.ident is None or self.host is None:
            raise ValueError("cannot hash a User with no ident or host")
        return hash((self.ident, self.host))

    def __eq__(self, other):
        return self._compare(other, __class__, "nick", "ident", "host", "realname", "account")

    # User objects are not copyable - this is a deliberate design decision
    # Therefore, those two functions here only return the object itself
    # Even if we tried to create new instances, the logic in __new__ would
    # just fetch back the same instance, so we save ourselves the trouble

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def swap(self, new):
        """Swap yourself out with the new user everywhere."""
        if self is new:
            return # as far as the caller is aware, we've swapped

        _ghosts.discard(self)
        if not self.channels:
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

        # It is the containers' reponsibility to properly remove themself from the users
        # So if any list is non-empty, something went terribly wrong
        assert not self.lists + self.sets + self.dict_keys + self.dict_values

    def lower(self):
        temp = type(self)(self.client, lower(self.nick), lower(self.ident), lower(self.host, casemapping="ascii"), lower(self.realname), lower(self.account))
        if temp is not self: # If everything is already lowercase, we'll get back the same instance
            temp.channels = self.channels
            temp.ref = self.ref or self
        return temp

    def is_owner(self):
        if self.is_fake:
            return False

        hosts = set(botconfig.OWNERS)
        accounts = set(botconfig.OWNERS_ACCOUNTS)

        if self.account is not None:
            for pattern in accounts:
                if fnmatch.fnmatch(lower(self.account), lower(pattern)):
                    return True

        for hostmask in hosts:
            if self.match_hostmask(hostmask):
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
                db.set_pingif(0, temp.account, None)
                if old is not None:
                    with var.WARNING_LOCK:
                        if old in var.PING_IF_NUMS_ACCS:
                            var.PING_IF_NUMS_ACCS[old].discard(temp.account)
        else:
            if temp.account is not None:
                var.PING_IF_PREFS_ACCS[temp.account] = value
                db.set_pingif(value, temp.account, None)
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

    def update_account_data(self, callback: Callable):
        """Refresh stale account data on networks that don't support certain features.

        :param callback: Callback to execute when account data is fully updated
        """
        if self.account is not None and Features.get("account-notify", False):
            # account-notify is enabled, so we're already up to date on our account name
            callback()
            return

        listener_id = "update_account_data." + self.name
        listener = None # type: Optional[EventListener]
        found_account = None

        def whox_listener(evt, var, chan, user):
            if user is self:
                listener.remove("who_reply")
                callback()

        def whoisaccount_listener(cli, server, nick, account):
            nonlocal found_account
            user = _get(nick) # FIXME
            if user is self:
                hook.unhook(listener_id + ".acc")
                found_account = account

        def endofwhois_listener(cli, server, nick):
            user = _get(nick)  # FIXME
            if user is self:
                hook.unhook(listener_id + ".end")
                self.account = found_account # will be None if the user is not logged in
                callback()

        if Features.get("WHOX", False):
            # A WHOX query performs less network noise than WHOIS, so use that if available
            EventListener(whox_listener, listener_id=listener_id).install("who_reply")
            self.who()
        else:
            # Fallback to WHOIS
            hook("whoisaccount", hookid=listener_id + ".acc")(whoisaccount_listener)
            hook("endofwhois", hookid=listener_id + ".end")(endofwhois_listener)

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

    @property
    def disconnected(self):
        return self in _ghosts

    @disconnected.setter
    def disconnected(self, disconnected):
        if disconnected:
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
        return cls(None, nick, None, None, None, None)

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
        raise ValueError("may not change the raw nick of a fake user")

class BotUser(User): # TODO: change all the 'if x is Bot' for 'if isinstance(x, BotUser)'

    def __new__(cls, cli, nick):
        self = super().__new__(cls, cli, nick, None, None, None, None)
        self.modes = set()
        return self

    def with_host(self, host):
        """Create a new bot instance with a new host."""
        if self.ident is None and self.host is None:
            # we don't have full details on our ident yet; setting host now causes bugs down the road since
            # ident will subsequently not update. We'll pick up the new host whenever we finish setting ourselves up
            return self
        new = super().__new__(type(self), self.client, self.nick, self.ident, host, self.realname, self.account)
        if new is not self:
            new.modes = set(self.modes)
            new.channels = {chan: set(modes) for chan, modes in self.channels.items()}
        return new

    def lower(self):
        temp = super().__new__(type(self), self.client, lower(self.nick), lower(self.ident), lower(self.host, casemapping="ascii"), lower(self.realname), lower(self.account))
        if temp is not self: # If everything is already lowercase, we'll get back the same instance
            temp.channels = self.channels
            temp.ref = self.ref or self
        return temp

    def change_nick(self, nick=None):
        if nick is None:
            nick = self.nick
        self.client.send("NICK", nick)
