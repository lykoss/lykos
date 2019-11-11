from src.containers import UserDict, DefaultUserDict
from src.decorators import event_listener
from src.functions import get_players
from src.messages import messages
from src.events import Event
from src.cats import All

__all__ = ["add_protection", "try_protection", "remove_all_protections"]

PROTECTIONS = UserDict() # type: UserDict[User, UserDict[Optional[User], List[Tuple[Category, str]]]]

def add_protection(var, target, protector, protector_role, scope=All):
    """Add a protection to the target affecting the relevant scope."""
    if target not in get_players():
        return

    if target not in PROTECTIONS:
        PROTECTIONS[target] = DefaultUserDict(list)

    prot_entry = (scope, protector_role)
    PROTECTIONS[target][protector].append(prot_entry)

def try_protection(var, target, attacker, attacker_role, reason):
    """Attempt to protect the player, and return a list of messages or None."""
    prots = []
    for protector, entries in PROTECTIONS.get(target, {}).items():
        for scope, protector_role in entries:
            if attacker_role in scope:
                entry = (protector, protector_role, scope)
                prots.append(entry)

    try_evt = Event("try_protection", {"protections": prots, "messages": []})
    if not try_evt.dispatch(var, target, attacker, attacker_role, reason) or not try_evt.data["protections"]:
        return None

    protector, protector_role, scope = try_evt.data["protections"].pop(0)

    PROTECTIONS[target][protector].remove((scope, protector_role))

    prot_evt = Event("player_protected", {"messages": try_evt.data["messages"]})
    prot_evt.dispatch(var, target, attacker, attacker_role, protector, protector_role, reason)

    return prot_evt.data["messages"]

def remove_all_protections(var, target, attacker, attacker_role, reason, scope=All):
    """Remove all protections from a player."""
    if target not in PROTECTIONS:
        return

    for protector, entries in list(PROTECTIONS[target].items()):
        for cat, protector_role in entries:
            if scope & cat:
                evt = Event("remove_protection", {"remove": False})
                evt.dispatch(var, target, attacker, attacker_role, protector, protector_role, reason)
                if evt.data["remove"]:
                    PROTECTIONS[target][protector].remove((cat, protector_role))

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    if player in PROTECTIONS:
        del PROTECTIONS[player]

    for protected, entries in PROTECTIONS.items():
        if player in entries:
            del entries[player]

@event_listener("remove_protection")
def on_remove_protection(evt, var, target, attacker, attacker_role, protector, protector_role, reason):
    if attacker is protector:
        evt.data["remove"] = True
        target.send(messages["protector_disappeared"])

@event_listener("revealroles")
def on_revealroles(evt, var):
    if PROTECTIONS:
        evt.data["output"].append(messages["protection_revealroles"].format(PROTECTIONS))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    PROTECTIONS.clear()

@event_listener("reset")
def on_reset(evt, var):
    PROTECTIONS.clear()

# vim: set sw=4 expandtab:
