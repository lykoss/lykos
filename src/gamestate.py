from __future__ import annotations
import typing

__all__ = ["GameState"]

class GameState:
    pass

# expose user containers for type checking purposes
# putting it at the end avoids the type checker choking on the import loop
if typing.TYPE_CHECKING:
    from src.users import User
    from src.containers import UserSet, UserDict, UserList
