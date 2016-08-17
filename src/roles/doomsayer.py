import re
import random

import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

SEEN = set()
KILLS = {}
SICK = {}
LYCANS = {}

@cmd("see", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("doomsayer",))
def see(cli, nick, chan, rest):
    """Use your paranormal senses to determine a player's doom."""
    role = get_role(nick)
    if nick in SEEN:
        pm(cli, nick, messages["seer_fail"])
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if victim == nick:
        pm(cli, nick, messages["no_see_self"])
        return
    if in_wolflist(nick, victim):
        pm(cli, nick, messages["no_see_wolf"])
        return

    evt = Event("targeted_command", {"target": victim, "misdirection": True, "exchange": True})
    evt.dispatch(cli, var, "see", nick, victim, frozenset({"detrimental", "immediate"}))
    if evt.prevent_default:
        return
    victim = evt.data["target"]
    victimrole = get_role(victim)
    
    mode = random.randint(1, 3)
    if mode == 1:
        mode = "DEATH"
        pm(cli, nick, messages["doomsayer_death"].format(victim))
        KILLS[nick] = victim
    elif mode == 2:
        mode = "LYCAN"
        pm(cli, nick, messages["doomsayer_lycan"].format(victim))
        LYCANS[nick] = victim
    elif mode == 3:
        mode = "SICK"
        pm(cli, nick, messages["doomsayer_sick"].format(victim))
        SICK[nick] = victim

    debuglog("{0} ({1}) SEE: {2} ({3}) - {4}".format(nick, role, victim, victimrole, mode))
    relay_wolfchat_command(cli, nick, messages["doomsayer_wolfchat"].format(nick, victim), ("doomsayer",), is_wolf_command=True)

    SEEN.add(nick)
    chk_nightdone(cli)

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    if prefix in SEEN:
        SEEN.remove(prefix)
        SEEN.add(nick)
    for dictvar in (KILLS, SICK, LYCANS):
        kvp = []
        for a, b in dictvar.items():
            if a == prefix:
                a = nick
            if b == prefix:
                b = nick
            kvp.append((a, b))
        dictvar.update(kvp)
        if prefix in dictvar:
            del dictvar[prefix]

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in SEEN:
        evt.data["acted"] = True

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    if actor_role == "doomsayer" and nick_role != "doomsayer":
        SEEN.discard(actor)
        if actor in KILLS:
            del KILLS[actor]
        elif actor in SICK:
            del SICK[actor]
        elif actor in LYCANS:
            del LYCANS[actor]
    elif nick_role == "doomsayer" and actor_role != "doomsayer":
        SEEN.discard(nick)
        if nick in KILLS:
            del KILLS[nick]
        elif nick in SICK:
            del SICK[nick]
        elif nick in LYCANS:
            del LYCANS[nick]

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    SEEN.discard(nick)
    for dictvar in (KILLS, SICK, LYCANS):
        for k, v in list(dictvar.items()):
            if nick == k or nick == v:
                del dictvar[k]

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    evt.data["actedcount"] += len(SEEN)
    evt.data["nightroles"].extend(get_roles("doomsayer"))

@event_listener("transition_day", priority=2)
def on_transition_day(evt, cli, var):
    for k, d in list(KILLS.items()):
        evt.data["victims"].append(d)
        # even though doomsayer is a wolf, remove from onlybywolves since
        # that particular item indicates that they were the target of a wolf !kill.
        # If doomsayer doesn't remove this, roles such as harlot or monster will not
        # die if they are the target of a doomsayer !see that ends up killing the target.
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d].append(k)

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    var.DISEASED.update(SICK.values())
    var.SILENCED.update(SICK.values())
    var.LYCANTHROPES.update(LYCANS.values())

    SEEN.clear()
    KILLS.clear()
    SICK.clear()
    LYCANS.clear()

@event_listener("reset")
def on_reset(evt, var):
    SEEN.clear()
    KILLS.clear()
    SICK.clear()
    LYCANS.clear()

# vim: set sw=4 expandtab:
