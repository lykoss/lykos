import re
import random
import itertools
import math
from collections import defaultdict

from src.functions import get_all_players, get_main_role
from src import users, channels, errlog, plog
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.cats import Wolfchat

@event_listener("see")
def on_see(evt, var, seer, target):
    if target in var.ROLES["cursed villager"]:
        evt.data["role"] = "wolf"

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["cursed villager"] = {"Village", "Cursed"}

@event_listener("send_role")
def on_send_role(evt, var):
    cursed = get_all_players(var, ("cursed villager",))
    wolves = get_all_players(var, Wolfchat)
    for player in cursed:
        if get_main_role(var, player) == "cursed villager" or player in wolves:
            player.send(messages["cursed_notify"])
