import re
import random

import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    special = set(list_players(("harlot", "priest", "prophet", "matchmaker",
                                "doctor", "hag", "sorcerer", "turncoat", "clone", "piper")))
    evt2 = Event("get_special", {"special": special})
    evt2.dispatch(cli, var)
    pl = set(list_players())
    wolves = set(list_players(var.WOLFTEAM_ROLES))
    neutral = set(list_players(var.TRUE_NEUTRAL_ROLES))
    special = evt2.data["special"]

    if nick_role == "wolf mystic" and actor_role != "wolf mystic":
        # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
        numvills = len(special & (pl - wolves - neutral))
        evt.data["actor_messages"].append(messages["wolf_mystic_info"].format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
    elif nick_role == "mystic" and actor_role != "mystic":
        numevil = len(wolves)
        evt.data["actor_messages"].append(messages["mystic_info"].format("are" if numevil != 1 else "is", numevil, "s" if numevil != 1 else ""))

    if actor_role == "wolf mystic" and nick_role != "wolf mystic":
        # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
        numvills = len(special & (pl - wolves - neutral))
        evt.data["nick_messages"].append(messages["wolf_mystic_info"].format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
    elif actor_role == "mystic" and nick_role != "mystic":
        numevil = len(wolves)
        evt.data["nick_messages"].append(messages["mystic_info"].format("are" if numevil != 1 else "is", numevil, "s" if numevil != 1 else ""))

@event_listener("transition_night_end", priority=2.01)
def on_transition_night_end(evt, cli, var):
    # init with all roles that haven't been split yet
    special = set(list_players(("harlot", "priest", "prophet", "matchmaker",
                                "doctor", "hag", "sorcerer", "turncoat", "clone", "piper")))
    evt2 = Event("get_special", {"special": special})
    evt2.dispatch(cli, var)
    pl = set(list_players())
    wolves = set(list_players(var.WOLFTEAM_ROLES))
    neutral = set(list_players(var.TRUE_NEUTRAL_ROLES))
    special = evt2.data["special"]

    for wolf in var.ROLES["wolf mystic"]:
        # if adding this info to !myrole, you will need to save off this count so that they can't get updated info until the next night
        # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
        numvills = len(special & (pl - wolves - neutral))
        pm(cli, wolf, messages["wolf_mystic_info"].format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
    for mystic in var.ROLES["mystic"]:
        if mystic in var.PLAYERS and not is_user_simple(mystic):
            pm(cli, mystic, messages["mystic_notify"])
        else:
            pm(cli, mystic, messages["mystic_simple"])
        # if adding this info to !myrole, you will need to save off this count so that they can't get updated info until the next night
        numevil = len(wolves)
        pm(cli, mystic, messages["mystic_info"].format("are" if numevil != 1 else "is", numevil, "s" if numevil != 1 else ""))

@event_listener("get_special")
def on_get_special(evt, cli, var):
    # mystics count as special even though they don't have any commands
    evt.data["special"].update(list_players(("mystic",)))

# vim: set sw=4 expandtab:
