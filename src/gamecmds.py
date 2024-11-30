from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional
import time
import sys
import re

from src.decorators import command
from src.containers import UserDict
from src.functions import get_players, get_main_role
from src.messages import messages
from src.events import Event, EventListener, event_listener
from src.cats import Wolfteam, Neutral, role_order, Vampire_Team
from src import config, users, channels, pregame, trans
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState
from src.users import User

LAST_STATS: Optional[datetime] = None
LAST_TIME: Optional[datetime] = None
LAST_ADMINS: Optional[datetime] = None
LAST_GOAT: UserDict[User, datetime] = UserDict()

ADMIN_PINGING: bool = False

@command("stats", pm=True, phases=("join", "day", "night"))
def stats(wrapper: MessageDispatcher, message: str):
    """Displays the player statistics."""
    global LAST_STATS
    var = wrapper.game_state
    pl = get_players(var)

    if wrapper.public and (wrapper.source in pl or var.current_phase == "join"):
        # only do this rate-limiting stuff if the person is in game
        if LAST_STATS and LAST_STATS + timedelta(seconds=config.Main.get("ratelimits.stats")) > datetime.now():
            wrapper.pm(messages["command_ratelimited"])
            return

        LAST_STATS = datetime.now()

    try:
        player_role = get_main_role(var, wrapper.source)
    except ValueError:
        player_role = None
    if wrapper.private and var.in_game and player_role in Wolfteam and "src.roles.helper.wolves" in sys.modules:
        from src.roles.helper.wolves import get_wolflist
        msg = messages["players_list_count"].format(
            len(pl), get_wolflist(var, wrapper.source, shuffle=False, remove_player=False))
    elif wrapper.private and var.in_game and player_role in Vampire_Team and "src.roles.vampire" in sys.modules:
        from src.roles.vampire import get_vampire_list
        msg = messages["players_list_count"].format(
            len(pl), get_vampire_list(var, wrapper.source, shuffle=False, remove_player=False))
    else:
        msg = messages["players_list_count"].format(len(pl), pl)

    wrapper.reply(msg)

    if var.current_phase == "join" or var.stats_type == "disabled":
        return

    entries = []
    first_count = 0

    start_roles = set(var.original_main_roles.values())
    for roleset, amount in var.current_mode.ACTIVE_ROLE_SETS.items():
        if amount == 0:
            continue
        for role, count in var.current_mode.ROLE_SETS[roleset].items():
            if count == 0:
                continue
            start_roles.add(role)

    # Uses events in order to enable roles to modify logic
    # The events are fired off as part of transition_day and del_player, and are not calculated here
    if var.stats_type == "default":
        # Collapse the role stats into a dict[str, tuple[int, int]]
        role_stats: dict[str, tuple[int, int]] = {}
        for stat_set in var.get_role_stats():
            for r, a in stat_set:
                if r not in role_stats:
                    role_stats[r] = (a, a)
                else:
                    mn, mx = role_stats[r]
                    role_stats[r] = (min(mn, a), max(mx, a))
        # remove any 0/0 entries if they weren't starting roles, otherwise we may have bad grammar in !stats
        role_stats = {r: v for r, v in role_stats.items() if r in start_roles or v != (0, 0)}
        order = [r for r in role_order() if r in role_stats]
        if var.default_role in order:
            order.remove(var.default_role)
            order.append(var.default_role)
        first = role_stats[order[0]]
        if first[0] == first[1] == 1:
            first_count = 1

        for role in order:
            if role in var.current_mode.SECONDARY_ROLES:
                continue
            count = role_stats.get(role, (0, 0))
            if count[0] == count[1]:
                if count[0] == 0:
                    if role not in start_roles:
                        continue
                    entries.append(messages["stats_reply_entry_none"].format(role))
                else:
                    entries.append(messages["stats_reply_entry_single"].format(role, count[0]))
            else:
                entries.append(messages["stats_reply_entry_range"].format(role, count[0], count[1]))

    # Show everything as-is, with no hidden information
    elif var.stats_type == "accurate":
        l1 = [k for k in var.roles if var.roles[k]]
        l2 = [k for k in var.original_roles if var.original_roles[k]]
        rs = set(l1+l2)
        rs = [role for role in role_order() if role in rs]

        # picky ordering: villager always last
        if var.default_role in rs:
            rs.remove(var.default_role)
        rs.append(var.default_role)

        for role in rs:
            count = len(var.roles[role])
            # only show actual roles
            if role in var.current_mode.SECONDARY_ROLES:
                continue

            if role == rs[0]:
                if count == 1:
                    first_count = 1

            if count == 0:
                if role not in start_roles:
                    continue
                entries.append(messages["stats_reply_entry_none"].format(role))
            else:
                entries.append(messages["stats_reply_entry_single"].format(role, count))

    # Only show team affiliation, this may be different than what mystics
    # and wolf mystics are told since neutrals are split off. Determination
    # of what numbers are shown is the same as summing up counts in "accurate"
    # as accurate, this contains no hidden information
    elif var.stats_type == "team":
        wolfteam = 0
        villagers = 0
        neutral = 0

        for role, players in var.roles.items():
            if role in var.current_mode.SECONDARY_ROLES:
                continue
            if role in Wolfteam:
                wolfteam += len(players)
            elif role in Neutral:
                neutral += len(players)
            else:
                villagers += len(players)

        if wolfteam == 1:
            first_count = 1

        if wolfteam == 0:
            entries.append(messages["stats_reply_entry_none"].format("wolfteam player"))
        else:
            entries.append(messages["stats_reply_entry_single"].format("wolfteam player", wolfteam))

        if villagers == 0:
            entries.append(messages["stats_reply_entry_none"].format("village member"))
        else:
            entries.append(messages["stats_reply_entry_single"].format("village member", villagers))

        if neutral == 0:
            entries.append(messages["stats_reply_entry_none"].format("neutral player"))
        else:
            entries.append(messages["stats_reply_entry_single"].format("neutral player", neutral))

    wrapper.reply(messages["stats_reply"].format(var.current_phase, first_count, entries))

@event_listener("reconfigure_stats")
def on_reconfigure_stats(evt: Event, var: GameState, roleset: Counter, reason: str):
    global LAST_STATS
    LAST_STATS = None

@command("time", pm=True, phases=("join", "day", "night"))
def timeleft(wrapper: MessageDispatcher, message: str):
    """Returns the time left until the next day/night transition."""
    global LAST_TIME
    var = wrapper.game_state

    if wrapper.public:
        if LAST_TIME and LAST_TIME + timedelta(seconds=config.Main.get("ratelimits.time")) > datetime.now():
            wrapper.pm(messages["command_ratelimited"].format())
            return

        LAST_TIME = datetime.now()

    if var.current_phase == "join":
        dur = int((pregame.CAN_START_TIME - datetime.now()).total_seconds())
        msg = None
        if dur > 0:
            msg = messages["start_timer"].format(dur)

        if msg is not None:
            wrapper.reply(msg)

    if var.current_phase in trans.TIMERS or f"{var.current_phase}_limit" in trans.TIMERS:
        if var.current_phase == "day":
            what = "sunset" # FIXME: hardcoded english
            name = "day_limit"
        elif var.current_phase == "night":
            what = "sunrise"
            name = "night_limit"
        elif var.current_phase == "join":
            what = "the game is canceled if it's not started"
            name = "join"
        else:
            what = "the end of the phase"
            name = var.current_phase if var.current_phase in trans.TIMERS else f"{var.current_phase}_limit"

        remaining = int((trans.TIMERS[name][1] + trans.TIMERS[name][2]) - time.time())
        msg = "There is \u0002{0[0]:0>2}:{0[1]:0>2}\u0002 remaining until {1}.".format(divmod(remaining, 60), what)
    else:
        msg = messages["timers_disabled"].format(var.current_phase.capitalize())

    wrapper.reply(msg)

@command("admins", pm=True)
def show_admins(wrapper: MessageDispatcher, message: str):
    """Pings the admins that are available."""
    global LAST_ADMINS, ADMIN_PINGING
    var = wrapper.game_state
    admins = []

    if wrapper.public:
        if LAST_ADMINS and LAST_ADMINS + timedelta(seconds=config.Main.get("ratelimits.admins")) > datetime.now():
            wrapper.pm(messages["command_ratelimited"])
            return

        LAST_ADMINS = datetime.now()

    if ADMIN_PINGING:
        return

    ADMIN_PINGING = True

    def admin_whoreply(event, chan, user):
        if not ADMIN_PINGING or chan is not channels.Main:
            return

        if user.is_admin() and user is not users.Bot and not event.params.away:
            admins.append(user)

    def admin_endwho(event, target):
        global ADMIN_PINGING
        if not ADMIN_PINGING or target is not channels.Main:
            return

        who_result.remove("who_result")
        who_end.remove("who_end")
        admins.sort(key=lambda x: x.nick)
        wrapper.reply(messages["available_admins"].format(admins))
        ADMIN_PINGING = False

    who_result = EventListener(admin_whoreply)
    who_result.install("who_result")
    who_end = EventListener(admin_endwho)
    who_end.install("who_end")

    channels.Main.who()

@command("goat")
def goat(wrapper: MessageDispatcher, message: str):
    """Use a goat to interact with anyone in the channel during the day."""
    var = wrapper.game_state

    if wrapper.source in LAST_GOAT and LAST_GOAT[wrapper.source] + timedelta(seconds=config.Main.get("ratelimits.goat")) > datetime.now():
        wrapper.pm(messages["command_ratelimited"])
        return
    target = re.split(" +", message)[0]
    if not target:
        wrapper.pm(messages["not_enough_parameters"])
        return
    victim = users.complete_match(users.lower(target), wrapper.target.users)
    if not victim:
        wrapper.pm(messages["goat_target_not_in_channel"].format(target))
        return

    LAST_GOAT[wrapper.source] = datetime.now()
    wrapper.send(messages["goat_success"].format(wrapper.source, victim.get()))

@command("fgoat", flag="j")
def fgoat(wrapper: MessageDispatcher, message: str):
    """Forces a goat to interact with anyone or anything, without limitations."""

    nick = message.split(' ')[0].strip()
    victim = users.complete_match(users.lower(nick), wrapper.target.users)
    if victim:
        togoat = victim.get()
    else:
        togoat = message

    wrapper.send(messages["goat_success"].format(wrapper.source, togoat))

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    LAST_GOAT.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    global LAST_STATS, LAST_TIME
    LAST_STATS = None
    LAST_TIME = None
    LAST_GOAT.clear()
