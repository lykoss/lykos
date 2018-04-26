import re
import random

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

def setup_variables(rolename, *, send_role, types):
    LAST_COUNT = UserDict() # type: Dict[users.User, int]

    role = rolename.replace(" ", "_")

    @event_listener("transition_night_end")
    def on_transition_night_end(evt, var):
        villagers = set(get_players(("priest", "prophet", "matchmaker", "doctor")))
        win_stealers = set(get_players(("fool", "monster", "demoniac")))
        neutrals = set(get_players(("turncoat", "clone", "jester")))

        special_evt = Event("get_special", {"villagers": villagers, "wolves": set(), "win_stealers": win_stealers, "neutrals": neutrals})
        special_evt.dispatch(var)

        targets = set()
        for name in types:
            targets.update(special_evt.data[name])

        count = len(targets)
        key = "{0}_info_{1}".format(role, ("singular" if count == 1 else "plural"))

        for mystic in get_all_players((rolename,)):
            LAST_COUNT[mystic] = count
            if send_role:
                to_send = "{0}_{1}".format(role, ("simple" if mystic.prefers_simple() else "notify"))
                mystic.send(messages[to_send])
            mystic.send(messages[key].format(count))

    @event_listener("exchange_roles")
    def on_exchange_roles(evt, var, actor, target, actor_role, target_role):
        if actor_role == rolename and target_role != rolename:
            count = LAST_COUNT.pop(actor)
            LAST_COUNT[target] = count
            key = "{0}_info_{1}_{2}".format(role, var.PHASE, ("singular" if count == 1 else "plural"))
            evt.data["target_messages"].append(messages[key].format(count))

        if target_role == rolename and actor_role != rolename:
            count = LAST_COUNT.pop(target)
            LAST_COUNT[actor] = count
            key = "{0}_info_{1}_{2}".format(role, var.PHASE, ("singular" if count == 1 else "plural"))
            evt.data["actor_messages"].append(messages[key].format(count))

    @event_listener("reset")
    def on_reset(evt, var):
        LAST_COUNT.clear()

    @event_listener("myrole")
    def on_myrole(evt, var, user):
        if user in get_all_players((rolename,)):
            key = "{0}_info_{1}_{2}".format(role, var.PHASE, ("singular" if LAST_COUNT[user] == 1 else "plural"))
            evt.data["messages"].append(messages[key].format(LAST_COUNT[user]))

    return LAST_COUNT

# vim: set sw=4 expandtab:
