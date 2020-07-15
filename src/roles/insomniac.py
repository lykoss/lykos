from src.functions import get_players, get_all_players, get_all_roles
from src.decorators import event_listener
from src.messages import messages
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

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    if var.NIGHT_COUNT == 1 or var.ALWAYS_PM_ROLE:
        for insomniac in get_all_players(("insomniac",)):
            insomniac.send(messages["insomniac_notify"])

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    pl = get_players()
    for insomniac in get_all_players(("insomniac",)):
        p1, p2 = _get_targets(var, pl, insomniac)
        p1_roles = get_all_roles(p1)
        p2_roles = get_all_roles(p2)
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
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["insomniac"] = {"Village", "Nocturnal"}
