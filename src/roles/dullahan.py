import math
import re
import random
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

KILLS = {} # type: Dict[str, str]
TARGETS = {} # type: Dict[str, Set[str]]

@cmd("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("dullahan",))
def dullahan_kill(cli, nick, chan, rest):
    """Kill someone at night as a dullahan until everyone on your list is dead."""
    if not TARGETS[nick] & set(list_players()):
        pm(cli, nick, messages["dullahan_targets_dead"])
        return

    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if victim == nick:
        pm(cli, nick, messages["no_suicide"])
        return

    orig = victim
    evt = Event("targeted_command", {"target": victim, "misdirection": True, "exchange": True})
    evt.dispatch(cli, var, "kill", nick, victim, frozenset({"detrimental"}))
    if evt.prevent_default:
        return
    victim = evt.data["target"]

    KILLS[nick] = victim

    msg = messages["wolf_target"].format(orig)
    pm(cli, nick, messages["player"].format(msg))

    debuglog("{0} ({1}) KILL: {2} ({3})".format(nick, get_role(nick), victim, get_role(victim)))

    chk_nightdone(cli)

@cmd("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("dullahan",))
def dullahan_retract(cli, nick, chan, rest):
    """Removes a dullahan's kill selection."""
    if nick not in KILLS:
        return
    if nick in KILLS:
        del KILLS[nick]
    pm(cli, nick, messages["retracted_kill"])

@event_listener("player_win")
def on_player_win(evt, cli, var, nick, role, winner, survived):
    if role != "dullahan":
        return
    alive = set(list_players())
    if nick in var.ENTRANCED:
        alive -= var.ROLES["succubus"]
    if not TARGETS[nick] & alive:
        evt.data["iwon"] = True

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    for h,v in list(KILLS.items()):
        if v == nick:
            pm(cli, h, messages["hunter_discard"])
            del KILLS[h]
        elif h == nick:
            del KILLS[h]
    if death_triggers and nickrole == "dullahan":
        pl = evt.data["pl"]
        targets = TARGETS[nick] & set(pl)
        if targets:
            target = random.choice(list(targets))
            if "totem" in var.ACTIVE_PROTECTIONS[target]:
                var.ACTIVE_PROTECTIONS[target].remove("totem")
                cli.msg(botconfig.CHANNEL, messages["dullahan_die_totem"].format(nick, target))
            elif "angel" in var.ACTIVE_PROTECTIONS[target]:
                var.ACTIVE_PROTECTIONS[target].remove("angel")
                cli.msg(botconfig.CHANNEL, messages["dullahan_die_angel"].format(nick, target))
            elif "bodyguard" in var.ACTIVE_PROTECTIONS[target]:
                var.ACTIVE_PROTECTIONS[target].remove("bodyguard")
                for bg in var.ROLES["bodyguard"]:
                    if var.GUARDED.get(bg) == target:
                        cli.msg(botconfig.CHANNEL, messages["dullahan_die_bodyguard"].format(nick, target, bg))
                        evt.params.del_player(cli, bg, True, end_game=False, killer_role=nickrole, deadlist=evt.params.deadlist, original=evt.params.original, ismain=False)
                        evt.data["pl"] = evt.params.refresh_pl(pl)
                        break
            elif "blessing" in var.ACTIVE_PROTECTIONS[target] or (var.GAMEPHASE == "day" and target in var.ROLES["blessed villager"]):
                if "blessing" in var.ACTIVE_PROTECTIONS[target]:
                    var.ACTIVE_PROTECTIONS[target].remove("blessing")
                # don't message the channel whenever a blessing blocks a kill, but *do* let the dullahan know so they don't try to report it as a bug
                pm(cli, nick, messages["assassin_fail_blessed"].format(target))
            else:
                if var.ROLE_REVEAL in ("on", "team"):
                    role = get_reveal_role(target)
                    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                    cli.msg(botconfig.CHANNEL, messages["dullahan_die_success"].format(nick, target, an, role))
                else:
                    cli.msg(botconfig.CHANNEL, messages["dullahan_die_success_noreveal"].format(nick, target))
                debuglog("{0} ({1}) DULLAHAN ASSASSINATE: {2} ({3})".format(nick, nickrole, target, get_role(target)))
                evt.params.del_player(cli, target, True, end_game=False, killer_role=nickrole, deadlist=evt.params.deadlist, original=evt.params.original, ismain=False)
                evt.data["pl"] = evt.params.refresh_pl(pl)

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

@event_listener("acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in KILLS:
        evt.data["acted"] = True

@event_listener("transition_day", priority=2)
def on_transition_day(evt, cli, var):
    for k, d in list(KILLS.items()):
        evt.data["victims"].append(d)
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d] = k
        del KILLS[k]

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    if actor in KILLS:
        del KILLS[actor]
    if nick in KILLS:
        del KILLS[nick]
    if actor_role == "dullahan" and nick_role != "dullahan" and actor in TARGETS:
        TARGETS[nick] = TARGETS[actor] - {nick}
        del TARGETS[actor]
    elif nick_role == "dullahan" and actor_role != "dullahan" and nick in TARGETS:
        TARGETS[actor] = TARGETS[nick] - {actor}
        del TARGETS[nick]

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    spl = set(list_players())
    evt.data["actedcount"] += len(KILLS)
    for p in var.ROLES["dullahan"]:
        if TARGETS[p] & spl:
            evt.data["nightroles"].append(p)

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    for dullahan in var.ROLES["dullahan"]:
        targets = list(TARGETS[dullahan])
        for target in var.DEAD:
            if target in targets:
                targets.remove(target)
        if not targets: # already all dead
            pm(cli, dullahan, messages["dullahan_targets_dead"])
            continue
        random.shuffle(targets)
        if dullahan in var.PLAYERS and not is_user_simple(dullahan):
            pm(cli, dullahan, messages["dullahan_notify"])
        else:
            pm(cli, dullahan, messages["dullahan_simple"])
        t = messages["dullahan_targets"] if var.FIRST_NIGHT else messages["dullahan_remaining_targets"]
        pm(cli, dullahan, t + ", ".join(targets))

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
def on_revealroles_role(evt, cli, var, nickname, role):
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

# vim: set sw=4 expandtab:
