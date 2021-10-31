from typing import Optional

from src import status
from src.events import Event, event_listener
from src.functions import get_all_players
from src.gamestate import GameState
from src.messages import messages


@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for blessed in get_all_players(var, ("blessed villager",)):
        status.add_protection(var, blessed, blessed, "blessed villager")
        if not var.setup_completed or var.always_pm_role:
            blessed.send(messages["blessed_notify"])

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user):
    if user in var.roles["blessed villager"]:
        evt.data["messages"].append(messages["blessed_myrole"])

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["blessed villager"] = {"Village", "Innocent"}
