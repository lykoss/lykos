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
        cultroles = {"cultist"}
        if var.hidden_role == "cultist":
            cultroles |= Hidden
        cultists = get_players(var, cultroles)
        if cultists:
            for cultist in cultists:
                cultist.queue_message(messages["cultist_notify"])
            User.send_messages()

@event_listener("chk_win", priority=3)
def on_chk_win(evt: Event, var: GameState, rolemap: dict[str, set[User]], mainroles: dict[User, str], lpl: int, lwolves: int, lrealwolves: int, lvampires: int):
    if evt.data["winner"] is not None or lvampires > 0:
        return
    if lwolves == lpl / 2:
        evt.data["winner"] = "wolves"
        evt.data["message"] = messages["wolf_win_equal"]
    elif lwolves > lpl / 2:
        evt.data["winner"] = "wolves"
        evt.data["message"] = messages["wolf_win_greater"]

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["cultist"] = {"Wolfteam"}
