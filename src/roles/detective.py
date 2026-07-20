from __future__ import annotations

import re
from typing import Optional

from src import config
from src.cats import Safe, Wolfteam
from src.containers import UserSet
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_players, get_main_role, get_target
from src.messages import messages
from src.roles.helper.wolves import get_wolfchat_roles
from src.status import try_misdirection, try_exchange
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState
from src.users import User
from src.random import random

INVESTIGATED = UserSet()

@command("id", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("detective",))
async def investigate(wrapper: MessageDispatcher, message: str):
    """Investigate a player to determine their exact role."""
    if wrapper.source in INVESTIGATED:
        wrapper.send(messages["already_investigated"])
        return

    var = wrapper.game_state

    target = await get_target(wrapper, re.split(" +", message)[0], not_self_message="no_investigate_self")
    if target is None:
        return

    target = try_misdirection(var, wrapper.source, target)
    if await try_exchange(var, wrapper.source, target):
        return

    targrole = await get_main_role(var, target)

    evt = Event("spy", {"role": targrole})
    await evt.dispatch(var, wrapper.source, target, "detective")
    targrole = evt.data["role"]

    INVESTIGATED.add(wrapper.source)
    wrapper.send(messages["investigate_success"].format(target, targrole))

    if random.randrange(0, 100) < config.Main.get("gameplay.safes.detective_reveal"):  # a 2/5 chance (changeable in settings)
        # The detective's identity is compromised! Let the wolves know
        if await get_main_role(var, wrapper.source) in Wolfteam:
            to_notify = get_players(var, Safe)
        else:
            to_notify = get_players(var, get_wolfchat_roles())
            
        if to_notify:
            for player in to_notify:
                player.queue_message(messages["detective_reveal"].format(wrapper.source))
            await User.send_messages()

@event_listener("del_player")
async def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    INVESTIGATED.discard(player)

@event_listener("new_role")
async def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "detective" and evt.data["role"] != "detective":
        INVESTIGATED.discard(player)

@event_listener("send_role")
async def on_send_role(evt: Event, var: GameState):
    ps = get_players(var)
    for dttv in var.roles["detective"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(dttv)
        chance = config.Main.get("gameplay.safes.detective_reveal")

        dttv.send(messages["detective_notify"])
        if chance > 0:
            dttv.send(messages["detective_chance"].format(chance))
        dttv.send(messages["players_list"].format(pl))

@event_listener("transition_night_begin")
async def on_transition_night_begin(evt: Event, var: GameState):
    INVESTIGATED.clear()

@event_listener("reset")
async def on_reset(evt: Event, var: GameState):
    INVESTIGATED.clear()

@event_listener("get_role_metadata")
async def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["detective"] = {"Village", "Spy", "Safe"}
