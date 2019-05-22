# Setup: the formatter needs to be ready when we import the messages
from src.messages.formatter import Formatter
message_formatter = Formatter()

from src.messages.messages import Messages

__all__ = ["messages", "message_formatter"]

messages = Messages()

def get_role_name(name, *, number=1):
    """Return the localized and potentially pluralized role name."""
    role = message_formatter.convert_field(name, "role")
    return message_formatter._plural(role, number)
