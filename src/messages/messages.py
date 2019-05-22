import json
import os

import src.settings as var
from src.messages.message import Message

MESSAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "messages")
ROOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..")


class Messages:
    def __init__(self):
        self.lang = var.LANGUAGE
        self._load_messages()

    def get(self, key):
        if not self.messages[key]:
            raise KeyError("Key {0!r} does not exist! Add it to messages.json".format(key))
        return Message(key, self.messages[key])

    __getitem__ = get

    def raw(self, *args):
        m = self.messages
        for key in args:
            m = m[key]

        return m

    def _load_messages(self):
        with open(os.path.join(MESSAGES_DIR, self.lang + ".json"), encoding="utf-8") as f:
            self.messages = json.load(f)

        fallback = self.messages["_metadata"]["fallback"]
        seen = {self.lang}
        while fallback is not None:
            if fallback in seen:
                raise TypeError("Fallback loop detected")
            seen.add(fallback)
            with open(os.path.join(MESSAGES_DIR, fallback + ".json"), encoding="utf-8") as f:
                fallback_msgs = json.load(f)
                fallback = self.messages["_metadata"]["fallback"]
                for key, message in fallback_msgs.items():
                    if key not in self.messages:
                        self.messages[key] = message

        if not os.path.isfile(os.path.join(ROOT_DIR, "messages.json")):
            return
        with open(os.path.join(ROOT_DIR, "messages.json"), encoding="utf-8") as f:
            custom_msgs = json.load(f)

        if not custom_msgs:
            return

        for key, message in custom_msgs.items():
            if key in self.messages:
                if isinstance(self.messages[key], dict):
                    if not isinstance(message, dict):
                        raise TypeError("messages.json: Key {0!r} must be of type dict".format(key))
                    self.messages[key].update(message)
                elif isinstance(self.messages[key], list):
                    if not isinstance(message, (list, dict)):
                        raise TypeError("messages.json: Key {0!r} must be of type list or dict (with merge_strategy and value keys)".format(key))

                    if isinstance(message, list):
                        self.messages[key] = message
                    elif message["merge_strategy"] == "extend":
                        self.messages[key].extend(message["value"])
                    elif message["merge_strategy"] == "replace":
                        self.messages[key] = message["value"]
                else:
                    if not isinstance(message, type(self.messages[key])):
                        raise TypeError("messages.json: Key {0!r} must be of type {1!r}".format(key, type(
                            self.messages[key]).__name__))
                    self.messages[key] = message
            else:
                self.messages[key] = message
