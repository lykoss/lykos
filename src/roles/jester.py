from __future__ import annotations

from typing import Optional

from src.cats import Category
from src.containers import UserSet
from src.events import Event, event_listener
from src.functions import get_all_players
from src.messages import messages
from src.gamestate import GameState
from src.users import User

JESTERS = UserSet()

@event_listener("day_vote")
def on_day_vote(evt: Event, var: GameState, votee, voters):
    if votee in get_all_players(var, ("jester",)):
        JESTERS.add(votee)

@event_listener("player_win")
def on_player_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: set[str], winner: Category, team_win: bool, survived: bool):
    if player in JESTERS:
        evt.data["individual_win"] = True

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for jester in get_all_players(var, ("jester",)):
        jester.send(messages["jester_notify"])

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    JESTERS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["jester"] = {"Neutral", "Innocent"}
