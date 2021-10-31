from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from src.events import Event, event_listener
from src.functions import get_all_players
from src.messages import messages

if TYPE_CHECKING:
    from src.gamestate import GameState
    from src.users import User

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for demoniac in get_all_players(var, ("demoniac",)):
        demoniac.send(messages["demoniac_notify"])

# monster is at priority 4, and we want demoniac to take precedence
@event_listener("chk_win", priority=4.1) # FIXME: Kill the priorities
def on_chk_win(evt: Event, var: GameState, rolemap: dict[str, set[User]], mainroles: dict[User, str], lpl: int, lwolves: int, lrealwolves: int):
    demoniacs = len(rolemap.get("demoniac", ()))
    traitors = len(rolemap.get("traitor", ()))
    cubs = len(rolemap.get("wolf cub", ()))

    if not lrealwolves and not traitors and not cubs and demoniacs:
        evt.data["message"] = messages["demoniac_win"].format(demoniacs)
        evt.data["winner"] = "demoniacs"

@event_listener("team_win")
def on_team_win(evt: Event, var: GameState, player, main_role, all_roles, winner):
    if main_role == "demoniac" and winner == "demoniacs":
        evt.data["team_win"] = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["demoniac"] = {"Neutral", "Win Stealer"}
