import math
import re
import random
from collections import defaultdict, deque

from src.utilities import *
from src.functions import get_players, get_all_players, get_target, get_main_role
from src import users, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.messages import messages
from src.events import Event
import botconfig

KILLS = {} # type: Dict[users.User, users.User]
TARGETS = {} # type: Dict[users.User, Set[users.User]]

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("dullahan",))
def dullahan_kill(var, wrapper, message):
    """Kill someone at night as a dullahan until everyone on your list is dead."""
    if not TARGETS[wrapper.source] & set(get_players()):
        wrapper.pm(messages["dullahan_targets_dead"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0])
    if not target:
        return

    if target is wrapper.source:
        wrapper.pm(messages["no_suicide"])
        return

    orig = target
    evt = Event("targeted_command", {"target": target.nick, "misdirection": True, "exchange": True})
    evt.dispatch(wrapper.client, var, "kill", wrapper.source.nick, target.nick, frozenset({"detrimental"}))
    if evt.prevent_default:
        return
    target = users._get(evt.data["target"]) # FIXME: Need to fix once targeted_command uses the new API

    KILLS[wrapper.source] = target

    wrapper.pm(messages["player_kill"].format(orig))

    debuglog("{0} (dullahan) KILL: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

    chk_nightdone(wrapper.client)

@command("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("dullahan",))
def dullahan_retract(var, wrapper, message):
    """Removes a dullahan's kill selection."""
    if KILLS.pop(wrapper.source, None):
        wrapper.pm(messages["retracted_kill"])

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
        targets = TARGETS[user].intersection(pl)
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
                role = get_reveal_role(target.nick)
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

@event_listener("swap_player")
def on_swap(evt, var, old_user, user):
    if old_user in KILLS:
        KILLS[user] = KILLS.pop(old_user)
    if old_user in TARGETS:
        TARGETS[user] = TARGETS.pop(old_user)

    for dullahan, target in KILLS.items():
        if target is old_user:
            KILLS[dullahan] = user

    for dullahan, targets in TARGETS.items():
        if old_user in targets:
            targets.remove(old_user)
            targets.add(user)

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("dullahan",)))

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
            TARGETS[target] = TARGETS.pop(k) - {target}
        elif target_role == "dullahan" and actor_role != "dullahan" and k is target:
            TARGET[actor] = TARGETS.pop(k) - {actor}

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
def on_role_assignment(evt, cli, var, gamemode, pl, restart):
    # assign random targets to dullahan to kill
    if var.ROLES["dullahan"]:
        max_targets = math.ceil(8.1 * math.log(len(pl), 10) - 5)
        for dull in var.ROLES["dullahan"]:
            TARGETS[users._get(dull)] = set() # FIXME
        dull_targets = Event("dullahan_targets", {"targets": TARGETS}) # support sleepy
        dull_targets.dispatch(cli, var, {users._get(x) for x in var.ROLES["dullahan"]}, max_targets) # FIXME

        players = [users._get(x) for x in pl] # FIXME

        for dull, ts in TARGETS.items():
            ps = players[:]
            ps.remove(dull)
            while len(ts) < max_targets:
                target = random.choice(ps)
                ps.remove(target)
                ts.add(target)

@event_listener("succubus_visit")
def on_succubus_visit(evt, cli, var, nick, victim):
    user = users._get(victim) # FIXME
    if user in TARGETS:
        succ_target = False
        for target in set(TARGETS[user]):
            if target.nick in var.ROLES["succubus"]:
                TARGETS[user].remove(target)
                succ_target = True
        if succ_target:
            pm(cli, victim, messages["dullahan_no_kill_succubus"])
    if user in KILLS and KILLS[user].nick in var.ROLES["succubus"]:
        pm(cli, victim, messages["no_kill_succubus"].format(KILLS[user]))
        del KILLS[user]

@event_listener("myrole")
def on_myrole(evt, var, user):
    # Remind dullahans of their targets
    if user.nick in var.ROLES["dullahan"]:
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
def on_revealroles_role(evt, var, wrapper, nickname, role):
    user = users._get(nickname) # FIXME
    if role == "dullahan" and user in TARGETS: # FIXME
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
            user = users._get(dull) # FIXME
            for target in TARGETS[user]:
                if target.nick not in var.DEAD:
                    num += 1
                    break
        evt.data["dullahan"] = num

# vim: set sw=4 expandtab:
