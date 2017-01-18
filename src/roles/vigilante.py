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
PASSED = set()

@cmd("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("vigilante",))
def vigilante_kill(cli, nick, chan, rest):
    """Kill someone at night, but you die too if they aren't a wolf or win stealer!"""
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
    PASSED.discard(nick)

    msg = messages["wolf_target"].format(orig)
    pm(cli, nick, messages["player"].format(msg))

    debuglog("{0} ({1}) KILL: {2} ({3})".format(nick, get_role(nick), victim, get_role(victim)))

    chk_nightdone(cli)

@cmd("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("vigilante",))
def vigilante_retract(cli, nick, chan, rest):
    """Removes a vigilante's kill selection."""
    if nick not in KILLS and nick not in PASSED:
        return
    if nick in KILLS:
        del KILLS[nick]
    PASSED.discard(nick)
    pm(cli, nick, messages["retracted_kill"])

@cmd("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("vigilante",))
def vigilante_pass(cli, nick, chan, rest):
    """Do not kill anyone tonight as a vigilante."""
    if nick in KILLS:
        del KILLS[nick]
    PASSED.add(nick)
    pm(cli, nick, messages["hunter_pass"])

    debuglog("{0} ({1}) PASS".format(nick, get_role(nick)))
    chk_nightdone(cli)

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    PASSED.discard(nick)
    if nick in KILLS:
        del KILLS[nick]
    for h,v in list(KILLS.items()):
        if v == nick:
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
    if prefix in PASSED:
        PASSED.discard(prefix)
        PASSED.add(nick)

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in KILLS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(var.ROLES["vigilante"])

@event_listener("transition_day", priority=2)
def on_transition_day(evt, cli, var):
    for k, d in list(KILLS.items()):
        evt.data["victims"].append(d)
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d].append(k)
        # important, otherwise our del_player listener lets hunter kill again
        del KILLS[k]

        if get_role(d) not in var.WOLF_ROLES | var.WIN_STEALER_ROLES:
            var.DYING.add(k)

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    if actor in KILLS:
        del KILLS[actor]
    if nick in KILLS:
        del KILLS[nick]
    PASSED.discard(actor)
    PASSED.discard(nick)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    evt.data["actedcount"] += len(KILLS) + len(PASSED)
    evt.data["nightroles"].extend(get_roles("vigilante"))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    ps = list_players()
    for vigilante in var.ROLES["vigilante"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(vigilante)
        if vigilante in var.PLAYERS and not is_user_simple(vigilante):
            pm(cli, vigilante, messages["vigilante_notify"])
        else:
            pm(cli, vigilante, messages["vigilante_simple"])
        pm(cli, vigilante, "Players: " + ", ".join(pl))

@event_listener("succubus_visit")
def on_succubus_visit(evt, cli, var, nick, victim):
    if KILLS.get(victim) in var.ROLES["succubus"]:
        pm(cli, victim, messages["no_kill_succubus"].format(KILLS[victim]))
        del KILLS[victim]

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    KILLS.clear()
    PASSED.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, cli, var, kind):
    if kind == "night_kills":
        evt.data["vigilante"] = len(var.ROLES["vigilante"])

# vim: set sw=4 expandtab:
