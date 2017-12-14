import math
import re
import random

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

INVESTIGATED = set()

@cmd("id", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("detective",))
def investigate(cli, nick, chan, rest):
    """Investigate a player to determine their exact role."""
    if nick in INVESTIGATED:
        pm(cli, nick, messages["already_investigated"])
        return
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if victim == nick:
        pm(cli, nick, messages["no_investigate_self"])
        return

    evt = Event("targeted_command", {"target": victim, "misdirection": True, "exchange": True})
    evt.dispatch(cli, var, "see", nick, victim, frozenset({"info", "immediate"}))
    if evt.prevent_default:
        return
    victim = evt.data["target"]
    vrole = get_role(victim)
    if vrole == "amnesiac":
        vrole = var.AMNESIAC_ROLES[victim]

    evt = Event("investigate", {"role": vrole})
    evt.dispatch(cli, var, nick, victim)
    vrole = evt.data["role"]

    INVESTIGATED.add(nick)
    pm(cli, nick, (messages["investigate_success"]).format(victim, vrole))
    debuglog("{0} ({1}) ID: {2} ({3})".format(nick, get_role(nick), victim, vrole))
    
    if random.random() < var.DETECTIVE_REVEALED_CHANCE:  # a 2/5 chance (should be changeable in settings)
        # The detective's identity is compromised!
        wcroles = var.WOLFCHAT_ROLES
        if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
            if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
                wcroles = var.WOLF_ROLES
            else:
                wcroles = var.WOLF_ROLES | {"traitor"}

        mass_privmsg(cli, list_players(wcroles), messages["investigator_reveal"].format(nick))
        debuglog("{0} ({1}) PAPER DROP".format(nick, get_role(nick)))

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    if prefix in INVESTIGATED:
        INVESTIGATED.remove(prefix)
        INVESTIGATED.add(nick)

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    INVESTIGATED.discard(user.nick)

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("detective",)))

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if actor_role == "detective" and target_role != "detective":
        INVESTIGATED.discard(actor.nick)
    elif target_role == "detective" and actor_role != "detective":
        INVESTIGATED.discard(target.nick)

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = get_players()
    for dttv in var.ROLES["detective"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(dttv)
        chance = math.floor(var.DETECTIVE_REVEALED_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = messages["detective_chance"].format(chance)
        to_send = "detective_notify"
        if dttv.prefers_simple():
            to_send = "detective_simple"
        dttv.send(messages[to_send].format(warning), "Players: " + ", ".join(p.nick for p in pl), sep="\n")

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, cli, var):
    INVESTIGATED.clear()

@event_listener("reset")
def on_reset(evt, var):
    INVESTIGATED.clear()

# vim: set sw=4 expandtab:
