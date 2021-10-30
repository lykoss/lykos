from typing import Optional

from src.events import Event, event_listener, find_listener
from src.functions import get_players, get_all_players
from src.gamestate import GameState
from src.messages import messages
from src.users import User

from src.roles.helper.gunners import setup_variables
from src.roles.helper.wolves import register_wolf, is_known_wolf_ally

HIT_CHANCE       = 7/10
HEADSHOT_CHANCE  = 6/10
EXPLODE_CHANCE   = 0/10
SHOTS_MULTIPLIER = 0.06

register_wolf("wolf gunner")
GUNNERS = setup_variables("wolf gunner", hit=HIT_CHANCE, headshot=HEADSHOT_CHANCE, explode=EXPLODE_CHANCE, multiplier=SHOTS_MULTIPLIER)
# unregister the gunner night message and send the number of bullets a different way
find_listener("send_role", "gunners.<wolf gunner>.on_send_role").remove("send_role")
# wolf gunners don't shoot other wolves at night nor get their gun stolen
find_listener("transition_day_resolve_end", "gunners.<wolf gunner>.on_transition_day_resolve_end").remove("transition_day_resolve_end")

@event_listener("wolf_notify")
def on_wolf_notify(evt: Event, var: GameState, role: str):
    if role != "wolf gunner":
        return
    gunners = get_all_players(var, ("wolf gunner",))
    for gunner in gunners:
        if GUNNERS[gunner] or var.always_pm_role:
            gunner.send(messages["gunner_bullets"].format(GUNNERS[gunner]))

@event_listener("gun_shoot")
def on_gun_shoot(evt: Event, var: GameState, player: User, target: User, role: str):
    if role == "wolf gunner" and is_known_wolf_ally(var, player, target):
        evt.data["hit"] = False

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["wolf gunner"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Village Objective", "Wolf Objective"}
