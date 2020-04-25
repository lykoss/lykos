import random

from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.cats import Wolf

RECEIVED_INFO = UserSet()
KNOWS_MINIONS = UserSet()

def wolf_list(var):
    wolves = [wolf.nick for wolf in get_all_players(Wolf)]
    random.shuffle(wolves)
    return messages["wolves_list"].format(", ".join(wolves))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end2(evt, var):
    for minion in get_all_players(("minion",)):
        if minion in RECEIVED_INFO and not var.ALWAYS_PM_ROLE:
            continue
        minion.send(messages["minion_notify"])
        minion.send(wolf_list(var))
        RECEIVED_INFO.add(minion)

@event_listener("transition_night_end", priority=3)
def on_transition_night_end3(evt, var):
    minions = len(get_all_players(("minion",)))
    if minions == 0:
        return
    wolves = get_all_players(Wolf) - KNOWS_MINIONS
    for wolf in wolves:
        wolf.send(messages["has_minions"].format(minions))
        KNOWS_MINIONS.add(wolf)

@event_listener("new_role")
def on_new_role(evt, var, player, old_role):
    if old_role is not None and evt.data["role"] == "minion":
        evt.data["messages"].append(wolf_list(var))
        RECEIVED_INFO.add(player)

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in get_all_players(("minion",)):
        wolves = []
        for wolfrole in Wolf:
            for player in var.ORIGINAL_ROLES[wolfrole]:
                wolves.append(player)
        evt.data["messages"].append(messages["original_wolves"].format(wolves))

@event_listener("reset")
def on_reset(evt, var):
    RECEIVED_INFO.clear()
    KNOWS_MINIONS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["minion"] = {"Wolfteam", "Intuitive"}
