from __future__ import annotations

import random
from typing import Set, Optional, TYPE_CHECKING

from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.events import Event, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.cats import Wolf

if TYPE_CHECKING:
    from src.users import User

RECEIVED_INFO = UserSet()
KNOWS_MINIONS = UserSet()

def wolf_list(var: GameState):
    wolves = [wolf.nick for wolf in get_all_players(var, Wolf)]
    random.shuffle(wolves)
    return messages["wolves_list"].format(", ".join(wolves))

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for minion in get_all_players(var, ("minion",)):
        if minion in RECEIVED_INFO and not var.always_pm_role:
            continue
        minion.send(messages["minion_notify"])
        minion.send(wolf_list(var))
        RECEIVED_INFO.add(minion)

@event_listener("transition_night_end")
def on_transition_night_end(evt: Event, var: GameState):
    minions = len(get_all_players(var, ("minion",)))
    if minions == 0:
        return
    wolves = get_all_players(var, Wolf) - KNOWS_MINIONS
    for wolf in wolves:
        wolf.send(messages["has_minions"].format(minions))
        KNOWS_MINIONS.add(wolf)

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role is not None and evt.data["role"] == "minion":
        evt.data["messages"].append(wolf_list(var))
        RECEIVED_INFO.add(player)

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user: User):
    if user in get_all_players(var, ("minion",)):
        wolves = []
        for wolfrole in Wolf:
            for player in var.ORIGINAL_ROLES[wolfrole]:
                wolves.append(player)
        evt.data["messages"].append(messages["original_wolves"].format(wolves))

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    RECEIVED_INFO.clear()
    KNOWS_MINIONS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["minion"] = {"Wolfteam", "Intuitive"}
