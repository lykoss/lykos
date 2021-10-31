from typing import Optional

from src.events import Event, event_listener
from src.gamestate import GameState
from src.roles.helper.gunners import setup_variables

HIT_CHANCE       = 1/1
HEADSHOT_CHANCE  = 1/1
EXPLODE_CHANCE   = 0/1
SHOTS_MULTIPLIER = 0.06

GUNNERS = setup_variables("sharpshooter", hit=HIT_CHANCE, headshot=HEADSHOT_CHANCE, explode=EXPLODE_CHANCE, multiplier=SHOTS_MULTIPLIER)

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["sharpshooter"] = {"Village", "Safe", "Killer"}
