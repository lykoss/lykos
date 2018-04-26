import re
import random

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.functions import get_players, get_all_players, get_main_role
from src.messages import messages
from src.events import Event

def setup_variables(rolename):
    SEEN = UserSet()

    @event_listener("del_player")
    def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
        SEEN.discard(user)

    @event_listener("night_acted")
    def on_acted(evt, var, user, actor):
        if user in SEEN:
            evt.data["acted"] = True

    @event_listener("get_special")
    def on_get_special(evt, var):
        evt.data["villagers"].update(get_players((rolename,)))

    @event_listener("exchange_roles")
    def on_exchange(evt, var, actor, target, actor_role, target_role):
        if actor_role == rolename and target_role != rolename:
            SEEN.discard(actor)
        elif target_role == rolename and actor_role != rolename:
            SEEN.discard(target)

    @event_listener("chk_nightdone")
    def on_chk_nightdone(evt, var):
        evt.data["actedcount"] += len(SEEN)
        evt.data["nightroles"].extend(get_all_players((rolename,)))

    @event_listener("transition_night_end", priority=2)
    def on_transition_night_end(evt, var):
        for seer in get_all_players((rolename,)):
            pl = get_players()
            random.shuffle(pl)
            pl.remove(seer)  # remove self from list

            a = "a"
            if rolename.startswith(("a", "e", "i", "o", "u")):
                a = "an"

            what = messages[rolename + "_ability"]

            to_send = "seer_role_info"
            if seer.prefers_simple():
                to_send = "seer_simple"
            seer.send(messages[to_send].format(a, rolename, what), "Players: " + ", ".join(p.nick for p in pl), sep="\n")

    @event_listener("begin_day")
    def on_begin_day(evt, var):
        SEEN.clear()

    @event_listener("reset")
    def on_reset(evt, var):
        SEEN.clear()

    return SEEN

# vim: set sw=4 expandtab:
