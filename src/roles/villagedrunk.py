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
from src.status import try_misdirection, try_exchange

@event_listener("send_role")
def on_send_role(evt, var):
    for drunk in get_all_players(("village drunk",)):
        drunk.send(messages["village_drunk_notify"])

@event_listener("assassin_target")
def on_assassin_target(evt, var, assassin, players):
    if evt.data["target"] is None and assassin in get_all_players(("village drunk",)):
        evt.data["target"] = random.choice(players)
        assassin.send(messages["drunken_assassin_notification"].format(evt.data["target"]))

@event_listener("gun_chances")
def on_gun_chances(evt, var, user, role):
    if user in get_all_players(("village drunk",)):
        hit, miss, headshot = var.DRUNK_GUN_CHANCES
        evt.data["hit"] += hit
        evt.data["miss"] += miss
        evt.data["headshot"] += headshot

@event_listener("gun_bullets")
def on_gun_bullets(evt, var, user, role):
    if user in get_all_players(("village drunk",)):
        evt.data["bullets"] *= var.DRUNK_SHOTS_MULTIPLIER

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["village drunk"] = {"Village", "Safe"}
