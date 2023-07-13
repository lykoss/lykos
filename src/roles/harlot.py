from __future__ import annotations

import random
import re
from typing import Optional, Union

from src import users
from src.cats import Wolf
from src.containers import UserSet, UserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.locations import Reason
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.users import User

VISITED: UserDict[users.User, users.User] = UserDict()
PASSED = UserSet()
FORCE_PASSED = UserSet()

@command("visit", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("harlot",))
def hvisit(wrapper: MessageDispatcher, message: str):
    """Visit a player. You will die if you visit a wolf or a target of the wolves."""
    if VISITED.get(wrapper.source):
        wrapper.pm(messages["harlot_already_visited"].format(VISITED[wrapper.source]))
        return

    if wrapper.source in FORCE_PASSED:
        wrapper.pm(messages["already_being_visited"])
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="harlot_not_self")
    if not target:
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    VISITED[wrapper.source] = target
    PASSED.discard(wrapper.source)
    var.set_user_location(wrapper.source, var.find_house(target), Reason.visiting)

    wrapper.pm(messages["harlot_success"].format(target))
    if target is not wrapper.source:
        target.send(messages["harlot_success"].format(wrapper.source))
        revt = Event("visit", {})
        revt.dispatch(var, "harlot", wrapper.source, target)

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("harlot",))
def pass_cmd(wrapper: MessageDispatcher, message: str):
    """Do not visit someone tonight."""
    if VISITED.get(wrapper.source):
        wrapper.pm(messages["harlot_already_visited"].format(VISITED[wrapper.source]))
        return

    PASSED.add(wrapper.source)
    wrapper.pm(messages["no_visit"])

@event_listener("visit")
def on_visit(evt: Event, var: GameState, visitor_role: str, visitor: User, visited: User):
    if visited in get_all_players(var, ("harlot",)):
        # if we're being visited by anyone and we haven't visited yet, we have to stay home with them
        if visited not in VISITED:
            FORCE_PASSED.add(visited)
            PASSED.add(visited)
            visited.send(messages["already_being_visited"])

@event_listener("night_kills")
def on_night_kills(evt: Event, var: GameState):
    wolves = get_players(var, Wolf)
    for harlot, target in VISITED.items():
        if target in wolves:
            evt.data["victims"].add(harlot)
            evt.data["killers"][harlot].append("@wolves")

@event_listener("night_death_message")
def on_night_death_message(evt: Event, var: GameState, victim: User, killer: Union[User, str]):
    if killer == "@wolves" and victim in VISITED:
        if VISITED[victim] in get_players(var, Wolf):
            evt.data["key"] = "harlot_visited_wolf"
        else:
            evt.data["key"] = "visited_victim" if var.role_reveal in ("on", "team") else "visited_victim_no_reveal"

@event_listener("retribution_kill")
def on_retribution_kill(evt: Event, var: GameState, victim: User, loser: User):
    if VISITED.get(victim) in get_players(var, Wolf):
        evt.data["target"] = VISITED[victim]

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(VISITED)
    evt.data["acted"].extend(PASSED)
    evt.data["nightroles"].extend(get_all_players(var, ("harlot",)))

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "harlot" and evt.data["role"] != "harlot":
        PASSED.discard(player)
        FORCE_PASSED.discard(player)
        if player in VISITED:
            VISITED.pop(player).send(messages["harlot_disappeared"].format(player))

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for harlot in get_all_players(var, ("harlot",)):
        pl = get_players(var)
        random.shuffle(pl)
        pl.remove(harlot)
        harlot.send(messages["harlot_notify"])
        if var.next_phase == "night":
            harlot.send(messages["players_list"].format(pl))

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    VISITED.clear()
    PASSED.clear()
    FORCE_PASSED.clear()

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    if "harlot" not in all_roles:
        return
    del VISITED[:player:]
    PASSED.discard(player)
    FORCE_PASSED.discard(player)

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    VISITED.clear()
    PASSED.clear()
    FORCE_PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["harlot"] = {"Village", "Safe", "Nocturnal"}
    elif kind == "lycanthropy_role":
        evt.data["harlot"] = {"prefix": "harlot"}
