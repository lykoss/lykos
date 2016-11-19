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
GHOSTS = {} # type: Dict[str, str]

# temporary holding variable, only non-empty during transition_day
# as such, no need to track nick changes, etc. with it
drivenoff = {} # type: Dict[str, str]

@cmd("kill", chan=False, pm=True, playing=False, silenced=True, phases=("night",), nicks=GHOSTS, old_api=True)
def vg_kill(cli, nick, chan, rest):
    """Take revenge on someone each night after you die."""
    if GHOSTS[nick][0] == "!":
        return

    victim = get_victim(cli, nick, re.split(" +",rest)[0], False)
    if not victim:
        return

    if victim == nick:
        pm(cli, nick, messages["player_dead"])
        return

    wolves = list_players(var.WOLFTEAM_ROLES)
    if GHOSTS[nick] == "wolves" and victim not in wolves:
        pm(cli, nick, messages["vengeful_ghost_wolf"])
        return
    elif GHOSTS[nick] == "villagers" and victim in wolves:
        pm(cli, nick, messages["vengeful_ghost_villager"])
        return

    orig = victim
    evt = Event("targeted_command", {"target": victim, "misdirection": True, "exchange": False})
    evt.dispatch(cli, var, "kill", nick, victim, frozenset({"detrimental"}))
    if evt.prevent_default:
        return
    victim = evt.data["target"]

    KILLS[nick] = victim

    msg = messages["wolf_target"].format(orig)
    pm(cli, nick, messages["player"].format(msg))

    debuglog("{0} ({1}) KILL: {2} ({3})".format(nick, get_role(nick), victim, get_role(victim)))
    chk_nightdone(cli)

@cmd("retract", "r", chan=False, pm=True, playing=False, phases=("night",), old_api=True)
def vg_retract(cli, nick, chan, rest):
    """Removes a vengeful ghost's kill selection."""
    if nick not in GHOSTS:
        return
    if nick in KILLS:
        del KILLS[nick]
        pm(cli, nick, messages["retracted_kill"])

@event_listener("list_participants")
def on_list_participants(evt, var):
    evt.data["pl"].extend([p for p in GHOSTS if GHOSTS[p][0] != "!"])
    evt.data["pl"].extend([p for p in drivenoff])

@event_listener("player_win", priority=1)
def on_player_win(evt, cli, var, nick, role, winner, survived):
    # alive VG winning is handled in villager.py
    # extending VG to work with new teams can be done by registering
    # a listener at priority > 1, importing src.roles.vengefulghost,
    # and checking if the nick is in GHOSTS.
    if nick in GHOSTS:
        evt.data["special"].append("vg activated")
        against = GHOSTS[nick]
        if GHOSTS[nick][0] == "!":
            evt.data["special"].append("vg driven off")
            against = against[1:]
        if against == "villagers" and winner == "wolves":
            evt.data["won"] = True
            evt.data["iwon"] = True
        elif against == "wolves" and winner == "villagers":
            evt.data["won"] = True
            evt.data["iwon"] = True
        else:
            evt.data["won"] = False
            evt.data["iwon"] = False

@event_listener("del_player", priority=6)
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    for h,v in list(KILLS.items()):
        if v == nick:
            pm(cli, h, messages["hunter_discard"])
            del KILLS[h]
    # extending VG to work with new teams can be done by registering a listener
    # at priority < 6, importing src.roles.vengefulghost, and setting
    # GHOSTS[nick] to something; if that is done then this logic is not run.
    if death_triggers and nickrole == "vengeful ghost" and nick not in GHOSTS:
        if evt.params.killer_role in var.WOLFTEAM_ROLES:
            GHOSTS[nick] = "wolves"
        else:
            GHOSTS[nick] = "villagers"
        pm(cli, nick, messages["vengeful_turn"].format(GHOSTS[nick]))
        debuglog(nick, "(vengeful ghost) TRIGGER", GHOSTS[nick])

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
    if prefix in GHOSTS:
        GHOSTS[nick] = GHOSTS.pop(prefix)

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in KILLS:
        evt.data["acted"] = True

@event_listener("transition_day_begin", priority=6)
def on_transition_day_begin(evt, cli, var):
    # select a random target for VG if they didn't kill
    wolves = set(list_players(var.WOLFTEAM_ROLES))
    villagers = set(list_players()) - wolves
    for ghost, target in GHOSTS.items():
        if target[0] == "!" or ghost in var.SILENCED:
            continue
        if ghost not in KILLS:
            choice = set()
            if target == "wolves":
                choice = wolves.copy()
            elif target == "villagers":
                choice = villagers.copy()
            evt = Event("vg_kill", {"pl": choice})
            evt.dispatch(cli, var, ghost, target)
            choice = evt.data["pl"]
            # roll this into the above event once succubus is split off
            if ghost in var.ENTRANCED:
                choice -= var.ROLES["succubus"]
            if choice:
                KILLS[ghost] = random.choice(list(choice))

@event_listener("transition_day", priority=2)
def on_transition_day(evt, cli, var):
    for k, d in KILLS.items():
        evt.data["victims"].append(d)
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d].append(k)

@event_listener("transition_day", priority=3.01)
def on_transition_day3(evt, cli, var):
    for k, d in list(KILLS.items()):
        if GHOSTS[k] == "villagers":
            evt.data["killers"][d].remove(k)
            evt.data["killers"][d].insert(0, k)

@event_listener("transition_day", priority=6.01)
def on_transition_day6(evt, cli, var):
    for k, d in list(KILLS.items()):
        if GHOSTS[k] == "villagers" and k in evt.data["killers"][d]:
            evt.data["killers"][d].remove(k)
            evt.data["killers"][d].insert(0, k)
        # important, otherwise our del_player listener messages the vg
        del KILLS[k]

@event_listener("retribution_kill")
def on_retribution_kill(evt, cli, var, victim, orig_target):
    t = evt.data["target"]
    if t in GHOSTS:
        drivenoff[t] = GHOSTS[t]
        GHOSTS[t] = "!" + GHOSTS[t]
        evt.data["message"].append(messages["totem_banish"].format(victim, t))
        evt.data["target"] = None

@event_listener("get_participant_role")
def on_get_participant_role(evt, var, nick):
    if nick in GHOSTS:
        if nick in drivenoff:
            against = drivenoff[nick]
        else:
            against = GHOSTS[nick]
        if against == "villagers":
            evt.data["role"] = "wolf"
        elif against == "wolves":
            evt.data["role"] = "villager"

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    evt.data["actedcount"] += len(KILLS)
    evt.data["nightroles"].extend([p for p in GHOSTS if GHOSTS[p][0] != "!"])

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    # alive VGs are messaged as part of villager.py, this handles dead ones
    ps = list_players()
    wolves = list_players(var.WOLFTEAM_ROLES)
    for v_ghost, who in GHOSTS.items():
        if who[0] == "!":
            continue
        if who == "wolves":
            pl = wolves[:]
        else:
            pl = ps[:]
            for wolf in wolves:
                pl.remove(wolf)

        random.shuffle(pl)

        if v_ghost in var.PLAYERS and not is_user_simple(v_ghost):
            pm(cli, v_ghost, messages["vengeful_ghost_notify"].format(who))
        else:
            pm(cli, v_ghost, messages["vengeful_ghost_simple"])
        pm(cli, v_ghost, who.capitalize() + ": " + ", ".join(pl))
        debuglog("GHOST: {0} (target: {1}) - players: {2}".format(v_ghost, who, ", ".join(pl)))

@event_listener("myrole")
def on_myrole(evt, cli, var, nick):
    if nick in GHOSTS:
        evt.prevent_default = True
        if GHOSTS[nick][0] != "!":
            pm(cli, nick, messages["vengeful_role"].format(GHOSTS[nick]))

@event_listener("revealroles")
def on_revealroles(evt, cli, var):
    if GHOSTS:
        glist = []
        for ghost, team in GHOSTS.items():
            dead = "driven away, " if team[0] == "!" else ""
            glist.append("{0} ({1}against {2})".format(ghost, dead, team.lstrip("!")))
        evt.data["output"].append("\u0002dead vengeful ghost\u0002: {0}".format(", ".join(glist)))

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    drivenoff.clear()
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    GHOSTS.clear()

# vim: set sw=4 expandtab:
