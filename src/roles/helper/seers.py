import re
import random

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.functions import get_players, get_all_players, get_main_role
from src.messages import messages
from src.events import Event

def setup_variables(rolename):
    SEEN = UserSet()

    @event_listener("del_player", listener_id="<{}>.on_del_player".format(rolename))
    def on_del_player(evt, var, player, all_roles, death_triggers):
        SEEN.discard(player)

    @event_listener("new_role", listener_id="<{}>.on_new_role".format(rolename))
    def on_new_role(evt, var, user, old_role):
        if old_role == rolename and evt.data["role"] != rolename:
            SEEN.discard(user)

    @event_listener("chk_nightdone", listener_id="<{}>.on_chk_nightdone".format(rolename))
    def on_chk_nightdone(evt, var):
        evt.data["actedcount"] += len(SEEN)
        evt.data["nightroles"].extend(get_all_players((rolename,)))

    @event_listener("transition_night_end", priority=2, listener_id="<{}>.on_transition_night_end".format(rolename))
    def on_transition_night_end(evt, var):
        for seer in get_all_players((rolename,)):
            pl = get_players()
            random.shuffle(pl)
            pl.remove(seer)  # remove self from list

            seer.send(messages["seer_info_general"].format(rolename), messages[rolename + "_info"])
            seer.send(messages["players_list"].format(pl))

    @event_listener("begin_day", listener_id="<{}>.on_begin_day".format(rolename))
    def on_begin_day(evt, var):
        SEEN.clear()

    @event_listener("reset", listener_id="<{}>.on_reset".format(rolename))
    def on_reset(evt, var):
        SEEN.clear()

    return SEEN

