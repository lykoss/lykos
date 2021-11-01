from __future__ import annotations

import re
from typing import Optional

from src.containers import UserSet, UserDict
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.messages import messages
from src.roles.helper.wolves import get_wolfchat_roles, is_known_wolf_ally, send_wolfchat_message, get_wolflist, \
    register_wolf
from src.status import try_misdirection, try_exchange
from src.users import User
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState

register_wolf("warlock")

CURSED: UserDict[User, User] = UserDict()
PASSED: UserSet = UserSet()

@command("curse", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def curse(wrapper: MessageDispatcher, message: str):
    var = wrapper.game_state
    target = get_target(wrapper, re.split(" +", message)[0])
    if not target:
        return

    if target in get_all_players(var, ("cursed villager",)):
        wrapper.pm(messages["target_already_cursed"].format(target))
        return

    # There may actually be valid strategy in cursing other wolfteam members,
    # but for now it is not allowed. If someone seems suspicious and shows as
    # villager across multiple nights, safes can use that as a tell that the
    # person is likely wolf-aligned.
    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["no_curse_wolf"])
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    CURSED[wrapper.source] = target
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["curse_success"].format(orig))
    send_wolfchat_message(var, wrapper.source, messages["curse_success_wolfchat"].format(wrapper.source, orig), {"warlock"}, role="warlock", command="curse")

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def pass_cmd(wrapper: MessageDispatcher, message: str):
    """Decline to use your special power for that night."""
    del CURSED[:wrapper.source:]
    PASSED.add(wrapper.source)

    wrapper.pm(messages["warlock_pass"])
    send_wolfchat_message(wrapper.game_state, wrapper.source, messages["warlock_pass_wolfchat"].format(wrapper.source), {"warlock"}, role="warlock", command="pass")

@command("retract", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def retract(wrapper: MessageDispatcher, message: str):
    """Retract your curse or pass."""
    del CURSED[:wrapper.source:]
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["warlock_retract"])
    send_wolfchat_message(wrapper.game_state, wrapper.source, messages["warlock_retract_wolfchat"].format(wrapper.source), {"warlock"}, role="warlock", command="retract")

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(CURSED)
    evt.data["acted"].extend(PASSED)
    evt.data["nightroles"].extend(get_all_players(var, ("warlock",)))

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, allroles: set[str], death_triggers: bool):
    del CURSED[:player:]
    PASSED.discard(player)

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "warlock" and evt.data["role"] != "warlock":
        del CURSED[:player:]
        PASSED.discard(player)

    if not evt.data["in_wolfchat"] and evt.data["role"] == "warlock":
        # this means warlock isn't in wolfchat, so only give cursed list
        player.send(messages["players_list"].format(get_wolflist(var, player)))

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    pl = get_players(var)
    wroles = get_wolfchat_roles()
    for warlock, target in CURSED.items():
        if target in pl and get_main_role(var, target) not in wroles:
            var.roles["cursed villager"].add(target)

    CURSED.clear()
    PASSED.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    CURSED.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["warlock"] = {"Wolfchat", "Wolfteam", "Nocturnal", "Wolf Objective"}
