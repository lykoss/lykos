import math
import re
import random
from collections import defaultdict, deque

import src.settings as var
from src.utilities import *
from src.functions import get_players, get_target
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
    target = evt.data["target"]

    KILLS[wrapper.source] = target

    wrapper.pm(messages["player"].format(messages["wolf_target"].format(orig)))

    debuglog("{0} ({1}) KILL: {2} ({3})".format(wrapper.source, get_role(wrapper.source.nick), target, get_role(target.nick)))

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
<<<<<<< HEAD
    alive = set(list_players())
    if not TARGETS[user.nick] & alive:
=======
    alive = set(get_players())
    if user.nick in var.ENTRANCED:
        alive.difference_update(users._get(x) for x in var.ROLES["succubus"]) # FIXME
    if not TARGETS[user] & alive:
>>>>>>> parent of 2354269... Revert unintentional change to dullahan
        evt.data["iwon"] = True

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    for h, v in list(KILLS.items()):
        if v.nick == nick:
            h.send(messages["hunter_discard"])
            del KILLS[h]
        elif h.nick == nick:
            del KILLS[h]
    if death_triggers and nickrole == "dullahan":
        pl = evt.data["pl"]
        targets = TARGETS[users._get(nick)].union(users._get(x) for x in pl) # FIXME
        if targets:
            target = random.choice(list(targets)).nick
            prots = deque(var.ACTIVE_PROTECTIONS[target])
            aevt = Event("assassinate", {"pl": evt.data["pl"]},
                    del_player=evt.params.del_player,
                    deadlist=evt.params.deadlist,
                    original=evt.params.original,
                    refresh_pl=evt.params.refresh_pl,
                    message_prefix="dullahan_die_",
                    nickrole=nickrole,
                    nicktpls=nicktpls,
                    prots=prots)
            while len(prots) > 0:
                # an event can read the current active protection and cancel the totem
                # if it cancels, it is responsible for removing the protection from var.ACTIVE_PROTECTIONS
                # so that it cannot be used again (if the protection is meant to be usable once-only)
                if not aevt.dispatch(cli, var, nick, target, prots[0]):
                    evt.data["pl"] = aevt.data["pl"]
                    return
                prots.popleft()
            if var.ROLE_REVEAL in ("on", "team"):
                role = get_reveal_role(target)
                an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                cli.msg(botconfig.CHANNEL, messages["dullahan_die_success"].format(nick, target, an, role))
            else:
                cli.msg(botconfig.CHANNEL, messages["dullahan_die_success_noreveal"].format(nick, target))
            debuglog("{0} ({1}) DULLAHAN ASSASSINATE: {2} ({3})".format(nick, nickrole, target, get_role(target)))
            evt.params.del_player(cli, target, True, end_game=False, killer_role=nickrole, deadlist=evt.params.deadlist, original=evt.params.original, ismain=False)
            evt.data["pl"] = evt.params.refresh_pl(pl)

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if users._get(nick) in KILLS: # FIXME
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(list_players(("dullahan",)))

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    kvp = []
    for a,b in KILLS.items():
        if a == prefix:
            a = nick
        if b == prefix:
            b = nick
        kvp.append((a,b))
    KILLS.update(kvp)
    if prefix in KILLS:
        del KILLS[prefix]
    kvp = []
    for a,b in TARGETS.items():
        nl = set()
        for n in b:
            if n == prefix:
                n = nick
            nl.add(n)
        if a == prefix:
            a = nick
        kvp.append((a,nl))
    TARGETS.update(kvp)
    if prefix in TARGETS:
        del TARGETS[prefix]

<<<<<<< HEAD
@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in KILLS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(var.ROLES["dullahan"])

=======
>>>>>>> parent of 2354269... Revert unintentional change to dullahan
@event_listener("transition_day", priority=2)
def on_transition_day(evt, cli, var):
    while KILLS:
        k, d = KILLS.popitem()
        evt.data["victims"].append(d.nick)
        evt.data["onlybywolves"].discard(d.nick)
        evt.data["killers"][d.nick].append(k.nick)

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    for k in set(KILLS):
        if k.nick == actor or k.nick == nick:
            del KILLS[k]

    for k in set(TARGETS):
        if actor_role == "dullahan" and nick_role != "dullahan" and k.nick == actor:
            TARGETS[users._get(nick)] = TARGETS.pop(k) - {users._get(nick)} # FIXME
        elif nick_role == "dullahan" and actor_role != "dullahan" and k.nick == nick:
            TARGET[users._get(actor)] = TARGETS.pop(k) - {users._get(actor)} # FIXME

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    spl = set(get_players())
    evt.data["actedcount"] += len(KILLS)
    for d, targets in TARGETS.items():
        if targets & spl:
            evt.data["nightroles"].append(d.nick)

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    for dullahan, targets in TARGETS.items():
        targets = (targets - var.DEAD)
        if not targets: # already all dead
            dullahan.send("{0} {1}".format(messages["dullahan_simple"], messages["dullahan_targets_dead"]))
            continue
        random.shuffle(targets)
        dullahan.send(messages["dullahan_" + ("simple" if dullahan.prefers_simple() else "notify")])
        t = messages["dullahan_targets"] if var.FIRST_NIGHT else messages["dullahan_remaining_targets"]
        dullahan.send(t + ", ".join([t.nick for t in targets]))

@event_listener("role_assignment")
def on_role_assignment(evt, cli, var, gamemode, pl, restart):
    # assign random targets to dullahan to kill
    if var.ROLES["dullahan"]:
        max_targets = math.ceil(8.1 * math.log(len(pl), 10) - 5)
        for dull in var.ROLES["dullahan"]:
            TARGETS[dull] = set()
        dull_targets = Event("dullahan_targets", {"targets": TARGETS}) # support sleepy
        dull_targets.dispatch(cli, var, var.ROLES["dullahan"], max_targets)

        for dull, ts in TARGETS.items():
            ps = pl[:]
            ps.remove(dull)
            while len(ts) < max_targets:
                target = random.choice(ps)
                ps.remove(target)
                ts.add(target)

@event_listener("succubus_visit")
def on_succubus_visit(evt, cli, var, nick, victim):
    if victim in TARGETS and TARGETS[victim] & var.ROLES["succubus"]:
        TARGETS.difference_update(var.ROLES["succubus"])
        pm(cli, victim, messages["dullahan_no_kill_succubus"])
    if KILLS.get(victim) in var.ROLES["succubus"]:
        pm(cli, victim, messages["no_kill_succubus"].format(KILLS[victim]))
        del KILLS[victim]

@event_listener("myrole")
def on_myrole(evt, cli, var, nick):
    role = get_role(nick)
    # Remind dullahans of their targets
    if role == "dullahan":
        targets = list(TARGETS[nick])
        for target in var.DEAD:
            if target in targets:
                targets.remove(target)
        random.shuffle(targets)
        if targets:
            t = messages["dullahan_targets"] if var.FIRST_NIGHT else messages["dullahan_remaining_targets"]
            evt.data["messages"].append(t + ", ".join(targets))
        else:
            evt.data["messages"].append(messages["dullahan_targets_dead"])

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, wrapper, nickname, role):
    if role == "dullahan" and nickname in TARGETS:
        targets = TARGETS[nickname] - var.DEAD
        if targets: 
            evt.data["special_case"].append("need to kill {0}".format(", ".join(TARGETS[nickname] - var.DEAD)))
        else:
            evt.data["special_case"].append("All targets dead")

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    TARGETS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, cli, var, kind):
    if kind == "night_kills":
        num = 0
        for dull in var.ROLES["dullahan"]:
            if TARGETS[dull] - var.DEAD:
                num += 1
        evt.data["dullahan"] = num

# vim: set sw=4 expandtab:
