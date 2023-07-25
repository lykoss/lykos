from __future__ import annotations

from typing import TYPE_CHECKING

from enum import Enum

from src.users import User
from src.containers import UserDict, UserList

if TYPE_CHECKING:
    from src.gamestate import GameState

class Location:
    """Base class for locations."""
    def __init__(self, var: GameState, name: str):
        self._gs = var
        self.name = name
        self.users: UserDict[User, tuple[str | None, bool]] = UserDict()

    def __contains__(self, item):
        return item in self.users

    def __iter__(self):
        return iter(self.users)

    def __len__(self):
        return len(self.users)

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def _teardown(self):
        """Method for subclasses to define if needed."""

    def teardown(self):
        assert self._gs.tearing_down, "cannot tear down locations from outside of GameState.teardown()"
        self._teardown()
        self.name = "<DELETED>"
        self.users.clear()

class Square(Location):
    def __init__(self, var: GameState):
        super().__init__(var, "Village Square")

class Graveyard(Location):
    def __init__(self, var: GameState):
        super().__init__(var, "Graveyard")

class House(Location):
    def __init__(self, var: GameState, player: User, pos: int):
        super().__init__(var, f"{player.account}'s house")
        self._owner = UserList([player])
        self.pos = pos

    @property
    def owner(self) -> User:
        return self._owner[0]

    def _teardown(self):
        self._owner.clear()
