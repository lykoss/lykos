from __future__ import annotations

from typing import Optional

from src.events import Event, event_listener
from src.functions import get_all_players
from src.gamestate import GameState
from src.messages import messages
from src.users import User
from src.random import random

HIT_CHANCE       = -5/20
HEADSHOT_CHANCE  = -3/20
EXPLODE_CHANCE   = 1/20
SHOTS_MULTIPLIER = 3

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for drunk in get_all_players(var, ("village drunk",)):
        drunk.send(messages["village_drunk_notify"])

@event_listener("assassin_target")
def on_assassin_target(evt: Event, var: GameState, assassin: User, players: list[User]):
    if evt.data["target"] is None and assassin in get_all_players(var, ("village drunk",)):
        evt.data["target"] = random.choice(players)
        assassin.send(messages["drunken_assassin_notification"].format(evt.data["target"]))

@event_listener("gun_chances")
def on_gun_chances(evt: Event, var: GameState, user: User, role: str):
    if user in get_all_players(var, ("village drunk",)):
        evt.data["hit"] += HIT_CHANCE
        evt.data["headshot"] += HEADSHOT_CHANCE
        evt.data["explode"] += EXPLODE_CHANCE

@event_listener("gun_bullets")
def on_gun_bullets(evt: Event, var: GameState, user: User, role: str):
    if user in get_all_players(var, ("village drunk",)):
        evt.data["bullets"] *= SHOTS_MULTIPLIER

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["village drunk"] = {"Village", "Safe"}
