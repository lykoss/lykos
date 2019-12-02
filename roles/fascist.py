import copy
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
from src.cats import Hidden

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    if var.NIGHT_COUNT == 1 or var.ALWAYS_PM_ROLE:
        fascists = get_players({"fascist"})
        if fascists:
            num_players = len(var.ALL_PLAYERS)
            for fascist in fascists:
                fascist.queue_message(messages["fascist_notify"])
            fascist.send_messages()

            hitlers = get_players({"hitler"})
            for fascist in fascists:
                other_fascists = copy.copy(fascists)
                other_fascists.remove(fascist)
                to_send = []
                if other_fascists:
                    to_send.append(messages["fascists_list_with_hitler"].format("hitler", hitlers, "fascist", other_fascists))
                else:
                    to_send.append(messages["fascists_list"].format("hitler", hitlers))
                if num_players >= 7:
                    to_send.append(messages["hitler_unaware"])
                else:
                    to_send.append(messages["hitler_aware"])
                fascist.send(*to_send, sep=" ")

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["fascist"] = {"Village"}
