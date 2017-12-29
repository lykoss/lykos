import re
import random
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_target, get_main_role
from src.decorators import command, event_listener
from src.messages import messages
from src.events import Event

KILLS = {} # type: Dict[users.User, users.User]
GHOSTS = {} # type: Dict[users.User, str]

# temporary holding variable, only non-empty during transition_day
drivenoff = {} # type: Dict[users.User, str]

@command("kill", chan=False, pm=True, playing=False, silenced=True, phases=("night",), users=GHOSTS)
def vg_kill(var, wrapper, message):
    """Take revenge on someone each night after you die."""
    if GHOSTS[wrapper.source][0] == "!":
        return

    target = get_target(var, wrapper, re.split(" +", message)[0])
    if not target:
        return

    if target is wrapper.source:
        wrapper.pm(messages["player_dead"])
        return

    wolves = get_players(var.WOLFTEAM_ROLES)
    if GHOSTS[wrapper.source] == "wolves" and target not in wolves:
        wrapper.pm(messages["vengeful_ghost_wolf"])
        return
    elif GHOSTS[wrapper.source] == "villagers" and target in wolves:
        wrapper.pm(messages["vengeful_ghost_villager"])
        return

    orig = target
    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": False})
    evt.dispatch(var, "kill", wrapper.source, target, frozenset({"detrimental"}))
    if evt.prevent_default:
        return
    target = evt.data["target"]

    KILLS[wrapper.source] = target

    wrapper.pm(messages["player_kill"].format(orig))

    debuglog("{0} (vengeful ghost) KILL: {1} ({2})".format(wrapper.source.nick, target, get_main_role(target)))
    chk_nightdone(wrapper.source.client)

@command("retract", "r", chan=False, pm=True, playing=False, phases=("night",))
def vg_retract(var, wrapper, message):
    """Removes a vengeful ghost's kill selection."""
    if wrapper.source not in GHOSTS:
        return
    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        wrapper.pm(messages["retracted_kill"])

@event_listener("get_participants")
def on_get_participants(evt, var):
    evt.data["players"].extend([p for p in GHOSTS if GHOSTS[p][0] != "!"])
    evt.data["players"].extend(drivenoff)

@event_listener("player_win", priority=1)
def on_player_win(evt, var, user, role, winner, survived):
    # alive VG winning is handled in villager.py
    # extending VG to work with new teams can be done by registering
    # a listener at priority > 1, importing src.roles.vengefulghost,
    # and checking if the user is in GHOSTS.
    if user in GHOSTS:
        evt.data["special"].append("vg activated")
        against = GHOSTS[user]
        if against[0] == "!":
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
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    for h, v in list(KILLS.items()):
        if user is v:
            h.send(messages["hunter_discard"])
            del KILLS[h]
    # extending VG to work with new teams can be done by registering a listener
    # at priority < 6, importing src.roles.vengefulghost, and setting
    # GHOSTS[user] to something; if that is done then this logic is not run.
    if death_triggers and mainrole == "vengeful ghost" and user not in GHOSTS:
        if evt.params.killer_role in var.WOLFTEAM_ROLES:
            GHOSTS[user] = "wolves"
        else:
            GHOSTS[user] = "villagers"
        user.send(messages["vengeful_turn"].format(GHOSTS[user]))
        debuglog(user.nick, "(vengeful ghost) TRIGGER", GHOSTS[user])

@event_listener("transition_day_begin", priority=6)
def on_transition_day_begin(evt, var):
    # select a random target for VG if they didn't kill
    wolves = set(get_players(var.WOLFTEAM_ROLES))
    villagers = set(get_players()) - wolves
    for ghost, target in GHOSTS.items():
        if target[0] == "!" or ghost.nick in var.SILENCED:
            continue
        if ghost not in KILLS:
            choice = set()
            if target == "wolves":
                choice = wolves.copy()
            elif target == "villagers":
                choice = villagers.copy()
            evt = Event("vg_kill", {"pl": choice})
            evt.dispatch(var, ghost, target)
            choice = evt.data["pl"]
            if choice:
                KILLS[ghost] = random.choice(list(choice))

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    for k, d in KILLS.items():
        evt.data["victims"].append(d)
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d].append(k)

@event_listener("transition_day", priority=3.01)
def on_transition_day3(evt, var):
    for k, d in list(KILLS.items()):
        if GHOSTS[k] == "villagers":
            evt.data["killers"][d].remove(k)
            evt.data["killers"][d].insert(0, k)

@event_listener("transition_day", priority=6.01)
def on_transition_day6(evt, var):
    for k, d in list(KILLS.items()):
        if GHOSTS[k] == "villagers" and k in evt.data["killers"][d]:
            evt.data["killers"][d].remove(k)
            evt.data["killers"][d].insert(0, k)
        # important, otherwise our del_player listener messages the vg
        del KILLS[k]

@event_listener("retribution_kill", priority=6)
def on_retribution_kill(evt, var, victim, orig_target):
    target = evt.data["target"]
    if target in GHOSTS:
        drivenoff[target] = GHOSTS[target]
        GHOSTS[target] = "!" + GHOSTS[target]
        evt.data["message"].append(messages["totem_banish"].format(victim, target))
        evt.data["target"] = None

@event_listener("get_participant_role")
def on_get_participant_role(evt, var, user):
    if user in GHOSTS:
        if user in drivenoff:
            against = drivenoff[user]
        else:
            against = GHOSTS[user]
        if against == "villagers":
            evt.data["role"] = "wolf"
        elif against == "wolves":
            evt.data["role"] = "villager"

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(KILLS)
    evt.data["nightroles"].extend([p for p in GHOSTS if GHOSTS[p][0] != "!"])

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    # alive VGs are messaged as part of villager.py, this handles dead ones
    ps = get_players()
    wolves = get_players(var.WOLFTEAM_ROLES)
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

        to_send = "vengeful_ghost_notify"
        if v_ghost.prefers_simple():
            to_send = "vengeful_ghost_simple"
        v_ghost.send(messages[to_send].format(who), who.capitalize() + ": " + ", ".join(p.nick for p in pl), sep="\n")
        debuglog("GHOST: {0} (target: {1}) - players: {2}".format(v_ghost, who, ", ".join(p.nick for p in pl)))

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in GHOSTS:
        evt.prevent_default = True
        if GHOSTS[user][0] != "!":
            user.send(messages["vengeful_role"].format(GHOSTS[user]))

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if GHOSTS:
        glist = []
        for ghost, team in GHOSTS.items():
            dead = "driven away, " if team[0] == "!" else ""
            glist.append("{0} ({1}against {2})".format(ghost.nick, dead, team.lstrip("!")))
        evt.data["output"].append("\u0002dead vengeful ghost\u0002: {0}".format(", ".join(glist)))

@event_listener("begin_day")
def on_begin_day(evt, var):
    drivenoff.clear()
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    GHOSTS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        evt.data["vengeful ghost"] = sum(1 for against in GHOSTS.values() if against[0] != "!")
    elif kind == "special_keys":
        evt.data["vengeful ghost"] = {"vg activated", "vg driven off"}

# vim: set sw=4 expandtab:
