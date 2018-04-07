import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict
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

# Set evt.data["acted"] = True if target acted during night and spy is able to know that info
# Used for werecrow and insomniac
@event_listener("night_acted")
def on_night_acted(evt, var, target, spy):
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

# Update evt.data["special"] with the Users who have this role as their main role,
# assuming this is some sort of special role (can act). Do *not* update this if this is a wolfteam
# special role, simply remove the event instead.
# Used by wolf mystic to determine the number of special villagers still alive.
@event_listener("get_special")
def on_get_special(evt, var):
    pass

# Update any game state which happens when player dies. If this role does things upon death,
# ensure that you check death_triggers (it's a bool) before firing it.
@event_listener("del_player")
def on_del_player(evt, var, player, mainrole, allroles, death_triggers):
    pass

# Clear all game state. Called whenever the game ends.
@event_listener("reset")
def on_reset(evt, var):
    pass

# Swap out a user with a different one. Update all game state to use the new User.
@event_listener("swap_player")
def on_swap_player(evt, var, old, new):
    pass

# Gets metadata about this role; kind will be a str with one of the following values:
# night_kills: Add metadata about any deaths this role can cause at night which use the standard
#              death message (i.e. do not have a custom death message). Set the data as follows:
#              evt.data["rolename"] = N (where N is the max # of deaths that this role can cause)
# Used in !stats in order to handle interactions between roles in a generic fashion so that
# more accurate results can be reported.
@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    pass


# vim: set sw=4 expandtab:
