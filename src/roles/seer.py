import re
import random

import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

SEEN = set()

@cmd("see", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("seer", "oracle", "augur"))
def see(cli, nick, chan, rest):
    """Use your paranormal powers to determine the role or alignment of a player."""
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

    evt = Event("targeted_command", {"target": victim, "misdirection": True, "exchange": True})
    evt.dispatch(cli, var, "see", nick, victim, frozenset({"info", "immediate"}))
    if evt.prevent_default:
        return
    victim = evt.data["target"]
    victimrole = get_role(victim)
    vrole = victimrole # keep a copy for logging

    if role != "augur":
        if (victimrole in var.SEEN_WOLF and victimrole not in var.SEEN_DEFAULT):
            victimrole = "wolf"
        elif victimrole in var.SEEN_DEFAULT:
            victimrole = var.DEFAULT_ROLE
            if var.DEFAULT_SEEN_AS_VILL:
                victimrole = "villager"

        evt = Event("see", {"role": victimrole})
        evt.dispatch(cli, var, nick, victim)
        victimrole = evt.data["role"]
    else:
        if victimrole == "amnesiac":
            victimrole = var.AMNESIAC_ROLES[victim]

        evt = Event("investigate", {"role": victimrole})
        evt.dispatch(cli, var, nick, victim)
        victimrole = evt.data["role"]

    if role == "seer":
        pm(cli, nick, (messages["seer_success"]).format(victim, victimrole))
        debuglog("{0} ({1}) SEE: {2} ({3}) as {4}".format(nick, role, victim, vrole, victimrole))
    elif role == "oracle":
        iswolf = False
        if (victimrole in var.SEEN_WOLF and victimrole not in var.SEEN_DEFAULT):
            iswolf = True
        pm(cli, nick, (messages["oracle_success"]).format(victim, "" if iswolf else "\u0002not\u0002 ", "\u0002" if iswolf else ""))
        debuglog("{0} ({1}) SEE: {2} ({3}) (Wolf: {4})".format(nick, role, victim, vrole, str(iswolf)))
    elif role == "augur":
        aura = "blue"
        if victimrole in var.WOLFTEAM_ROLES:
            aura = "red"
        elif victimrole in var.TRUE_NEUTRAL_ROLES:
            aura = "grey"
        pm(cli, nick, (messages["augur_success"]).format(victim, aura))
        debuglog("{0} ({1}) SEE: {2} ({3}) as {4} ({5} aura)".format(nick, role, victim, vrole, victimrole, aura))

    SEEN.add(nick)
    chk_nightdone(cli)

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    if prefix in SEEN:
        SEEN.remove(prefix)
        SEEN.add(nick)

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    SEEN.discard(nick)

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in SEEN:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(list_players(("seer", "oracle", "augur")))

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    if actor_role in ("seer", "oracle", "augur"):
        SEEN.discard(actor)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    evt.data["actedcount"] += len(SEEN)
    evt.data["nightroles"].extend(get_roles("seer", "oracle", "augur"))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    for seer in list_players(("seer", "oracle", "augur")):
        pl = list_players()
        random.shuffle(pl)
        role = get_role(seer)
        pl.remove(seer)  # remove self from list

        a = "a"
        if role in ("oracle", "augur"):
            a = "an"

        if role == "seer":
            what = messages["seer_ability"]
        elif role == "oracle":
            what = messages["oracle_ability"]
        elif role == "augur":
            what = messages["augur_ability"]
        else:
            what = messages["seer_role_bug"]

        if seer in var.PLAYERS and not is_user_simple(seer):
            pm(cli, seer, messages["seer_role_info"].format(a, role, what))
        else:
            pm(cli, seer, messages["seer_simple"].format(a, role))  # !simple
        pm(cli, seer, "Players: " + ", ".join(pl))


@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    SEEN.clear()

@event_listener("reset")
def on_reset(evt, var):
    SEEN.clear()

# vim: set sw=4 expandtab:
