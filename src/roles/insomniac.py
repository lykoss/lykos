from typing import Optional

from src.functions import get_players, get_all_players, get_all_roles
from src.gamestate import GameState
from src.messages import messages
from src.events import Event, event_listener
from src.cats import Nocturnal

def _get_targets(var, pl, user):
    index = var.ALL_PLAYERS.index(user)
    num_players = len(var.ALL_PLAYERS)
    # determine left player
    i = index
    while True:
        i = (i - 1) % num_players
        if var.ALL_PLAYERS[i] in pl or var.ALL_PLAYERS[i] is user:
            target1 = var.ALL_PLAYERS[i]
            break
    # determine right player
    i = index
    while True:
        i = (i + 1) % num_players
        if var.ALL_PLAYERS[i] in pl or var.ALL_PLAYERS[i] is user:
            target2 = var.ALL_PLAYERS[i]
            break

    return (target1, target2)

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    if not var.ROLES_SENT or var.always_pm_role:
        for insomniac in get_all_players(var, ("insomniac",)):
            insomniac.send(messages["insomniac_notify"])

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    if var.NIGHT_COUNT == 0: # starting with day
        return
    pl = get_players(var)
    for insomniac in get_all_players(var, ("insomniac",)):
        p1, p2 = _get_targets(var, pl, insomniac)
        p1_roles = get_all_roles(var, p1)
        p2_roles = get_all_roles(var, p2)
        if p1_roles & Nocturnal and p2_roles & Nocturnal:
            # both of the players next to the insomniac were awake last night
            insomniac.send(messages["insomniac_both_awake"].format(p1, p2))
        elif p1_roles & Nocturnal:
            insomniac.send(messages["insomniac_awake"].format(p1))
        elif p2_roles & Nocturnal:
            insomniac.send(messages["insomniac_awake"].format(p2))
        else:
            # both players next to the insomniac were asleep all night
            insomniac.send(messages["insomniac_asleep"].format(p1, p2))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["insomniac"] = {"Village", "Nocturnal"}
