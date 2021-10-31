from __future__ import annotations

import re
import typing

from src import users
from src.containers import UserDict
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_all_players, get_target
from src.messages import messages
from src.roles.helper.wolves import is_known_wolf_ally, send_wolfchat_message, register_wolf
from src.status import try_misdirection, try_exchange, add_silent

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.gamestate import GameState
    from src.users import User
    from typing import Optional

register_wolf("hag")

HEXED: UserDict[users.User, users.User] = UserDict()
LASTHEXED: UserDict[users.User, users.User] = UserDict()

@command("hex", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hag",))
def hex_cmd(wrapper: MessageDispatcher, message: str):
    """Hex someone, preventing them from acting the next day and night."""
    if wrapper.source in HEXED:
        wrapper.pm(messages["already_hexed"])
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0])
    if not target:
        return

    if LASTHEXED.get(wrapper.source) is target:
        wrapper.pm(messages["no_multiple_hex"].format(target))
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["no_hex_wolf"])
        return

    HEXED[wrapper.source] = target

    wrapper.pm(messages["hex_success"].format(target))

    send_wolfchat_message(var, wrapper.source, messages["hex_success_wolfchat"].format(wrapper.source, target), {"hag"}, role="hag", command="hex")

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, allroles: set[str], death_triggers: bool):
    del LASTHEXED[:player:]

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(HEXED)
    evt.data["nightroles"].extend(get_all_players(var, ("hag",)))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt: Event, var: GameState):
    HEXED.clear()

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    LASTHEXED.clear()
    for hag, target in HEXED.items():
        LASTHEXED[hag] = target
        add_silent(var, target)

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "hag" and evt.data["role"] != "hag":
        del HEXED[:player:]
        del LASTHEXED[:player:]

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    LASTHEXED.clear()
    HEXED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["hag"] = {"Wolfchat", "Wolfteam", "Nocturnal", "Wolf Objective"}
