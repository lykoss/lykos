from __future__ import annotations

import re
import random
from typing import List, Tuple, TYPE_CHECKING

from src import users, channels, cats
from src.functions import get_players, get_all_players
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event, event_listener

if TYPE_CHECKING:
    from src.gamestate import GameState
    from src.users import User

# Generated message keys used in this file:
# mystic_night_num, mystic_day_num, mystic_info,
# mystic_notify, wolf_mystic_notify

def register_mystic(rolename: str, *, send_role: bool, types: Tuple[str]):
    LAST_COUNT: UserDict[User, List[Tuple[str, int]]] = UserDict()

    role = rolename.replace(" ", "_")

    @event_listener("send_role", listener_id="mystics.<{}>.on_send_role".format(rolename))
    def on_send_role(evt: Event, var: GameState):
        values = []

        for t in types:
            cat = cats.get(t)
            players = get_players(var, cat)
            values.append((len(players), t))

        msg = messages["mystic_info_initial"].format(values[0][0], [messages["mystic_join"].format(c, t) for c, t in values])

        for mystic in get_all_players(var, (rolename,)):
            LAST_COUNT[mystic] = values
            if send_role:
                to_send = "{0}_notify".format(role)
                mystic.send(messages[to_send].format(rolename))
            mystic.send(msg)

    @event_listener("new_role", listener_id="mystics.<{}>.on_new_role".format(rolename))
    def on_new_role(evt: Event, var: GameState, player: User, old_role: str):
        if evt.params.inherit_from in LAST_COUNT and old_role != rolename and evt.data["role"] == rolename:
            values = LAST_COUNT.pop(evt.params.inherit_from)
            LAST_COUNT[player] = values
            key = "mystic_info_{0}".format(var.current_phase)
            msg = messages[key].format(values[0][0], [messages["mystic_join"].format(c, t) for c, t in values])
            evt.data["messages"].append(msg)

    @event_listener("reset", listener_id="mystics.<{}>.on_reset".format(rolename))
    def on_reset(evt: Event, var: GameState):
        LAST_COUNT.clear()

    @event_listener("myrole", listener_id="mystics.<{}>.on_myrole".format(rolename))
    def on_myrole(evt: Event, var: GameState, user: User):
        if user in get_all_players(var, (rolename,)):
            values = LAST_COUNT[user]
            key = "mystic_info_{0}".format(var.current_phase)
            msg = messages[key].format(values[0][0], [messages["mystic_join"].format(c, t) for c, t in values])
            evt.data["messages"].append(msg)
