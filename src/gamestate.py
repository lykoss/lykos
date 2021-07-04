from __future__ import annotations
import typing

from src.containers import UserSet, UserDict, UserList
from src.cats import All

if typing.TYPE_CHECKING:
    from src.users import User
    from typing import FrozenSet, Set, Tuple

__all__ = ["GameState"]

class PregameState:
    def __init__(self):
        pass

    @property
    def in_game(self):
        return False

class GameState:
    def __init__(self, pregame_state: PregameState):
        self.setup_completed = False
        self._roles:     UserDict[str, UserSet]          = UserDict()
        self._rolestats: Set[FrozenSet[Tuple[str, int]]] = set()

    def setup(self):
        if self.setup_completed:
            raise RuntimeError("GameState.setup() called while already setup")
        for role in All:
            self._roles[role] = UserSet()
        self.setup_completed = True

    def teardown(self):
        self._roles.clear()

    @property
    def in_game(self):
        return self.setup_completed

    @property
    def ROLES(self):
        return self._roles

    def get_role_stats(self) -> FrozenSet[FrozenSet[Tuple[str, int]]]:
        return frozenset(self._rolestats)

    def set_role_stats(self, value) -> None:
        self._rolestats.clear()
        self._rolestats.update(value)

    def del_role_stats(self) -> None:
        self._rolestats.clear()

    ROLE_STATS = property(get_role_stats, set_role_stats, del_role_stats, "Manipulate and return the current valid role sets")


