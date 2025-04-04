from typing import Optional

from src.events import Event, event_listener
from src.gamestate import GameState
from src.roles.helper.wolves import register_wolf

register_wolf("cult leader")

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        # lack of Wolf Objective category is intentional;
        # despite having wolfchat access they are treated like cultist for determining wolf win condition
        evt.data["cult leader"] = {"Wolfchat", "Wolfteam", "Evil"}
