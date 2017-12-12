import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

ENTRANCED = set()
ENTRANCED_DYING = set()
VISITED = {}
ALL_SUCC_IDLE = True

@cmd("visit", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("succubus",))
def hvisit(cli, nick, chan, rest):
    """Entrance a player, converting them to your team."""
    if VISITED.get(nick):
        pm(cli, nick, messages["succubus_already_visited"].format(VISITED[nick]))
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, True)
    if not victim:
        return
    if nick == victim:
        pm(cli, nick, messages["succubus_not_self"])
        return

    succ = users._get(nick) # FIXME
    target = users._get(victim) # FIXME

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": False})
    evt.dispatch(var, "visit", succ, target, frozenset({"detrimental", "immediate"}))
    if evt.prevent_default:
        return
    victim = evt.data["target"].nick

    VISITED[nick] = victim
    if victim not in var.ROLES["succubus"]:
        ENTRANCED.add(victim)
        pm(cli, nick, messages["succubus_target_success"].format(victim))
    else:
        pm(cli, nick, messages["harlot_success"].format(victim))
    if nick != victim:
        if victim not in var.ROLES["succubus"]:
            pm(cli, victim, messages["notify_succubus_target"].format(nick))
        else:
            pm(cli, victim, messages["harlot_success"].format(nick))
        revt = Event("succubus_visit", {})
        revt.dispatch(cli, var, nick, victim)

        # TODO: split these into assassin, hag, and alpha wolf when they are split off
        if var.TARGETED.get(victim) in var.ROLES["succubus"]:
            msg = messages["no_target_succubus"].format(var.TARGETED[victim])
            del var.TARGETED[victim]
            if victim in var.ROLES["village drunk"]:
                target = random.choice(list(set(list_players()) - var.ROLES["succubus"] - {victim}))
                msg += messages["drunk_target"].format(target)
                var.TARGETED[victim] = target
            pm(cli, victim, nick)
        if victim in var.HEXED and var.LASTHEXED[victim] in var.ROLES["succubus"]:
            pm(cli, victim, messages["retract_hex_succubus"].format(var.LASTHEXED[victim]))
            var.TOBESILENCED.remove(nick)
            var.HEXED.remove(victim)
            del var.LASTHEXED[victim]
        if var.BITE_PREFERENCES.get(victim) in var.ROLES["succubus"]:
            pm(cli, victim, messages["no_kill_succubus"].format(var.BITE_PREFERENCES[victim]))
            del var.BITE_PREFERENCES[victim]

    debuglog("{0} (succubus) VISIT: {1} ({2})".format(nick, victim, get_role(victim)))
    chk_nightdone(cli)

@cmd("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("succubus",))
def pass_cmd(cli, nick, chan, rest):
    """Do not entrance someone tonight."""
    if VISITED.get(nick):
        pm(cli, nick, messages["succubus_already_visited"].format(VISITED[nick]))
        return
    VISITED[nick] = None
    pm(cli, nick, messages["succubus_pass"])
    debuglog("{0} (succubus) PASS".format(nick))
    chk_nightdone(cli)

@event_listener("harlot_visit")
def on_harlot_visit(evt, var, harlot, victim):
    if victim.nick in var.ROLES["succubus"]:
        harlot.send(messages["notify_succubus_target"].format(victim))
        victim.send(messages["succubus_harlot_success"].format(harlot))
        ENTRANCED.add(harlot.nick)

@event_listener("get_random_totem_targets")
def on_get_random_totem_targets(evt, var, shaman):
    if shaman.nick in ENTRANCED:
        for succubus in get_all_players(("succubus",)):
            if succubus in evt.data["targets"]:
                evt.data["targets"].remove(succubus)

@event_listener("chk_decision", priority=0)
def on_chk_decision(evt, cli, var, force):
    for votee, voters in evt.data["votelist"].items():
        if votee in var.ROLES["succubus"]:
            for vtr in ENTRANCED:
                if vtr in voters:
                    voters.remove(vtr)

def _kill_entranced_voters(var, votelist, not_lynching, votee):
    if not var.ROLES["succubus"] & (set(itertools.chain(*votelist.values())) | not_lynching):
        # none of the succubi voted (or there aren't any succubi), so short-circuit
        return
    # kill off everyone entranced that did not follow one of the succubi's votes or abstain
    # unless a succubus successfully voted the target, then people that didn't follow are spared
    ENTRANCED_DYING.update(ENTRANCED - var.DEAD)
    for other_votee, other_voters in votelist.items():
        if var.ROLES["succubus"] & set(other_voters):
            if votee == other_votee:
                ENTRANCED_DYING.clear()
                return
            ENTRANCED_DYING.difference_update(other_voters)
    if var.ROLES["succubus"] & not_lynching:
        if votee is None:
            ENTRANCED_DYING.clear()
            return
        ENTRANCED_DYING.difference_update(not_lynching)

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
    nick = user.nick
    if nick in ENTRANCED:
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
    lentranced = len(ENTRANCED - var.DEAD)
    if lsuccubi and var.PHASE == "day" and lpl - lsuccubi == lentranced:
        evt.data["winner"] = "succubi"
        evt.data["message"] = messages["succubus_win"].format(plural("succubus", lsuccubi), plural("has", lsuccubi), plural("master's", lsuccubi))

@event_listener("can_exchange")
def on_can_exchange(evt, var, user, target):
    if user.nick in var.ROLES["succubus"] or target.nick in var.ROLES["succubus"]:
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    global ALL_SUCC_IDLE
    if "succubus" not in allroles:
        return
    if user.nick in VISITED:
        # if it's night, also unentrance the person they visited
        if var.PHASE == "night" and var.GAMEPHASE == "night":
            if VISITED[user.nick] in ENTRANCED:
                ENTRANCED.discard(VISITED[user.nick])
                ENTRANCED_DYING.discard(VISITED[user.nick])
                pm(user.client, VISITED[user.nick], messages["entranced_revert_win"])
        del VISITED[user.nick]

    # if all succubi are dead, one of two things happen:
    # 1. if all succubi idled out (every last one of them), un-entrance people
    # 2. otherwise, kill all entranced people immediately, they still remain entranced (and therefore lose)
    # death_triggers is False for an idle-out, so we use that to determine which it is
    if death_triggers:
        ALL_SUCC_IDLE = False
    if len(var.ROLES["succubus"]) == 0:
        entranced_alive = {users._get(x) for x in ENTRANCED}.difference(evt.params.deadlist).intersection(evt.data["pl"]) # FIXME
        if ALL_SUCC_IDLE:
            while ENTRANCED:
                e = ENTRANCED.pop()
                pm(user.client, e, messages["entranced_revert_win"])
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
    if victim.nick in var.ROLES["succubus"] and VISITED.get(victim.nick) and victim not in evt.data["dead"] and victim in evt.data["onlybywolves"]:
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
        if victim in evt.data["dead"] and victim.nick in VISITED.values() and (victim in evt.data["bywolves"] or victim in evt.data["bitten"]):
            for succ in VISITED:
                user = users._get(succ) # FIXME
                if VISITED[succ] == victim.nick and user not in evt.data["bitten"] and user not in evt.data["dead"]:
                    if var.ROLE_REVEAL in ("on", "team"):
                        evt.data["message"].append(messages["visited_victim"].format(succ, get_reveal_role(succ)))
                    else:
                        evt.data["message"].append(messages["visited_victim_noreveal"].format(succ))
                    evt.data["bywolves"].add(user)
                    evt.data["onlybywolves"].add(user)
                    evt.data["dead"].append(user)

@event_listener("night_acted")
def on_night_acted(evt, var, user, actor):
    if VISITED.get(user.nick):
        evt.data["acted"] = True

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(VISITED)
    evt.data["nightroles"].extend(get_all_players(("succubus",)))

@event_listener("targeted_command")
def on_targeted_command(evt, var, name, actor, orig_target, tags):
    if "beneficial" not in tags and actor.nick in ENTRANCED and evt.data["target"].nick in var.ROLES["succubus"]:
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

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    for v in ENTRANCED_DYING:
        user = users._get(v) # FIXME
        var.DYING.add(user) # indicate that the death bypasses protections
        evt.data["victims"].append(user)
        evt.data["onlybywolves"].discard(user)
        # we do not add to killers as retribution totem should not work on entranced not following succubus

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("succubus",)))

@event_listener("vg_kill")
def on_vg_kill(evt, var, ghost, target):
    if ghost.nick in ENTRANCED:
        evt.data["pl"] -= var.ROLES["succubus"]

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    if prefix in ENTRANCED:
        ENTRANCED.remove(prefix)
        ENTRANCED.add(nick)
    if prefix in ENTRANCED_DYING:
        ENTRANCED_DYING.remove(prefix)
        ENTRANCED_DYING.add(nick)
    kvp = {}
    for a,b in VISITED.items():
        s = nick if a == prefix else a
        t = nick if b == prefix else b
        kvp[s] = t
    VISITED.update(kvp)
    if prefix in VISITED:
        del VISITED[prefix]

@event_listener("reset")
def on_reset(evt, var):
    global ALL_SUCC_IDLE
    ALL_SUCC_IDLE = True
    ENTRANCED.clear()
    ENTRANCED_DYING.clear()
    VISITED.clear()

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if ENTRANCED:
        evt.data["output"].append("\u0002entranced players\u0002: {0}".format(", ".join(ENTRANCED)))

    if ENTRANCED_DYING:
        evt.data["output"].append("\u0002dying entranced players\u0002: {0}".format(", ".join(ENTRANCED_DYING)))

# vim: set sw=4 expandtab:
