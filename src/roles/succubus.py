from __future__ import annotations

import random
import re
from typing import Optional, Union

from src import users
from src.containers import UserSet, UserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_reveal_role, get_target
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange, is_dead
from src.users import User

ENTRANCED = UserSet()
VISITED: UserDict[users.User, users.User] = UserDict()
PASSED = UserSet()
FORCE_PASSED = UserSet()
ALL_SUCC_IDLE = True

@command("visit", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("succubus",))
def hvisit(wrapper: MessageDispatcher, message: str):
    """Entrance a player, converting them to your team."""
    if VISITED.get(wrapper.source):
        wrapper.send(messages["succubus_already_visited"].format(VISITED[wrapper.source]))
        return

    if wrapper.source in FORCE_PASSED:
        wrapper.send(messages["already_being_visited"])
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="succubus_not_self")
    if not target:
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    VISITED[wrapper.source] = target
    PASSED.discard(wrapper.source)
    house = var.players.index(target)
    var.locations[wrapper.source] = f"house_{house}"

    if target not in get_all_players(var, ("succubus",)):
        ENTRANCED.add(target)
        wrapper.send(messages["succubus_target_success"].format(target))
    else:
        wrapper.send(messages["harlot_success"].format(target))

    if wrapper.source is not target:
        if target not in get_all_players(var, ("succubus",)):
            target.send(messages["notify_succubus_target"].format(wrapper.source))
        else:
            target.send(messages["harlot_success"].format(wrapper.source))

        revt = Event("visit", {})
        revt.dispatch(var, "succubus", wrapper.source, target)

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("succubus",))
def pass_cmd(wrapper: MessageDispatcher, message: str):
    """Do not entrance someone tonight."""
    if VISITED.get(wrapper.source):
        wrapper.send(messages["succubus_already_visited"].format(VISITED[wrapper.source]))
        return

    PASSED.add(wrapper.source)
    wrapper.send(messages["succubus_pass"])

@event_listener("visit")
def on_visit(evt: Event, var: GameState, visitor_role: str, visitor: User, visited: User):
    if visited in get_all_players(var, ("succubus",)):
        # if we're being visited by anyone and we haven't visited yet, we have to stay home with them
        if visited not in VISITED:
            FORCE_PASSED.add(visited)
            PASSED.add(visited)
            visited.send(messages["already_being_visited"])

        # if we're being visited by a non-succubus, entrance them
        if visitor_role != "succubus":
            visitor.send(messages["notify_succubus_target"].format(visited))
            visited.send(messages["succubus_harlot_success"].format(visitor))
            ENTRANCED.add(visitor)

# entranced logic should run after team wins have already been determined (aka run last)
# FIXME: I hate event priorities and want them to die in a fire
@event_listener("team_win", priority=7)
def on_team_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: set[str], winner: str):
    if player in ENTRANCED and winner != "succubi":
        evt.data["team_win"] = False
    if main_role == "succubus" and winner == "succubi":
        evt.data["team_win"] = True

@event_listener("player_win")
def on_player_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: set[str], winner: str, team_win: bool, survived: bool):
    if player in ENTRANCED:
        evt.data["special"].append("entranced")
        if winner == "succubi":
            evt.data["individual_win"] = True

@event_listener("chk_win", priority=2)
def on_chk_win(evt: Event, var: GameState, rolemap: dict[str, set[User]], mainroles: dict[User, str], lpl: int, lwolves: int, lrealwolves: int):
    lsuccubi = len(rolemap.get("succubus", ()))
    lentranced = len([x for x in ENTRANCED if not is_dead(var, x)])
    if var.current_phase == "day" and lsuccubi and lpl - lsuccubi == lentranced:
        evt.data["winner"] = "succubi"
        evt.data["message"] = messages["succubus_win"].format(lsuccubi)
    elif not lsuccubi and lentranced and var.current_phase == "day" and lpl == lentranced:
        evt.data["winner"] = "succubi"
        evt.data["message"] = messages["entranced_win"]

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "succubus" and evt.data["role"] != "succubus":
        del VISITED[:player:]
        PASSED.discard(player)
        FORCE_PASSED.discard(player)

    if evt.data["role"] == "succubus" and player in ENTRANCED:
        ENTRANCED.remove(player)
        player.send(messages["no_longer_entranced"])

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    global ALL_SUCC_IDLE
    if "succubus" not in all_roles:
        return
    if player in VISITED:
        # if it's night, also unentrance the person they visited
        if var.current_phase == "night" and not var.in_phase_transition:
            if VISITED[player] in ENTRANCED:
                ENTRANCED.discard(VISITED[player])
                VISITED[player].send(messages["entranced_revert_win"])
        del VISITED[player]

    PASSED.discard(player)
    FORCE_PASSED.discard(player)

    # if all succubi idled out (every last one of them), un-entrance people
    # death_triggers is False for an idle-out, so we use that to determine which it is
    if death_triggers:
        ALL_SUCC_IDLE = False
    if ALL_SUCC_IDLE and not get_all_players(var, ("succubus",)):
        while ENTRANCED:
            e = ENTRANCED.pop()
            e.send(messages["entranced_revert_win"])

@event_listener("night_death_message")
def on_night_death_message(evt: Event, var: GameState, victim: User, killer: Union[User, str]):
    if killer == "@wolves" and victim in VISITED:
        evt.data["key"] = "visited_victim" if var.role_reveal in ("on", "team") else "visited_victim_no_reveal"

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(VISITED)
    evt.data["acted"].extend(PASSED)
    evt.data["nightroles"].extend(get_all_players(var, ("succubus",)))

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    succubi = get_all_players(var, ("succubus",))
    role_map = messages.get_role_mapping()
    for succubus in succubi:
        pl = get_players(var)
        random.shuffle(pl)
        pl.remove(succubus)
        succ = []
        for p in pl:
            if p in succubi:
                succ.append("{0} ({1})".format(p, role_map["succubus"]))
            else:
                succ.append(p.nick)
        succubus.send(messages["succubus_notify"], messages["players_list"].format(succ), sep="\n")

@event_listener("gun_shoot")
def on_gun_shoot(evt: Event, var: GameState, user: User, target: User, role: str):
    if target in get_all_players(var, ("succubus",)):
        evt.data["kill"] = False

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    VISITED.clear()
    PASSED.clear()
    FORCE_PASSED.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    global ALL_SUCC_IDLE
    ALL_SUCC_IDLE = True
    ENTRANCED.clear()
    VISITED.clear()
    PASSED.clear()
    FORCE_PASSED.clear()

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if ENTRANCED:
        evt.data["output"].append(messages["entranced_revealroles"].format(ENTRANCED))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["succubus"] = {"Neutral", "Win Stealer", "Cursed", "Nocturnal"}
