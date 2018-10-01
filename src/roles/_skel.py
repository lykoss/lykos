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

# Skeleton file for new roles. Not all events are represented, only the most common ones.

# Instead of using list, set or dict, please use UserList, UserSet or UserDict respectively
# Please refer to the notes in src/containers.py for proper use

# Add to evt.data["actedcount"] and evt.data["nightroles"] if this role can act during night
# nightroles lists all Users who have this role and are capable of acting tonight
# actedcount should be added to (via +=) with everyone who has this role and has already acted
# Used to determine when all roles have acted (and therefore night should end)
@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    pass

# PM players who have this role with instructions
# Set priority=2 if this is a main role, and priority=5 if this is a secondary role
# (secondary roles are like gunner, assassin, etc. which by default stack on top of main roles)
@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    pass

# Update any role state that happens when someone with this role exchanges with someone else.
@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    pass

# Update any game state which happens when player dies. If this role does things upon death,
# ensure that you check death_triggers (it's a bool) before firing it.
@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    pass

# Clear all game state. Called whenever the game ends.
@event_listener("reset")
def on_reset(evt, var):
    pass

# Gets metadata about this role; kind will be a str with one of the following values:
# night_kills: Add metadata about any deaths this role can cause at night which use the standard
#              death message (i.e. do not have a custom death message). Set the data as follows:
#              evt.data["rolename"] = N (where N is the max # of deaths that this role can cause)
#              If this role does not kill at night, you can ignore this kind of metadata.
# special_keys: Add metadata about things related to this role that are recorded as stats in the db.
#               For example, "lovers" is a special key for matchmaker so that we can track stats as a lover,
#               and "vg activated" and "vg driven off" are special keys for vengeful ghost so we can
#               track stats for those things as well. Anything added to evt.data["special"] in the player_win
#               event should be present here in the metadata as well. Set the data as follows:
#               evt.data["rolename"] = {"key1", "key2", ...} (the value is a set)
#               If this role does not add special data in player_win, you can ignore this kind of metadata.
# role_categories: Add metadata about which role categories this role belongs to. See src/cats.py ROLE_CATS
#                  for the full list and a description of what each category is for. Set the data as follows:
#                  evt.data["rolename"] = {"cat1", "cat2", ...} (the value is a set)
#                  All roles must implement this kind of metadata.
@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    pass

# vim: set sw=4 expandtab:
