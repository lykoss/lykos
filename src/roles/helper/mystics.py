import re
import random
from collections import Counter

from src.utilities import *
from src import users, channels, debuglog, errlog, plog, cats
from src.functions import get_players, get_all_players
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

# Generated message keys used in this file:
# mystic_safe, mystic_wolfteam, mystic_win_stealer,
# mystic_night_num, mystic_day_num, mystic_info,
# mystic_simple, mystic_notify, wolf_mystic_simple, wolf_mystic_notify

def setup_variables(rolename, *, send_role, types):
    LAST_COUNT = UserDict() # type: Dict[users.User, Tuple[str, bool]]

    role = rolename.replace(" ", "_")

    @event_listener("transition_night_end")
    def on_transition_night_end(evt, var):
        pl = set()
        ctr = Counter()

        for t in types:
            cat = cats.get(t)
            players = get_players(cat)
            pl.update(players)
            ctr[t] += len(players)

        values = []
        plural = True
        for name in types:
            keyname = "mystic_" + name.lower().replace(" ", "_")
            l = ctr[name]
            if l:
                if not values and l == 1:
                    plural = False
            else:
                l = "no"
            values.append("\u0002{0}\u0002 {1}{2}".format(l, messages[keyname], "" if l == 1 else "s"))

        if len(values) > 2:
            value = " and ".join((", ".join(values[:-1]), values[-1]))
        else:
            value = " and ".join(values)
        msg = messages["mystic_info"].format("are" if plural else "is", value, " still", "")

        for mystic in get_all_players((rolename,)):
            LAST_COUNT[mystic] = (value, plural)
            if send_role:
                to_send = "{0}_{1}".format(role, ("simple" if mystic.prefers_simple() else "notify"))
                mystic.send(messages[to_send])
            mystic.send(msg)

    @event_listener("new_role")
    def on_new_role(evt, var, player, old_role):
        if evt.params.inherit_from is not None and old_role != rolename and evt.data["role"] == rolename:
            value, plural = LAST_COUNT.pop(evt.params.inherit_from)
            LAST_COUNT[player] = (value, plural)
            key = "were" if plural else "was"
            msg = messages["mystic_info"].format(key, value, "", messages["mystic_{0}_num".format(var.PHASE)])
            evt.data["messages"].append(msg)

    @event_listener("reset")
    def on_reset(evt, var):
        LAST_COUNT.clear()

    @event_listener("myrole")
    def on_myrole(evt, var, user):
        if user in get_all_players((rolename,)):
            value, plural = LAST_COUNT[user]
            key = "were" if plural else "was"
            msg = messages["mystic_info"].format(key, value, "", messages["mystic_{0}_num".format(var.PHASE)])
            evt.data["messages"].append(msg)

    return LAST_COUNT

# vim: set sw=4 expandtab:
