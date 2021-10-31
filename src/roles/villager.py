from __future__ import annotations

from typing import Optional

from src.cats import Hidden
from src.events import Event, event_listener
from src.functions import get_players
from src.gamestate import GameState
from src.messages import messages
from src.users import User


@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    if not var.setup_completed or var.always_pm_role:
        villroles = {"villager"}
        if var.hidden_role == "villager":
            villroles |= Hidden
        villagers = get_players(var, villroles)
        if villagers:
            for villager in villagers:
                villager.queue_message(messages["villager_notify"])
            User.send_messages()

@event_listener("chk_win", priority=3)
def on_chk_win(evt: Event, var: GameState, rolemap: dict[str, set[User]], mainroles: dict[User, str], lpl: int, lwolves: int, lrealwolves: int):
    if evt.data["winner"] is not None:
        return
    if lrealwolves == 0:
        evt.data["winner"] = "villagers"
        evt.data["message"] = messages["villager_win"]

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["villager"] = {"Village"}
