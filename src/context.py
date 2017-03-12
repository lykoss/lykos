from collections import defaultdict
from operator import attrgetter

from src.logger import debuglog

Features = {"CASEMAPPING": "rfc1459", "CHARSET": "utf-8", "STATUSMSG": {"@", "+"}, "CHANTYPES": {"#"}, "TARGMAX": {"PRIVMSG": 1, "NOTICE": 1}}

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

def _send(data, first, sep, client, send_type, name):
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
            client.send("{0} {1} :{2}{3}".format(send_type, name, first, extra))

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

    _messages = defaultdict(list)

    def __init__(self, name, client):
        self.name = name
        self.client = client
        self.ref = None

    def __format__(self, format_spec=""):
        if not format_spec:
            return self.name
        raise ValueError("Format specificer {0} has undefined semantics".format(format_spec))

    def __eq__(self, other):
        return self._compare(other, __class__) # This will always return False

    def _compare(self, other, cls, *attributes):
        """Compare two instances and return a proper value."""
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
        temp = type(self)(lower(name), client)
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
        for message, targets in cls._messages.items():
            if isinstance(message, str):
                message = (message,)
            send_types = defaultdict(list)
            for target in targets:
                send_types[target.get_send_type(is_notice=notice, is_privmsg=privmsg)].append(target)
            for send_type, targets in send_types.items():
                max_targets = Features["TARGMAX"][send_type]
                while targets:
                    using, targets = targets[:max_targets], targets[max_targets:]
                    _send(message, "", " ", using[0].client, send_type, ",".join([t.nick for t in using]))

        cls._messages.clear()

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

    def send(self, *data, first=None, sep=None, notice=False, privmsg=False, prefix=None):
        if self.is_fake:
            # Leave out 'fake' from the message; get_context_type() takes care of that
            debuglog("Would message {0} {1}: {2!r}".format(self.get_context_type(), self.name, " ".join(data)))
            return

        send_type = self.get_send_type(is_notice=notice, is_privmsg=privmsg)
        name = self.name
        if prefix is not None:
            name = prefix + name
        if first is None:
            first = ""
        if sep is None:
            sep = " "
        _send(data, first, sep, self.client, send_type, name)
