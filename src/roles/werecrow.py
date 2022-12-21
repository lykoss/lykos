from __future__ import annotations

import re
from typing import Optional

from src import users
from src.containers import UserDict
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_all_players, get_target
from src.messages import messages
from src.roles.helper.wolves import is_known_wolf_ally, send_wolfchat_message, register_wolf
from src.status import try_misdirection, try_exchange, is_awake
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState
from src.trans import NIGHT_IDLE_EXEMPT
from src.users import User

register_wolf("werecrow")

OBSERVED: UserDict[users.User, users.User] = UserDict()

@command("observe", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("werecrow",))
def observe(wrapper: MessageDispatcher, message: str):
    """Observe a player to see whether they are able to act at night."""
    if wrapper.source in OBSERVED:
        wrapper.pm(messages["werecrow_already_observing"].format(OBSERVED[wrapper.source]))
        return
    var = wrapper.game_state
    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="werecrow_no_observe_self")
    if not target:
        return
    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["werecrow_no_target_wolf"])
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    OBSERVED[wrapper.source] = target
    wrapper.pm(messages["werecrow_observe_success"].format(orig))
    send_wolfchat_message(var, wrapper.source, messages["wolfchat_observe"].format(wrapper.source, target), {"werecrow"}, role="werecrow", command="observe")

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    for crow, target in OBSERVED.items():
        # if any of target's roles (primary or secondary) are Nocturnal, we see them as awake
        if is_awake(var, target):
            crow.send(messages["werecrow_success"].format(target))
        else:
            crow.send(messages["werecrow_failure"].format(target))

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    OBSERVED.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    OBSERVED.clear()

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(OBSERVED)
    evt.data["nightroles"].extend(get_all_players(var, ("werecrow",)))

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    del OBSERVED[:player:]
    for crow, target in list(OBSERVED.items()):
        if target is player:
            NIGHT_IDLE_EXEMPT.add(crow)
            del OBSERVED[crow]

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    # remove the observation if they're turning from a crow into a not-crow
    if old_role == "werecrow" and evt.data["role"] != "werecrow":
        OBSERVED.pop(player, None)

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["werecrow"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Spy", "Village Objective", "Wolf Objective"}
