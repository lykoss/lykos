import re
import random
import itertools
import math
from collections import defaultdict

from src.functions import get_all_players, get_main_role
from src import users, channels, debuglog, errlog, plog
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

@event_listener("transition_night_end", priority=3)
def on_transition_night_end(evt, var):
    cursed = get_all_players(("cursed villager",))
    wolves = get_all_players(Wolfchat)
    for player in cursed:
        if get_main_role(player) == "cursed villager" or cursed in wolves:
            cursed.send(messages["cursed_notify"])
