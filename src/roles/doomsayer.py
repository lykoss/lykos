from __future__ import annotations

import random
import re
from typing import Optional

from src import status
from src.cats import All
from src.containers import UserSet, UserDict
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_all_players, get_target
from src.messages import messages
from src.roles.helper.wolves import is_known_wolf_ally, register_wolf, send_wolfchat_message
from src.status import try_misdirection, try_exchange
from src.users import User
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState

register_wolf("doomsayer")

SEEN = UserSet()
LASTSEEN: UserDict[User, User] = UserDict()
KILLS: UserDict[User, User] = UserDict()
SICK: UserDict[User, User] = UserDict()
LYCANS: UserDict[User, User] = UserDict()

_mappings = ("death", KILLS), ("lycan", LYCANS), ("sick", SICK)

@command("see", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("doomsayer",))
def see(wrapper: MessageDispatcher, message: str):
    """Use your paranormal senses to determine a player's doom."""
    if wrapper.source in SEEN:
        wrapper.send(messages["seer_fail"])
        return

    var = wrapper.game_state
    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_see_self")
    if not target:
        return

    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.send(messages["no_see_wolf"])
        return

    if LASTSEEN.get(wrapper.source) is target:
        wrapper.send(messages["no_see_same"])
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    mode, mapping = random.choice(_mappings)
    # keys: doomsayer_death, doomsayer_lycan, doomsayer_sick
    wrapper.send(messages["doomsayer_{0}".format(mode)].format(target))
    mapping[wrapper.source] = target

    send_wolfchat_message(var, wrapper.source, messages["doomsayer_wolfchat"].format(wrapper.source, target), ("doomsayer",), role="doomsayer", command="see")

    SEEN.add(wrapper.source)
    LASTSEEN[wrapper.source] = target

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "doomsayer" and evt.data["role"] != "doomsayer":
        SEEN.discard(player)
        for name, mapping in _mappings:
            del mapping[:player:]

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    # only remove from SEEN; keep results of sees intact on death
    # so that we can apply them in begin_day even if doomsayer dies.
    SEEN.discard(player)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(SEEN)
    evt.data["nightroles"].extend(get_all_players(var, ("doomsayer",)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    for target in SICK.values():
        target.queue_message(messages["player_sick"])
    if SICK:
        User.send_messages()

@event_listener("night_kills")
def on_night_kills(evt: Event, var: GameState):
    for killer, victim in list(KILLS.items()):
        evt.data["victims"].add(victim)
        evt.data["killers"][victim].append(killer)

@event_listener("transition_night_end")
def on_transition_night_end(evt: Event, var: GameState):
    if LASTSEEN:
        # if doomsayer is in play and at least one of them saw someone the previous night,
        # let stats know that anyone could be a lycan
        status.add_lycanthropy_scope(var, All)
    for lycan in LYCANS.values():
        status.add_lycanthropy(var, lycan)
    for sick in SICK.values():
        status.add_disease(var, sick)

    LYCANS.clear()
    SICK.clear()

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    for sick in SICK.values():
        var.set_user_location(sick, var.find_house(sick), "illness", forced=True)
        status.add_silent(var, sick)

    # clear out LASTSEEN for people that didn't see last night
    for doom in list(LASTSEEN.keys()):
        if doom not in SEEN:
            del LASTSEEN[doom]

    SEEN.clear()
    KILLS.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    SEEN.clear()
    KILLS.clear()
    SICK.clear()
    LYCANS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["doomsayer"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Village Objective", "Wolf Objective"}
