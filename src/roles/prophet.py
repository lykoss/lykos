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

PRAYED = UserSet() # type: Set[users.User]

@command("pray", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("prophet",))
def pray(var, wrapper, message):
    """Receive divine visions of who has a role."""
    if wrapper.source in PRAYED:
        wrapper.pm(messages["already_prayed"])
        return

    what = re.split(" +", message)[0]
    if not what:
        wrapper.pm(messages["not_enough_parameters"])
        return

    # complete this as a match with other roles (so "cursed" can match "cursed villager" for instance)
    role = complete_one_match(what.lower(), {p for p in var.ROLE_GUIDE if p not in var.TEMPLATE_RESTRICTIONS})
    if role is None and what.lower() in var.ROLE_ALIASES:
        role = var.ROLE_ALIASES[what.lower()]
        if role in var.TEMPLATE_RESTRICTIONS: # allow only main roles
            role = None
    if role is None:
        # typo, let them fix it
        wrapper.pm(messages["specific_invalid_role"].format(what))
        return

    # get a list of all roles actually in the game, including roles that amnesiacs will be turning into
    # (amnesiacs are special since they're also listed as amnesiac; that way a prophet can see both who the
    # amnesiacs themselves are as well as what they'll become)
    pl = get_players()
    from src.roles.amnesiac import ROLES as amn_roles
    valid_roles = {r for p, r in amn_roles.items() if p in pl}.union(var.MAIN_ROLES.values())

    PRAYED.add(wrapper.source)

    if role in valid_roles:
        # this sees through amnesiac, so the amnesiac's final role counts as their role
        # also, if we're the only person with that role, say so
        people = set(get_all_players((role,))) | {p for p, r in amn_roles.items() if p in pl and r == role}
        if len(people) == 1 and wrapper.source in people:
            wrapper.pm(messages["vision_only_role_self"].format(role))
            PRAYED.add(wrapper.source)
            debuglog("{0} (prophet) PRAY {1} - ONLY".format(wrapper.source, role))
            return

        target = random.choice(list(people))
        part = random.sample([p for p in pl if p is not wrapper.source], len(pl) // 3)
        if target not in part:
            part[0] = target
        random.shuffle(part)
        part = [p.nick for p in part]

        an = ""
        if role.startswith(("a", "e", "i", "o", "u")):
            an = "n"

        key = "vision_players"
        if len(part) == 1:
            key = "vision_role"

        if len(part) > 2:
            msg = "{0}, and {1}".format(", ".join(part[:-1]), part[-1])
        else:
            msg = " and ".join(part)

        wrapper.pm(messages[key].format(role, an, msg))
        debuglog("{0} (prophet) PRAY {1} ({2})".format(wrapper.source, role, target))

    else:
        # role is not in this game, this still counts as a successful activation of the power!
        wrapper.pm(messages["vision_none"].format(plural(role)))
        debuglog("{0} (prophet) PRAY {1} - NONE".format(wrapper.source, role))

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    for pht in get_all_players(("prophet",)):
        if pht.prefers_simple():
            pht.send(messages["prophet_simple"])
        else:
            pht.send(messages["prophet_notify"])

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["nightroles"].extend(get_all_players(("prophet",)))
    evt.data["actedcount"] += len(PRAYED)

@event_listener("night_acted")
def on_night_acted(evt, var, spy, user):
    if user in PRAYED:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["villagers"].update(get_players(("prophet",)))

@event_listener("begin_day")
def on_begin_day(evt, var):
    PRAYED.clear()

@event_listener("reset")
def on_reset(evt, var):
    PRAYED.clear()
