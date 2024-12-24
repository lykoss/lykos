from typing import Optional

from src.events import Event, event_listener
from src.gamestate import GameState
from src.roles.helper.mystics import register_mystic

register_mystic("mystic", send_role=True, types=("Evil", "Win Stealer"))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["mystic"] = {"Village", "Safe", "Intuitive"}
