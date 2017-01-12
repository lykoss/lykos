from src import channels, users
from src import settings as var

from src.utilities import list_players

class MessageDispatcher:
    """Dispatcher class for raw IRC messages."""

    def __init__(self, source, target):
        self.source = source
        self.target = target
        self.client = source.client

    @property
    def private(self):
        return self.target is users.Bot

    @property
    def public(self):
        return self.target is not users.Bot

    def pm(self, *messages, **kwargs):
        """Send a private message or notice to the sender."""
        kwargs.setdefault("notice", self.public)
        self.source.send(*messages, **kwargs)

    def send(self, *messages, **kwargs):
        """Send a message to the channel or a private message."""
        if self.private:
            self.pm(*messages, **kwargs)
        else:
            self.target.send(*messages, **kwargs)

    def reply(self, *messages, prefix_nick=False, **kwargs):
        """Reply to the user, either in channel or privately."""
        first = ""
        if prefix_nick:
            first = "{0}: ".format(self.source.nick)
        if self.private:
            self.source.send(*messages, **kwargs)
        elif (self.target is channels.Main and
                ((self.source.nick not in list_players() and var.PHASE in var.GAME_PHASES) or
                (var.DEVOICE_DURING_NIGHT and var.PHASE == "night"))): # FIXME
            kwargs.setdefault("notice", True)
            self.source.send(*messages, **kwargs)
        else:
            kwargs.setdefault("first", first)
            self.target.send(*messages, **kwargs)
