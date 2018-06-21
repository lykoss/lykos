import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

CLONED = UserDict() # type: Dict[users.User, users.User]
CLONE_ENABLED = False # becomes True if at least one person died and there are clones

@command("clone", chan=False, pm=True, playing=True, phases=("night",), roles=("clone",))
def clone(var, wrapper, message):
    """Clone another player. You will turn into their role if they die."""
    if not var.FIRST_NIGHT:
        return
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

@event_listener("init")
def on_init(evt):
    # We need to add "clone" to the role command exceptions so there's no error
    # This is done here so that var isn't imported at the global scope
    # (when we implement proper game state this will be in a different event)
    from src import settings as var
    var.ROLE_COMMAND_EXCEPTIONS.add("clone")

@event_listener("get_reveal_role")
def on_get_reveal_role(evt, var, user):
    if var.HIDDEN_CLONE and user in var.ORIGINAL_ROLES["clone"]:
        evt.data["role"] = "clone"

@event_listener("del_player")
def on_del_player(evt, var, player, mainrole, allroles, death_triggers):
    # clone happens regardless of death_triggers being true or not
    if var.PHASE not in var.GAME_PHASES:
        return

    clones = get_all_players(("clone",))
    for clone in clones:
        if clone in CLONED and clone not in evt.params.deadlist:
            target = CLONED[clone]
            if player is target:
                # clone is cloning target, so clone becomes target's role
                # clone does NOT get any of target's templates (gunner/assassin/etc.)
                del CLONED[clone]
                if mainrole == "amnesiac":
                    from src.roles.amnesiac import ROLES as amn_roles
                    # clone gets the amnesiac's real role
                    mainrole = amn_roles[player]
                change_role(clone, "clone", mainrole)
                debuglog("{0} (clone) CLONE DEAD PLAYER: {1} ({2})".format(clone, target, mainrole))
                sayrole = mainrole
                if sayrole in var.HIDDEN_VILLAGERS:
                    sayrole = "villager"
                elif sayrole in var.HIDDEN_ROLES:
                    sayrole = var.DEFAULT_ROLE
                an = "n" if sayrole.startswith(("a", "e", "i", "o", "u")) else ""
                clone.send(messages["clone_turn"].format(an, sayrole))
                # if a clone is cloning a clone, clone who the old clone cloned
                if mainrole == "clone" and player in CLONED:
                    if CLONED[player] is clone:
                        clone.send(messages["forever_aclone"].format(player))
                    else:
                        CLONED[clone] = CLONED[player]
                        clone.send(messages["clone_success"].format(CLONED[clone]))
                        debuglog("{0} (clone) CLONE: {1} ({2})".format(clone, CLONED[clone], get_main_role(CLONED[clone])))
                elif mainrole in var.WOLFCHAT_ROLES:
                    wolves = get_players(var.WOLFCHAT_ROLES)
                    wolves.remove(clone) # remove self from list
                    for wolf in wolves:
                        wolf.queue_message(messages["clone_wolf"].format(clone, player))
                    if wolves:
                        wolf.send_messages()
                    if var.PHASE == "day":
                        random.shuffle(wolves)
                        for i, wolf in enumerate(wolves):
                            wolfrole = get_main_role(wolf)
                            wevt = Event("wolflist", {"tags": set()})
                            wevt.dispatch(var, wolf, clone)
                            tags = " ".join(wevt.data["tags"])
                            if tags:
                                tags += " "
                            wolves[i] = "\u0002{0}\u0002 ({1}{2})".format(wolf, tags, wolfrole)

                        if wolves:
                            clone.send(messages["wolves_list"].format(wolves))
                        else:
                            clone.send(messages["no_other_wolves"])
                elif mainrole == "turncoat":
                    var.TURNCOATS[clone.nick] = ("none", -1) # FIXME

    if mainrole == "clone" and player in CLONED:
        del CLONED[player]

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    if var.FIRST_NIGHT or var.ALWAYS_PM_ROLE:
        ps = get_players()
        for clone in get_all_players(("clone",)):
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
    if var.FIRST_NIGHT:
        evt.data["actedcount"] += len(CLONED)
        evt.data["nightroles"].extend(get_all_players(("clone",)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    if var.FIRST_NIGHT:
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

@event_listener("exchange_roles")
def on_exchange_roles(evt, var, actor, target, actor_role, target_role):
    actor_target = None
    target_target = None
    if actor_role == "clone":
        if actor in CLONED:
            actor_target = CLONED.pop(actor)
            evt.data["target_messages"].append(messages["clone_target"].format(actor_target))
    if target_role == "clone":
        if target in CLONED:
            target_target = CLONED.pop(target)
            evt.data["actor_messages"].append(messages["clone_target"].format(target_target))

    if actor_target is not None:
        CLONED[target] = actor_target
    if target_target is not None:
        CLONED[actor] = target_target

@event_listener("player_win")
def on_player_win(evt, var, player, role, winner, survived):
    # this means they ended game while being clone and not some other role
    if role == "clone" and survived and not winner.startswith("@") and singular(winner) not in var.WIN_STEALER_ROLES:
        evt.data["iwon"] = True

@event_listener("del_player")
def first_death_occured(evt, var, player, mainrole, allroles, death_triggers):
    global CLONE_ENABLED
    if CLONE_ENABLED:
        return
    if var.PHASE in var.GAME_PHASES and (CLONED or get_all_players(("clone",))) and not var.FIRST_NIGHT:
        CLONE_ENABLED = True

@event_listener("update_stats")
def on_update_stats(evt, var, player, mainrole, revealrole, allroles):
    if CLONE_ENABLED:
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

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["neutrals"].update(get_players(("clone",)))

@event_listener("reset")
def on_reset(evt, var):
    global CLONE_ENABLED
    CLONE_ENABLED = False
    CLONED.clear()
