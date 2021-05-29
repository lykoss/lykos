from __future__ import annotations

import sys
from collections import defaultdict, OrderedDict
from operator import attrgetter
from typing import Dict, Any, ClassVar, List, Set, Optional, Tuple

import src.settings as var # FIXME
from src.messages.message import Message
from src.logger import debuglog

def _who(cli, target, data=b""):
    """Handle WHO requests."""

    if isinstance(data, str):
        data = data.encode(Features["CHARSET"])
    elif isinstance(data, int):
        if data > 0xFFFFFF:
            data = b""
        else:
            data = data.to_bytes(3, "little")

    if len(data) > 3:
        data = b""

    if "WHOX" in Features:
        cli.send("WHO", target, b"%tcuihsnfdlar," + data)
    else:
        cli.send("WHO", target)

    return int.from_bytes(data, "little")

def _send(data, first, sep, client, send_type, name, chan=None):
    full_address = "{cli.nickname}!{cli.ident}@{cli.hostmask}".format(cli=client)

    # Maximum length of sent data is 512 bytes. However, we have to
    # reduce the maximum length allowed to account for:
    # 1 (1) - The initial colon at the front of the data
    # 2 (1) - The space between the sender (us) and the command
    # 3 (1) - The space between the command and the target
    # 4 (1) - The space between the target and the data
    # 5 (1) - The colon at the front of the data to send
    # 6 (2) - The trailing \r\n
    length = 512 - 7
    # Next, we need to reduce the length to account for our address
    length -= len(full_address)
    # Then we also need to account for the target's length
    length -= len(name)
    # Finally, we need to account for the send type's length
    length -= len(send_type)
    # The 'first' argument is sent along with every message, so deduce that too
    if length - len(first) > 0: # make sure it's not negative (or worse, 0)
        length -= len(first)
    else:
        first = ""

    if chan and send_type.lower() in ("cprivmsg", "cnotice"):
        chan = chan.strip() + " "
        # if sending CPRIVMSG or CNOTICE, we need a channel parameter as well
        length -= len(chan)
    else:
        chan = ""

    messages = []
    count = 0
    for line in data:
        if count and count + len(sep) + len(line) > length:
            count = len(line)
            cur_sep = "\n"
        elif not messages:
            count = len(line)
            cur_sep = ""
        else:
            count += len(sep) + len(line)
            cur_sep = sep

        messages.append(cur_sep)
        messages.append(line)

    for line in "".join(messages).split("\n"):
        while line:
            extra, line = line[:length], line[length:]
            client.send("{0} {1} {4}:{2}{3}".format(send_type, name, first, extra, chan))

def lower(nick, *, casemapping=None):
    if nick is None:
        return None
    if isinstance(nick, IRCContext):
        return nick.lower()
    if casemapping is None:
        casemapping = Features["CASEMAPPING"]

    mapping = {
        "[": "{",
        "]": "}",
        "\\": "|",
        "^": "~",
    }

    if casemapping == "strict-rfc1459":
        mapping.pop("^")
    elif casemapping == "ascii":
        mapping.clear()

    return nick.lower().translate(str.maketrans(mapping))

def equals(nick1, nick2):
    return nick1 is not None and nick2 is not None and lower(nick1) == lower(nick2)

def context_types(*types):
    def wrapper(cls):
        cls._getters = l = []
        cls.is_fake = False
        for context_type in types:
            name = "is_" + context_type
            setattr(cls, name, False)
            l.append((context_type, attrgetter(name)))
        return cls
    return wrapper

@context_types("channel", "user")
class IRCContext:
    """Base class for channels and users."""

    _messages: Dict[str, List[IRCContext]] = defaultdict(list)

    is_fake: ClassVar[bool] = False

    def __init__(self, name, client):
        self.name = name
        self.client = client
        self.ref = None

    def __format__(self, format_spec):
        if not format_spec:
            return self.name
        raise ValueError("Format specifier {0} has undefined semantics".format(format_spec))

    def __eq__(self, other):
        return self._compare(other, __class__) # This will always return False

    def _compare(self, other, cls, *attributes):
        """Compare two instances and return a proper value."""
        if self is other:
            return True
        if not isinstance(other, cls):
            return NotImplemented

        done = False
        for attr in attributes:
            if getattr(self, attr) is None or getattr(other, attr) is None:
                continue
            done = True
            if getattr(self, attr) != getattr(other, attr):
                return False

        return done

    def lower(self):
        temp = type(self)(lower(self.name), self.client)
        temp.ref = self.ref or self
        return temp

    def get_send_type(self, *, is_notice=False, is_privmsg=False):
        if is_notice and not is_privmsg:
            return "NOTICE"
        return "PRIVMSG"

    def queue_message(self, message):
        if self.is_fake:
            self.send(message) # Don't actually queue it
            return

        if isinstance(message, list):
            message = tuple(message)

        self._messages[message].append(self)

    @classmethod
    def send_messages(cls, *, notice=False, privmsg=False):
        messages = list(cls._messages.items())
        cls._messages.clear()
        for message, targets in messages:
            if isinstance(message, Message):
                message = message.format()
            if isinstance(message, str):
                message = (message,)
            send_types = defaultdict(list)
            for target in targets:
                send_type = target.get_send_type(is_notice=notice, is_privmsg=privmsg)
                send_type, send_chan = target.use_cprivmsg(send_type)
                send_types[(send_type, send_chan)].append(target)
            for (send_type, send_chan), targets in send_types.items():
                max_targets = Features["TARGMAX"][send_type]
                while targets:
                    using, targets = targets[:max_targets], targets[max_targets:]
                    _send(message, "", " ", using[0].client, send_type, ",".join([t.nick for t in using]), send_chan)

    @classmethod
    def get_context_type(cls, *, max_types=1):
        context_type = []
        if cls.is_fake:
            context_type.append("fake")
        for name, getter in cls._getters:
            if getter(cls):
                context_type.append(name)

        final = " ".join(context_type)

        if len(context_type) > (cls.is_fake + max_types):
            raise RuntimeError("Invalid context type for {0}: {1!r}".format(cls.__name__, final))

        return final

    def who(self, data=b""):
        """Send a WHO request with respect to the server's capabilities.

        To get the WHO replies, add an event listener for "who_result",
        and an event listener for "who_end" for the end of WHO replies.

        The return value of this function is an integer equal to the data
        given. If the server supports WHOX, the same integer will be in the
        event.params.data attribute. Otherwise, this attribute will be 0.

        """

        return _who(self.client, self.name, data)

    def use_cprivmsg(self, send_type):
        if not self.is_user or var.DISABLE_CPRIVMSG: # FIXME: uses var
            return send_type, None

        # check if bot is opped in any channels shared with this user
        from src import users
        cprivmsg_eligible = None # type: Optional[IRCContext]
        op_modes = set()
        for status, mode in Features.PREFIX.items():
            op_modes.add(mode)
            if status == "@":
                break
        for chan in self.channels:
            if users.Bot.channels[chan] & op_modes:
                cprivmsg_eligible = chan
                break
        if cprivmsg_eligible:
            if send_type == "PRIVMSG" and Features.CPRIVMSG:
                return "CPRIVMSG", cprivmsg_eligible.name
            elif send_type == "NOTICE" and Features.CNOTICE:
                return "CNOTICE", cprivmsg_eligible.name
        return send_type, None

    def send(self, *data, first=None, sep=None, notice=False, privmsg=False, prefix=None):
        new = []
        for line in data:
            if isinstance(line, Message):
                line = line.format()
            new.append(line)
        if self.is_fake:
            # Leave out 'fake' from the message; get_context_type() takes care of that
            debuglog("Would message {0} {1}: {2!r}".format(self.get_context_type(), self.name, " ".join(new)))
            return

        send_type = self.get_send_type(is_notice=notice, is_privmsg=privmsg)
        send_type, send_chan = self.use_cprivmsg(send_type)

        name = self.name
        if prefix is not None:
            name = prefix + name
        if first is None:
            first = ""
        if sep is None:
            sep = " "
        _send(new, first, sep, self.client, send_type, name, send_chan)

class IRCFeatures:
    """Class to store features that the ircd supports."""
    # RPL_ISUPPORT and CAP can support more than what is listed here, we store all tokens into _features
    # even if we don't have a property that directly exposes it. A bot operator writing custom code can use
    # the generic get() and set() methods to retrieve and manipulate those values.
    # Note: we store whatever the ircd tells us, but normalize return values to what the bot expects
    _features = {} # type: Dict[str, Any]

    # RPL_ISUPPORT tokens

    @property
    def CASEMAPPING(self) -> str:
        value = self._features.get("CASEMAPPING", "rfc1459")
        if value not in ("rfc1459", "rfc1459-strict", "ascii"):
            value = "rfc1459"
        return value

    @CASEMAPPING.setter
    def CASEMAPPING(self, value: str):
        self._features["CASEMAPPING"] = value

    @property
    def CHANLIMIT(self) -> Dict[str, int]:
        limits = self._features.get("CHANLIMIT", {})
        value = {}
        for t in self.CHANTYPES:
            value[t] = limits.get(t, sys.maxsize)
            if value[t] is None:
                value[t] = sys.maxsize
        return value

    @CHANLIMIT.setter
    def CHANLIMIT(self, value: str):
        self._features["CHANLIMIT"] = {}
        parts = value.split(",")
        for part in parts:
            prefixes, limit_str = part.split(":")
            if limit_str == "":
                limit: Optional[int] = None
            else:
                limit = int(limit_str)
            for prefix in prefixes:
                self._features["CHANLIMIT"][prefix] = limit

    @property
    def CHANMODES(self) -> Tuple[str, str, str, str]:
        modes = self._features.get("CHANMODES", [])
        while len(modes) < 4:
            modes.append("")
        rA, rB, rC, rD = modes[:4]
        return (rA, rB, rC, rD)

    @CHANMODES.setter
    def CHANMODES(self, value: str):
        self._features["CHANMODES"] = value.split(",")

    @property
    def CHANTYPES(self) -> Set[str]:
        return self._features.get("CHANTYPES", set())

    @CHANTYPES.setter
    def CHANTYPES(self, value: str):
        self._features["CHANTYPES"] = set(value)

    @property
    def CHARSET(self) -> str:
        return self._features.get("CHARSET", "utf-8")

    @CHARSET.setter
    def CHARSET(self, value: str):
        self._features["CHARSET"] = value

    @property
    def CNOTICE(self) -> bool:
        return self._features.get("CNOTICE", False)

    @CNOTICE.setter
    def CNOTICE(self, value: str):
        self._features["CNOTICE"] = True

    @property
    def CPRIVMSG(self) -> bool:
        return self._features.get("CPRIVMSG", False)

    @CPRIVMSG.setter
    def CPRIVMSG(self, value: str):
        self._features["CPRIVMSG"] = True

    @property
    def EXCEPTS(self) -> Optional[str]:
        return self._features.get("EXCEPTS", None)

    @EXCEPTS.setter
    def EXCEPTS(self, value: str):
        if not value:
            value = "e"
        self._features["EXCEPTS"] = value

    @property
    def EXTBAN(self) -> Tuple[Optional[str], str]:
        return self._features.get("EXTBAN", (None, ""))

    @EXTBAN.setter
    def EXTBAN(self, value: str):
        prefix: Optional[str]
        prefix, types = value.split(",")
        if not prefix:
            prefix = None
        self._features["EXTBAN"] = (prefix, types)

    @property
    def INVEX(self) -> Optional[str]:
        return self._features.get("INVEX", None)

    @INVEX.setter
    def INVEX(self, value: str):
        if not value:
            value = "I"
        self._features["INVEX"] = value

    @property
    def MAXLIST(self) -> Dict[str, int]:
        limits = self._features.get("MAXLIST", {})
        value = {}
        for t in self.CHANMODES[0]:
            value[t] = limits.get(t, sys.maxsize)
        return value

    @MAXLIST.setter
    def MAXLIST(self, value: str):
        self._features["MAXLIST"] = {}
        parts = value.split(",")
        for part in parts:
            modes, limit = part.split(":")
            for mode in modes:
                self._features["MAXLIST"][mode] = int(limit)

    @property
    def MAXTARGETS(self) -> int:
        return self._features.get("MAXTARGETS", 1)

    @MAXTARGETS.setter
    def MAXTARGETS(self, value: str):
        self._features["MAXTARGETS"] = int(value)

    @property
    def MODES(self) -> int:
        return self._features.get("MODES", 1)

    @MODES.setter
    def MODES(self, value: str):
        self._features["MODES"] = int(value)

    @property
    def PREFIX(self) -> OrderedDict[str, str]:
        return self._features.get("PREFIX", OrderedDict())

    @PREFIX.setter
    def PREFIX(self, value: str):
        self._features["PREFIX"] = OrderedDict()
        if not value:
            return
        modes, prefixes = value.split(")", maxsplit=1)
        modes = modes[1:] # remove leading (
        for i in range(len(modes)):
            self._features["PREFIX"][prefixes[i]] = modes[i]

    @property
    def STATUSMSG(self) -> Set[str]:
        value = self._features.get("STATUSMSG", set())
        return value & self.PREFIX.keys()

    @STATUSMSG.setter
    def STATUSMSG(self, value: str):
        self._features["STATUSMSG"] = set(value)

    @property
    def TARGMAX(self) -> IRCTargMaxFeature:
        return self._features.get("TARGMAX", IRCTargMaxFeature(self))

    @TARGMAX.setter
    def TARGMAX(self, value: str):
        self._features["TARGMAX"] = IRCTargMaxFeature(self, value)

    @property
    def WHOX(self) -> bool:
        return self._features.get("WHOX", False)

    @WHOX.setter
    def WHOX(self, value: str):
        self._features["WHOX"] = True

    # CAP capabilities

    @property
    def account_notify(self) -> bool:
        return self._features.get("account-notify", False)

    @account_notify.setter
    def account_notify(self, value: str):
        self._features["account-notify"] = True

    @property
    def account_tag(self) -> bool:
        return self._features.get("account-tag", False)

    @account_tag.setter
    def account_tag(self, value: str):
        self._features["account-tag"] = True

    @property
    def away_notify(self) -> bool:
        return self._features.get("away-notify", False)

    @away_notify.setter
    def away_notify(self, value: str):
        self._features["away-notify"] = True

    @property
    def batch(self) -> bool:
        return self._features.get("batch", False)

    @batch.setter
    def batch(self, value: str):
        self._features["batch"] = True

    @property
    def chghost(self) -> bool:
        return self._features.get("chghost", False)

    @chghost.setter
    def chghost(self, value: str):
        self._features["chghost"] = True

    @property
    def extended_join(self) -> bool:
        return self._features.get("extended-join", False)

    @extended_join.setter
    def extended_join(self, value: str):
        self._features["extended-join"] = True

    @property
    def labeled_response(self) -> bool:
        return self._features.get("labeled-response", False)

    @labeled_response.setter
    def labeled_response(self, value: str):
        self._features["labeled-response"] = True

    @property
    def message_tags(self) -> bool:
        return self._features.get("message-tags", False)

    @message_tags.setter
    def message_tags(self, value: str):
        self._features["message-tags"] = True

    @property
    def multi_prefix(self) -> bool:
        return self._features.get("multi-prefix", False)

    @multi_prefix.setter
    def multi_prefix(self, value: str):
        self._features["multi-prefix"] = True

    @property
    def sasl(self) -> Optional[str]:
        return self._features.get("sasl", None)

    @sasl.setter
    def sasl(self, value: str):
        self._features["sasl"] = value

    @property
    def userhost_in_names(self) -> bool:
        return self._features.get("userhost-in-names", False)

    @userhost_in_names.setter
    def userhost_in_names(self, value: str):
        self._features["userhost-in-names"] = True

    # General-purpose methods to view and manipulate data

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            return self._features[item]

    def __setitem__(self, key: str, value: str):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self._features[key] = value

    def __contains__(self, item: str) -> bool:
        return item in self._features

    def __str__(self) -> str:
        return "IRCFeatures(" + str(self._features) + ")"

    def __repr__(self) -> str:
        return "IRCFeatures(" + repr(self._features) + ")"

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def set(self, key: str, value: str):
        self[key] = value

    def unset(self, key: str):
        del self._features[key]

class IRCTargMaxFeature:
    def __init__(self, features: IRCFeatures, value: Optional[str] = None):
        self._features = features
        self._commands = {} # type: Dict[str, int]

    def __getitem__(self, item: str) -> int:
        item = item.lower()
        if item in self._commands:
            value = self._commands[item]
        elif item in ("privmsg", "notice"):
            value = self._features.MAXTARGETS
        else:
            value = 1
        return value

    def __str__(self) -> str:
        return "IRCTargMaxFeature(" + str(self._commands) + ")"

    def __repr__(self) -> str:
        return "IRCTargMaxFeature(" + repr(self._commands) + ")"

Features = IRCFeatures()
