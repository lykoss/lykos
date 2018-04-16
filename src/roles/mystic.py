import re
import random

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if actor_role not in ("mystic", "wolf mystic") and target_role not in ("mystic", "wolf mystic"):
        return

    special = set(get_players(("harlot", "priest", "prophet", "matchmaker",
                               "doctor", "hag", "sorcerer", "turncoat", "clone")))
    evt2 = Event("get_special", {"special": special})
    evt2.dispatch(var)
    pl = set(get_players())
    wolves = set(get_players(var.WOLFTEAM_ROLES))
    neutral = set(get_players(var.TRUE_NEUTRAL_ROLES))
    special = evt2.data["special"]

    if target_role == "wolf mystic" and actor_role != "wolf mystic":
        # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
        numvills = len(special & (pl - wolves - neutral))
        evt.data["actor_messages"].append(messages["wolf_mystic_info"].format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
    elif target_role == "mystic" and actor_role != "mystic":
        numevil = len(wolves)
        evt.data["actor_messages"].append(messages["mystic_info"].format("are" if numevil != 1 else "is", numevil, "s" if numevil != 1 else ""))

    if actor_role == "wolf mystic" and target_role != "wolf mystic":
        # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
        numvills = len(special & (pl - wolves - neutral))
        evt.data["target_messages"].append(messages["wolf_mystic_info"].format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
    elif actor_role == "mystic" and target_role != "mystic":
        numevil = len(wolves)
        evt.data["target_messages"].append(messages["mystic_info"].format("are" if numevil != 1 else "is", numevil, "s" if numevil != 1 else ""))

@event_listener("transition_night_end", priority=2.01)
def on_transition_night_end(evt, var):
    # init with all roles that haven't been split yet
    special = set(get_players(("harlot", "priest", "prophet", "matchmaker",
                               "doctor", "hag", "sorcerer", "turncoat", "clone")))
    evt2 = Event("get_special", {"special": special})
    evt2.dispatch(var)
    pl = set(get_players())
    wolves = set(get_players(var.WOLFTEAM_ROLES))
    neutral = set(get_players(var.TRUE_NEUTRAL_ROLES))
    special = evt2.data["special"]

    for wolf in get_all_players(("wolf mystic",)):
        # if adding this info to !myrole, you will need to save off this count so that they can't get updated info until the next night
        # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
        numvills = len(special & (pl - wolves - neutral))
        wolf.send(messages["wolf_mystic_info"].format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
    for mystic in get_all_players(("mystic",)):
        to_send = "mystic_notify"
        if mystic.prefers_simple():
            to_send = "mystic_simple"
        # if adding this info to !myrole, you will need to save off this count so that they can't get updated info until the next night
        numevil = len(wolves)
        mystic.send(messages[to_send], messages["mystic_info"].format("are" if numevil != 1 else "is", numevil, "s" if numevil != 1 else ""), sep="\n")

@event_listener("get_special")
def on_get_special(evt, var):
    # mystics count as special even though they don't have any commands
    evt.data["special"].update(get_players(("mystic",)))

# vim: set sw=4 expandtab:
