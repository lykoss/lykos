import re
import random
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_target, get_main_role, get_all_roles
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_silent, is_silent
from src.cats import All, Wolfteam

KILLS = UserDict() # type: UserDict[users.User, users.User]
GHOSTS = UserDict() # type: UserDict[users.User, str]

# temporary holding variable, only non-empty during transition_day
drivenoff = UserDict() # type: UserDict[users.User, str]

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

    wolves = get_players(Wolfteam)
    if GHOSTS[wrapper.source] == "wolf" and target not in wolves:
        wrapper.pm(messages["vengeful_ghost_wolf"])
        return
    elif GHOSTS[wrapper.source] == "villager" and target in wolves:
        wrapper.pm(messages["vengeful_ghost_villager"])
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)

    KILLS[wrapper.source] = target

    wrapper.pm(messages["player_kill"].format(orig))

    debuglog("{0} (vengeful ghost) KILL: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("retract", chan=False, pm=True, playing=False, phases=("night",))
def vg_retract(var, wrapper, message):
    """Removes a vengeful ghost's kill selection."""
    if wrapper.source not in GHOSTS:
        return

    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        wrapper.pm(messages["retracted_kill"])
        debuglog("{0} (vengeful ghost) RETRACT".format(wrapper.source))

@event_listener("get_participants")
def on_get_participants(evt, var):
    evt.data["players"].extend([p for p in GHOSTS if GHOSTS[p][0] != "!"])
    evt.data["players"].extend(drivenoff)

@event_listener("consecrate")
def on_consecrate(evt, var, actor, target):
    if target in GHOSTS:
        add_silent(var, target)

@event_listener("gun_shoot")
def on_gun_shoot(evt, var, user, target, role):
    if evt.data["hit"] and "vengeful ghost" in get_all_roles(target):
        # VGs automatically die if hit by a gun to make gunner a bit more dangerous in some modes
        evt.data["kill"] = True
        
# needs to happen after regular team win is determined, but before succubus
# FIXME: I hate priorities, did I mention that?
@event_listener("team_win", priority=6)
def on_team_win(evt, var, player, main_role, all_roles, winner):
    if player in GHOSTS:
        against = GHOSTS[player].lstrip("!")
        if against == "villager" and winner == "wolves":
            evt.data["team_win"] = True
        elif against == "wolf" and winner == "villagers":
            evt.data["team_win"] = True
        else:
            evt.data["team_win"] = False

@event_listener("player_win")
def on_player_win(evt, var, player, main_role, all_roles, winner, team_win, survived):
    if player in GHOSTS:
        evt.data["special"].append("vg activated")
        if GHOSTS[player][0] == "!":
            evt.data["special"].append("vg driven off")
        elif team_win:
            # VG gets an individual win while dead if they haven't been driven off and their team wins
            evt.data["individual_win"] = True

@event_listener("del_player", priority=6)
def on_del_player(evt, var, player, all_roles, death_triggers):
    for h, v in list(KILLS.items()):
        if player is v:
            h.send(messages["hunter_discard"])
            del KILLS[h]
    # extending VG to work with new teams can be done by registering a listener
    # at priority < 6, importing src.roles.vengefulghost, and setting
    # GHOSTS[user] to something; if that is done then this logic is not run.
    if death_triggers and "vengeful ghost" in all_roles and player not in GHOSTS:
        if evt.params.killer_role in Wolfteam:
            GHOSTS[player] = "wolf"
        else:
            GHOSTS[player] = "villager"
        player.send(messages["vengeful_turn"].format(GHOSTS[player]))
        debuglog(player.nick, "(vengeful ghost) TRIGGER", GHOSTS[player])

@event_listener("transition_day_begin", priority=6)
def on_transition_day_begin(evt, var):
    # select a random target for VG if they didn't kill
    wolves = get_players(Wolfteam)
    villagers = get_players(All - Wolfteam)
    for ghost, target in GHOSTS.items():
        if target[0] == "!" or is_silent(var, ghost):
            continue
        if ghost not in KILLS:
            choice = None
            if target == "wolf":
                choice = wolves.copy()
            elif target == "villager":
                choice = villagers.copy()
            if choice:
                KILLS[ghost] = random.choice(choice)

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    for k, d in KILLS.items():
        evt.data["victims"].append(d)
        evt.data["killers"][d].append(k)

@event_listener("transition_day", priority=3.01)
def on_transition_day3(evt, var):
    for k, d in list(KILLS.items()):
        if GHOSTS[k] == "villager":
            evt.data["killers"][d].remove(k)
            evt.data["killers"][d].insert(0, k)

@event_listener("transition_day", priority=6.01)
def on_transition_day6(evt, var):
    for k, d in list(KILLS.items()):
        if GHOSTS[k] == "villager" and k in evt.data["killers"][d]:
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
        if against == "villager":
            evt.data["role"] = "wolf"
        elif against == "wolf":
            evt.data["role"] = "villager"

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["acted"].extend(KILLS)
    evt.data["nightroles"].extend([p for p in GHOSTS if GHOSTS[p][0] != "!"])

@event_listener("send_role")
def on_transition_night_end(evt, var):
    # alive VGs are messaged as part of villager.py, this handles dead ones
    villagers = get_players(All - Wolfteam)
    wolves = get_players(Wolfteam)
    for v_ghost, who in GHOSTS.items():
        if who[0] == "!":
            continue
        if who == "wolf":
            pl = wolves[:]
        else:
            pl = villagers[:]

        random.shuffle(pl)

        v_ghost.send(messages["vengeful_ghost_notify"].format(who), messages["vengeful_ghost_team"].format(who, pl), sep="\n")

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in GHOSTS:
        evt.prevent_default = True
        if GHOSTS[user][0] != "!":
            user.send(messages["vengeful_role"].format(GHOSTS[user]))

@event_listener("revealroles")
def on_revealroles(evt, var):
    if GHOSTS:
        glist = []
        for ghost, team in GHOSTS.items():
            to_send = []
            if team[0] == "!":
                to_send.append(messages["vg_driven_away"].format()) # call .format() so it's actually a str
            to_send.append(messages["vg_against"].format(team.lstrip("!")))
            glist.append("{0} ({1})".format(ghost, ", ".join(to_send)))
        evt.data["output"].append(messages["vengeful_ghost_revealroles"].format(glist))

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
    elif kind == "role_categories":
        evt.data["vengeful ghost"] = {"Hidden"}
