from typing import Optional

from src.cats import Wolfchat
from src.events import Event, event_listener
from src.functions import get_all_players, get_main_role
from src.gamestate import GameState
from src.messages import messages
from src.users import User

@event_listener("see")
def on_see(evt: Event, var: GameState, seer, target):
    if target in var.roles["cursed villager"]:
        evt.data["role"] = "wolf"

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["cursed villager"] = {"Village", "Cursed"}

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    cursed = get_all_players(var, ("cursed villager",))
    from src.roles.helper.wolves import is_known_wolf_ally
    for player in cursed:
        if get_main_role(var, player) == "cursed villager" or is_known_wolf_ally(var, player, player):
            player.send(messages["cursed_notify"])

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, player: User):
    from src.roles.helper.wolves import is_known_wolf_ally
    if not is_known_wolf_ally(var, player, player):
        evt.data["secondary"].discard("cursed villager")
