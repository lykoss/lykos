from typing import Optional

from src import channels
from src.containers import UserSet
from src.events import Event, event_listener
from src.functions import get_all_players
from src.gamestate import GameState
from src.messages import messages
from src.status import add_lynch_immunity
from src.users import User

REVEALED_MAYORS = UserSet()

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    for user in get_all_players(var, ("mayor",)):
        if user not in REVEALED_MAYORS:
            add_lynch_immunity(var, user, "mayor")

@event_listener("lynch_immunity")
def on_lynch_immunity(evt: Event, var: GameState, user: User, reason: str):
    if reason == "mayor":
        channels.Main.send(messages["mayor_reveal"].format(user))
        evt.data["immune"] = True
        REVEALED_MAYORS.add(user)

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    REVEALED_MAYORS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["mayor"] = {"Village", "Safe"}
