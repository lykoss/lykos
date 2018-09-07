from src.containers import UserDict, DefaultUserDict
from src.events import Event
from src.cats import All

__all__ = ["add_protection", "try_protection", "remove_all_protections"]

PROTECTIONS = UserDict() # type: UserDict[User, UserDict[Optional[User], List[Tuple[Category, Optional[str]]]]]

def add_protection(var, target, protector, protector_role, scope=All):
    if target not in PROTECTIONS:
        PROTECTIONS[target] = DefaultUserDict(list)

    prot_entry = (scope, protector_role)
    PROTECTIONS[target][protector].append(prot_entry)

def try_protection(var, target, attacker, attacker_role):
    if target not in PROTECTIONS:
        return None

    prots = []
    for protector, entries in PROTECTIONS[target].items():
        for scope, protector_role in entries:
            if attacker_role in scope:
                entry = (protector, protector_role, scope)
                prots.append(entry)

    try_evt = Event("try_protection", {"protections": prots, "messages": []})
    if not try_evt.dispatch(var, target, attacker, attacker_role) or not try_evt.data["protections"]:
        return None

    protector, protector_role, scope = try_evt.data["protections"].pop(0)

    PROTECTIONS[target][protector].remove((scope, protector_role))

    prot_evt = Event("player_protected", {"messages": try_evt.data["messages"]})
    prot_evt.dispatch(var, target, attacker, attacker_role, protector, protector_role)

    return prot_evt.data["messages"]

def remove_all_protections(var, target, attacker, attacker_role, scope=All):
    if target not in PROTECTIONS:
        return

    for protector, entries in list(PROTECTIONS[target].items()):
        for cat, protector_role in list(entries):
            if scope & cat:
                evt = Event("remove_protection", {"remove": False, "messages": []})
                evt.dispatch(var, target, attacker, attacker_role, protector, protector_role)
                if evt.data["remove"]:
                    PROTECTIONS[target][protector].remove((cat, protector_role))
                    target.send(*evt.data["messages"])

        if not entries:
            del PROTECTIONS[target][protector]

    if not PROTECTIONS[target]:
        del PROTECTIONS[target]
