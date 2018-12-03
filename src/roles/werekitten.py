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
from src.roles.helper.wolves import register_killer

register_killer("werekitten")

@event_listener("gun_shoot")
def on_gun_shoot(evt, var, user, target):
    if get_main_role(target) == "werekitten":
        evt.data["hit"] = False

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["werekitten"] = {"Wolf", "Wolfchat", "Wolfteam", "Innocent", "Killer", "Nocturnal"}
