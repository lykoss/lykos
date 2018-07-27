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
    evt.dispatch(var, wrapper.source, target)
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

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    while KILLS:
        k, d = KILLS.popitem()
        evt.data["victims"].append(d)
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d].append(k)

@event_listener("new_role")
def on_new_role(evt, var, player, old_role):
    if player in TARGETS and old_role == "dullahan" and evt.data["role"] != "dullahan":
        del KILLS[:player:]
        del TARGETS[player]

    if player not in TARGETS and evt.data["role"] == "dullahan":
        ps = get_players()
        max_targets = math.ceil(8.1 * math.log(len(ps), 10) - 5)
        TARGETS[player] = UserSet()

        dull_targets = Event("dullahan_targets", {"targets": TARGETS[player]}) # support sleepy
        dull_targets.dispatch(var, player, max_targets)

        ps.remove(player)
        while len(TARGETS[player]) < max_targets:
            target = random.choice(ps)
            ps.remove(target)
            TARGETS[player].add(target)

@event_listener("swap_role_state")
def on_swap_role_state(evt, var, actor, target, role):
    if role == "dullahan":
        targ_targets = TARGETS.pop(target)
        if actor in targ_targets:
            targ_targets.remove(actor)
            targ_targets.add(target)
        act_targets = TARGETS.pop(actor)
        if target in act_targets:
            act_targets.remove(target)
            act_targets.add(actor)

        TARGETS[actor] = targ_targets
        TARGETS[target] = act_targets

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

@event_listener("succubus_visit")
def on_succubus_visit(evt, var, succubus, target):
    succubi = get_all_players(("succubus",))
    if target in TARGETS and TARGETS[target].intersection(succubi):
        TARGETS[target].difference_update(succubi)
        target.send(messages["dullahan_no_kill_succubus"])

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
    elif kind == "role_categories":
        evt.data["dullahan"] = {"Killer", "Nocturnal", "Neutral"}

# vim: set sw=4 expandtab:
