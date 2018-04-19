import re
import random
import itertools
from collections import defaultdict, deque

import botconfig
from src.utilities import *
from src import debuglog, errlog, plog, users, channels
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.dispatcher import MessageDispatcher
from src.messages import messages
from src.events import Event

from src.roles._shaman_helper import havetotem, _get_target, _give_totem, _apply_totem

TOTEMS = UserDict()         # type: Dict[users.User, str]
LASTGIVEN = UserDict()      # type: Dict[users.User, users.User]
SHAMANS = UserDict()        # type: Dict[users.User, List[users.User]]

@command("give", "totem", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("wolf shaman",))
def wolf_shaman_totem(var, wrapper, message, prefix="You"):
    """Give a totem to a player."""

    target = _get_target(var, wrapper, message, LASTGIVEN)
    if not target:
        return

    tags = set()
    if TOTEMS[wrapper.source] in var.BENEFICIAL_TOTEMS:
        tags.add("beneficial")

    _give_totem(var, wrapper, target, prefix, tags, "wolf shaman", " of {0}".format(TOTEMS[wrapper.source]), SHAMANS)

    relay_wolfchat_command(wrapper.client, wrapper.source.nick, messages["shaman_wolfchat"].format(wrapper.source, target), ("wolf shaman",), is_wolf_command=True)

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    for a,(b,c) in list(SHAMANS.items()):
        if user in (a, b, c):
            del SHAMANS[a]

@event_listener("night_acted")
def on_acted(evt, var, user, actor):
    if user in SHAMANS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("wolf shaman",)))

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    actor_totem = None
    target_totem = None
    if actor_role == "wolf shaman":
        actor_totem = TOTEMS.pop(actor)
        if actor in SHAMANS:
            del SHAMANS[actor]
        if actor in LASTGIVEN:
            del LASTGIVEN[actor]

    if target_role == "wolf shaman":
        target_totem = TOTEMS.pop(target)
        if target in SHAMANS:
            del SHAMANS[target]
        if target in LASTGIVEN:
            del LASTGIVEN[target]

    if target_totem:
        evt.data["actor_messages"].append(messages["shaman_totem"].format(target_totem))
        TOTEMS[actor] = target_totem
    if actor_totem:
        evt.data["target_messages"].append(messages["shaman_totem"].format(actor_totem))
        TOTEMS[target] = actor_totem

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(SHAMANS)
    evt.data["nightroles"].extend(get_players(("wolf shaman",)))

@event_listener("transition_day_begin", priority=4)
def on_transition_day_begin(evt, var):
    # Select random totem recipients if shamans didn't act
    pl = get_players()
    for shaman in get_players(("wolf shaman",)):
        if shaman not in SHAMANS and shaman.nick not in var.SILENCED:
            ps = pl[:]
            if shaman in LASTGIVEN:
                if LASTGIVEN[shaman] in ps:
                    ps.remove(LASTGIVEN[shaman])
            levt = Event("get_random_totem_targets", {"targets": ps})
            levt.dispatch(var, shaman)
            ps = levt.data["targets"]
            if ps:
                target = random.choice(ps)
                dispatcher = MessageDispatcher(shaman, shaman)

                tags = set()
                if TOTEMS[shaman] in var.BENEFICIAL_TOTEMS:
                    tags.add("beneficial")

                _give_totem(var, dispatcher, target, messages["random_totem_prefix"], tags, "wolf shaman", " of {0}".format(TOTEMS[shaman]), SHAMANS)
                relay_wolfchat_command(shaman.client, shaman.nick, messages["shaman_wolfchat"].format(shaman, target), ("wolf shaman",), is_wolf_command=True)
            else:
                LASTGIVEN[shaman] = None
        elif shaman not in SHAMANS:
            LASTGIVEN[shaman] = None

@event_listener("transition_day_begin", priority=7)
def on_transition_day_begin2(evt, var):
    for shaman, (victim, target) in SHAMANS.items():
        _apply_totem(TOTEMS[shaman], shaman, victim)

        if target is not victim:
            shaman.send(messages["totem_retarget"].format(victim))
        LASTGIVEN[shaman] = victim

    havetotem.extend(sorted(filter(None, LASTGIVEN.values())))

@event_listener("transition_night_end", priority=2.01)
def on_transition_night_end(evt, var):
    max_totems = 0
    ps = get_players()
    shamans = get_players(("wolf shaman",))
    index = var.TOTEM_ORDER.index("wolf shaman")
    for c in var.TOTEM_CHANCES.values():
        max_totems += c[index]

    for s in list(LASTGIVEN):
        if s not in shamans:
            del LASTGIVEN[s]

    for shaman in shamans:
        pl = ps[:]
        random.shuffle(pl)
        if LASTGIVEN.get(shaman):
            if LASTGIVEN[shaman] in pl:
                pl.remove(LASTGIVEN[shaman])

        target = 0
        rand = random.random() * max_totems
        for t in var.TOTEM_CHANCES.keys():
            target += var.TOTEM_CHANCES[t][index]
            if rand <= target:
                TOTEMS[shaman] = t
                break
        if shaman.prefers_simple():
            # Message about role was sent with wolfchat
            shaman.send(messages["totem_simple"].format(TOTEMS[shaman]))
        else:
            totem = TOTEMS[shaman]
            tmsg = messages["shaman_totem"].format(totem)
            try:
                tmsg += messages[totem + "_totem"]
            except KeyError:
                tmsg += messages["generic_bug_totem"]
                channels.Main.send(messages["something_happened"])
            shaman.send(tmsg)

@event_listener("begin_day")
def on_begin_day(evt, var):
    SHAMANS.clear()

@event_listener("reset")
def on_reset(evt, var):
    TOTEMS.clear()
    LASTGIVEN.clear()
    SHAMANS.clear()

@event_listener("succubus_visit")
def on_succubus_visit(evt, var, succubus, target):
    if target in SHAMANS and SHAMANS[target][1] in get_all_players(("succubus",)):
        if TOTEMS[target] not in var.BENEFICIAL_TOTEMS:
            target.send(messages["retract_totem_succubus"].format(SHAMANS[target][1]))
            del SHAMANS[target]

@event_listener("myrole")
def on_myrole(evt, var, user):
    if evt.data["role"] == "wolf shaman" and var.PHASE == "night" and user not in SHAMANS:
        evt.data["messages"].append(messages["totem_simple"].format(TOTEMS[user]))

@event_listener("revealroles_role")
def on_revealroles(evt, var, wrapper, user, role):
    if user in TOTEMS:
        if user in SHAMANS:
            evt.data["special_case"].append("giving {0} totem to {1}".format(TOTEMS[user], SHAMANS[user][0]))
        elif var.PHASE == "night":
            evt.data["special_case"].append("has {0} totem".format(TOTEMS[user]))
        elif user in LASTGIVEN and LASTGIVEN[user]:
            evt.data["special_case"].append("gave {0} totem to {1}".format(TOTEMS[user], LASTGIVEN[user]))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        # only add shamans here if they were given a death totem
        # even though retribution kills, it is given a special kill message
        evt.data["wolf shaman"] = list(TOTEMS.values()).count("death")

# vim: set sw=4 expandtab:
