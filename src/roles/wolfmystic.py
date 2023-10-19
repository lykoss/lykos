from typing import Optional

from src.events import Event, event_listener
from src.gamestate import GameState
from src.roles.helper.mystics import register_mystic
from src.roles.helper.wolves import register_wolf

register_mystic("wolf mystic", send_role=False, types=("Safe", "Win Stealer", "Vampire Team"))
register_wolf("wolf mystic")

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["wolf mystic"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Intuitive", "Village Objective", "Wolf Objective", "Evil"}
