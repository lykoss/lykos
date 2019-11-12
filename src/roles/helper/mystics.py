import re
import random

from src.utilities import *
from src import users, channels, debuglog, errlog, plog, cats
from src.functions import get_players, get_all_players
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

# Generated message keys used in this file:
# mystic_night_num, mystic_day_num, mystic_info,
# mystic_notify, wolf_mystic_notify

def register_mystic(rolename, *, send_role, types):
    LAST_COUNT = UserDict() # type: Dict[users.User, List[Tuple[str, int]]]

    role = rolename.replace(" ", "_")

    @event_listener("transition_night_end", listener_id="<{}>.on_transition_night_end".format(rolename))
    def on_transition_night_end(evt, var):
        values = []

        for t in types:
            cat = cats.get(t)
            players = get_players(cat)
            values.append((len(players), t))

        msg = messages["mystic_info_initial"].format(values[0][0], [messages["mystic_join"].format(c, t) for c, t in values])

        for mystic in get_all_players((rolename,)):
            LAST_COUNT[mystic] = values
            if send_role:
                to_send = "{0}_notify".format(role)
                mystic.send(messages[to_send].format(rolename))
            mystic.send(msg)

    @event_listener("new_role", listener_id="<{}>.on_new_role".format(rolename))
    def on_new_role(evt, var, player, old_role):
        if evt.params.inherit_from in LAST_COUNT and old_role != rolename and evt.data["role"] == rolename:
            values = LAST_COUNT.pop(evt.params.inherit_from)
            LAST_COUNT[player] = values
            key = "mystic_info_{0}".format(var.PHASE)
            msg = messages[key].format(values[0][0], [messages["mystic_join"].format(c, t) for c, t in values])
            evt.data["messages"].append(msg)

    @event_listener("reset", listener_id="<{}>.on_reset".format(rolename))
    def on_reset(evt, var):
        LAST_COUNT.clear()

    @event_listener("myrole", listener_id="<{}>.on_myrole".format(rolename))
    def on_myrole(evt, var, user):
        if user in get_all_players((rolename,)):
            values = LAST_COUNT[user]
            key = "mystic_info_{0}".format(var.PHASE)
            msg = messages[key].format(values[0][0], [messages["mystic_join"].format(c, t) for c, t in values])
            evt.data["messages"].append(msg)

# vim: set sw=4 expandtab:
