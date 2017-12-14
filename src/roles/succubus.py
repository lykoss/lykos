import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.decorators import command, event_listener
from src.messages import messages
from src.events import Event

ENTRANCED = set() # type: Set[users.User]
ENTRANCED_DYING = set() # type: Set[users.User]
VISITED = {} # type: Dict[users.User, users.User]
PASSED = set() # type: Set[users.User]
ALL_SUCC_IDLE = True

@command("visit", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("succubus",))
def hvisit(var, wrapper, message):
    """Entrance a player, converting them to your team."""
    if VISITED.get(wrapper.source):
        wrapper.send(messages["succubus_already_visited"].format(VISITED[wrapper.source]))
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="succubus_not_self")

    if not target:
        return

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": False})
    evt.dispatch(var, "visit", wrapper.source, target, frozenset({"detrimental", "immediate"}))
    if evt.prevent_default:
        return
    target = evt.data["target"]

    VISITED[wrapper.source] = target
    PASSED.discard(wrapper.source)

    if target.nick not in var.ROLES["succubus"]:
        ENTRANCED.add(target)
        wrapper.send(messages["succubus_target_success"].format(target))
    else:
        wrapper.send(messages["harlot_success"].format(target))

    if wrapper.source is not target:
        if target not in var.ROLES["succubus"]:
            target.send(messages["notify_succubus_target"].format(wrapper.source))
        else:
            target.send(messages["harlot_success"].format(wrapper.source))

        revt = Event("succubus_visit", {})
        revt.dispatch(var, wrapper.source, target)

        # TODO: split these into assassin, hag, and alpha wolf when they are split off
        if users._get(var.TARGETED.get(target.nick), allow_none=True) in var.ROLES["succubus"]: # FIXME
            msg = messages["no_target_succubus"].format(var.TARGETED[target.nick])
            del var.TARGETED[target.nick]
            if target.nick in var.ROLES["village drunk"]:
                victim = random.choice(list(get_players() - var.ROLES["succubus"] - {target}))
                msg += messages["drunk_target"].format(victim)
                var.TARGETED[target.nick] = victim.nick
            target.send(msg)

        if target.nick in var.HEXED and users._get(var.LASTHEXED[target.nick]) in var.ROLES["succubus"]: # FIXME
            target.send(messages["retract_hex_succubus"].format(var.LASTHEXED[target.nick]))
            var.TOBESILENCED.remove(wrapper.source.nick)
            var.HEXED.remove(target.nick)
            del var.LASTHEXED[target.nick]
        if users._get(var.BITE_PREFERENCES.get(target.nick), allow_none=True) in var.ROLES["succubus"]: # FIXME
            target.send(messages["no_kill_succubus"].format(var.BITE_PREFERENCES[target.nick]))
            del var.BITE_PREFERENCES[target.nick]

    debuglog("{0} (succubus) VISIT: {1} ({2})".format(wrapper.source, target, get_main_role(target)))
    chk_nightdone(wrapper.client)

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("succubus",))
def pass_cmd(var, wrapper, message):
    """Do not entrance someone tonight."""
    if VISITED.get(wrapper.source):
        wrapper.send(messages["succubus_already_visited"].format(VISITED[wrapper.source]))
        return

    PASSED.add(wrapper.source)
    wrapper.send(messages["succubus_pass"])
    debuglog("{0} (succubus) PASS".format(wrapper.source))
    chk_nightdone(wrapper.client)

@event_listener("harlot_visit")
def on_harlot_visit(evt, var, harlot, victim):
    if victim in var.ROLES["succubus"]:
        harlot.send(messages["notify_succubus_target"].format(victim))
        victim.send(messages["succubus_harlot_success"].format(harlot))
        ENTRANCED.add(harlot)

@event_listener("get_random_totem_targets")
def on_get_random_totem_targets(evt, var, shaman):
    if shaman in ENTRANCED:
        for succubus in get_all_players(("succubus",)):
            if succubus in evt.data["targets"]:
                evt.data["targets"].remove(succubus)

@event_listener("chk_decision", priority=0)
def on_chk_decision(evt, cli, var, force):
    for votee, voters in evt.data["votelist"].items():
        if users._get(votee) in var.ROLES["succubus"]: # FIXME
            for vtr in ENTRANCED:
                if vtr.nick in voters:
                    voters.remove(vtr.nick)

def _kill_entranced_voters(var, votelist, not_lynching, votee):
    if not var.ROLES["succubus"] & (set(itertools.chain(*votelist.values())) | not_lynching):
        # none of the succubi voted (or there aren't any succubi), so short-circuit
        return
    # kill off everyone entranced that did not follow one of the succubi's votes or abstain
    # unless a succubus successfully voted the target, then people that didn't follow are spared
    for x in ENTRANCED:
        if x.nick not in var.DEAD:
            ENTRANCED_DYING.add(x)

    for other_votee, other_voters in votelist.items():
        if {p.nick for p in var.ROLES["succubus"]} & set(other_voters): # FIXME
            if votee == other_votee:
                ENTRANCED_DYING.clear()
                return

            for x in set(ENTRANCED_DYING):
                if x.nick in other_voters:
                    ENTRANCED_DYING.remove(x)

    if {p.nick for p in var.ROLES["succubus"]} & not_lynching: # FIXME
        if votee is None:
            ENTRANCED_DYING.clear()
            return

        for x in set(ENTRANCED_DYING):
            if x.nick in not_lynching:
                ENTRANCED_DYING.remove(x)

@event_listener("chk_decision_lynch", priority=5)
def on_chk_decision_lynch(evt, cli, var, voters):
    # a different event may override the original votee, but people voting along with succubus
    # won't necessarily know that, so base whether or not they risk death on the person originally voted
    _kill_entranced_voters(var, evt.params.votelist, evt.params.not_lynching, evt.params.original_votee)

@event_listener("chk_decision_abstain")
def on_chk_decision_abstain(evt, cli, var, not_lynching):
    _kill_entranced_voters(var, evt.params.votelist, not_lynching, None)

# entranced logic should run after team wins have already been determined (aka run last)
# we do not want to override the win conditions for neutral roles should they win while entranced
# For example, entranced monsters should win with other monsters should mosnters win, and be
# properly credited with a team win in that event.
@event_listener("player_win", priority=6)
def on_player_win(evt, var, user, role, winner, survived):
    if user in ENTRANCED:
        evt.data["special"].append("entranced")
        if winner != "succubi" and role not in var.TRUE_NEUTRAL_ROLES:
            evt.data["won"] = False
        else:
            evt.data["iwon"] = True
    if role == "succubus" and winner == "succubi":
        evt.data["won"] = True

@event_listener("chk_win", priority=2)
def on_chk_win(evt, cli, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    lsuccubi = len(rolemap.get("succubus", ()))
    lentranced = len([x for x in ENTRANCED if x.nick not in var.DEAD])
    if lsuccubi and var.PHASE == "day" and lpl - lsuccubi == lentranced:
        evt.data["winner"] = "succubi"
        evt.data["message"] = messages["succubus_win"].format(plural("succubus", lsuccubi), plural("has", lsuccubi), plural("master's", lsuccubi))

@event_listener("can_exchange")
def on_can_exchange(evt, var, user, target):
    if user in var.ROLES["succubus"] or target in var.ROLES["succubus"]:
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    global ALL_SUCC_IDLE
    if "succubus" not in allroles:
        return
    if user in VISITED:
        # if it's night, also unentrance the person they visited
        if var.PHASE == "night" and var.GAMEPHASE == "night":
            if VISITED[user] in ENTRANCED:
                ENTRANCED.discard(VISITED[user])
                ENTRANCED_DYING.discard(VISITED[user])
                VISITED[user].send(messages["entranced_revert_win"])
        del VISITED[user]

    # if all succubi are dead, one of two things happen:
    # 1. if all succubi idled out (every last one of them), un-entrance people
    # 2. otherwise, kill all entranced people immediately, they still remain entranced (and therefore lose)
    # death_triggers is False for an idle-out, so we use that to determine which it is
    if death_triggers:
        ALL_SUCC_IDLE = False
    if var.ROLES["succubus"]:
        entranced_alive = ENTRANCED.difference(evt.params.deadlist).intersection(evt.data["pl"])
        if ALL_SUCC_IDLE:
            while ENTRANCED:
                e = ENTRANCED.pop()
                e.send(messages["entranced_revert_win"])
        elif entranced_alive:
            msg = []
            # Run in two loops so we can play the message for everyone dying at once before we actually
            # kill any of them off (if we killed off first, the message order would be wrong wrt death chains)
            comma = ""
            if var.ROLE_REVEAL in ("on", "team"):
                comma = ","
            for e in entranced_alive:
                if var.ROLE_REVEAL in ("on", "team"):
                    role = get_reveal_role(e.nick)
                    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                    msg.append("\u0002{0}\u0002, a{1} \u0002{2}\u0002".format(e, an, role))
                else:
                    msg.append("\u0002{0}\u0002".format(e))
            if len(msg) == 1:
                channels.Main.send(messages["succubus_die_kill"].format(msg[0] + comma))
            elif len(msg) == 2:
                channels.Main.send(messages["succubus_die_kill"].format(msg[0] + comma + " and " + msg[1] + comma))
            else:
                channels.Main.send(messages["succubus_die_kill"].format(", ".join(msg[:-1]) + ", and " + msg[-1] + comma))
            for e in entranced_alive:
                # to ensure we do not double-kill someone, notify all child deaths that we'll be
                # killing off everyone else that is entranced so they don't need to bother
                dlc = list(evt.params.deadlist)
                dlc.extend(entranced_alive - {e})
                debuglog("{0} (succubus) SUCCUBUS DEATH KILL: {1} ({2})".format(user, e, get_main_role(e)))
                evt.params.del_player(e, end_game=False, killer_role="succubus",
                    deadlist=dlc, original=evt.params.original, ismain=False)
                evt.data["pl"] = evt.params.refresh_pl(evt.data["pl"])
        ENTRANCED_DYING.clear()

@event_listener("transition_day_resolve", priority=1)
def on_transition_day_resolve(evt, var, victim):
    if victim in var.ROLES["succubus"] and VISITED.get(victim) and victim not in evt.data["dead"] and victim in evt.data["onlybywolves"]:
        # TODO: check if this is necessary for succubus, it's to prevent a message playing if alpha bites
        # a harlot that is visiting a wolf, since the bite succeeds in that case.
        if victim not in evt.data["bitten"]:
            evt.data["message"].append(messages["target_not_home"])
            evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_day_resolve_end", priority=1)
def on_transition_day_resolve_end(evt, var, victims):
    for victim in victims + evt.data["bitten"]:
        if victim in evt.data["dead"] and victim in VISITED.values() and (victim in evt.data["bywolves"] or victim in evt.data["bitten"]):
            for succubus in VISITED:
                if VISITED[succubus] is victim and succubus not in evt.data["bitten"] and succubus not in evt.data["dead"]:
                    if var.ROLE_REVEAL in ("on", "team"):
                        evt.data["message"].append(messages["visited_victim"].format(succubus, get_reveal_role(succubus.nick)))
                    else:
                        evt.data["message"].append(messages["visited_victim_noreveal"].format(succubus))
                    evt.data["bywolves"].add(succubus)
                    evt.data["onlybywolves"].add(succubus)
                    evt.data["dead"].append(succubus)

@event_listener("night_acted")
def on_night_acted(evt, var, target, spy):
    if VISITED.get(target):
        evt.data["acted"] = True

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(VISITED) + len(PASSED)
    evt.data["nightroles"].extend(get_all_players(("succubus",)))

@event_listener("targeted_command")
def on_targeted_command(evt, var, name, actor, orig_target, tags):
    if "beneficial" not in tags and actor in ENTRANCED and evt.data["target"].nick in var.ROLES["succubus"]:
        try:
            what = evt.params.action
        except AttributeError:
            what = name
        actor.send(messages["no_acting_on_succubus"].format(what))
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    succubi = get_all_players(("succubus",))
    for succubus in succubi:
        pl = get_players()
        random.shuffle(pl)
        pl.remove(succubus)
        to_send = "succubus_notify"
        if succubus.prefers_simple():
            to_send = "succubus_simple"
        succ = []
        for p in pl:
            if p in succubi:
                succ.append("{0} (succubus)".format(p))
            else:
                succ.append(p.nick)
        succubus.send(messages[to_send], "Players: " + ", ".join(succ), sep="\n")

@event_listener("begin_day")
def on_begin_day(evt, var):
    VISITED.clear()
    ENTRANCED_DYING.clear()
    PASSED.clear()

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    for v in ENTRANCED_DYING:
        var.DYING.add(v) # indicate that the death bypasses protections
        evt.data["victims"].append(v)
        evt.data["onlybywolves"].discard(v)
        # we do not add to killers as retribution totem should not work on entranced not following succubus

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("succubus",)))

@event_listener("vg_kill")
def on_vg_kill(evt, var, ghost, target):
    if ghost in ENTRANCED:
        evt.data["pl"] -= get_all_players(("succubus",))

@event_listener("swap_player")
def on_swap(evt, var, old_user, user):
    if old_user in ENTRANCED:
        ENTRANCED.remove(old_user)
        ENTRANCED.add(user)
    if old_user in ENTRANCED_DYING:
        ENTRANCED_DYING.remove(old_user)
        ENTRANCED_DYING.add(user)

    for succubus, target in set(VISITED.items()):
        if old_user is succubus:
            VISITED[user] = VISITED.pop(succubus)
        if old_user is target:
            VISITED[succubus] = user

    if old_user in PASSED:
        PASSED.remove(old_user)
        PASSED.add(user)

@event_listener("reset")
def on_reset(evt, var):
    global ALL_SUCC_IDLE
    ALL_SUCC_IDLE = True
    ENTRANCED.clear()
    ENTRANCED_DYING.clear()
    VISITED.clear()
    PASSED.clear()

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if ENTRANCED:
        evt.data["output"].append("\u0002entranced players\u0002: {0}".format(", ".join(p.nick for p in ENTRANCED)))

    if ENTRANCED_DYING:
        evt.data["output"].append("\u0002dying entranced players\u0002: {0}".format(", ".join(p.nick for p in ENTRANCED_DYING)))

# vim: set sw=4 expandtab:
