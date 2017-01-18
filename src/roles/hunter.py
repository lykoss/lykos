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
HUNTERS = set()
PASSED = set()

@cmd("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hunter",))
def hunter_kill(cli, nick, chan, rest):
    """Kill someone once per game."""
    if nick in HUNTERS and nick not in KILLS:
        pm(cli, nick, messages["hunter_already_killed"])
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
    HUNTERS.add(nick)
    PASSED.discard(nick)

    msg = messages["wolf_target"].format(orig)
    pm(cli, nick, messages["player"].format(msg))

    debuglog("{0} ({1}) KILL: {2} ({3})".format(nick, get_role(nick), victim, get_role(victim)))
    chk_nightdone(cli)

@cmd("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("hunter",))
def hunter_retract(cli, nick, chan, rest):
    """Removes a hunter's kill selection."""
    if nick not in KILLS and nick not in PASSED:
        return
    if nick in KILLS:
        del KILLS[nick]
    HUNTERS.discard(nick)
    PASSED.discard(nick)
    pm(cli, nick, messages["retracted_kill"])

@cmd("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hunter",))
def hunter_pass(cli, nick, chan, rest):
    """Do not use hunter's once-per-game kill tonight."""
    if nick in HUNTERS and nick not in KILLS:
        pm(cli, nick, messages["hunter_already_killed"])
        return
    if nick in KILLS:
        del KILLS[nick]
    HUNTERS.discard(nick)
    PASSED.add(nick)
    pm(cli, nick, messages["hunter_pass"])

    debuglog("{0} ({1}) PASS".format(nick, get_role(nick)))
    chk_nightdone(cli)

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    HUNTERS.discard(nick)
    PASSED.discard(nick)
    if nick in KILLS:
        del KILLS[nick]
    for h,v in list(KILLS.items()):
        if v == nick:
            HUNTERS.discard(h)
            pm(cli, h, messages["hunter_discard"])
            del KILLS[h]

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
    if prefix in HUNTERS:
        HUNTERS.discard(prefix)
        HUNTERS.add(nick)
    if prefix in PASSED:
        PASSED.discard(prefix)
        PASSED.add(nick)

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in KILLS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(var.ROLES["hunter"])

@event_listener("transition_day", priority=2)
def on_transition_day(evt, cli, var):
    for k, d in list(KILLS.items()):
        evt.data["victims"].append(d)
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d].append(k)
        # important, otherwise our del_player listener lets hunter kill again
        del KILLS[k]

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    if actor in KILLS:
        del KILLS[actor]
    if nick in KILLS:
        del KILLS[nick]
    HUNTERS.discard(actor)
    HUNTERS.discard(nick)
    PASSED.discard(actor)
    PASSED.discard(nick)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    evt.data["actedcount"] += len(KILLS) + len(PASSED)
    evt.data["nightroles"].extend([p for p in var.ROLES["hunter"] if p not in HUNTERS or p in KILLS])

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    ps = list_players()
    for hunter in var.ROLES["hunter"]:
        if hunter in HUNTERS:
            continue #already killed
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(hunter)
        if hunter in var.PLAYERS and not is_user_simple(hunter):
            pm(cli, hunter, messages["hunter_notify"])
        else:
            pm(cli, hunter, messages["hunter_simple"])
        pm(cli, hunter, "Players: " + ", ".join(pl))

@event_listener("succubus_visit")
def on_succubus_visit(evt, cli, var, nick, victim):
    if KILLS.get(victim) in var.ROLES["succubus"]:
        pm(cli, victim, messages["no_kill_succubus"].format(KILLS[victim]))
        del KILLS[victim]
        HUNTERS.discard(victim)

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    KILLS.clear()
    PASSED.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    PASSED.clear()
    HUNTERS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, cli, var, kind):
    if kind == "night_kills":
        # hunters is the set of all hunters that have not killed in a *previous* night
        # (if they're in both HUNTERS and KILLS, then they killed tonight and should be counted)
        hunters = (set(var.ROLES["hunter"]) - HUNTERS) | set(KILLS.keys())
        evt.data["hunter"] = len(hunters)

# vim: set sw=4 expandtab:
