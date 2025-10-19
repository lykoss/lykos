from __future__ import annotations

import re
from typing import Optional

from src import users
from src.cats import All, Wolfteam, Vampire_Team, Win_Stealer, get_team, Category
from src.containers import UserDict, UserSet
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_players, get_target, get_all_roles
from src.messages import messages
from src.status import try_misdirection, add_silent, is_silent
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState
from src.users import User
from src.random import random

KILLS: UserDict[users.User, users.User] = UserDict()
GHOSTS: UserDict[users.User, str] = UserDict()
TARGETS: UserDict[users.User, UserSet] = UserDict()

# temporary holding variable, only non-empty during transition_day
drivenoff: UserDict[users.User, str] = UserDict()

@command("kill", chan=False, pm=True, playing=False, silenced=True, phases=("night",), users=GHOSTS)
def vg_kill(wrapper: MessageDispatcher, message: str):
    """Take revenge on someone each night after you die."""
    if GHOSTS[wrapper.source][0] == "!":
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0])
    if not target:
        return

    if target is wrapper.source:
        wrapper.pm(messages["player_dead"])
        return

    if target not in TARGETS[wrapper.source]:
        # keys: vengeful_ghost_wolf vengeful_ghost_villager
        wrapper.pm(messages["vengeful_ghost_{0}".format(GHOSTS[wrapper.source])])
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)

    KILLS[wrapper.source] = target

    wrapper.pm(messages["player_kill"].format(orig))

@command("retract", chan=False, pm=True, playing=False, phases=("night",))
def vg_retract(wrapper: MessageDispatcher, message: str):
    """Removes a vengeful ghost's kill selection."""
    if wrapper.source not in GHOSTS:
        return

    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        wrapper.pm(messages["retracted_kill"])

@event_listener("get_participants")
def on_get_participants(evt: Event, var: GameState):
    evt.data["players"].extend([p for p in GHOSTS if GHOSTS[p][0] != "!"])
    evt.data["players"].extend(drivenoff)

@event_listener("consecrate")
def on_consecrate(evt: Event, var: GameState, actor: User, target: User):
    if target in GHOSTS:
        add_silent(var, target)

@event_listener("gun_shoot")
def on_gun_shoot(evt: Event, var: GameState, user: User, target: User, role: str):
    if evt.data["hit"] and "vengeful ghost" in get_all_roles(var, target):
        # VGs automatically die if hit by a gun to make gunner a bit more dangerous in some modes
        evt.data["kill"] = True
        
@event_listener("team_win")
def on_team_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: set[str], winner: Category):
    # VG wins as long as an actual team (not a win stealer) won and the team they are against lost
    if player in GHOSTS and not evt.params.is_win_stealer:
        against = GHOSTS[player].lstrip("!")
        against_team = get_team(var, against)
        evt.data["team_win"] = winner is not against_team

@event_listener("player_win")
def on_player_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: set[str], winner: Category, team_win: bool, survived: bool):
    if player in GHOSTS:
        evt.data["special"].append("vg activated")
        if GHOSTS[player][0] == "!":
            evt.data["special"].append("vg driven off")
        elif team_win:
            # VG gets an individual win while dead if they haven't been driven off and their team wins
            evt.data["individual_win"] = True

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    for ghost, victim in list(KILLS.items()):
        if player is victim:
            ghost.send(messages["hunter_discard"])
            del KILLS[ghost]
    del KILLS[:player:]

    for targets in TARGETS.values():
        targets.discard(player)
    del TARGETS[:player:]

    if death_triggers and "vengeful ghost" in all_roles and player not in GHOSTS:
        if evt.params.killer_role in Wolfteam:
            GHOSTS[player] = "wolf"
        elif evt.params.killer_role in Vampire_Team:
            GHOSTS[player] = "vampire"
        else:
            GHOSTS[player] = "villager"
        player.send(messages["vengeful_turn"].format(GHOSTS[player]))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    # select a random target for VG if they didn't kill
    for ghost, target in GHOSTS.items():
        if target[0] == "!" or is_silent(var, ghost):
            continue
        if ghost not in KILLS and TARGETS.get(ghost, None):
            KILLS[ghost] = random.choice(list(TARGETS[ghost]))
    TARGETS.clear()

@event_listener("night_kills")
def on_night_kills(evt: Event, var: GameState):
    for k, d in KILLS.items():
        evt.data["victims"].add(d)
        evt.data["killers"][d].append(k)
        if GHOSTS[k] == "villager":
            # wolf-aligned VGs take precedence over other killers
            evt.data["kill_priorities"][k] = -5
    # prevent VGs from being messaged in del_player that they can choose someone else
    KILLS.clear()

@event_listener("retribution_kill")
def on_retribution_kill(evt: Event, var: GameState, victim: User, orig_target: User):
    target = evt.data["target"]
    if target in GHOSTS:
        drivenoff[target] = GHOSTS[target]
        GHOSTS[target] = "!" + GHOSTS[target]
        # VGs only kill at night so we only need a night message
        evt.data["message"].append(messages["retribution_totem_night_banish"].format(victim, target))
        evt.data["target"] = None

@event_listener("get_participant_role")
def on_get_participant_role(evt: Event, var: GameState, user: User):
    if user in GHOSTS:
        if user in drivenoff:
            against = drivenoff[user]
        else:
            against = GHOSTS[user]
        if against == "villager":
            orig_wolves = len(get_players(var, Wolfteam, mainroles=var.original_main_roles))
            orig_vamps = len(get_players(var, Vampire_Team, mainroles=var.original_main_roles))
            # if vampires are the ONLY evil team, make against-village VG aligned with them instead of wolves
            # and if we somehow lack both wolves and vampires, default to wolf
            evt.data["role"] = "wolf" if orig_wolves or not orig_vamps else "vampire"
        else:
            evt.data["role"] = "villager"

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(KILLS)
    evt.data["nightroles"].extend([p for p in GHOSTS if GHOSTS[p][0] != "!" and TARGETS.get(p, None)])

@event_listener("send_role")
def on_transition_night_end(evt: Event, var: GameState):
    # alive VGs are messaged as part of villager.py, this handles dead ones
    targets = {
        "villager": get_players(var, All - Wolfteam - Vampire_Team),
        "wolf": get_players(var, Wolfteam),
        "vampire": get_players(var, Vampire_Team)
    }

    for v_ghost, who in GHOSTS.items():
        if who[0] == "!":
            continue
        pl = targets[who][:]
        random.shuffle(pl)
        TARGETS[v_ghost] = UserSet(pl)
        v_ghost.send(messages["vengeful_ghost_notify"].format(who),
                     messages["vengeful_ghost_team"].format(who, pl),
                     sep="\n")

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user: User):
    if user in GHOSTS:
        evt.prevent_default = True
        m = []
        if GHOSTS[user][0] != "!":
            m.append(messages["vengeful_role"].format(GHOSTS[user]))
            if TARGETS.get(user, None):
                pl = list(TARGETS[user])
                random.shuffle(pl)
                m.append(messages["vengeful_ghost_team"].format(GHOSTS[user], pl))
            user.send(*m, sep="\n")

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if GHOSTS:
        glist = []
        for ghost, team in GHOSTS.items():
            to_send = []
            if team[0] == "!":
                to_send.append(messages["vg_driven_away"].format()) # call .format() so it's actually a str
            to_send.append(messages["vg_against"].format(team.lstrip("!")))
            glist.append("{0} ({1})".format(ghost, ", ".join(to_send)))
        evt.data["output"].append(messages["vengeful_ghost_revealroles"].format(glist))

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    drivenoff.clear()
    KILLS.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    KILLS.clear()
    GHOSTS.clear()
    TARGETS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "night_kills":
        evt.data["vengeful ghost"] = sum(1 for against in GHOSTS.values() if against[0] != "!")
    elif kind == "special_keys":
        evt.data["vengeful ghost"] = {"vg activated", "vg driven off"}
    elif kind == "role_categories":
        evt.data["vengeful ghost"] = {"Hidden"}
