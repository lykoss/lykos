from typing import Iterator, TypeVar, Optional, Set
import collections.abc
from src import config
from src.debug.history import History

__all__ = ["CheckedSet"]

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)

class CheckedSet(collections.abc.MutableSet):
    """ Set container with additional features to aid in debugging.

    Common mutation methods are exposed to more easily set breakpoints,
    and a history of mutations can be enabled to track when and where the
    collection was modified in the past.
    """

    def __new__(cls, name: str, iterable: Optional[Iterator[T_co]] = None):
        if not config.Main.get("debug.enabled"):
            if iterable is None:
                return set()
            else:
                return set(iterable)

        return super().__new__(cls)

    def __init__(self, name: str, iterable: Optional[Iterator[T_co]] = None):
        self._history = History(name)
        if iterable is None:
            self._set = set() # type: Set[T]
        else:
            self._set = set(iterable) # type: Set[T]

    def __iter__(self) -> Iterator[T_co]:
        return iter(self._set)

    def __len__(self) -> int:
        return len(self._set)

    def __contains__(self, x: object) -> bool:
        return x in self._set

    def __format__(self, format_spec: str) -> str:
        return format(self._set, format_spec)

    def __str__(self) -> str:
        return str(self._set)

    def __repr__(self) -> str:
        return repr(self._set)

    def clear(self) -> None:
        self._history.add("clear")
        self._set.clear()

    def discard(self, x: T) -> None:
        self._history.add("discard", x)
        self._set.discard(x)

    def add(self, x: T) -> None:
        self._history.add("add", x)
        self._set.add(x)
