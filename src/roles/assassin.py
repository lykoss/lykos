from __future__ import annotations

import re
from typing import Optional

from src import channels, users
from src.containers import UserSet, UserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_reveal_role, get_target
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange, try_protection, add_dying, is_silent
from src.users import User
from src.random import random

TARGETED: UserDict[users.User, users.User] = UserDict()
PREV_ACTED = UserSet()

@command("target", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("assassin",))
def target_cmd(wrapper: MessageDispatcher, message: str):
    """Pick a player as your target, killing them if you die."""
    if wrapper.source in PREV_ACTED:
        wrapper.send(messages["assassin_already_targeted"])
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0])
    if not target:
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    TARGETED[wrapper.source] = target

    wrapper.send(messages["assassin_target_success"].format(orig))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["nightroles"].extend(get_all_players(var, ("assassin",)) - PREV_ACTED)
    evt.data["acted"].extend(TARGETED.keys() - PREV_ACTED)

@event_listener("transition_day_resolve")
def on_transition_day_resolve(evt: Event, var: GameState, dead: set[User], killers):
    # Select a random target for assassin if they didn't target
    pl = set(get_players(var)) - dead
    for ass in get_all_players(var, ("assassin",)):
        if ass not in TARGETED and not is_silent(var, ass):
            ps = list(pl - {ass})
            if ps:
                target = random.choice(ps)
                TARGETED[ass] = target
                ass.send(messages["assassin_random"].format(target))
    PREV_ACTED.update(TARGETED.keys())

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for ass in get_all_players(var, ("assassin",)):
        if ass in TARGETED:
            continue # someone already targeted

        pl = get_players(var)
        random.shuffle(pl)
        pl.remove(ass)

        ass_evt = Event("assassin_target", {"target": None})
        ass_evt.dispatch(var, ass, pl)

        if ass_evt.data["target"] is not None:
            TARGETED[ass] = ass_evt.data["target"]
            PREV_ACTED.add(ass)
        else:
            ass.send(messages["assassin_notify"])
            if var.next_phase == "night":
                ass.send(messages["players_list"].format(pl))

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    if player in TARGETED.values():
        for x, y in list(TARGETED.items()):
            if y is player:
                del TARGETED[x]
                PREV_ACTED.discard(x)

    if death_triggers and "assassin" in all_roles and player in TARGETED:
        target = TARGETED[player]
        del TARGETED[player]
        PREV_ACTED.discard(player)
        if target in get_players(var):
            protected = try_protection(var, target, player, "assassin", "assassin_fail")
            if protected is not None:
                channels.Main.send(*protected)
                return
            to_send = "assassin_success_no_reveal"
            if var.role_reveal in ("on", "team"):
                to_send = "assassin_success"
            channels.Main.send(messages[to_send].format(player, target, get_reveal_role(var, target)))
            add_dying(var, target, killer_role=evt.params.main_role, reason="assassin", killer=player)

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user):
    if user in get_all_players(var, ("assassin",)):
        if user in TARGETED:
            evt.data["messages"].append(messages["assassin_targeting"].format(TARGETED[user]))
        else:
            evt.data["messages"].append(messages["assassin_no_target"])

@event_listener("revealroles_role")
def on_revealroles_role(evt: Event, var: GameState, user, role):
    if role == "assassin" and user in TARGETED:
        evt.data["special_case"].append(messages["assassin_revealroles"].format(TARGETED[user]))

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    TARGETED.clear()
    PREV_ACTED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["assassin"] = {"Village"}
