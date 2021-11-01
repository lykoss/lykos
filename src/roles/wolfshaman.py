from __future__ import annotations

import itertools
import random
from typing import Optional

from src.decorators import command
from src.events import Event, find_listener, event_listener
from src.functions import get_players, get_all_players
from src.messages import messages
from src.roles.helper.shamans import get_totem_target, give_totem, setup_variables, totem_message
from src.roles.helper.wolves import register_wolf, send_wolfchat_message
from src.status import is_silent
from src import users
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState

TOTEMS, LASTGIVEN, SHAMANS, RETARGET = setup_variables("wolf shaman", knows_totem=True)

register_wolf("wolf shaman")

@command("totem", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("wolf shaman",))
def wolf_shaman_totem(wrapper: MessageDispatcher, message: str):
    """Give a totem to a player."""

    var = wrapper.game_state

    totem_types = list(TOTEMS[wrapper.source].keys())
    totem, target = get_totem_target(var, wrapper, message, LASTGIVEN, totem_types)
    if not target:
        return

    if not totem:
        totem_types = list(TOTEMS[wrapper.source].keys())
        if len(totem_types) == 1:
            totem = totem_types[0]
        else:
            wrapper.send(messages["shaman_ambiguous_give"])
            return

    orig_target = target
    target = RETARGET[wrapper.source].get(target, target)
    if target in itertools.chain.from_iterable(SHAMANS[wrapper.source].values()):
        wrapper.send(messages["shaman_no_stacking"].format(orig_target))
        return

    given = give_totem(var, wrapper, target, totem, key="shaman_success_night_known", role="wolf shaman")
    if given:
        victim, target = given
        if victim is not target:
            RETARGET[wrapper.source][target] = victim
        SHAMANS[wrapper.source][totem].append(victim)
        if len(SHAMANS[wrapper.source][totem]) > TOTEMS[wrapper.source][totem]:
            SHAMANS[wrapper.source][totem].pop(0)

    send_wolfchat_message(var, wrapper.source, messages["shaman_wolfchat"].format(wrapper.source, target), ("wolf shaman",), role="wolf shaman", command="totem")

@event_listener("transition_day_begin", priority=4)
def on_transition_day_begin(evt: Event, var: GameState):
    # Select random totem recipients if shamans didn't act
    pl = get_players(var)
    for shaman in get_all_players(var, ("wolf shaman",)):
        if is_silent(var, shaman):
            continue

        ps = pl[:]
        for given in itertools.chain.from_iterable(LASTGIVEN[shaman].values()):
            if given in ps:
                ps.remove(given)
        for given in itertools.chain.from_iterable(SHAMANS[shaman].values()):
            if given in ps:
                ps.remove(given)
        for totem, count in TOTEMS[shaman].items():
            mustgive = count - len(SHAMANS[shaman][totem])
            for i in range(mustgive):
                if ps:
                    target = random.choice(ps)
                    ps.remove(target)
                    dispatcher = MessageDispatcher(shaman, users.Bot)
                    given = give_totem(var, dispatcher, target, totem, key="shaman_success_random_known", role="wolf shaman")
                    if given:
                        send_wolfchat_message(var, shaman, messages["shaman_wolfchat"].format(shaman, target), ("wolf shaman",), role="wolf shaman", command="totem")
                        SHAMANS[shaman][totem].append(given[0])

@event_listener("send_role")
def on_transition_night_end(evt: Event, var: GameState):
    chances = var.current_mode.TOTEM_CHANCES
    max_totems = sum(x["wolf shaman"] for x in chances.values())
    ps = get_players(var)
    shamans = get_all_players(var, ("wolf shaman",))
    for s in list(LASTGIVEN):
        if s not in shamans:
            del LASTGIVEN[s]

    shamans = list(shamans)
    random.shuffle(shamans)
    for shaman in shamans:
        if var.next_phase != "night":
            shaman.send(messages["shaman_notify"].format("wolf shaman"))
            continue
        pl = ps[:]
        random.shuffle(pl)
        for given in itertools.chain.from_iterable(LASTGIVEN[shaman].values()):
            if given in pl:
                pl.remove(given)

        event = Event("num_totems", {"num": var.current_mode.NUM_TOTEMS["wolf shaman"]})
        event.dispatch(var, shaman, "wolf shaman")
        num_totems = event.data["num"]

        totems = {}
        for i in range(num_totems):
            target = 0
            rand = random.random() * max_totems
            for t in chances:
                target += chances[t]["wolf shaman"]
                if rand <= target:
                    if t in totems:
                        totems[t] += 1
                    else:
                        totems[t] = 1
                    break
        event = Event("totem_assignment", {"totems": totems})
        event.dispatch(var, shaman, "wolf shaman")
        TOTEMS[shaman] = event.data["totems"]

        num_totems = sum(TOTEMS[shaman].values())
        if num_totems > 1:
            shaman.send(messages["shaman_notify_multiple_known"].format("wolf shaman"))
        else:
            shaman.send(messages["shaman_notify"].format("wolf shaman"))
        tmsg = totem_message(TOTEMS[shaman])
        for totem in TOTEMS[shaman]:
            tmsg += " " + messages[totem + "_totem"]
        shaman.send(tmsg)
        # player list and notification that WS can kill is handled by shared wolves handler

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["wolf shaman"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Village Objective", "Wolf Objective"}

@event_listener("default_totems")
def set_wolf_totems(evt: Event, chances: dict[str, dict[str, int]]):
    chances["protection"]   ["wolf shaman"] = 1
    chances["silence"]      ["wolf shaman"] = 1
    chances["impatience"]   ["wolf shaman"] = 1
    chances["pacifism"]     ["wolf shaman"] = 1
    chances["lycanthropy"]  ["wolf shaman"] = 1
    chances["luck"]         ["wolf shaman"] = 1
    chances["retribution"]  ["wolf shaman"] = 1
    chances["misdirection"] ["wolf shaman"] = 1
    chances["deceit"]       ["wolf shaman"] = 1

# ensure the wolf shaman notify plays before overall wolf notify
_l = find_listener("send_role", "wolves.<wolf shaman>.on_send_role")
_l.remove("send_role")
_l.install("send_role")
del _l
