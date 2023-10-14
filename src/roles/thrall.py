from __future__ import annotations

from typing import Optional

from src.functions import get_players
from src.gamestate import GameState
from src.messages import messages
from src.events import Event, event_listener
from src.users import User
from src.cats import Hidden

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    if not var.setup_completed or var.always_pm_role:
        send_roles = {"thrall"}
        if var.hidden_role == "thrall":
            send_roles |= Hidden
        thralls = get_players(var, send_roles)
        for thrall in thralls:
            thrall.queue_message(messages["thrall_notify"])
        User.send_messages()

@event_listener("chk_win", priority=3)
def on_chk_win(evt: Event,
               var: GameState,
               role_map: dict[str, set[User]],
               main_roles: dict[User, str],
               num_players: int,
               num_wolves: int,
               num_real_wolves: int,
               num_vampires: int):
    if evt.data["winner"] is not None or num_wolves > 0:
        return
    if num_vampires == num_players / 2:
        evt.data["winner"] = "vampires"
        evt.data["message"] = messages["vampire_win_equal"]
    elif num_vampires > num_players / 2:
        evt.data["winner"] = "vampires"
        evt.data["message"] = messages["vampire_win_greater"]

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["thrall"] = {"Vampire Team"}
