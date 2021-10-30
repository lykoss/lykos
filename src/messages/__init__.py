from typing import Optional, Any
from abc import ABC, abstractmethod

# Setup: the formatter needs to be ready when we import the messages
from src.messages.formatter import Formatter
message_formatter = Formatter()

from src.messages import _messages
from src.messages.message import Message

__all__ = ["messages", "message_formatter",
           "LocalRole", "LocalMode", "LocalTotem"]

messages = _messages.Messages()

class LocalKeyValueWrapper(ABC):
    def __init__(self, key: str, custom: Any):
        self._key = key
        self._custom = custom

    def __hash__(self):
        return hash((self._key, self._custom))

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self._key == other._key and self._custom == other._custom

    def __str__(self):
        return self.local

    @property
    def key(self) -> str:
        return self._key

    @property
    @abstractmethod
    def local(self) -> str:
        pass

class LocalRole(LocalKeyValueWrapper):
    def __init__(self, key: str, singular: Optional[str] = None, plural: Optional[str] = None):
        super().__init__(key, (singular, plural))
        self._singular = singular
        self._plural = plural

    def _resolve(self, number: int) -> str:
        return Message("*", "{0!role:plural({1})}").format(self.key, number)

    @property
    def local(self) -> str:
        return self.singular

    @property
    def singular(self) -> str:
        if self._singular is None:
            self._singular = self._resolve(number=1)
        return self._singular

    @property
    def plural(self) -> str:
        if self._plural is None:
            self._plural = self._resolve(number=2)
        return self._plural

class LocalMode(LocalKeyValueWrapper):
    def __init__(self, key: str, local: Optional[str] = None):
        super().__init__(key, local)
        self._local = local

    @property
    def local(self) -> str:
        if self._local is None:
            self._local = Message("*", "{0!mode}").format(self.key)
        return self._local

class LocalTotem(LocalKeyValueWrapper):
    def __init__(self, key: str, local: Optional[str] = None):
        super().__init__(key, local)
        self._local = local

    @property
    def local(self) -> str:
        if self._local is None:
            self._local = Message("*", "{0!totem}").format(self.key)
        return self._local
