from __future__ import annotations

from typing import Optional

from src.containers import UserSet
from src.events import Event, event_listener
from src.functions import get_players, get_all_players
from src.messages import messages
from src.gamestate import GameState
from src.users import User
from src.random import random

def setup_variables(rolename):
    SEEN = UserSet()

    @event_listener("del_player", listener_id="<{}>.on_del_player".format(rolename))
    def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
        SEEN.discard(player)

    @event_listener("new_role", listener_id="<{}>.on_new_role".format(rolename))
    def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
        if old_role == rolename and evt.data["role"] != rolename:
            SEEN.discard(player)

    @event_listener("chk_nightdone", listener_id="<{}>.on_chk_nightdone".format(rolename))
    def on_chk_nightdone(evt: Event, var: GameState):
        evt.data["acted"].extend(SEEN)
        evt.data["nightroles"].extend(get_all_players(var, (rolename,)))

    @event_listener("send_role", priority=2, listener_id="<{}>.on_send_role".format(rolename))
    def on_transition_night_end(evt: Event, var: GameState):
        for seer in get_all_players(var, (rolename,)):
            pl = get_players(var)
            random.shuffle(pl)
            pl.remove(seer)  # remove self from list

            seer.send(messages["seer_info_general"].format(rolename), messages[rolename + "_info"])
            if var.next_phase == "night":
                seer.send(messages["players_list"].format(pl))

    @event_listener("begin_day", listener_id="<{}>.on_begin_day".format(rolename))
    def on_begin_day(evt: Event, var: GameState):
        SEEN.clear()

    @event_listener("reset", listener_id="<{}>.on_reset".format(rolename))
    def on_reset(evt: Event, var: GameState):
        SEEN.clear()

    return SEEN
