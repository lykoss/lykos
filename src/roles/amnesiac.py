from __future__ import annotations

from typing import Optional

from src import users, config
from src.cats import role_order, Win_Stealer, Hidden_Eligible, all_teams, Neutral
from src.containers import UserDict
from src.events import Event, event_listener
from src.functions import get_all_players, change_role
from src.messages import messages
from src.gamestate import GameState
from src.users import User
from src.random import random

__all__ = ["get_blacklist", "get_stats_flag"]

ROLES: UserDict[users.User, str] = UserDict()
STATS_FLAG = False # if True, we begin accounting for amnesiac in update_stats

def get_blacklist(var: GameState):
    bl = Win_Stealer | Hidden_Eligible | {"amnesiac"} | set(var.current_mode.SECONDARY_ROLES.keys())
    # don't introduce teams that don't already exist in the mode (except neutrals, since that's not a real team)
    starting_roles = set(var.original_main_roles.values())
    for team in all_teams():
        if team is not Neutral and not (team & starting_roles):
            bl |= team
    return bl

def get_stats_flag(var):
    return STATS_FLAG

@event_listener("transition_night_begin")
def on_transition_night_begin(evt: Event, var: GameState):
    global STATS_FLAG
    if var.night_count == config.Main.get("gameplay.safes.amnesiac_night"):
        amnesiacs = get_all_players(var, ("amnesiac",))
        if amnesiacs and not config.Main.get("gameplay.hidden.amnesiac"):
            STATS_FLAG = True

        for amn in amnesiacs:
            change_role(var, amn, "amnesiac", ROLES[amn], message="amnesia_clear")

@event_listener("spy")
def on_investigate(evt: Event, var: GameState, actor: User, target: User, spy_role: str):
    if evt.data["role"] == "amnesiac" and spy_role in ("augur", "detective", "investigator", "sorcerer"):
        evt.data["role"] = ROLES[target]

@event_listener("new_role", priority=1) # Exchange, clone, etc. - assign the amnesiac's final role
def update_amnesiac(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    # FIXME: exchange totem messes with gameplay.hidden.amnesiac (the new amnesiac is no longer hidden should they die)
    if evt.params.inherit_from is not None and evt.data["role"] == "amnesiac" and old_role != "amnesiac":
        evt.data["role"] = ROLES[evt.params.inherit_from]

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if evt.params.inherit_from is None and evt.data["role"] == "amnesiac":
        roles = set(role_order()) - get_blacklist(var)
        ROLES[player] = random.choice(list(roles))

@event_listener("role_revealed")
def on_revealing_totem(evt: Event, var: GameState, user: User, role: str):
    if role not in get_blacklist(var) and not config.Main.get("gameplay.hidden.amnesiac") and var.original_roles["amnesiac"]:
        global STATS_FLAG
        STATS_FLAG = True
    if role == "amnesiac":
        user.send(messages["amnesia_clear"].format(ROLES[user]))
        change_role(var, user, "amnesiac", ROLES[user])

@event_listener("get_reveal_role")
def on_reveal_role(evt: Event, var: GameState, user: User):
    if config.Main.get("gameplay.hidden.amnesiac") and var.original_main_roles[user] == "amnesiac":
        evt.data["role"] = "amnesiac"

@event_listener("get_endgame_message")
def on_get_endgame_message(evt: Event, var: GameState, player: User, role: str, is_main_role: bool):
    if role == "amnesiac":
        evt.data["message"].append(messages["amnesiac_endgame"].format(ROLES[player]))

@event_listener("revealroles_role")
def on_revealroles_role(evt: Event, var: GameState, user: User, role: str):
    if role == "amnesiac":
        evt.data["special_case"].append(messages["amnesiac_revealroles"].format(ROLES[user]))

@event_listener("update_stats")
def on_update_stats(evt: Event, var: GameState, player: User, mainrole: str, revealrole: str, allroles: set[str]):
    if STATS_FLAG and not get_blacklist(var) & {mainrole, revealrole}:
        evt.data["possible"].add("amnesiac")

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    global STATS_FLAG
    ROLES.clear()
    STATS_FLAG = False

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["amnesiac"] = {"Hidden", "Team Switcher"}
