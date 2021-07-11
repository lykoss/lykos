from typing import Union

from src import channels, config, users
from src.functions import get_players

class MessageDispatcher:
    """Dispatcher class for raw IRC messages."""

    def __init__(self, source: users.User, target: Union[channels.Channel, users.BotUser]):
        self.source = source
        self.target = target
        self.client = source.client

    @property
    def game_state(self):
        # lazy evaluation means replacing the target doesn't break things
        return self.target.game_state

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
            first = "{0}: ".format(self.source)
        if self.private:
            self.source.send(*messages, **kwargs)
        elif (self.target is channels.Main and self.game_state is not None and 
                (self.source not in get_players(self.game_state) or
                (config.Main.get("gameplay.nightchat") and self.game_state.PHASE == "night"))):
            # TODO: ideally the above check would be handled in game logic somehow
            # (perhaps via an event) rather than adding game logic to the transport layer
            kwargs.setdefault("notice", True)
            self.source.send(*messages, **kwargs)
        else:
            kwargs.setdefault("first", first)
            self.target.send(*messages, **kwargs)
