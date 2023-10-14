from __future__ import annotations

import re
import random
from typing import Iterable, Optional

from src import config, gamestate, relay
from src.dispatcher import MessageDispatcher
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.decorators import command
from src.containers import UserSet, UserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_protection, add_absent, add_silent
from src.events import Event, event_listener
from src.users import User
from src.cats import Vampire

# some of this should be refactored into a helper class once we have more than one vampire role
# for now keeping it all together makes for cleaner code though, as I'm not 100% sure which parts will
# need to be shared and which parts will be unique to this particular vampire role; it'll depend on what
# the new role is/does.

class GameState(gamestate.GameState):
    def __init__(self):
        self.vampire_drained: UserSet = UserSet()
        self.vampire_acted: UserDict[User, User] = UserDict()

@command("bite", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("vampire",))
def vampire_bite(wrapper: MessageDispatcher, message: str):
    """Bite someone at night, draining their blood. Kills them if they were already drained."""
    var = wrapper.game_state # type: GameState
    target = get_target(wrapper, re.split(" +", message)[0])
    if not target:
        return

    if is_known_vampire_ally(var, wrapper.source, target):
        wrapper.send(messages["no_target_vampire"])
        return

    for vampire, victim in var.vampire_acted.items():
        if wrapper.source is vampire:
            # let the vampire target the same person multiple times in succession
            # doesn't really do anything but giving an error is even weirder
            continue
        if target is victim and is_known_vampire_ally(var, wrapper.source, vampire):
            wrapper.send(messages["already_bitten_tonight"].format(target))
            return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    var.vampire_acted[wrapper.source] = target
    wrapper.send(messages["vampire_bite"].format(orig))
    send_vampire_chat_message(var,
                              wrapper.source,
                              messages["vampire_bite_vampchat"].format(wrapper.source, target),
                              Vampire,
                              cmd="bite")

@command("retract", chan=False, pm=True, playing=True, phases=("night",), roles=("vampire",))
def vampire_retract(wrapper: MessageDispatcher, message: str):
    """Removes a vampire's bite selection."""
    var = wrapper.game_state
    if wrapper.source not in var.vampire_acted:
        return

    del var.vampire_acted[:wrapper.source:]
    wrapper.send(messages["retracted_bite"])
    send_vampire_chat_message(var,
                              wrapper.source,
                              messages["retracted_bite_vampchat"].format(wrapper.source),
                              Vampire,
                              cmd="retract")

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(var.vampire_acted)
    evt.data["nightroles"].extend(get_all_players(var, ("vampire",)))

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    # condition imposed on talking in wolfchat (only during day/night, or no talking)
    # 0 = no talking
    # 1 = normal
    # 2 = only during day
    # 3 = only during night
    cond = 1

    if config.Main.get("gameplay.wolfchat.disable_night"):
        if config.Main.get("gameplay.wolfchat.disable_day"):
            cond = 0
        else:
            cond = 2
    elif config.Main.get("gameplay.wolfchat.disable_day"):
        cond = 3

    for vampire in get_all_players(var, ("vampire",)):
        vampire.send(messages["vampire_notify"])
        if var.next_phase == "night":
            vampire.send(messages["players_list"].format(get_vampire_list(var, vampire)))
        if cond > 0:
            vampire.send(messages["wolfchat_notify_{0}".format(cond)].format("Vampire"))

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "vampire":
        del var.vampire_acted[:player:]
    elif old_role is None:
        # initial role assignment; don't notify other vampires
        return

    if evt.data["role"] == "vampire":
        vampires = get_players(var, ("vampire",))
        if not vampires:
            # no other vampires
            return

        for vamp in vampires:
            if vamp is evt.params.inherit_from:
                # if a vampire is being swapped out, don't inform them of their replacement
                continue
            # this message key is generic enough to be usable for vampire chat in addition to wolfchat
            vamp.queue_message(messages["wolfchat_new_member"].format(player, evt.data["role"]))
        User.send_messages()

        # defer resolution of get_vampire_list() until the time the message is actually being sent to the player
        # this way in a role swap we aren't working on an inaccurate view of who should have which role and potentially
        # leak information or give inaccurate information to the new vampire
        evt.data["messages"].append(
            lambda: messages["players_list"].format(get_vampire_list(var, player, role=evt.data["role"])))

@event_listener("night_kills")
def on_night_kills(evt: Event, var: GameState):
    for vampire, target in list(var.vampire_acted.items()):
        evt.data["victims"].add(target)
        evt.data["killers"][target].append(vampire)
        if target not in var.vampire_drained:
            # add a "protection" to this player to notify them they are drained and prevent the actual death
            # this allows other roles to intervene if necessary compared to doing that directly right now
            add_protection(var, target, vampire, "vampire", Vampire, priority=30)
    # important, otherwise our del_player listener instructs vampire to choose again
    var.vampire_acted.clear()

@event_listener("player_protected")
def on_player_protected(evt: Event,
                        var: GameState,
                        target: User,
                        attacker: Optional[User],
                        attacker_role: str,
                        protector: User,
                        protector_role: str,
                        reason: str):
    if protector_role == "vampire" and target not in var.vampire_drained:
        var.vampire_drained.add(target)
        target.send(messages["vampire_drained"])
        add_absent(var, target, "drained")
        add_silent(var, target)

@event_listener("add_lycanthropy")
def on_add_lycanthropy(evt: Event, var: GameState, target):
    if target in get_all_players(var, ("vampire",)):
        evt.prevent_default = True

@event_listener("add_disease")
def on_add_disease(evt: Event, var: GameState, target):
    if target in get_all_players(var, ("vampire",)):
        evt.prevent_default = True

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    if not var.in_game:
        return

    var.vampire_drained.discard(player)
    del var.vampire_acted[:player:]
    for vampire, target in list(var.vampire_acted.items()):
        if target is player:
            vampire.send(messages["hunter_discard"])
            del var.vampire_acted[vampire]

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "night_kills":
        evt.data["vampire"] = min(len(var.vampire_drained), len(get_all_players(var, ("vampire",))))
    elif kind == "role_categories":
        evt.data["vampire"] = {"Vampire", "Vampire Team", "Killer", "Nocturnal", "Vampire Objective", "Village Objective"}

_bite_cmds = ("bite", "retract")

def is_known_vampire_ally(var, actor, target):
    actor_role = get_main_role(var, actor)
    target_role = get_main_role(var, target)
    return actor_role in Vampire and target_role in Vampire

def send_vampire_chat_message(var: GameState,
                              player: User,
                              message: str,
                              roles: Iterable[str],
                              *,
                              cmd: Optional[str] = None):
    if cmd not in _bite_cmds and config.Main.get("gameplay.wolfchat.only_kill_command"):
        if var.current_phase == "night" and config.Main.get("gameplay.wolfchat.disable_night"):
            return
        if var.current_phase == "day" and config.Main.get("gameplay.wolfchat.disable_day"):
            return
    if not is_known_vampire_ally(var, player, player):
        return

    send_to_roles = Vampire
    if config.Main.get("gameplay.wolfchat.only_same_command"):
        if var.current_phase == "night" and config.Main.get("gameplay.wolfchat.disable_night"):
            send_to_roles = roles
        if var.current_phase == "day" and config.Main.get("gameplay.wolfchat.disable_day"):
            send_to_roles = roles

    send_to = get_players(var, send_to_roles)
    send_to.remove(player)

    player = None
    for player in send_to:
        player.queue_message(message)
    for player in relay.VAMPCHAT_SPECTATE:
        player.queue_message(messages["relay_command_vampchat"].format(message))
    if player is not None:
        player.send_messages()

def get_vampire_list(var,
                     player: User,
                     *,
                     shuffle: bool = True,
                     remove_player: bool = True,
                     role: Optional[str] = None) -> list[str]:
    """ Retrieve the list of players annotated for displaying to vampire team members.

    :param var: Game state
    :param player: Player the vampire list will be displayed to
    :param shuffle: Whether or not to randomize the player list being displayed
    :param remove_player: Whether to exclude ``player`` from the returned list
    :param role: Treat ``player`` as if they had this role as their main role, to customize list display
    :returns: List of localized message strings to pass into either players_list or players_list_count
    """

    pl = list(get_players(var))
    if remove_player:
        pl.remove(player)
    if shuffle:
        random.shuffle(pl)

    if role is None and player in get_players(var):
        role = get_main_role(var, player)

    if role in Vampire:
        entries = []
        for p in pl:
            prole = get_main_role(var, p)
            if prole in Vampire and is_known_vampire_ally(var, player, p):
                entries.append(messages["players_list_entry"].format(p, "bold", [prole]))
            elif player in var.vampire_drained:
                entries.append(messages["players_list_entry"].format(p, "", ["drained"]))
            else:
                entries.append(messages["players_list_entry"].format(p, "", []))
    else:
        entries = [messages["players_list_entry"].format(p, "", []) for p in pl]

    return entries
