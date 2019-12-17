from typing import Generic, Iterable, TypeVar

__all__ = ["Match"]

T = TypeVar("T")

class Match(Generic[T]):
    def __init__(self, matches: Iterable[T]):
        self._matches = list(matches)

    def __bool__(self) -> bool:
        return len(self._matches) == 1

    def __len__(self) -> int:
        return len(self._matches)

    def __iter__(self) -> Iterable[T]:
        return iter(self._matches)

    def get(self) -> T:
        if len(self._matches) != 1:
            raise ValueError("Can only call get on a match with a single result")
        return self._matches[0]
