from src.decorators import event_listener
from src.containers import UserSet
from src.functions import get_all_players, get_main_role, change_role
from src.cats import Wolf
from src._wolf_helper import get_wolfchat_roles

LYCANTHROPES = UserSet()

@event_listener("reconfigure_stats")
def on_reconfigure_stats(evt, var, roleset, reason):
    if reason != "howl":
        return

    evt2 = Event("get_role_metadata", {})
    evt2.dispatch("lycanthropy_role")

    roles = {}

    wolfchat = get_wolfchat_roles(var)
    for role, count in roleset.items():
        if role in wolfchat or count == 0:
            continue
        if role in evt2.data and "role" in evt2.data[role]:
            roles[role] = evt2.data[role]["role"]
        else:
            roles[role] = "wolf"

    if roles and roleset in evt.data["new"]:
        evt.data["new"].remove(roleset)

    for role, new_role in roles.items():
        rs = roleset.copy()
        rs[role] -= 1
        rs[new_role] = rs.get(new_role, 0) + 1
        evt.data["new"].append(rs)

@event_listener("bite", priority=1)
def on_bite(evt, var, biter, target):
    if target in get_all_players(("lycan",)) or target in LYCANTHROPES or target.nick in var.IMMUNIZED: # FIXME: Split into lycan/doctor (?)
        evt.data["kill"] = True

@event_listener("transition_day_resolve_end", priority=2)
def on_transition_day_resolve_end(evt, var, victims):
    for victim in victims:
        if (victim in get_all_players(("lycan",)) or victim in LYCANTHROPES) and victim in evt.data["onlybywolves"] and victim.nick not in var.IMMUNIZED:
            vrole = get_main_role(victim)
            if vrole not in Wolf:
                change_role(var, victim, vrole, "wolf", message="lycan_turn")
                var.ROLES["lycan"].discard(victim) # in the event lycan was a template, we want to ensure it gets purged
                evt.data["howl"] += 1
                evt.data["novictmsg"] = False
                evt.data["dead"].remove(victim)
                evt.data["bywolves"].discard(victim)
                evt.data["onlybywolves"].discard(victim)
                evt.data["killers"][victim].remove("@wolves")
                del evt.data["message"][victim]

@event_listener("begin_day") # XXX This is wrong
def on_begin_day(evt, var):
    LYCANTHROPES.clear()

@event_listener("reset")
def on_reset(evt, var):
    LYCANTHROPES.clear()
