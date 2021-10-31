from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from src import status
from src.events import Event, event_listener
from src.functions import get_all_players
from src.roles.helper.wolves import register_wolf

if TYPE_CHECKING:
    from src.gamestate import GameState
    from src.users import User

register_wolf("fallen angel")

@event_listener("try_protection")
def on_try_protection(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, reason: str):
    if attacker_role == "wolf" and get_all_players(var, ("fallen angel",)):
        status.remove_all_protections(var, target, attacker=attacker, attacker_role="fallen angel", reason="fallen_angel")
        evt.prevent_default = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["fallen angel"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Village Objective", "Wolf Objective"}
