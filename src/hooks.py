"""Handlers and dispatchers for IRC hooks live in this module.

Most of these hooks fire off specific events, which can be listened to
by code that wants to operate on these events. The events are explained
further in the relevant hook functions.

"""

import logging
import sys
from typing import Dict, Any

from src.decorators import hook
from src.context import Features, NotLoggedIn
from src.events import Event, event_listener

from src import config, context, channels, users

### WHO/WHOX responses handling

_who_old = {} # type: Dict[str, users.User]

@hook("whoreply")
def who_reply(cli, bot_server, bot_nick, chan, ident, host, server, nick, status, hopcount_gecos):
    """Handle WHO replies for servers without WHOX support.

    Ordering and meaning of arguments for a bare WHO response:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel the request was made on
    4 - The ident of the user in this reply
    5 - The hostname of the user in this reply
    6 - The server the user in this reply is on
    7 - The nickname of the user in this reply
    8 - The status (H = Not away, G = Away, * = IRC operator, @ = Opped in the channel in 4, + = Voiced in the channel in 4)
    9 - The hop count and realname (gecos)

    This fires off the "who_result" event, and dispatches it with two
    arguments, a Channel and a User. Less important attributes can be
    accessed via the event.params namespace.

    """

    hop, realname = hopcount_gecos.split(" ", 1)
    # We throw away the information about the operness of the user, but we probably don't need to care about that
    # We also don't directly pass which modes they have, since that's already on the channel/user
    is_away = ("G" in status)

    modes = {Features["PREFIX"].get(s) for s in status} - {None}

    user = users.get(nick, ident, host, allow_bot=True, allow_none=True)
    if user is None:
        user = users.add(cli, nick=nick, ident=ident, host=host)

    ch = channels.get(chan, allow_none=True)
    if ch is not None and ch not in user.channels:
        user.channels[ch] = modes
        ch.users.add(user)
        for mode in modes:
            if mode not in ch.modes:
                ch.modes[mode] = set()
            ch.modes[mode].add(user)

    _who_old[user.nick] = user
    event = Event("who_result", {}, away=is_away, data=0, old=user)
    event.dispatch(ch, user)

@hook("whospcrpl")
def extended_who_reply(cli, bot_server, bot_nick, data, chan, ident, ip_address, host, server, nick, status, hop, idle, account, realname):
    """Handle WHOX responses for servers that support it.

    An extended WHO (WHOX) is characterised by a second parameter to the request
    That parameter must be '%' followed by at least one of 'tcuihsnfdlar'
    If the 't' specifier is present, the specifiers must be followed by a comma and at most 3 bytes
    This is the ordering if all parameters are present, but not all of them are required
    If a parameter depends on a specifier, it will be stated at the front
    If a specifier is not given, the parameter will be omitted in the reply

    Ordering and meaning of arguments for an extended WHO (WHOX) response:

    0  -   - The IRCClient instance (like everywhere else)
    1  -   - The server the requester (i.e. the bot) is on
    2  -   - The nickname of the requester (i.e. the bot)
    3  - t - The data sent alongside the request
    4  - c - The channel the request was made on
    5  - u - The ident of the user in this reply
    6  - i - The IP address of the user in this reply
    7  - h - The hostname of the user in this reply
    8  - s - The server the user in this reply is on
    9  - n - The nickname of the user in this reply
    10 - f - Status (H = Not away, G = Away, * = IRC operator, @ = Opped in the channel in 5, + = Voiced in the channel in 5)
    11 - d - The hop count
    12 - l - The idle time (or 0 for users on other servers)
    13 - a - The services account name (or 0 if none/not logged in)
    14 - r - The realname (gecos)

    This fires off the "who_result" event, and dispatches it with two
    arguments, a Channel and a User. Less important attributes can be
    accessed via the event.params namespace.

    """

    if account == "0":
        account = NotLoggedIn

    is_away = ("G" in status)

    data = int.from_bytes(data.encode(Features["CHARSET"]), "little")

    modes = {Features["PREFIX"].get(s) for s in status} - {None}

    # WHOX may be issued to retrieve updated account info so exclude account from users.get()
    # we handle the account change differently below and don't want to add duplicate users
    user = users.get(nick, ident, host, allow_bot=True, allow_none=True)
    if user is None:
        user = users.add(cli, nick=nick, ident=ident, host=host, account=account)

    new_user = user
    if {user.account, account} != {NotLoggedIn} and not context.equals(user.account, account):
        # first check tests if both are NotLoggedIn, and skips over this if so
        old_account = user.account
        user.account = account
        new_user = users.get(nick, ident, host, account, allow_bot=True)
        Event("account_change", {}, old=user).dispatch(new_user, old_account)

    ch = channels.get(chan, allow_none=True)
    if ch is not None and ch not in user.channels:
        user.channels[ch] = modes
        ch.users.add(user)
        for mode in modes:
            if mode not in ch.modes:
                ch.modes[mode] = set()
            ch.modes[mode].add(user)

    _who_old[new_user.nick] = user
    event = Event("who_result", {}, away=is_away, data=data, old=user)
    event.dispatch(ch, new_user)

@hook("endofwho")
def end_who(cli, bot_server, bot_nick, target, rest):
    """Handle the end of WHO/WHOX responses from the server.

    Ordering and meaning of arguments for the end of a WHO/WHOX request:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The target the request was made against
    4 - A string containing some information; traditionally "End of /WHO list."

    This fires off the "who_end" event, and dispatches it with one
    argument: The channel or user the request was made to, or None
    if it could not be resolved.

    """

    try:
        target = channels.get(target)
    except KeyError:
        try:
            target = users.get(target)
        except KeyError:
            target = None
    else:
        target.dispatch_queue()

    old = _who_old.get(target.name, target)
    _who_old.clear()
    Event("who_end", {}, old=old).dispatch(target)

### WHOIS Reponse Handling

_whois_pending = {} # type: Dict[str, Dict[str, Any]]

@hook("whoisuser")
def on_whois_user(cli, bot_server, bot_nick, nick, ident, host, sep, realname):
    """Set up the user for a WHOIS reply.

    Ordering and meaning of arguments for a WHOIS user reply:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The nickname of the target
    4 - The ident of the target
    5 - The host of the target
    6 - The literal character '*'
    7 - The realname of the target

    This does not fire an event by itself, but sets up the proper data
    for the "endofwhois" listener to fire an event.

    """

    user = users.get(nick, ident, host, allow_bot=True, allow_none=True)
    if user is None:
        user = users.add(cli, nick=nick, ident=ident, host=host)
    _whois_pending[nick] = {"user": user, "account": None, "away": False, "channels": set()}

@hook("whoisaccount")
def on_whois_account(cli, bot_server, bot_nick, nick, account, logged):
    """Update the account of the user in a WHOIS reply.

    Ordering and meaning of arguments for a WHOIS account reply:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The nickname of the target
    4 - The account of the target
    5 - A human-friendly message, e.g. "is logged in as"

    This does not fire an event by itself, but sets up the proper data
    for the "endofwhois" listener to fire an event.

    """

    _whois_pending[nick]["account"] = account

@hook("whoischannels")
def on_whois_channels(cli, bot_server, bot_nick, nick, chans):
    """Handle WHOIS replies for the channels.

    Ordering and meaning of arguments for a WHOIS channels reply:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The nickname of the target
    4 - A space-separated string of channels

    This does not fire an event by itself, but sets up the proper data
    for the "endofwhois" listener to fire an event.

    """

    arg = "".join(Features["PREFIX"])
    for chan in chans.split(" "):
        ch = channels.get(chan.lstrip(arg), allow_none=True)
        if ch is not None:
            _whois_pending[nick]["channels"].add(ch)

@hook("away")
def on_away(cli, bot_server, bot_nick, nick, message):
    """Handle away replies for WHOIS.

    Ordering and meaning of arguments for an AWAY reply:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The nickname of the target
    4 - The away message

    This does not fire an event by itself, but sets up the proper data
    for the "endofwhois" listener to fire an event.

    """

    # This may be called even if we're not in the middle of a WHOIS
    # In that case just ignore it; we only care about WHOIS
    if nick in _whois_pending:
        _whois_pending[nick]["away"] = True

@hook("endofwhois")
def on_whois_end(cli, bot_server, bot_nick, nick, message):
    """Handle the end of WHOIS and fire events.

    Ordering and meaning of arguments for an end of WHOIS reply:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The nickname of the target
    4 - A human-friendly message, usually "End of /WHOIS list."

    This uses data accumulated from the above WHOIS listeners, and
    fires the "who_result" event (once per shared channel with the bot)
    and the "who_end" event with the relevant User instance as the arg.

    """

    values = _whois_pending.pop(nick)
    # check for account change
    new_user = user = values["user"]
    if {user.account, values["account"]} != {NotLoggedIn} and not context.equals(user.account, values["account"]):
        # first check tests if both are NotLoggedIn, and skips over this if so
        old_account = user.account
        user.account = values["account"]
        new_user = users.get(user.nick, user.ident, user.host, values["account"], allow_bot=True)
        Event("account_change", {}, old=user).dispatch(new_user, old_account)

    event = Event("who_result", {}, away=values["away"], data=0, old=user)
    for chan in values["channels"]:
        event.dispatch(chan, new_user)
    Event("who_end", {}, old=user).dispatch(new_user)

### Host changing handling

@hook("event_hosthidden")
def host_hidden(cli, server, nick, host, message):
    """Properly update the bot's knowledge of itself.

    Ordering and meaning of arguments for a host hidden event:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the bot is on
    2 - The user's nick (i.e. the bot's nick)
    3 - The new host we are now using
    4 - A human-friendly message (e.g. "is now your hidden host")

    """

    # Either we get our own nick, or the nick is a UID
    # If it's our nick, update ourselves. Otherwise, ignore.
    # UnrealIRCd does some weird stuff where it sends our host twice,
    # Once with our nick and once with our UID. We ignore the last one.

    if nick == users.Bot.nick:
        users.Bot.host = host

@hook("loggedin")
def on_loggedin(cli, server, nick, rawnick, account, message):
    """Update our own rawnick with proper info.

    Ordering and meaning of arguments for a logged-in event:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the bot is on
    2 - The requester's nick (us)
    3 - The full rawnick post-authentication
    4 - The account we're now logged into
    5 - A human-readable message (e.g. "You are now logged in as lykos.")

    """

    if users.Bot is None:
        from src import handler
        data = users.parse_rawnick_as_dict(rawnick)
        handler._temp_ident = data["ident"]
        handler._temp_host = data["host"]
        handler._temp_account = account
    else:
        users.Bot.rawnick = rawnick
        users.Bot.account = account

### Server PING handling

@hook("ping")
def on_ping(cli, prefix, server):
    """Send out PONG replies to the server's PING requests.

    Ordering and meaning of arguments for a PING request:

    0 - The IRCClient instance (like everywhere else)
    1 - Nothing (always None)
    2 - The server which sent out the request

    """

    with cli:
        cli.send("PONG", server)

### Fetch and store server information

@hook("featurelist")
def get_features(cli, server, nick, *features):
    """Fetch and store the IRC server features.

    Ordering and meaning of arguments for a feature listing:

    0 - The IRCClient instance(like everywhere else)
    1 - Server the requestor is on
    2 - Bot's nick
    * - A variable number of arguments, one per available feature

    """

    # final thing in each feature listing is the text "are supported by this server" -- discard it
    features = features[:-1]

    for feature in features:
        if feature[0] == "-":
            # removing a feature
            Features.unset(feature[1:])
        elif "=" in feature:
            name, data = feature.split("=", maxsplit=1)
            Features.set(name, data)
        else:
            Features.set(feature, "")

### Channel and user MODE handling

@hook("channelmodeis")
def current_modes(cli, server, bot_nick, chan, mode, *targets):
    """Update the channel modes with the existing ones.

    Ordering and meaning of arguments for a bare MODE response:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel holding the modes
    4 - The modes of the channel
    * - The targets to the modes (if any)

    """

    ch = channels.add(chan, cli)
    ch.update_modes(server, mode, targets)

@hook("channelcreate")
def chan_created(cli, server, bot_nick, chan, timestamp):
    """Update the channel timestamp with the server's information.

    Ordering and meaning of arguments for a bare MODE response end:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel in question
    4 - The UNIX timestamp of when the channel was created

    We probably don't need to care about this at all, but it doesn't
    hurt to keep it around. If we ever need it, it will be there.

    """

    channels.add(chan, cli).timestamp = int(timestamp)

@hook("mode")
def mode_change(cli, rawnick, chan, mode, *targets):
    """Update the channel and user modes whenever a mode change occurs.

    Ordering and meaning of arguments for a MODE change:

    0 - The IRCClient instance (like everywhere else)
    1 - The raw nick of the mode setter/actor
    2 - The channel (target) of the mode change
    3 - The mode changes
    * - The targets of the modes (if any)

    This takes care of properly updating all relevant users and the
    channel modes to make sure we remain internally consistent.

    """

    if chan == users.Bot.nick: # we only see user modes set to ourselves
        users.Bot.modes.update(mode)
        return

    if "!" not in rawnick:
        # Only sync modes if a server changed modes because
        # 1) human ops probably know better
        # 2) other bots might start a fight over modes
        # 3) recursion; we see our own mode changes.
        evt = Event("sync_modes", {})
        evt.dispatch()
        return

    actor = users.get(rawnick, allow_none=True)
    target = channels.add(chan, cli)
    target.queue("mode_change", {"mode": mode, "targets": targets}, (actor, target))

@event_listener("mode_change", 0) # This should fire before anything else!
def apply_mode_changes(evt, actor, target):
    """Apply all mode changes before any other event."""

    target.update_modes(actor, evt.data.pop("mode"), evt.data.pop("targets"))

### List modes handling (bans, quiets, ban and invite exempts)

def handle_listmode(cli, chan, mode, target, setter, timestamp):
    """Handle and store list modes."""

    ch = channels.add(chan, cli)
    if mode not in ch.modes:
        ch.modes[mode] = {}
    ch.modes[mode][target] = (setter, int(timestamp))

@hook("banlist")
def check_banlist(cli, server, bot_nick, chan, target, setter, timestamp):
    """Update the channel ban list with the current one.

    Ordering and meaning of arguments for the ban listing:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel holding the ban list
    4 - The target of the ban
    5 - The setter of the ban
    6 - A UNIX timestamp of when the ban was set

    """

    handle_listmode(cli, chan, "b", target, setter, timestamp)

@hook("quietlist")
def check_quietlist(cli, server, bot_nick, chan, mode, target, setter, timestamp):
    """Update the channel quiet list with the current one.

    Ordering and meaning of arguments for the quiet listing:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel holding the quiet list
    4 - The quiet mode of the server (single letter)
    5 - The target of the quiet
    6 - The setter of the quiet
    7 - A UNIX timestamp of when the quiet was set

    """

    handle_listmode(cli, chan, mode, target, setter, timestamp)

@hook("exceptlist")
def check_banexemptlist(cli, server, bot_nick, chan, target, setter, timestamp):
    """Update the channel ban exempt list with the current one.

    Ordering and meaning of arguments for the ban exempt listing:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel holding the ban exempt list
    4 - The target of the ban exempt
    5 - The setter of the ban exempt
    6 - A UNIX timestamp of when the ban exempt was set

    """

    handle_listmode(cli, chan, "e", target, setter, timestamp)

@hook("invitelist")
def check_inviteexemptlist(cli, server, bot_nick, chan, target, setter, timestamp):
    """Update the channel invite exempt list with the current one.

    Ordering and meaning of arguments for the invite exempt listing:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel holding the invite exempt list
    4 - The target of the invite exempt
    5 - The setter of the invite exempt
    6 - A UNIX timestamp of when the invite exempt was set

    """

    handle_listmode(cli, chan, "I", target, setter, timestamp)

def handle_endlistmode(cli, chan, mode):
    """Handle the end of a list mode listing."""

    ch = channels.add(chan, cli)
    ch.queue("end_listmode", {}, (ch, mode))

@hook("endofbanlist")
def end_banlist(cli, server, bot_nick, chan, message):
    """Handle the end of the ban list.

    Ordering and meaning of arguments for the end of ban list:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel holding the ban list
    4 - A string containing some information; traditionally "End of Channel Ban List."

    """

    handle_endlistmode(cli, chan, "b")

@hook("quietlistend")
def end_quietlist(cli, server, bot_nick, chan, mode, message=None):
    """Handle the end of the quiet listing.

    Ordering and meaning of arguments for the end of quiet list:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel holding the quiet list
    4 - The quiet mode of the server (single letter)
    5 - A string containing some information; traditionally "End of Channel Quiet List."

    """

    if not message:
        # charybdis includes a 'q' token before "End of Channel Quiet List", but
        # some IRCds (such as ircd-yeti) don't. This is a workaround to make it work.
        mode = "q"

    handle_endlistmode(cli, chan, mode)

@hook("endofexceptlist")
def end_banexemptlist(cli, server, bot_nick, chan, message):
    """Handle the end of the ban exempt list.

    Ordering and meaning of arguments for the end of ban exempt list:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel holding the ban exempt list
    4 - A string containing some information; traditionally "End of Channel Exception List."

    """

    handle_endlistmode(cli, chan, "e")

@hook("endofinvitelist")
def end_inviteexemptlist(cli, server, bot_nick, chan, message):
    """Handle the end of the invite exempt list.

    Ordering and meaning of arguments for the end of invite exempt list:

    0 - The IRCClient instance (like everywhere else)
    1 - The server the requester (i.e. the bot) is on
    2 - The nickname of the requester (i.e. the bot)
    3 - The channel holding the invite exempt list
    4 - A string containing some information; traditionally "End of Channel Invite List."

    """

    handle_endlistmode(cli, chan, "I")

### NICK handling

@hook("nick")
def on_nick_change(cli, old_rawnick, nick):
    """Handle a user changing nicks, which may be the bot itself.

    Ordering and meaning of arguments for a NICK change:

    0 - The IRCClient instance (like everywhere else)
    1 - The old (raw) nickname the user changed from
    2 - The new nickname the user changed to

    """

    user = users.get(old_rawnick, allow_bot=True, update=True)
    old_nick = user.nick
    user.nick = nick
    new_user = users.get(nick, user.ident, user.host, user.account, allow_bot=True)

    Event("nick_change", {}, old=user).dispatch(new_user, old_nick)

### ACCOUNT handling

@hook("account")
def on_account_change(cli, rawnick, account):
    """Handle a user changing accounts, if enabled.

    Ordering and meaning of arguments for an ACCOUNT change:

    0 - The IRCClient instance (like everywhere else)
    1 - The raw nick (nick!ident@host) of the user changing accounts
    2 - The account the user changed to

    We don't see our own account changes, so be careful!

    """

    user = users.get(rawnick, update=True)
    old_account = user.account
    user.account = account
    new_user = users.get(user.nick, user.ident, user.host, account, allow_bot=True)

    Event("account_change", {}, old=user).dispatch(new_user, old_account)

### JOIN handling

@hook("join")
def join_chan(cli, rawnick, chan, account=None, realname=None):
    """Handle a user joining a channel, which may be the bot itself.

    Ordering and meaning of arguments for a channel JOIN:

    0 - The IRCClient instance (like everywhere else)
    1 - The raw nick (nick!ident@host) of the user joining the channel
    2 - The channel the user joined

    The following two arguments are optional and only present if the
    server supports the extended-join capability (we will have requested
    it when we connected if it was supported):

    3 - The account the user is identified to, or "*" if none
    4 - The realname (gecos) of the user, or "" if none

    """

    if account == "*":
        account = NotLoggedIn

    if realname == "":
        realname = None

    ch = channels.add(chan, cli)

    user = users.get(nick=rawnick, account=account, allow_bot=True, allow_none=True, allow_ghosts=True, update=True)
    if user is None:
        user = users.add(cli, nick=rawnick, account=account)
    if account:
        # ensure we work for the case when user left, changed accounts, then rejoined as a different account
        user.account = account
        user = users.get(nick=rawnick, account=account)
    ch.users.add(user)
    user.channels[ch] = set()
    # mark the user as here, in case they used to be connected before but left
    user.disconnected = False

    Event("chan_join", {}).dispatch(ch, user)

    if user is users.Bot:
        ch.mode()
        ch.mode(Features["CHANMODES"][0])
        ch.who()

### PART handling

@hook("part")
def part_chan(cli, rawnick, chan, reason=""):
    """Handle a user leaving a channel, which may be the bot itself.

    Ordering and meaning of arguments for a channel PART:

    0 - The IRCClient instance (like everywhere else)
    1 - The raw nick (nick!ident@host) of the user leaving the channel
    2 - The channel being left

    The following argument may or may not be present:

    3 - The reason the user gave for parting (if any)

    """

    ch = channels.add(chan, cli)
    user = users.get(rawnick, allow_bot=True, update=True)
    Event("chan_part", {}).dispatch(ch, user, reason)

    if user is users.Bot: # oh snap! we're no longer in the channel!
        ch.clear()
    else:
        ch.remove_user(user)

### KICK handling

@hook("kick")
def kicked_from_chan(cli, rawnick, chan, target, reason):
    """Handle a user being kicked from a channel.

    Ordering and meaning of arguments for a channel KICK:

    0 - The IRCClient instance (like everywhere else)
    1 - The raw nick (nick!ident@host) of the user performing the kick
    2 - The channel the kick was performed on
    3 - The target of the kick
    4 - The reason given for the kick (always present)

    """

    ch = channels.add(chan, cli)
    actor = users.get(rawnick, allow_none=True, update=True)
    user = users.get(target, allow_bot=True)
    Event("chan_kick", {}).dispatch(ch, actor, user, reason)

    if user is users.Bot:
        ch.clear()
    else:
        ch.remove_user(user)

### QUIT handling

def quit(context, message=""):
    """Quit the bot from IRC."""

    cli = context.client

    if cli is None or cli.socket.fileno() < 0:
        transport_name = config.Main.get("transports[0].name")
        logger = logging.getLogger("transport.{}".format(transport_name))
        logger.warning("Socket is already closed. Exiting.")
        sys.exit(0)

    with cli:
        cli.send("QUIT :{0}".format(message))

@hook("quit")
def on_quit(cli, rawnick, reason):
    """Handle a user quitting the IRC server.

    Ordering and meaning of arguments for a server QUIT:

    0 - The IRCClient instance (like everywhere else)
    1 - The raw nick (nick!ident@host) of the user quitting
    2 - The reason for the quit (always present)

    """

    user = users.get(rawnick, allow_bot=True, update=True)
    user.disconnected = True
    Event("server_quit", {}).dispatch(user, reason)

    for chan in set(user.channels):
        if user is users.Bot:
            chan.clear()
        else:
            chan.remove_user(user)

### CHGHOST Handling

@hook("chghost")
def on_chghost(cli, rawnick, ident, host):
    """Handle a user changing host without a quit.

    Ordering and meaning of arguments for CHGHOST:

    0 - The IRCClient instance (like everywhere else)
    1 - The raw nick (nick!ident@host) of the user switching
    2 - The new ident for the user (or same if unchanged)
    3 - The new host for the user (or same if unchanged)

    """

    user = users.get(rawnick, allow_bot=True, update=True)
    old_ident = user.ident
    old_host = user.host
    # we avoid multiple swaps if we change the rawnick instead of ident and host separately
    new_rawnick = "{0}!{1}@{2}".format(user.nick, ident, host)
    user.rawnick = new_rawnick
    new_user = users.get(new_rawnick, allow_bot=True)

    Event("host_change", {}, old=user).dispatch(new_user, old_ident, old_host)
