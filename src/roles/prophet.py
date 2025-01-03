from __future__ import annotations

from typing import Optional

from src import gamestate
from src.containers import UserSet
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, match_role
from src.messages import messages
from src.dispatcher import MessageDispatcher
from src.random import random

class GameState(gamestate.GameState):
    def __init__(self):
        self.prophet_prayed = UserSet()

@command("pray", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("prophet",))
def pray(wrapper: MessageDispatcher, message: str):
    """Receive divine visions of who has a role."""
    var: GameState = wrapper.game_state

    if wrapper.source in var.prophet_prayed:
        wrapper.pm(messages["already_prayed"])
        return

    if not message:
        wrapper.pm(messages["not_enough_parameters"])
        return

    # complete this as a match with other roles (so "cursed" can match "cursed villager" for instance)
    matches = match_role(message, allow_special=False)
    if len(matches) == 0:
        wrapper.pm(messages["no_such_role"].format(message))
        return
    elif len(matches) > 1:
        wrapper.pm(messages["ambiguous_role"].format([m.singular for m in matches]))
        return

    role = matches.get().key
    pl = get_players(var)
    var.prophet_prayed.add(wrapper.source)

    # this sees through amnesiac, so the amnesiac's final role counts as their role
    from src.roles.amnesiac import ROLES as amn_roles
    people = set(get_all_players(var, (role,))) | {p for p, r in amn_roles.items() if p in pl and r == role}
    if len(people) == 0:
        # role is not in this game, this still counts as a successful activation of the power!
        wrapper.pm(messages["vision_none"].format(role))
        return

    target = random.choice(list(people))
    part = random.sample([p for p in pl if p is not wrapper.source], len(pl) // 3)
    if target not in part:
        part[0] = target
    random.shuffle(part)

    if len(part) == 1:
        wrapper.pm(messages["vision_role"].format(role, target))
    else:
        wrapper.pm(messages["vision_players"].format(role, part))

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for pht in get_all_players(var, ("prophet",)):
        pht.send(messages["prophet_notify"])

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["nightroles"].extend(get_all_players(var, ("prophet",)))
    evt.data["acted"].extend(var.prophet_prayed)

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    var.prophet_prayed.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["prophet"] = {"Village", "Safe", "Nocturnal", "Spy"}
