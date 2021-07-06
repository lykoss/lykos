from typing import Optional

from src.gamestate import GameState
from src.events import Event, event_listener
from src.roles.helper.wolves import register_wolf

register_wolf("wolf")

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["wolf"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Village Objective", "Wolf Objective"}
