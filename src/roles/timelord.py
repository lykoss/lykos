import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

TIME_ATTRIBUTES = (
    ("DAY_TIME_LIMIT", "TIME_LORD_DAY_LIMIT"),
    ("DAY_TIME_WARN", "TIME_LORD_DAY_WARN"),
    ("SHORT_DAY_LIMIT", "TIME_LORD_DAY_LIMIT"),
    ("SHORT_DAY_WARN", "TIME_LORD_DAY_WARN"),
    ("NIGHT_TIME_LIMIT", "TIME_LORD_NIGHT_LIMIT"),
    ("NIGHT_TIME_WARN", "TIME_LORD_NIGHT_WARN"),
)

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    if not death_triggers or "time lord" not in allroles:
        return

    for attr, new_attr in TIME_ATTRIBUTES:
        if attr not in var.ORIGINAL_SETTINGS:
            var.ORIGINAL_SETTINGS[attr] = getattr(var, attr)

        setattr(var, attr, getattr(var, new_attr))

    channels.Main.send(messages["time_lord_dead"].format(var.TIME_LORD_DAY_LIMIT, var.TIME_LORD_NIGHT_LIMIT))

    if var.GAMEPHASE == "day":
        time_limit = var.DAY_TIME_LIMIT
        time_warn = var.DAY_TIME_WARN
        phase_id = "DAY_ID"
        timer_name = "day_warn"
    elif var.GAMEPHASE == "night":
        time_limit = var.NIGHT_TIME_LIMIT
        time_warn = var.NIGHT_TIME_WARN
        phase_id = "NIGHT_ID"
        timer_name = "night_warn"
    else:
        raise ValueError("var.GAMEPHASE is neither day nor night: {}".format(var.GAMEPHASE))

    if timeleft_internal(var, var.GAMEPHASE) > time_limit > 0:
        t = threading.Timer(time_limit, hurry_up, [cli, phase_id, True])
        var.TIMERS[var.GAMEPHASE] = (t, time.time(), time_limit)
        t.daemon = True
        t.start()

        # Don't duplicate warnings, i.e. only set the warning timer if a warning was not already given
        if timer_name in var.TIMERS:
            timer = var.TIMERS[timer_name][0]
            if timer.isAlive():
                timer.cancel()
                t = threading.Timer(time_warn, hurry_up, [cli, phase_id, False])
                var.TIMERS[timer_name] = (t, time.time(), time_warn)
                t.daemon = True
                t.start()

    debuglog("{0} (time lord) TRIGGER".format(user))

# vim: set sw=4 expandtab:
