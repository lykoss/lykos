import re
import random
import itertools
import math
import threading
import time
from collections import defaultdict

from src.utilities import *
from src import channels, users, config
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import event_listener

TIME_ATTRIBUTES = (
    ("DAY_TIME_LIMIT", "TIME_LORD_DAY_LIMIT"),
    ("DAY_TIME_WARN", "TIME_LORD_DAY_WARN"),
    ("SHORT_DAY_LIMIT", "TIME_LORD_DAY_LIMIT"),
    ("SHORT_DAY_WARN", "TIME_LORD_DAY_WARN"),
    ("NIGHT_TIME_LIMIT", "TIME_LORD_NIGHT_LIMIT"),
    ("NIGHT_TIME_WARN", "TIME_LORD_NIGHT_WARN"),
)

TRIGGERED = False

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    global TRIGGERED
    if not death_triggers or "time lord" not in all_roles:
        return

    for attr, new_attr in TIME_ATTRIBUTES:
        if attr not in var.ORIGINAL_SETTINGS:
            var.ORIGINAL_SETTINGS[attr] = getattr(var, attr)

        setattr(var, attr, getattr(var, new_attr))

    TRIGGERED = True
    channels.Main.send(messages["time_lord_dead"].format(var.TIME_LORD_DAY_LIMIT, var.TIME_LORD_NIGHT_LIMIT))

    from src.trans import hurry_up, night_warn, night_timeout, DAY_ID, TIMERS
    if var.GAMEPHASE == "day":
        time_limit = var.DAY_TIME_LIMIT
        limit_cb = hurry_up
        limit_args = [var, DAY_ID, True]
        time_warn = var.DAY_TIME_WARN
        warn_cb = hurry_up
        warn_args = [var, DAY_ID, False]
        timer_name = "day_warn"
    elif var.GAMEPHASE == "night":
        time_limit = var.NIGHT_TIME_LIMIT
        limit_cb = night_timeout
        limit_args = [var, var.NIGHT_ID]
        time_warn = var.NIGHT_TIME_WARN
        warn_cb = night_warn
        warn_args = [var, var.NIGHT_ID]
        timer_name = "night_warn"
    else:
        return

    if f"{var.GAMEPHASE}_limit" in TIMERS:
        time_left = int((TIMERS[f"{var.GAMEPHASE}_limit"][1] + TIMERS[f"{var.GAMEPHASE}_limit"][2]) - time.time())

        if time_left > time_limit > 0:
            t = threading.Timer(time_limit, limit_cb, limit_args)
            TIMERS[f"{var.GAMEPHASE}_limit"] = (t, time.time(), time_limit)
            t.daemon = True
            t.start()

            # Don't duplicate warnings, i.e. only set the warning timer if a warning was not already given
            if timer_name in TIMERS and time_warn > 0:
                timer = TIMERS[timer_name][0]
                if timer.isAlive():
                    timer.cancel()
                    t = threading.Timer(time_warn, warn_cb, warn_args)
                    TIMERS[timer_name] = (t, time.time(), time_warn)
                    t.daemon = True
                    t.start()

@event_listener("night_idled")
def on_night_idled(evt, var, player):
    # don't give people warning points on night idle when time lord is active
    if TRIGGERED:
        evt.prevent_default = True

@event_listener("reset")
def on_reset(evt, var):
    global TRIGGERED
    TRIGGERED = False

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["time lord"] = {"Hidden"}
