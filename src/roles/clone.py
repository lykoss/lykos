import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import events, channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target, change_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Win_Stealer

CLONED = UserDict() # type: Dict[users.User, users.User]
CLONE_ENABLED = False # becomes True if at least one person died and there are clones

@command("clone", chan=False, pm=True, playing=True, phases=("night",), roles=("clone",))
def clone(var, wrapper, message):
    """Clone another player. You will turn into their role if they die."""
    if wrapper.source in CLONED:
        wrapper.pm(messages["already_cloned"])
        return

    params = re.split(" +", message)
    # allow for role-prefixed command such as !clone clone target
    # if we get !clone clone (with no 3rd arg), we give preference to prefixed version;
    # meaning if the person wants to clone someone named clone, they must type !clone clone clone
    # (or just !clone clon, !clone clo, etc. assuming those would be unambiguous matches)
    if params[0] == "clone":
        if len(params) > 1:
           del params[0]
        else:
            wrapper.pm(messages["clone_clone_clone"])
            return

    target = get_target(var, wrapper, params[0])
    if target is None:
        return

    CLONED[wrapper.source] = target
    wrapper.pm(messages["clone_target_success"].format(target))

    debuglog("{0} (clone) CLONE: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

def setup_clone(evt):
    # We need to add "clone" to the role command exceptions so there's no error
    # This is done here so that var isn't imported at the global scope
    # (when we implement proper game state this will be in a different event)
    from src import settings as var
    var.ROLE_COMMAND_EXCEPTIONS.add("clone")

events.add_listener("init", setup_clone) # no IRC connection, so no possible error handler yet

@event_listener("get_reveal_role")
def on_get_reveal_role(evt, var, user):
    if var.HIDDEN_CLONE and user in var.ORIGINAL_ROLES["clone"]:
        evt.data["role"] = "clone"

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    # clone happens regardless of death_triggers being true or not
    if var.PHASE not in var.GAME_PHASES:
        return

    clones = get_all_players(("clone",))
    mainrole = evt.params.main_role
    for clone in clones:
        if clone in CLONED:
            target = CLONED[clone]
            if player is target:
                # clone is cloning target, so clone becomes target's role
                # clone does NOT get any of target's templates (gunner/assassin/etc.)
                del CLONED[clone]
                mainrole = change_role(var, clone, "clone", mainrole, inherit_from=target)
                # if a clone is cloning a clone, clone who the old clone cloned
                if mainrole == "clone" and player in CLONED:
                    if CLONED[player] is clone:
                        clone.send(messages["forever_aclone"].format(player))
                    else:
                        CLONED[clone] = CLONED[player]
                        clone.send(messages["clone_success"].format(CLONED[clone]))
                        debuglog("{0} (clone) CLONE: {1} ({2})".format(clone, CLONED[clone], get_main_role(CLONED[clone])))

                debuglog("{0} (clone) CLONE DEAD PLAYER: {1} ({2})".format(clone, target, mainrole))

    del CLONED[:player:]

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    ps = get_players()
    for clone in get_all_players(("clone",)):
        if clone in CLONED and not var.ALWAYS_PM_ROLE:
            continue
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(clone)
        if clone.prefers_simple():
            clone.send(messages["clone_simple"])
        else:
            clone.send(messages["clone_notify"])
        clone.send(messages["players_list"].format(", ".join(p.nick for p in pl)))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(CLONED)
    evt.data["nightroles"].extend(get_all_players(("clone",)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    # Select a random target for clone if they didn't choose someone
    pl = get_players()
    for clone in get_all_players(("clone",)):
        if clone not in CLONED:
            ps = pl[:]
            ps.remove(clone)
            if len(ps) > 0:
                target = random.choice(ps)
                CLONED[clone] = target
                clone.send(messages["random_clone"].format(target))

@event_listener("swap_role_state")
def on_swap_role_state(evt, var, actor, target, role):
    if role == "clone":
        CLONED[target], CLONED[actor] = CLONED.pop(actor), CLONED.pop(target)
        evt.data["target_messages"].append(messages["clone_target"].format(CLONED[target]))
        evt.data["actor_messages"].append(messages["clone_target"].format(CLONED[actor]))

@event_listener("player_win")
def on_player_win(evt, var, player, role, winner, survived):
    # this means they ended game while being clone and not some other role
    if role == "clone" and survived and not winner.startswith("@") and singular(winner) not in Win_Stealer:
        evt.data["iwon"] = True

@event_listener("del_player", priority=1)
def first_death_occured(evt, var, player, all_roles, death_triggers):
    global CLONE_ENABLED
    if CLONE_ENABLED:
        return
    if CLONED and var.PHASE in var.GAME_PHASES:
        CLONE_ENABLED = True

@event_listener("update_stats")
def on_update_stats(evt, var, player, mainrole, revealrole, allroles):
    if CLONE_ENABLED and not var.HIDDEN_CLONE:
        evt.data["possible"].add("clone")

@event_listener("myrole")
def on_myrole(evt, var, user):
    # Remind clone who they have cloned
    if evt.data["role"] == "clone" and user in CLONED:
        evt.data["messages"].append(messages["clone_target"].format(CLONED[user]))

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "clone" and user in CLONED:
        evt.data["special_case"].append("cloning {0}".format(CLONED[user]))

@event_listener("reset")
def on_reset(evt, var):
    global CLONE_ENABLED
    CLONE_ENABLED = False
    CLONED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["clone"] = {"Neutral", "Team Switcher"}

# vim: set sw=4 expandtab:
