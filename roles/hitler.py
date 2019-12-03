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

# Hitler is considered to be in "Wolfchat", so will have the role information sent out by helper/wolves.py
"""@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    if var.NIGHT_COUNT == 1 or var.ALWAYS_PM_ROLE:
        hitlers = get_players({"hitler"})
        if hitlers:
            for hitler in hitlers:
                hitler.queue_message(messages["hitler_notify"])
            hitler.send_messages()"""

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["hitler"] = {"Wolfteam", "Wolfchat"}

@event_listener("transition_night_end", priority=2.1)
def on_transition_night_end(evt, var):
    if var.NIGHT_COUNT == 1:
        num_players = len(var.ALL_PLAYERS)
        hitlers = get_players({"hitler"})
        if hitlers:
            fascists = get_players({"fascist"})
            for hitler in hitlers:
                if num_players < 7:
                    # Preparing for all possibilities that will never actually happen :)
                    other_hitlers = copy.copy(hitlers)
                    other_hitlers.remove(hitler)
                    if other_hitlers:
                        hitler.send(messages["fascists_list_with_hitler"].format("hitler", other_hitlers, "fascist", fascists))
                    else:
                        hitler.send(messages["fascists_list"].format("fascist", fascists))
                else:
                    hitler.send(messages["no_fascist_list"])

@event_listener("player_win")
def on_player_win(evt, var, player, mainrole, winner, survived):
    if winner == "fascists" and (mainrole == "fascist" or mainrole == "hitler"):
        evt.data["won"] = True
    if winner == "liberals" and mainrole == "liberal":
        evt.data["won"] = True
