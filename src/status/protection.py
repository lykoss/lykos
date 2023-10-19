from __future__ import annotations

import random
from typing import Optional
from dataclasses import dataclass

from src.containers import UserDict, DefaultUserDict
from src.functions import get_players
from src.messages import messages
from src.events import Event, event_listener
from src.cats import All, Category
from src.users import User
from src.gamestate import GameState

__all__ = ["add_protection", "try_protection", "remove_all_protections", "ProtectionEntry"]

@dataclass(frozen=True)
class ProtectionEntry:
    scope: Category | set[str]
    protector_role: str
    priority: int

PROTECTIONS: UserDict[User, UserDict[Optional[User], list[ProtectionEntry]]] = UserDict()

def add_protection(var: GameState,
                   target: User,
                   protector: Optional[User],
                   protector_role: str,
                   scope: Category | set[str] = All,
                   priority: int = 0):
    """ Add a protection to the target affecting the relevant scope.

    :param var: Game state
    :param target: Player to protect
    :param protector: Who is protecting the target (potentially None)
    :param protector_role: Role of the protector
    :param scope: Protection scope. An attacker must belong to one of these roles for the protection to work.
    :param priority: Protection priority. Lower numbers apply before higher numbers. Ties are determined randomly.
    """
    if target not in get_players(var):
        return

    if target not in PROTECTIONS:
        PROTECTIONS[target] = DefaultUserDict(list)

    prot_entry = ProtectionEntry(scope, protector_role, priority)
    PROTECTIONS[target][protector].append(prot_entry)

def try_protection(var: GameState, target: User, attacker: Optional[User], attacker_role: str, reason: str):
    """Attempt to protect the player, and return a list of messages or None."""
    prots: list[tuple[Optional[User], ProtectionEntry]] = []
    for protector, entries in PROTECTIONS.get(target, {}).items():
        for entry in entries:
            if attacker_role in entry.scope:
                prots.append((protector, entry))

    try_evt = Event("try_protection", {"protections": prots, "messages": []})
    if not try_evt.dispatch(var, target, attacker, attacker_role, reason) or not try_evt.data["protections"]:
        return None

    # sort protections in the order in which they'll be applied
    # first by priority (low to high), then randomized
    prots = []
    priority = None
    for protector, entry in try_evt.data["protections"]:
        if priority is None or entry.priority < priority:
            prots.clear()
            priority = entry.priority
        elif entry.priority > priority:
            continue

        prots.append((protector, entry))

    protector, entry = random.choice(prots)
    PROTECTIONS[target][protector].remove(entry)
    prot_evt = Event("player_protected", {"messages": try_evt.data["messages"]})
    prot_evt.dispatch(var, target, attacker, attacker_role, protector, entry.protector_role, reason)
    return prot_evt.data["messages"]

def remove_all_protections(var: GameState, target: User, attacker: User, attacker_role: str, reason: str, scope: Category | set[str] = All):
    """Remove all protections from a player."""
    if target not in PROTECTIONS:
        return

    for protector, entries in list(PROTECTIONS[target].items()):
        for entry in entries:
            if scope & entry.scope:
                evt = Event("remove_protection", {"remove": False})
                evt.dispatch(var, target, attacker, attacker_role, protector, entry.protector_role, reason)
                if evt.data["remove"]:
                    PROTECTIONS[target][protector].remove(entry)

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    if player in PROTECTIONS:
        del PROTECTIONS[player]

    for protected, entries in PROTECTIONS.items():
        if player in entries:
            del entries[player]

@event_listener("remove_protection")
def on_remove_protection(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
    if attacker is protector:
        evt.data["remove"] = True
        target.send(messages["protector_disappeared"])

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if PROTECTIONS:
        evt.data["output"].append(messages["protection_revealroles"].format(PROTECTIONS))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt: Event, var: GameState):
    PROTECTIONS.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    PROTECTIONS.clear()
