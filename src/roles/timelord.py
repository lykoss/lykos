import re
import random
import itertools
import math
import threading
import time
from collections import defaultdict
from typing import Set, Optional

from src import channels, users, config
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import event_listener, Event
from src.gamestate import GameState
from src.users import User

TIME_LORD_DAY_LIMIT = 60
TIME_LORD_DAY_WARN = 45
TIME_LORD_NIGHT_LIMIT = 30
TIME_LORD_NIGHT_WARN = 0

TIME_ATTRIBUTES = (
    ("day_time_limit", TIME_LORD_DAY_LIMIT),
    ("day_time_warn", TIME_LORD_DAY_WARN),
    ("short_day_limit", TIME_LORD_DAY_LIMIT),
    ("short_day_warn", TIME_LORD_DAY_WARN),
    ("night_time_limit", TIME_LORD_NIGHT_LIMIT),
    ("night_time_warn", TIME_LORD_NIGHT_WARN),
)

TRIGGERED = False

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: Set[str], death_triggers: bool):
    global TRIGGERED
    if not death_triggers or "time lord" not in all_roles:
        return

    var.game_settings.update(TIME_ATTRIBUTES)

    TRIGGERED = True
    channels.Main.send(messages["time_lord_dead"].format(var.TIME_LORD_DAY_LIMIT, var.TIME_LORD_NIGHT_LIMIT))

    from src.trans import hurry_up, night_warn, night_timeout, DAY_ID, NIGHT_ID, TIMERS
    if var.current_phase == "day":
        time_limit = var.day_time_limit
        limit_cb = hurry_up
        limit_args = [var, DAY_ID, True]
        time_warn = var.day_time_warn
        warn_cb = hurry_up
        warn_args = [var, DAY_ID, False]
        timer_name = "day_warn"
    elif var.current_phase == "night":
        time_limit = var.night_time_limit
        limit_cb = night_timeout
        limit_args = [var, NIGHT_ID]
        time_warn = var.night_time_warn
        warn_cb = night_warn
        warn_args = [var, NIGHT_ID]
        timer_name = "night_warn"
    else:
        return

    if f"{var.current_phase}_limit" in TIMERS:
        time_left = int((TIMERS[f"{var.current_phase}_limit"][1] + TIMERS[f"{var.current_phase}_limit"][2]) - time.time())

        if time_left > time_limit > 0:
            t = threading.Timer(time_limit, limit_cb, limit_args)
            TIMERS[f"{var.current_phase}_limit"] = (t, time.time(), time_limit)
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
def on_night_idled(evt: Event, var: GameState, player: User):
    # don't give people warning points on night idle when time lord is active
    if TRIGGERED:
        evt.prevent_default = True

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    global TRIGGERED
    TRIGGERED = False

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["time lord"] = {"Hidden"}
