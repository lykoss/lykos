from typing import Generic, Iterable, Iterator, TypeVar, Optional

__all__ = ["Match", "match_all", "match_one"]

T = TypeVar("T")

class Match(Iterable[T], Generic[T]):
    def __init__(self, matches: Iterable[T]):
        self._matches = list(matches)

    def __bool__(self) -> bool:
        return len(self._matches) == 1

    def __len__(self) -> int:
        return len(self._matches)

    def __iter__(self) -> Iterator[T]:
        return iter(self._matches)

    def get(self) -> T:
        if len(self._matches) != 1:
            raise ValueError("Can only call get on a match with a single result")
        return self._matches[0]

def match_all(search: str, scope: Iterable[str]) -> Match[str]:
    """ Retrieve all items that begin with a search term.

    :param search: Term to search for (prefix)
    :param scope: Items to search for matches
    :return: Match object constructed as follows:
        If search exactly equals an item in scope, it will be the only returned value.
        Otherwise, all items that begin with search will be returned.
    """
    found = set()
    for item in scope:
        if search == item:
            found = {item}
            break
        if item.startswith(search):
            found.add(item)
    return Match(found)

def match_one(search: str, scope: Iterable[str]) -> Optional[str]:
    """ Retrieve a single item that begins with the search term.

    :param search: Term to search for (prefix)
    :param scope: Items to search for matches
    :return: If search matches exactly one item (as per the return value of match_all),
        returns that item. Otherwise, returns None.
    """
    m = match_all(search, scope)
    return m.get() if m else None
