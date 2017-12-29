import re
import random

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

SEEN = set()
KILLS = {}
SICK = {}
LYCANS = {}

_mappings = ("death", KILLS), ("lycan", LYCANS), ("sick", SICK)

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

    doomsayer = users._get(nick) # FIXME
    target = users._get(victim) # FIXME

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    evt.dispatch(var, "see", doomsayer, target, frozenset({"detrimental", "immediate"}))
    if evt.prevent_default:
        return
    victim = evt.data["target"].nick
    victimrole = get_role(victim)

    mode, mapping = random.choice(_mappings)
    pm(cli, nick, messages["doomsayer_{0}".format(mode)].format(victim))
    if mode != "sick" or nick not in var.IMMUNIZED:
        mapping[nick] = victim

    debuglog("{0} ({1}) SEE: {2} ({3}) - {4}".format(nick, role, victim, victimrole, mode.upper()))
    relay_wolfchat_command(cli, nick, messages["doomsayer_wolfchat"].format(nick, victim), ("doomsayer",), is_wolf_command=True)

    SEEN.add(nick)
    chk_nightdone(cli)

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    if prefix in SEEN:
        SEEN.remove(prefix)
        SEEN.add(nick)
    for name, dictvar in _mappings:
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
def on_acted(evt, var, user, actor):
    if user.nick in SEEN:
        evt.data["acted"] = True

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if actor_role == "doomsayer" and target_role != "doomsayer":
        SEEN.discard(actor.nick)
        for name, mapping in _mappings:
            mapping.pop(actor.nick, None)

    elif target_role == "doomsayer" and actor_role != "doomsayer":
        SEEN.discard(target.nick)
        for name, mapping in _mappings:
            mapping.pop(target.nick, None)

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    SEEN.discard(user.nick)
    for name, dictvar in _mappings:
        for k, v in list(dictvar.items()):
            if user.nick in (k, v):
                del dictvar[k]

@event_listener("doctor_immunize")
def on_doctor_immunize(evt, cli, var, doctor, target):
    if target in SICK.values():
        for n, v in list(SICK.items()):
            if v == target:
                del SICK[n]
        evt.data["message"] = "not_sick"

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("doomsayer",)))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(SEEN)
    evt.data["nightroles"].extend(get_all_players(("doomsayer",)))

@event_listener("abstain")
def on_abstain(evt, cli, var, nick):
    if nick in SICK.values():
        pm(cli, nick, messages["illness_no_vote"])
        evt.prevent_default = True

@event_listener("lynch")
def on_lynch(evt, cli, var, nick):
    if nick in SICK.values():
        pm(cli, nick, messages["illness_no_vote"])
        evt.prevent_default = True

@event_listener("get_voters")
def on_get_voters(evt, var):
    evt.data["voters"].difference_update(SICK.values())

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    for victim in SICK.values():
        user = users._get(victim)
        user.queue_message(messages["player_sick"])
    if SICK:
        user.send_messages()

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    for k, v in list(KILLS.items()):
        killer = users._get(k) # FIXME
        victim = users._get(v) # FIXME
        evt.data["victims"].append(victim)
        # even though doomsayer is a wolf, remove from onlybywolves since
        # that particular item indicates that they were the target of a wolf !kill.
        # If doomsayer doesn't remove this, roles such as harlot or monster will not
        # die if they are the target of a doomsayer !see that ends up killing the target.
        evt.data["onlybywolves"].discard(victim)
        evt.data["killers"][victim].append(killer)

@event_listener("begin_day")
def on_begin_day(evt, var):
    var.DISEASED.update(SICK.values())
    var.SILENCED.update(SICK.values())
    var.LYCANTHROPES.update(LYCANS.values())

    SEEN.clear()
    KILLS.clear()
    LYCANS.clear()

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, cli, var):
    SICK.clear()

@event_listener("reset")
def on_reset(evt, var):
    SEEN.clear()
    KILLS.clear()
    SICK.clear()
    LYCANS.clear()

# vim: set sw=4 expandtab:
