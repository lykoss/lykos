from src.decorators import event_listener
from src.containers import UserSet
from src.functions import get_all_players, get_main_role, change_role
from src.cats import Wolf

LYCANTHROPES = UserSet()

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

@event_listener("begin_day")
def on_begin_day(evt, var):
    LYCANTHROPES.clear()

@event_listener("reset")
def on_reset(evt, var):
    LYCANTHROPES.clear()
