import math
import re
import random
from collections import defaultdict, deque

from src.utilities import *
from src.functions import get_players, get_all_players, get_target, get_main_role, get_reveal_role
from src import users, channels, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
import botconfig

KILLS = UserDict() # type: Dict[users.User, users.User]
TARGETS = UserDict() # type: Dict[users.User, Set[users.User]]

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("dullahan",))
def dullahan_kill(var, wrapper, message):
    """Kill someone at night as a dullahan until everyone on your list is dead."""
    if not TARGETS[wrapper.source] & set(get_players()):
        wrapper.pm(messages["dullahan_targets_dead"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
    if not target:
        return

    orig = target
    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    evt.dispatch(var, "kill", wrapper.source, target, frozenset({"detrimental"}))
    if evt.prevent_default:
        return
    target = evt.data["target"]

    KILLS[wrapper.source] = target

    wrapper.pm(messages["player_kill"].format(orig))

    debuglog("{0} (dullahan) KILL: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("dullahan",))
def dullahan_retract(var, wrapper, message):
    """Removes a dullahan's kill selection."""
    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        wrapper.pm(messages["retracted_kill"])
        debuglog("{0} (dullahan) RETRACT".format(wrapper.source))

@event_listener("player_win")
def on_player_win(evt, var, user, role, winner, survived):
    if role != "dullahan":
        return
    alive = set(get_players())
    if not TARGETS[user] & alive:
        evt.data["iwon"] = True

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    for h, v in list(KILLS.items()):
        if v is user:
            h.send(messages["hunter_discard"])
            del KILLS[h]
        elif h is user:
            del KILLS[h]
    if death_triggers and "dullahan" in allroles:
        pl = evt.data["pl"]
        with TARGETS[user].intersection(pl) as targets:
            if targets:
                target = random.choice(list(targets))
                prots = deque(var.ACTIVE_PROTECTIONS[target.nick])
                aevt = Event("assassinate", {"pl": evt.data["pl"], "target": target},
                        del_player=evt.params.del_player,
                        deadlist=evt.params.deadlist,
                        original=evt.params.original,
                        refresh_pl=evt.params.refresh_pl,
                        message_prefix="dullahan_die_",
                        source="dullahan",
                        killer=user,
                        killer_mainrole=mainrole,
                        killer_allroles=allroles,
                        prots=prots)
                while len(prots) > 0:
                    # an event can read the current active protection and cancel or redirect the assassination
                    # if it cancels, it is responsible for removing the protection from var.ACTIVE_PROTECTIONS
                    # so that it cannot be used again (if the protection is meant to be usable once-only)
                    if not aevt.dispatch(var, user, target, prots[0]):
                        evt.data["pl"] = aevt.data["pl"]
                        if target is not aevt.data["target"]:
                            target = aevt.data["target"]
                            prots = deque(var.ACTIVE_PROTECTIONS[target.nick])
                            aevt.params.prots = prots
                            continue
                        return
                    prots.popleft()

                if var.ROLE_REVEAL in ("on", "team"):
                    role = get_reveal_role(target)
                    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                    channels.Main.send(messages["dullahan_die_success"].format(user, target, an, role))
                else:
                    channels.Main.send(messages["dullahan_die_success_noreveal"].format(user, target))
                debuglog("{0} (dullahan) DULLAHAN ASSASSINATE: {1} ({2})".format(user, target, get_main_role(target)))
                evt.params.del_player(target, end_game=False, killer_role="dullahan", deadlist=evt.params.deadlist, original=evt.params.original, ismain=False)
                evt.data["pl"] = evt.params.refresh_pl(pl)

@event_listener("night_acted")
def on_acted(evt, var, user, actor):
    if user in KILLS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["neutrals"].update(get_players(("dullahan",)))

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    while KILLS:
        k, d = KILLS.popitem()
        evt.data["victims"].append(d)
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d].append(k)

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    for k in set(KILLS):
        if k is actor or k is target:
            del KILLS[k]

    for k in set(TARGETS):
        if actor_role == "dullahan" and target_role != "dullahan" and k is actor:
            targets = TARGETS.pop(k)
            if target in targets:
                targets.remove(target)
                targets.add(actor)
            TARGETS[target] = targets
        if target_role == "dullahan" and actor_role != "dullahan" and k is target:
            targets = TARGETS.pop(k)
            if actor in targets:
                targets.remove(actor)
                targets.add(target)
            TARGETS[actor] = targets

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    spl = set(get_players())
    evt.data["actedcount"] += len(KILLS)
    for dullahan, targets in TARGETS.items():
        if targets & spl:
            evt.data["nightroles"].append(dullahan)

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    for dullahan in get_all_players(("dullahan",)):
        targets = list(TARGETS[dullahan])
        for target in targets[:]:
            if target.nick in var.DEAD:
                targets.remove(target) # FIXME: Update when var.DEAD holds User instances
        if not targets: # already all dead
            dullahan.send("{0} {1}".format(messages["dullahan_simple"], messages["dullahan_targets_dead"]))
            continue
        random.shuffle(targets)
        to_send = "dullahan_notify"
        if dullahan.prefers_simple():
            to_send = "dullahan_simple"
        t = messages["dullahan_targets"] if var.FIRST_NIGHT else messages["dullahan_remaining_targets"]
        dullahan.send(messages[to_send], t + ", ".join(t.nick for t in targets), sep="\n")

@event_listener("role_assignment")
def on_role_assignment(evt, var, gamemode, pl):
    # assign random targets to dullahan to kill
    if var.ROLES["dullahan"]:
        max_targets = math.ceil(8.1 * math.log(len(pl), 10) - 5)
        for dull in var.ROLES["dullahan"]:
            TARGETS[dull] = UserSet()
        dull_targets = Event("dullahan_targets", {"targets": TARGETS}) # support sleepy
        dull_targets.dispatch(var, var.ROLES["dullahan"], max_targets)

        for dull, ts in TARGETS.items():
            ps = pl[:]
            ps.remove(dull)
            while len(ts) < max_targets:
                target = random.choice(ps)
                ps.remove(target)
                ts.add(target)

@event_listener("succubus_visit")
def on_succubus_visit(evt, var, succubus, target):
    if target in TARGETS and succubus in TARGETS[target]:
        TARGETS[target].remove(succubus)
        target.send(messages["dullahan_no_kill_succubus"])
    if target in KILLS and KILLS[target] in get_all_players(("succubus",)):
        target.send(messages["no_kill_succubus"].format(KILLS[target]))
        del KILLS[target]

@event_listener("myrole")
def on_myrole(evt, var, user):
    # Remind dullahans of their targets
    if user in var.ROLES["dullahan"]:
        targets = list(TARGETS[user])
        for target in list(targets):
            if target.nick in var.DEAD:
                targets.remove(target)
        random.shuffle(targets)
        if targets:
            t = messages["dullahan_targets"] if var.FIRST_NIGHT else messages["dullahan_remaining_targets"]
            evt.data["messages"].append(t + ", ".join(t.nick for t in targets))
        else:
            evt.data["messages"].append(messages["dullahan_targets_dead"])

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "dullahan" and user in TARGETS:
        targets = set(TARGETS[user])
        for target in TARGETS[user]:
            if target.nick in var.DEAD:
                targets.remove(target)
        if targets:
            evt.data["special_case"].append(messages["dullahan_to_kill"].format(", ".join(t.nick for t in targets)))
        else:
            evt.data["special_case"].append(messages["dullahan_all_dead"])

@event_listener("begin_day")
def on_begin_day(evt, var):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    TARGETS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        num = 0
        for dull in var.ROLES["dullahan"]:
            for target in TARGETS[dull]:
                if target.nick not in var.DEAD:
                    num += 1
                    break
        evt.data["dullahan"] = num

# vim: set sw=4 expandtab:
