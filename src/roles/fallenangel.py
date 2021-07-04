import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import users, channels, status, errlog, plog
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.functions import get_players, get_all_players
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.cats import Wolf

from src.roles.helper.wolves import register_wolf

register_wolf("fallen angel")

@event_listener("try_protection")
def on_try_protection(evt, var, target, attacker, attacker_role, reason):
    if attacker_role == "wolf" and get_all_players(var, ("fallen angel",)):
        status.remove_all_protections(var, target, attacker=None, attacker_role="fallen angel", reason="fallen_angel")
        evt.prevent_default = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["fallen angel"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Village Objective", "Wolf Objective"}
