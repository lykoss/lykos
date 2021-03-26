import re
import random
import itertools
import math
from collections import defaultdict
from typing import List

from src.functions import get_main_role, get_players, get_all_roles, get_all_players, get_target
from src.decorators import event_listener, command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages, LocalRole
from src.status import try_misdirection, try_exchange, is_silent
from src.events import Event
from src.cats import Wolf, Wolfchat, Wolfteam, Killer, Hidden, All
from src import debuglog, users

KILLS = UserDict() # type: UserDict[users.User, UserList]

def register_wolf(rolename):
    @event_listener("send_role", listener_id="wolves.<{}>.on_send_role".format(rolename))
    def on_transition_night_end(evt, var):
        wolves = get_all_players((rolename,))
        for wolf in wolves:
            msg = "{0}_notify".format(rolename.replace(" ", "_"))
            wolf.send(messages[msg])
            wolf.send(messages["players_list"].format(get_wolflist(var, wolf)))
            if var.NIGHT_COUNT > 0:
                nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
                nevt.dispatch(var, wolf)
                if rolename in Killer and not nevt.data["numkills"] and nevt.data["message"]:
                    wolf.send(messages[nevt.data["message"]])
        wevt = Event("wolf_notify", {})
        wevt.dispatch(var, rolename)

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=Wolf)
def wolf_kill(var, wrapper, message):
    """Kill one or more players as a wolf."""
    # verify this user can actually kill
    if not get_all_roles(wrapper.source) & Wolf & Killer:
        return

    pieces = re.split(" +", message)
    targets = []
    orig = []

    nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
    nevt.dispatch(var, wrapper.source)
    num_kills = nevt.data["numkills"]

    if not num_kills:
        if nevt.data["message"]:
            wrapper.pm(messages[nevt.data["message"]])
        return

    if len(pieces) < num_kills:
        wrapper.pm(messages["wolf_must_target_multiple"])
        return

    for targ in pieces[:num_kills]:
        target = get_target(var, wrapper, targ, not_self_message="no_suicide")
        if target is None:
            return

        if is_known_wolf_ally(var, wrapper.source, target):
            wrapper.pm(messages["wolf_no_target_wolf"])
            return

        if target in orig:
            wrapper.pm(messages["wolf_must_target_multiple"])
            return

        orig.append(target)
        target = try_misdirection(var, wrapper.source, target)
        if try_exchange(var, wrapper.source, target):
            return

        targets.append(target)

    KILLS[wrapper.source] = UserList(targets)

    if len(orig) > 1:
        wrapper.pm(messages["player_kill_multiple"].format(orig))
        msg = messages["wolfchat_kill_multiple"].format(wrapper.source, orig)
    else:
        wrapper.pm(messages["player_kill"].format(orig[0]))
        msg = messages["wolfchat_kill"].format(wrapper.source, orig[0])

    send_wolfchat_message(var, wrapper.source, msg, Wolf, role="wolf", command="kill")

@command("retract", chan=False, pm=True, playing=True, phases=("night",), roles=Wolf)
def wolf_retract(var, wrapper, message):
    """Removes a wolf's kill selection."""
    if not get_all_roles(wrapper.source) & Wolf & Killer:
        return

    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        wrapper.pm(messages["retracted_kill"])
        send_wolfchat_message(var, wrapper.source, messages["wolfchat_retracted_kill"].format(wrapper.source), Wolf, role="wolf", command="retract")

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    for killer, targets in list(KILLS.items()):
        for target in targets:
            if player is target:
                targets.remove(target)
        if player is killer or not targets:
            del KILLS[killer]

@event_listener("transition_day", priority=1)
def on_transition_day(evt, var):
    # figure out wolf target
    found = defaultdict(int)
    wolves = get_all_players(Wolf)
    total_kills = 0
    for wolf, victims in KILLS.items():
        nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
        nevt.dispatch(var, wolf)
        num_kills = nevt.data["numkills"]
        if is_known_wolf_ally(var, wolf, wolf):
            total_kills = max(total_kills, num_kills)
            for victim in victims:
                found[victim] += 1
        else:
            # if they aren't in wolfchat, their kills are counted independently
            # however, they are still unable to kill other wolves (but may kill non-wolves in
            # wolfchat such as sorcerer or traitor, unlike main role wolves)
            for victim in victims:
                if victim not in wolves:
                    evt.data["victims"].append(victim)
                    evt.data["killers"][victim].append(wolf)
    # for wolves in wolfchat, determine who had the most kill votes and kill them,
    # choosing randomly in case of ties
    for i in range(total_kills):
        maxc = 0
        dups = []
        for v, c in found.items():
            if c > maxc:
                maxc = c
                dups = [v]
            elif c == maxc:
                dups.append(v)
        if maxc and dups:
            target = random.choice(dups)
            evt.data["victims"].append(target)
            # special key to let us know to randomly select a wolf in case of retribution totem
            evt.data["killers"][target].append("@wolves")
            del found[target]

def _reorganize_killers(killers):
    wolfteam = get_players(Wolfteam)
    for victim, attackers in list(killers.items()):
        k2 = []
        kappend = []
        wolves = False
        for k in attackers:
            if k in wolfteam:
                kappend.append(k)
            elif k == "@wolves":
                wolves = True
            else:
                k2.append(k)
        k2.extend(kappend)
        if wolves:
            k2.append("@wolves")
        killers[victim] = k2

@event_listener("transition_day", priority=3)
def on_transition_day3(evt, var):
    _reorganize_killers(evt.data["killers"])

@event_listener("transition_day", priority=6)
def on_transition_day6(evt, var):
    _reorganize_killers(evt.data["killers"])

@event_listener("retribution_kill")
def on_retribution_kill(evt, var, victim, orig_target):
    if evt.data["target"] == "@wolves": # kill a random wolf
        evt.data["target"] = random.choice(get_players(Wolf & Killer))

@event_listener("new_role", priority=4)
def on_new_role(evt, var, player, old_role):
    wcroles = get_wolfchat_roles(var)

    if old_role is None:
        # initial role assignment; don't do all the logic below about notifying other wolves and such
        if evt.data["role"] in wcroles:
            evt.data["in_wolfchat"] = True
        return

    sayrole = evt.data["role"]
    if sayrole in Hidden:
        sayrole = var.HIDDEN_ROLE

    if player in KILLS:
        del KILLS[player]

    if old_role not in wcroles and evt.data["role"] in wcroles:
        # a new wofl has joined the party, give them tummy rubs and the wolf list
        # and let the other wolves know to break out the confetti and villager steaks
        wofls = get_players(wcroles)
        evt.data["in_wolfchat"] = True
        if wofls:
            for wofl in wofls:
                wofl.queue_message(messages["wolfchat_new_member"].format(player, sayrole))
            wofl.send_messages()
        else:
            return # no other wolves, nothing else to do

        evt.data["messages"].append(messages["players_list"].format(get_wolflist(var, player)))

        if var.PHASE == "night" and evt.data["role"] in Wolf & Killer:
            # inform the new wolf that they can kill and stuff
            nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
            nevt.dispatch(var)
            if not nevt.data["numkills"] and nevt.data["message"]:
                evt.data["messages"].append(messages[nevt.data["message"]])

@event_listener("chk_nightdone", priority=3)
def on_chk_nightdone(evt, var):
    wolves = [x for x in get_all_players(Wolf & Killer) if not is_silent(var, x)]
    total_kills = 0
    independent = set()
    for wolf in wolves:
        nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
        nevt.dispatch(var, wolf)
        num_kills = nevt.data["numkills"]
        if is_known_wolf_ally(var, wolf, wolf):
            total_kills = max(total_kills, num_kills)
        else:
            independent.add(wolf)

    if not total_kills and not independent:
        return

    fake = users.FakeUser.from_nick("@WolvesAgree@")
    evt.data["nightroles"].extend(wolves)
    evt.data["acted"].extend(KILLS)
    evt.data["nightroles"].append(fake)

    kills = set()
    for wolf, ls in KILLS.items():
        if wolf not in independent:
            kills.update(ls)
    # check if wolves are actually agreeing
    if len(kills) == total_kills:
        evt.data["acted"].append(fake)

@event_listener("wolf_notify")
def on_transition_night_end(evt, var, role):
    # roles allowed to talk in wolfchat
    talkroles = get_talking_roles(var)

    # condition imposed on talking in wolfchat (only during day/night, or no talking)
    # 0 = no talking
    # 1 = normal
    # 2 = only during day
    # 3 = only during night
    wccond = 1

    if var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
        if var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            wccond = 0
        else:
            wccond = 2
    elif var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
        wccond = 3

    if role not in talkroles or wccond == 0:
        return

    wolves = get_players((role,))
    for wolf in wolves:
        wolf.send(messages["wolfchat_notify_{0}".format(wccond)])

@event_listener("begin_day")
def on_begin_day(evt, var):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()

@event_listener("gun_shoot", priority=3)
def on_gun_shoot(evt, var, user, target, role):
    if evt.data["hit"] and get_main_role(target) in Wolf:
        # wolves (as a main role) always die when shot
        # don't auto-kill wolves if they're only secondary roles
        evt.data["kill"] = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
        nevt.dispatch(var)
        evt.data["wolf"] = nevt.data["numkills"]

_kill_cmds = ("kill", "retract")

def wolf_can_kill(var, wolf):
    # a wolf can kill if wolves in general can kill, and the wolf is a Killer
    # this is a utility function meant to be used by other wolf role modules
    nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
    nevt.dispatch(var)
    num_kills = nevt.data["numkills"]
    if num_kills == 0:
        return False
    wolfroles = get_all_roles(wolf)
    return bool(Wolf & Killer & wolfroles)

def get_wolfchat_roles(var):
    wolves = Wolfchat
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF or "traitor" not in All:
            wolves = Wolf
        else:
            wolves = Wolf | {"traitor"}
    return wolves

def get_talking_roles(var):
    roles = Wolfchat
    if var.RESTRICT_WOLFCHAT & var.RW_WOLVES_ONLY_CHAT or var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF or "traitor" not in All:
            roles = Wolf
        else:
            roles = Wolf | {"traitor"}
    return roles

def is_known_wolf_ally(var, actor, target):
    actor_role = get_main_role(actor)
    target_role = get_main_role(target)
    wolves = get_wolfchat_roles(var)
    return actor_role in wolves and target_role in wolves

def send_wolfchat_message(var, user, message, roles, *, role=None, command=None):
    if role not in Wolf & Killer and var.RESTRICT_WOLFCHAT & var.RW_NO_INTERACTION:
        return
    if command not in _kill_cmds and var.RESTRICT_WOLFCHAT & var.RW_ONLY_KILL_CMD:
        if var.PHASE == "night" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
            return
        if var.PHASE == "day" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            return
    if not is_known_wolf_ally(var, user, user):
        return

    wcroles = get_wolfchat_roles(var)
    if var.RESTRICT_WOLFCHAT & var.RW_ONLY_SAME_CMD:
        if var.PHASE == "night" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
            wcroles = roles
        if var.PHASE == "day" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            wcroles = roles

    wcwolves = get_all_players(wcroles)
    wcwolves.remove(user)

    player = None
    for player in wcwolves:
        player.queue_message(message)
    for player in var.SPECTATING_WOLFCHAT:
        player.queue_message(messages["relay_command_wolfchat"].format(message))
    if player is not None:
        player.send_messages()

def get_wolflist(var, player: users.User, *, shuffle: bool = True, remove_player: bool = True) -> List[str]:
    """ Retrieve the list of players annotated for displaying to wolfteam members.

    :param var: Game state
    :param player: Player the wolf list will be displayed to
    :param shuffle: Whether or not to randomize the player list being displayed
    :param remove_player: Whether or not to exclude ``player`` from the returned list
    :returns: List of localized message strings to pass into either players_list or players_list_count
    """

    pl = list(get_players())
    if remove_player:
        pl.remove(player)
    if shuffle:
        random.shuffle(pl)

    badguys = Wolfchat
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF or "traitor" not in All:
            badguys = Wolf
        else:
            badguys = Wolf | {"traitor"}

    role = None
    if player in get_players():
        role = get_main_role(player)

    if role in badguys | {"warlock"}:
        entries = []
        if "cursed villager" in All:
            cursed = get_all_players(("cursed villager",))
        else:
            cursed = set()
        if role in badguys:
            for p in pl:
                prole = get_main_role(p)
                if prole in badguys:
                    if p in cursed:
                        entries.append(messages["players_list_entry"].format(
                            p, "bold", ["cursed villager", prole]))
                    else:
                        entries.append(messages["players_list_entry"].format(p, "bold", [prole]))
                elif p in cursed:
                    entries.append(messages["players_list_entry"].format(p, "", ["cursed villager"]))
                else:
                    entries.append(messages["players_list_entry"].format(p, "", []))
        elif role == "warlock":
            # warlock not in wolfchat explicitly only sees cursed
            for p in pl:
                if p in cursed:
                    entries.append(messages["players_list_entry"].format(p, "", ["cursed villager"]))
                else:
                    entries.append(messages["players_list_entry"].format(p, "", []))
    else:
        entries = [messages["players_list_entry"].format(p, "", []) for p in pl]

    return entries
