import json
import os

import src.settings as var

MESSAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "messages")
ROOT_DIR = os.path.join(os.path.dirname(__file__), "..")

class Messages:
    def __init__ (self):
        self.lang = var.LANGUAGE
        self._load_messages()

    def get(self, key):
        if not self.messages[key.lower()]:
            raise KeyError("Key {0!r} does not exist! Add it to messages.json".format(key))
        return self.messages[key.lower()]

    __getitem__ = get

    def _load_messages(self):
        with open(os.path.join(MESSAGES_DIR, self.lang + ".json")) as f:
            self.messages = json.load(f)

        if not os.path.isfile(os.path.join(ROOT_DIR, "messages.json")):
            return
        with open(os.path.join(ROOT_DIR, "messages.json")) as f:
            custom_msgs = json.load(f)

        if not custom_msgs:
            return

        for key, message in custom_msgs.items():
            if key in self.messages:
                if not isinstance(message, type(self.messages[key.lower()])):
                    raise TypeError("messages.json: Key {0!r} must be of type {1!r}".format(key, type(self.messages[key.lower()]).__name__))
            self.messages[key.lower()] = message

messages = Messages()

# Because woffle is needy
# vim: set sw=4 expandtab:
