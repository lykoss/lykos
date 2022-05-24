from __future__ import annotations

import random
import re
from collections import defaultdict
from typing import Optional, Iterable

from src import users, config, relay
from src.cats import Wolf, Wolfchat, Wolfteam, Killer, Hidden, All
from src.containers import UserList, UserDict
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_main_role, get_players, get_all_roles, get_all_players, get_target
from src.messages import messages
from src.status import try_misdirection, try_exchange, is_silent
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState
from src.users import User

KILLS: UserDict[users.User, UserList] = UserDict()

def register_wolf(rolename):
    @event_listener("send_role", listener_id="wolves.<{}>.on_send_role".format(rolename))
    def on_transition_night_end(evt: Event, var: GameState):
        wolves = get_all_players(var, (rolename,))
        for wolf in wolves:
            msg = "{0}_notify".format(rolename.replace(" ", "_"))
            wolf.send(messages[msg])
            wolf.send(messages["players_list"].format(get_wolflist(var, wolf)))
            if var.next_phase == "night":
                nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
                nevt.dispatch(var, wolf)
                if rolename in Killer and not nevt.data["numkills"] and nevt.data["message"]:
                    wolf.send(messages[nevt.data["message"]])
        wevt = Event("wolf_notify", {})
        wevt.dispatch(var, rolename)

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=Wolf)
def wolf_kill(wrapper: MessageDispatcher, message: str):
    """Kill one or more players as a wolf."""
    var = wrapper.game_state
    # verify this user can actually kill
    if not get_all_roles(var, wrapper.source) & Wolf & Killer:
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
        target = get_target(wrapper, targ, not_self_message="no_suicide")
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
def wolf_retract(wrapper: MessageDispatcher, message: str):
    """Removes a wolf's kill selection."""
    var = wrapper.game_state
    if not get_all_roles(var, wrapper.source) & Wolf & Killer:
        return

    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        wrapper.pm(messages["retracted_kill"])
        send_wolfchat_message(var, wrapper.source, messages["wolfchat_retracted_kill"].format(wrapper.source), Wolf, role="wolf", command="retract")

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    for killer, targets in list(KILLS.items()):
        for target in targets:
            if player is target:
                targets.remove(target)
        if player is killer or not targets:
            del KILLS[killer]

@event_listener("transition_day", priority=1)
def on_transition_day(evt: Event, var: GameState):
    # figure out wolf target
    found = defaultdict(int)
    wolves = get_all_players(var, Wolf)
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

def _reorganize_killers(var: GameState, killers):
    wolfteam = get_players(var, Wolfteam)
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
def on_transition_day3(evt: Event, var: GameState):
    _reorganize_killers(var, evt.data["killers"])

@event_listener("transition_day", priority=6)
def on_transition_day6(evt: Event, var: GameState):
    _reorganize_killers(var, evt.data["killers"])

@event_listener("retribution_kill")
def on_retribution_kill(evt: Event, var: GameState, victim, orig_target):
    if evt.data["target"] == "@wolves": # kill a random wolf
        evt.data["target"] = random.choice(get_players(var, Wolf & Killer))

@event_listener("new_role", priority=4)
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    wcroles = get_wolfchat_roles()

    if old_role is None:
        # initial role assignment; don't do all the logic below about notifying other wolves and such
        if evt.data["role"] in wcroles:
            evt.data["in_wolfchat"] = True
        return

    sayrole = evt.data["role"]
    if sayrole in Hidden:
        sayrole = var.hidden_role

    if player in KILLS:
        del KILLS[player]

    if old_role not in wcroles and evt.data["role"] in wcroles:
        # a new wofl has joined the party, give them tummy rubs and the wolf list
        # and let the other wolves know to break out the confetti and villager steaks
        wofls = get_players(var, wcroles)
        evt.data["in_wolfchat"] = True
        if wofls:
            for wofl in wofls:
                # if a wolf is leaving us, don't tell them about the new wolf
                if wofl is evt.params.inherit_from:
                    continue
                wofl.queue_message(messages["wolfchat_new_member"].format(player, sayrole))
            User.send_messages()
        else:
            return # no other wolves, nothing else to do

        evt.data["messages"].append(messages["players_list"].format(get_wolflist(var, player, role=evt.data["role"])))

        if var.current_phase == "night" and evt.data["role"] in Wolf & Killer:
            # inform the new wolf that they can kill and stuff
            nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
            nevt.dispatch(var, player)
            if not nevt.data["numkills"] and nevt.data["message"]:
                evt.data["messages"].append(messages[nevt.data["message"]])

@event_listener("chk_nightdone", priority=3)
def on_chk_nightdone(evt: Event, var: GameState):
    wolves = [x for x in get_all_players(var, Wolf & Killer) if not is_silent(var, x)]
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
def on_transition_night_end(evt: Event, var: GameState, role):
    # roles allowed to talk in wolfchat
    talkroles = get_talking_roles()

    # condition imposed on talking in wolfchat (only during day/night, or no talking)
    # 0 = no talking
    # 1 = normal
    # 2 = only during day
    # 3 = only during night
    wccond = 1

    if config.Main.get("gameplay.wolfchat.disable_night"):
        if config.Main.get("gameplay.wolfchat.disable_day"):
            wccond = 0
        else:
            wccond = 2
    elif config.Main.get("gameplay.wolfchat.disable_day"):
        wccond = 3

    if role not in talkroles or wccond == 0 or len(get_players(var, talkroles)) < 2:
        return

    wolves = get_players(var, (role,))
    for wolf in wolves:
        wolf.queue_message(messages["wolfchat_notify_{0}".format(wccond)])
    User.send_messages()

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    KILLS.clear()

@event_listener("gun_shoot", priority=3)
def on_gun_shoot(evt: Event, var: GameState, user, target, role):
    if evt.data["hit"] and get_main_role(var, target) in Wolf:
        # wolves (as a main role) always die when shot
        # don't auto-kill wolves if they're only secondary roles
        evt.data["kill"] = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "night_kills":
        wolves = [x for x in get_all_players(var, Wolf & Killer) if not is_silent(var, x)]
        total_kills = 0
        for wolf in wolves:
            nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
            nevt.dispatch(var, wolf)
            num_kills = nevt.data["numkills"]
            if is_known_wolf_ally(var, wolf, wolf):
                total_kills = max(total_kills, num_kills)
            else:
                evt.data["wolf@" + wolf.name] = num_kills
        evt.data["wolf"] = total_kills

_kill_cmds = ("kill", "retract")

def wolf_can_kill(var, wolf):
    # a wolf can kill if wolves in general can kill, and the wolf is a Killer
    # this is a utility function meant to be used by other wolf role modules
    nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
    nevt.dispatch(var, wolf)
    num_kills = nevt.data["numkills"]
    if num_kills == 0:
        return False
    wolfroles = get_all_roles(var, wolf)
    return bool(Wolf & Killer & wolfroles)

def get_wolfchat_roles():
    wolves = Wolfchat
    if config.Main.get("gameplay.wolfchat.remove_non_wolves"):
        if config.Main.get("gameplay.wolfchat.traitor_non_wolf") or "traitor" not in All:
            wolves = Wolf
        else:
            wolves = Wolf | {"traitor"}
    return wolves

def get_talking_roles():
    roles = Wolfchat
    if config.Main.get("gameplay.wolfchat.wolves_only_chat") or config.Main.get("gameplay.wolfchat.remove_non_wolves"):
        if config.Main.get("gameplay.wolfchat.traitor_non_wolf") or "traitor" not in All:
            roles = Wolf
        else:
            roles = Wolf | {"traitor"}
    return roles

def is_known_wolf_ally(var, actor, target):
    actor_role = get_main_role(var, actor)
    target_role = get_main_role(var, target)
    wolves = get_wolfchat_roles()
    return actor_role in wolves and target_role in wolves

def send_wolfchat_message(var: GameState, user: User, message: str, roles: Iterable[str], *, role=None, command: Optional[str] = None):
    if command not in _kill_cmds and config.Main.get("gameplay.wolfchat.only_kill_command"):
        if var.current_phase == "night" and config.Main.get("gameplay.wolfchat.disable_night"):
            return
        if var.current_phase == "day" and config.Main.get("gameplay.wolfchat.disable_day"):
            return
    if not is_known_wolf_ally(var, user, user):
        return

    wcroles = get_wolfchat_roles()
    if config.Main.get("gameplay.wolfchat.only_same_command"):
        if var.current_phase == "night" and config.Main.get("gameplay.wolfchat.disable_night"):
            wcroles = roles
        if var.current_phase == "day" and config.Main.get("gameplay.wolfchat.disable_day"):
            wcroles = roles

    wcwolves = get_players(var, wcroles)
    wcwolves.remove(user)

    player = None
    for player in wcwolves:
        player.queue_message(message)
    for player in relay.WOLFCHAT_SPECTATE:
        player.queue_message(messages["relay_command_wolfchat"].format(message))
    if player is not None:
        player.send_messages()

def get_wolflist(var,
                 player: users.User,
                 *,
                 shuffle: bool = True,
                 remove_player: bool = True,
                 role: Optional[str] = None) -> list[str]:
    """ Retrieve the list of players annotated for displaying to wolfteam members.

    :param var: Game state
    :param player: Player the wolf list will be displayed to
    :param shuffle: Whether or not to randomize the player list being displayed
    :param remove_player: Whether or not to exclude ``player`` from the returned list
    :param role: Treat ``player`` as if they had this role as their main role, to customize list display
    :returns: List of localized message strings to pass into either players_list or players_list_count
    """

    pl = list(get_players(var))
    if remove_player:
        pl.remove(player)
    if shuffle:
        random.shuffle(pl)

    badguys = Wolfchat
    if config.Main.get("gameplay.wolfchat.remove_non_wolves"):
        if config.Main.get("gameplay.wolfchat.traitor_non_wolf") or "traitor" not in All:
            badguys = Wolf
        else:
            badguys = Wolf | {"traitor"}

    if role is None and player in get_players(var):
        role = get_main_role(var, player)

    if role in badguys | {"warlock"}:
        entries = []
        if "cursed villager" in All:
            cursed = get_all_players(var, ("cursed villager",))
        else:
            cursed = set()
        if role in badguys:
            for p in pl:
                prole = get_main_role(var, p)
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
