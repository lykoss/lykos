import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    for drunk in get_all_players(("village drunk",)):
        if drunk.prefers_simple():
            drunk.send(messages["village_drunk_simple"])
        else:
            drunk.send(messages["village_drunk_notify"])

@event_listener("assassin_target")
def on_assassin_target(evt, var, assassin, players):
    if evt.data["target"] is None and assassin in get_all_players(("village drunk",)):
        evt.data["target"] = random.choice(players)
        message = messages["drunken_assassin_notification"].format(evt.data["target"])
        if not assassin.prefers_simple():
            message += messages["assassin_info"]
        assassin.send(message)

@event_listener("gun_shoot")
def on_gun_chances(evt, var, user, role):
    if role != "sharpshooter" and user in get_all_players(("village drunk",)):
        hit, miss, headshot = var.DRUNK_GUN_CHANCES
        evt.data["hit"] = hit
        evt.data["miss"] = miss
        evt.data["headshot"] = headshot
        evt.stop_processing = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["village drunk"] = {"Village", "Safe"}
