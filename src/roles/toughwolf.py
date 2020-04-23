from src import channels
from src.messages import messages
from src.decorators import event_listener
from src.containers import UserSet
from src.functions import get_all_players, get_all_roles
from src.status import add_lynch_immunity
from src.roles.helper.wolves import register_wolf

ACTIVATED = UserSet()

register_wolf("tough wolf")

@event_listener("reset")
def on_reset(evt, var):
    ACTIVATED.clear()

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    for player in get_all_players(("tough wolf",)):
        if player not in ACTIVATED:
            add_lynch_immunity(var, player, "tough_wolf")

@event_listener("lynch_immunity")
def on_lynch_immunity(evt, var, player, reason):
    if reason == "tough_wolf":
        channels.Main.send(messages["tough_wolf_reveal"].format(player))
        evt.data["immune"] = True
        ACTIVATED.add(player)

@event_listener("gun_shoot")
def on_gun_shoot(evt, var, user, target, role):
    if "tough wolf" in get_all_roles(target):
        evt.data["kill"] = False

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["tough wolf"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal"}
