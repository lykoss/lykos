from operator import attrgetter

from src.logger import debuglog

Features = {"CASEMAPPING": "rfc1459", "CHARSET": "utf-8", "STATUSMSG": {"@", "+"}, "CHANTYPES": {"#"}}

def lower(nick):
    if nick is None:
        return None
    if isinstance(nick, IRCContext):
        return nick.lower()

    mapping = {
        "[": "{",
        "]": "}",
        "\\": "|",
        "^": "~",
    }

    if Features["CASEMAPPING"] == "strict-rfc1459":
        mapping.pop("^")
    elif Features["CASEMAPPING"] == "ascii":
        mapping.clear()

    return nick.lower().translate(str.maketrans(mapping))

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

    def __init__(self, name, client, *, ref=None):
        self.name = name
        self.client = client
        self.ref = ref

    def lower(self):
        return type(self)(lower(name), client, ref=(self.ref or self))

    def get_send_type(self, *, is_notice=False, is_privmsg=False):
        if is_notice and not is_privmsg:
            return "NOTICE"
        return "PRIVMSG"

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

    @staticmethod
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

    def who(self, data=b""):
        """Send a WHO request with respect to the server's capabilities.

        To get the WHO replies, add an event listener for "who_result",
        and an event listener for "who_end" for the end of WHO replies.

        The return value of this function is an integer equal to the data
        given. If the server supports WHOX, the same integer will be in the
        event.params.data attribute. Otherwise, this attribute will be 0.

        """

        return self._who(self.client, self.name, data)

    @staticmethod
    def _send(data, client, send_type, name):
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

        for line in data.splitlines():
            while line:
                extra, line = line[:length], line[length:]
                client.send("{0} {1} :{2}".format(send_type, name, extra))

    def send(self, data, *, notice=False, privmsg=False, prefix=None):
        if self.is_fake:
            # Leave out 'fake' from the message; get_context_type() takes care of that
            debuglog("Would message {0} {1}: {2!r}".format(self.get_context_type(), self.name, data))
            return

        send_type = self.get_send_type(is_notice=notice, is_privmsg=privmsg)
        name = self.name
        if prefix is not None:
            name = prefix + name
        self._send(data, self.client, send_type, name)
