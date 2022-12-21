from typing import Optional

from src.functions import get_players, get_all_players, get_all_roles
from src.gamestate import GameState
from src.messages import messages
from src.events import Event, event_listener
from src.status import is_awake

def _get_targets(var: GameState, pl, user):
    index = var.players.index(user)
    num_players = len(var.players)
    # determine left player
    i = index
    while True:
        i = (i - 1) % num_players
        if var.players[i] in pl or var.players[i] is user:
            target1 = var.players[i]
            break
    # determine right player
    i = index
    while True:
        i = (i + 1) % num_players
        if var.players[i] in pl or var.players[i] is user:
            target2 = var.players[i]
            break

    return target1, target2

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    if not var.setup_completed or var.always_pm_role:
        for insomniac in get_all_players(var, ("insomniac",)):
            insomniac.send(messages["insomniac_notify"])

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    if var.night_count == 0 and var.start_with_day: # starting with day
        return
    pl = get_players(var)
    for insomniac in get_all_players(var, ("insomniac",)):
        p1, p2 = _get_targets(var, pl, insomniac)
        p1_awake = is_awake(var, p1)
        p2_awake = is_awake(var, p2)
        if p1_awake and p2_awake:
            # both of the players next to the insomniac were awake last night
            insomniac.send(messages["insomniac_both_awake"].format(p1, p2))
        elif p1_awake:
            insomniac.send(messages["insomniac_awake"].format(p1))
        elif p2_awake:
            insomniac.send(messages["insomniac_awake"].format(p2))
        else:
            # both players next to the insomniac were asleep all night
            insomniac.send(messages["insomniac_asleep"].format(p1, p2))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["insomniac"] = {"Village", "Nocturnal"}
