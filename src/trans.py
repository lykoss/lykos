from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional, Callable, Union
import threading
import time

from src.transport.irc import get_ircd
from src.decorators import command, handle_error
from src.containers import UserSet, UserDict, UserList
from src.functions import get_players, get_main_role, get_reveal_role
from src.locations import Location, VillageSquare, get_players_in_location, move_player, move_player_home
from src.warnings import expire_tempbans
from src.messages import messages
from src.status import is_silent, is_dying, try_protection, add_dying, kill_players, get_absent, try_lycanthropy
from src.users import User
from src.events import Event, event_listener
from src.votes import chk_decision
from src.cats import Win_Stealer, Wolf_Objective, Vampire_Objective, Village_Objective, role_order, get_team, All, \
    Category, Nobody
from src import channels, users, locks, config, db, reaper, relay
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState, PregameState
from src.random import random

# some type aliases to make things clearer later
UserOrLocation = Union[User, Location]
UserOrSpecialTag = Union[User, str]

NIGHT_IDLE_EXEMPT = UserSet()
TIMERS: dict[str, tuple[threading.Timer, float | int, int]] = {}

DAY_ID: float | int = 0
DAY_TIMEDELTA: timedelta = timedelta(0)
DAY_START_TIME: Optional[datetime] = None

NIGHT_ID: float | int = 0
NIGHT_TIMEDELTA: timedelta = timedelta(0)
NIGHT_START_TIME: Optional[datetime] = None

ENDGAME_COMMAND: Optional[Callable] = None
ADMIN_STOPPED = UserList() # this shouldn't hold more than one user at any point, but we need to keep track of it

ORIGINAL_ACCOUNTS: UserDict[User, str] = UserDict()

@handle_error
def hurry_up(timer_type: str, var: GameState, phase_id: float, *, admin_forced: bool = False):
    global DAY_ID
    if var.current_phase != "day" or var.in_phase_transition:
        return
    if phase_id and phase_id != DAY_ID:
        return

    if timer_type == "warn":
        event = Event("daylight_warning", {"message": "daylight_warning"})
        event.dispatch(var)
        channels.Main.send(messages[event.data["message"]])
        return

    DAY_ID = 0
    chk_decision(var, timeout=True, admin_forced=admin_forced)

@command("fnight", flag="N")
def fnight(wrapper: MessageDispatcher, message: str):
    """Force the day to end and night to begin."""
    if wrapper.game_state.current_phase != "day":
        wrapper.pm(messages["not_daytime"])
    else:
        hurry_up("limit", wrapper.game_state, 0, admin_forced=True)

@command("fday", flag="N")
def fday(wrapper: MessageDispatcher, message: str):
    """Force the night to end and the next day to begin."""
    if wrapper.game_state.current_phase != "night":
        wrapper.pm(messages["not_nighttime"])
    else:
        transition_day(wrapper.game_state)

def begin_day(var: GameState):
    global DAY_ID
    DAY_ID = time.time()
    pl = get_players(var)
    msg = messages["villagers_vote"].format(len(pl) // 2 + 1)
    channels.Main.send(msg)

    if config.Main.get("timers.shortday.enabled") and len(pl) <= config.Main.get("timers.shortday.players"):
        warn = var.short_day_time_warn
        limit = var.short_day_time_limit
    elif config.Main.get("timers.day.enabled"):
        warn = var.day_time_warn
        limit = var.day_time_limit
    else:
        warn = 0
        limit = 0

    var.end_phase_transition(limit, warn, hurry_up, (var, DAY_ID))

    if not config.Main.get("gameplay.nightchat"):
        modes = []
        for player in pl:
            if not player.is_fake:
                modes.append(("+v", player.nick))
        channels.Main.mode(*modes)

    # move everyone to the village square (or home if they're absent)
    absent = get_absent(var)
    for p in pl:
        if p in absent:
            move_player_home(var, p)
        else:
            move_player(var, p, VillageSquare)

    event = Event("begin_day", {})
    event.dispatch(var)
    # induce a vote if we need to (due to lots of pacifism/impatience totems or whatever)
    chk_decision(var)

def _night_warn(var: GameState):
    channels.Main.send(messages["twilight_warning"])

    # determine who hasn't acted yet and remind them to act
    event = Event("chk_nightdone", {"acted": [], "nightroles": [], "transition_day": transition_day})
    event.dispatch(var)

    # remove all instances of them if they are silenced (makes implementing the event easier)
    nightroles: list[User] = [p for p in event.data["nightroles"] if not is_silent(var, p)]
    idling = Counter(nightroles) - Counter(event.data["acted"])
    if not idling:
        return
    for player, count in idling.items():
        if player.is_fake or count == 0:
            continue
        idle_event = Event("night_idled", {})
        if idle_event.dispatch(var, player):
            player.queue_message(messages["night_idle_notice"])
    users.User.send_messages()

@handle_error
def night_timeout(timer_type: str, var: GameState, phase_id: int):
    if phase_id != NIGHT_ID or var.current_phase != "night" or var.in_phase_transition:
        return

    if timer_type == "warn":
        _night_warn(var)
        return

    # determine which roles idled out night and give them warnings
    event = Event("chk_nightdone", {"acted": [], "nightroles": [], "transition_day": transition_day})
    event.dispatch(var)

    # if night idle warnings are disabled, head straight to day
    if not config.Main.get("reaper.night_idle.enabled"):
        event.data["transition_day"](var)
        return

    # remove all instances of them if they are silenced (makes implementing the event easier)
    nightroles: list[User] = [p for p in event.data["nightroles"] if not is_silent(var, p)]
    idled = Counter(nightroles) - Counter(event.data["acted"])
    for player, count in idled.items():
        if player.is_fake or count == 0:
            continue
        # some circumstances may excuse a player from getting an idle warning
        # for example, if time lord is active or they have a nightmare in sleepy
        # these can block the player from getting a warning by setting prevent_default
        idle_event = Event("night_idled", {})
        if idle_event.dispatch(var, player):
            # don't give the warning right away:
            # 1. they may idle out entirely, in which case that replaces this warning
            # 2. warning is deferred to end of game so admins can't !fwarn list to cheat and determine who idled
            reaper.NIGHT_IDLED.add(player)

    event.data["transition_day"](var)

@event_listener("night_idled")
def on_night_idled(evt: Event, var: GameState, player):
    if player in NIGHT_IDLE_EXEMPT:
        evt.prevent_default = True

@handle_error
def transition_day(var: GameState, game_id: int = 0):
    global DAY_START_TIME, NIGHT_ID, NIGHT_TIMEDELTA, NIGHT_START_TIME
    if game_id and game_id != NIGHT_ID:
        return

    NIGHT_ID = 0

    if var.current_phase == "day":
        return

    var.begin_phase_transition("day")
    # var.day_count gets increased by 1 in begin_phase_transition
    DAY_START_TIME = datetime.now()

    event_begin = Event("transition_day_begin", {})
    event_begin.dispatch(var)

    if var.start_with_day and var.day_count == 1:
        begin_day(var)
        return

    assert isinstance(DAY_START_TIME, datetime) and isinstance(NIGHT_START_TIME, datetime)
    td = DAY_START_TIME - NIGHT_START_TIME
    NIGHT_START_TIME = None
    NIGHT_TIMEDELTA += td
    minimum, sec = td.seconds // 60, td.seconds % 60

    # Mark people who are dying as a direct result of night actions (i.e. not chained deaths)
    # We set the variables here first; listeners should mutate, not replace
    # We don't need to use User containers here, as these don't persist long enough
    # Kill priorities are used to determine which kill takes precedence over another; default priority is 0,
    # negative numbers make those kills take precedence, and positive numbers make those kills defer to others.
    # In default logic, wolf-aligned VG is priority -5, wolf kills (including harlot visiting wolf) are priority +5,
    # GA/bodyguard guarding a wolf is +10, suicides are +15, and everything else is 0.
    # Ties in priority are resolved randomly
    victims: set[UserOrLocation] = set()
    killers: dict[UserOrLocation, list[UserOrSpecialTag]] = defaultdict(list)
    kill_priorities: dict[UserOrSpecialTag, int] = defaultdict(int)
    message: dict[UserOrSpecialTag, list[str]] = defaultdict(list)
    message["*"].append(messages["sunrise"].format(minimum, sec))
    dead: set[User] = set()
    novictmsg = True
    howl_count = 0

    evt = Event("night_kills", {
        "victims": victims,
        "killers": killers,
        "kill_priorities": kill_priorities
        })
    evt.dispatch(var)

    # expand locations to encompass everyone at that location
    for v in set(victims):
        if isinstance(v, Location):
            pl = get_players_in_location(var, v)
            # Play the "target not home" message if the wolves attacked an empty location
            # This also suppresses the "no victims" message if nobody ends up dying tonight
            if not pl and "@wolves" in killers[v]:
                message["*"].append(messages["target_not_home"])
                novictmsg = False
            for p in pl:
                victims.add(p)
                killers[p].extend(killers[v])
            victims.remove(v)
            del killers[v]

    # sort the killers dict by kill priority, adding random jitter to break ties
    get_kill_priority = lambda x: kill_priorities[x] + random.random()
    killers = {u: sorted(kl, key=get_kill_priority) for u, kl in killers.items()}

    # save a copy of roles so we can credit kills to the roles the players were at night,
    # before any roleswaps due to night kills (e.g. lycanthropy)
    rolemap = {role: set(players) for role, players in var.roles.items()}
    mainroles = dict(var.main_roles)

    for victim in victims:
        if not is_dying(var, victim):
            for killer in list(killers[victim]):
                kdata = {
                    "attacker": None,
                    "role": None,
                    "try_protection": True,
                    "protection_reason": "night_death",
                    "try_lycanthropy": False
                }
                if killer == "@wolves":
                    kdata["role"] = "wolf"
                    kdata["try_lycanthropy"] = True
                elif isinstance(killer, str):
                    kevt = Event("resolve_killer_tag", kdata)
                    kevt.dispatch(var, victim, killer)
                    assert kdata["role"] is not None
                else:
                    kdata["attacker"] = killer
                    kdata["role"] = get_main_role(var, killer, mainroles=mainroles)
                protected = None
                if kdata["try_protection"]:
                    protected = try_protection(var, victim, kdata["attacker"], kdata["role"], reason=kdata["protection_reason"])
                if protected is not None:
                    message[victim].extend(protected)
                    killers[victim].remove(killer)
                    # if there's no particular protection message (e.g. blessed), then we still want no victims message to play
                    if protected:
                        novictmsg = False
                elif kdata["try_lycanthropy"] and try_lycanthropy(var, victim):
                    howl_count += 1
                    novictmsg = False
                    killers[victim].remove(killer)

            if not killers[victim]:
                continue

        dead.add(victim)

    # Delay messaging until all protections and lycanthropy has been processed for every victim
    for victim in dead:
        mevt = Event("night_death_message", {
            "key": "death" if var.role_reveal in ("on", "team") else "death_no_reveal",
            "args": [victim, get_reveal_role(var, victim)]
        }, rolemap=rolemap, mainroles=mainroles)
        if mevt.dispatch(var, victim, killers[victim][0]):
            message[victim].append(messages[mevt.data["key"]].format(*mevt.data["args"]))

    # Offer a chance for game modes and roles to inspect the fully-resolved state and act upon it.
    # The victims, dead, and killers collections should not be mutated in this event, use earlier events
    # to manipulate these (such as night_kills and by adding protections), or later events (del_player) in the case
    # of chained deaths.
    evt = Event("transition_day_resolve", {
        "message": message,
        "novictmsg": novictmsg,
        "howl": howl_count,
        }, victims=victims, rolemap=rolemap, mainroles=mainroles)
    evt.dispatch(var, dead, {v: k[0] for v, k in killers.items() if v in dead})

    # handle howls and novictmsg
    if evt.data["novictmsg"] and len(dead) == 0:
        message["*"].append(messages["no_victims"] + messages["no_victims_append"])
    for i in range(evt.data["howl"]):
        message["*"].append(messages["new_wolf"])

    # flatten message, * goes first then everyone else
    to_send = message["*"]
    del message["*"]
    for msg in message.values():
        to_send.extend(msg)

    channels.Main.send(*to_send, sep="\n")

    # chilling howl message was played, give roles the opportunity to update !stats
    # to account for this
    revt = Event("reconfigure_stats", {"new": []})
    for i in range(evt.data["howl"]):
        newstats = set()
        for rs in var.get_role_stats():
            d = Counter(dict(rs))
            revt.data["new"] = [d]
            revt.dispatch(var, d, "howl")
            for new_set in revt.data["new"]: # type: Counter[str]
                if min(new_set.values()) >= 0:
                    newstats.add(frozenset(new_set.items()))
        var.set_role_stats(newstats)

    killer_role = {}
    for deadperson in dead:
        if is_dying(var, deadperson):
            continue

        killer = killers[deadperson][0]
        if killer == "@wolves":
            killer = None
            killer_role[deadperson] = "wolf"
        elif isinstance(killer, str):
            kevt = Event("resolve_killer_tag", {
                "attacker": None,
                "role": None,
                "try_protection": True,
                "protection_reason": "night_death",
                "try_lycanthropy": False
            })
            kevt.dispatch(var, deadperson, killer)
            assert kevt.data["role"] is not None
            killer = kevt.data["attacker"]
            killer_role[deadperson] = kevt.data["role"]
        else:
            killer_role[deadperson] = get_main_role(var, killer)

        add_dying(var, deadperson, killer_role[deadperson], "night_kill", killer=killer)

    kill_players(var, end_game=False) # temporary hack; end_game=False also prevents kill_players from attempting phase transitions

    event_end = Event("transition_day_end", {"begin_day": begin_day})
    event_end.dispatch(var)

    # make sure that we process ALL of the transition_day events before checking for game end
    if chk_win(var): # game ending
        return

    event_end.data["begin_day"](var)

@handle_error
def transition_night(var: GameState):
    if var.current_phase == "night":
        return
    global NIGHT_ID, NIGHT_START_TIME, DAY_START_TIME, DAY_TIMEDELTA
    var.begin_phase_transition("night")
    # var.night_count gets increased by 1 in begin_phase_transition

    NIGHT_START_TIME = datetime.now()

    # move everyone back to their house
    pl = get_players(var)
    for p in pl:
        move_player_home(var, p)

    event_begin = Event("transition_night_begin", {})
    event_begin.dispatch(var)

    # game ended from bitten / amnesiac turning, narcolepsy totem expiring, or other weirdness
    if chk_win(var):
        return

    if not config.Main.get("gameplay.nightchat"):
        modes = []
        for player in get_players(var):
            if not player.is_fake:
                modes.append(("-v", player))
        channels.Main.mode(*modes)

    dmsg = []

    NIGHT_ID = time.time()
    if NIGHT_TIMEDELTA or var.start_with_day:  # transition from day
        assert isinstance(DAY_START_TIME, datetime) and isinstance(NIGHT_START_TIME, datetime)
        td = NIGHT_START_TIME - DAY_START_TIME
        DAY_START_TIME = None
        DAY_TIMEDELTA += td
        min, sec = td.seconds // 60, td.seconds % 60
        dmsg.append(messages["day_lasted"].format(min, sec))

    event_role = Event("send_role", {})
    event_role.dispatch(var)

    event_end = Event("transition_night_end", {})
    event_end.dispatch(var)

    dmsg.append(messages["night_begin"])

    if var.night_count:
        dmsg.append(messages["first_night_begin"])
    channels.Main.send(*dmsg, sep=" ")

    # it's now officially nighttime
    if config.Main.get("timers.night.enabled"):
        warn = var.night_time_warn
        limit = var.night_time_limit
    else:
        warn = 0
        limit = 0

    var.end_phase_transition(limit, warn, night_timeout, (var, NIGHT_ID))

    event_night = Event("begin_night", {"messages": []})
    event_night.dispatch(var)
    channels.Main.send(*event_night.data["messages"])

    # If there are no nightroles that can act, immediately turn it to daytime
    chk_nightdone(var)

def chk_nightdone(var: GameState):
    if var.current_phase != "night":
        return

    event = Event("chk_nightdone", {"acted": [], "nightroles": [], "transition_day": transition_day})
    event.dispatch(var)
    actedcount = len(event.data["acted"])

    # remove all instances of them if they are silenced (makes implementing the event easier)
    nightroles = [p for p in event.data["nightroles"] if not is_silent(var, p)]

    if var.current_phase == "night" and actedcount >= len(nightroles):
        event.data["transition_day"](var)

def stop_game(var: Optional[GameState | PregameState], winner: Category = Nobody, abort=False, additional_winners=None, log=True):
    global DAY_TIMEDELTA, NIGHT_TIMEDELTA, ENDGAME_COMMAND
    if abort:
        channels.Main.send(messages["role_attribution_failed"])
    elif var is None: # game already ended
        return
    if DAY_START_TIME:
        now = datetime.now()
        td = now - DAY_START_TIME
        DAY_TIMEDELTA += td
    if NIGHT_START_TIME:
        now = datetime.now()
        td = now - NIGHT_START_TIME
        NIGHT_TIMEDELTA += td

    daymin, daysec = DAY_TIMEDELTA.seconds // 60, DAY_TIMEDELTA.seconds % 60
    nitemin, nitesec = NIGHT_TIMEDELTA.seconds // 60, NIGHT_TIMEDELTA.seconds % 60
    total: timedelta = DAY_TIMEDELTA + NIGHT_TIMEDELTA
    tmin, tsec = total.seconds // 60, total.seconds % 60
    gameend_msg = messages["endgame_stats"].format(tmin, tsec, daymin, daysec, nitemin, nitesec)

    # we previously took in strings and things will break with weird errors if we're still passed a string
    # this should catch that earlier and provide a more useful error message
    assert isinstance(winner, Category)

    if not abort and var.in_game:
        assert isinstance(var, GameState)
        channels.Main.send(gameend_msg)

        roles_msg = []

        rolemap = var.original_roles # this returns a different dict than the underlying value, so it's fine to modify
        mainroles = var.original_main_roles
        orig_main = {} # if get_final_role changes mainroles, we want to stash original main role

        for player, role in mainroles.items():
            evt = Event("get_final_role", {"role": var.final_roles.get(player, role)})
            evt.dispatch(var, player, role)
            if role != evt.data["role"]:
                rolemap[role].remove(player)
                rolemap[evt.data["role"]].add(player)
                mainroles[player] = evt.data["role"]
                orig_main[player] = role

        # track if we already printed "was" for a role swap, e.g. The wolves were A (was seer), B (harlot)
        # so that we can make the message a bit more concise
        roleswap_key = "endgame_roleswap_long"

        for role in role_order():
            numrole = len(rolemap[role])
            if numrole == 0:
                continue
            msg = []
            for player in rolemap[role]:
                # check if the player changed roles during game, and if so insert the "was X" message
                player_msg = []
                if mainroles[player] == role and player in orig_main:
                    player_msg.append(messages[roleswap_key].format(orig_main[player]))
                    roleswap_key = "endgame_roleswap_short"
                evt = Event("get_endgame_message", {"message": player_msg})
                evt.dispatch(var, player, role, is_main_role=mainroles[player] == role)
                key = "endgame_role_player_short"
                if player_msg:
                    key = "endgame_role_player_long"
                msg.append(messages[key].format(player, player_msg))

            roles_msg.append(messages["endgame_role_msg"].format(role, msg))

        evt = Event("game_end_messages", {"messages": roles_msg})
        evt.dispatch(var)

        channels.Main.send(*roles_msg)

        # map player: all roles of that player (for below)
        allroles = {player: frozenset({role for role, players in rolemap.items() if player in players}) for player in mainroles}

        # "" indicates everyone died or abnormal game stop
        winners = set()
        player_list = []

        if log:
            is_win_stealer = bool(winner & Win_Stealer)
            if additional_winners is not None:
                winners.update(additional_winners)

            team_wins = set()
            for player, role in mainroles.items():
                if player in reaper.DCED_LOSERS:
                    continue
                # determine default team win
                won = role in winner

                # Let events modify this as necessary.
                # Neutral roles will need to listen in on this to determine team wins
                event = Event("team_win", {"team_win": won}, is_win_stealer=is_win_stealer)
                event.dispatch(var, player, role, allroles[player], winner)
                if event.data["team_win"]:
                    team_wins.add(player)

            # Once *all* team wins are settled, we can determine individual wins and get the final list of winners
            team_wins = frozenset(team_wins)
            for player, role in mainroles.items():
                entry = {"version": 4,
                         "account": player.account,
                         "main_role": role,
                         "all_roles": list(allroles[player]),
                         "special": [],
                         "team_win": player in team_wins,
                         "individual_win": False,
                         "count_game": True,
                         "dced": player in reaper.DCED_LOSERS
                         }
                # player.account could be None if they disconnected during the game. Use original tracked account name
                if entry["account"] is None and player in ORIGINAL_ACCOUNTS:
                    entry["account"] = ORIGINAL_ACCOUNTS[player]

                survived = player in get_players(var)
                if not entry["dced"]:
                    # by default, get an individual win if the team won and they survived
                    won = entry["team_win"] and survived

                    # let events modify this default and also add special tags/pseudo-roles to the stats
                    event = Event("player_win", {"individual_win": won, "special": [], "count_game": True},
                                  team_wins=team_wins, is_win_stealer=is_win_stealer)
                    event.dispatch(var, player, role, allroles[player], winner, entry["team_win"], survived)
                    won = event.data["individual_win"]
                    # count the game towards stats if the player_win event tells us to or if the player dced
                    # (so dc'ed players take a game stats penalty even if they're a role that normally doesn't count)
                    entry["count_game"] = event.data["count_game"] or entry["dced"]
                    # ensure that it is a) a list, and b) a copy (so it can't be mutated out from under us later)
                    entry["special"] = list(event.data["special"])

                    # special-case everyone for after the event
                    if winner is All:
                        won = True

                    entry["individual_win"] = won

                if entry["team_win"] or entry["individual_win"]:
                    winners.add(player)

                if not player.is_fake:
                    # don't record fakes to the database
                    player_list.append(entry)

            from src.status.dying import DEAD
            game_options = {"role reveal": var.role_reveal,
                            "stats": var.stats_type,
                            "abstain": "on" if var.abstain_enabled and not var.limit_abstain else "restricted" if var.abstain_enabled else "off",
                            "roles": {}}
            for role, pl in var.original_roles.items():
                if len(pl) > 0:
                    game_options["roles"][role] = len(pl)

            db.add_game(var.current_mode.name,
                        len(get_players(var)) + len(DEAD),
                        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(var.game_id)),
                        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                        winner,
                        player_list,
                        game_options)

            # spit out the list of winners
            if winners:
                sorted_winners = sorted(winners, key=lambda u: u.nick)
                channels.Main.send(messages["winners"].format(sorted_winners))
            else:
                channels.Main.send(messages["no_winners"])

    # Message players in deadchat letting them know that the game has ended
    for user in relay.DEADCHAT_PLAYERS:
        user.queue_message(messages["endgame_deadchat"].format(channels.Main))

    User.send_messages()

    reset(var)
    expire_tempbans()

    # This must be after reset()
    if ENDGAME_COMMAND is not None:
        ENDGAME_COMMAND()
        ENDGAME_COMMAND = None
    if ADMIN_STOPPED: # It was an flastgame
        channels.Main.send(messages["fstop_ping"].format(ADMIN_STOPPED))
        ADMIN_STOPPED.clear()

def chk_win(var: GameState, *, end_game=True, winner=None, count_absent=True):
    """ Returns True if someone won """
    global ENDGAME_COMMAND
    lpl = len(get_players(var))

    if var.current_phase == "join":
        if not lpl:
            reset(var)

            # This must be after reset()
            if ENDGAME_COMMAND is not None:
                ENDGAME_COMMAND()
                ENDGAME_COMMAND = None
            if ADMIN_STOPPED:  # It was an flastgame
                channels.Main.send(messages["fstop_ping"].format(ADMIN_STOPPED))
                ADMIN_STOPPED.clear()

            return True
        return False
    if var.setup_completed and not var.in_game:
        return False # some other thread already ended game probably

    return chk_win_conditions(var, var.roles, var.main_roles, end_game, winner, count_absent)

def chk_win_conditions(var: GameState,
                       rolemap: dict[str, set[User]] | UserDict[str, UserSet],
                       mainroles: dict[User, str] | UserDict[User, str],
                       end_game=True,
                       winner=None,
                       count_absent=True):
    """Internal handler for the chk_win function."""
    with locks.reaper:
        if var.current_phase == "day" and count_absent:
            pl = set(get_players(var)) - get_absent(var)
            lpl = len(pl)
        else:
            pl = set(get_players(var, mainroles=mainroles))
            lpl = len(pl)

        wolves = set(get_players(var, Wolf_Objective, mainroles=mainroles))
        vampires = set(get_players(var, Vampire_Objective, mainroles=mainroles))
        num_wolves = len(wolves & pl)
        num_vampires = len(vampires & pl)
        num_real_wolves = len(get_players(var, Village_Objective, mainroles=mainroles))

        message = ""
        if lpl < 1:
            message = messages["no_win"]
            # still want people like jesters, dullahans, etc. to get wins if they fulfilled their win conds
            winner = Nobody

        # TODO: flip priority order (so that things like fool run last, and therefore override previous win conds)
        # Priorities:
        # 0 = fool, other roles that end game immediately
        # 1 = things that could short-circuit game ending, such as cub growing up or traitor turning
        #     Such events should also set stop_processing and prevent_default to True to force a re-calcuation
        # 2 = win stealers not dependent on winners, such as succubus
        # Events in priority 3 and 4 should check if a winner was already set and short-circuit if so
        # it is NOT recommended that events in priorities 0 and 2 set stop_processing to True, as doing so
        # will prevent gamemode-specific win conditions from happening
        # 3 = normal roles
        # 4 = win stealers dependent on who won, such as demoniac and monster
        #     (monster's message changes based on who would have otherwise won)
        # 5 = gamemode-specific win conditions
        event = Event("chk_win", {"winner": winner, "message": message, "additional_winners": None})
        if not event.dispatch(var, rolemap, mainroles, lpl, num_wolves, num_real_wolves, num_vampires):
            return chk_win_conditions(var, rolemap, mainroles, end_game, winner)
        winner = event.data["winner"]
        message = event.data["message"]

        if winner is None:
            return False

        if end_game:
            channels.Main.send(message)
            stop_game(var, winner, additional_winners=event.data["additional_winners"])
        return True

@command("fstop", flag="S", phases=("join", "day", "night"))
def reset_game(wrapper: MessageDispatcher, message: str):
    """Forces the game to stop."""
    wrapper.send(messages["fstop_success"].format(wrapper.source))
    var = wrapper.game_state
    pl = None
    if var.current_phase == "join":
        pl = [p for p in get_players(var) if not p.is_fake]

    stop_game(var, log=False)
    if pl:
        wrapper.send(messages["fstop_ping"].format(pl))

def reset(var: Optional[GameState | PregameState]):
    # Reset game timers
    if var is not None:
        with locks.join_timer: # make sure it isn't being used by the ping join handler
            for timers in TIMERS.values():
                timers[0].cancel()
            TIMERS.clear()

        # Reset modes
        cmodes = []
        for plr in get_players(var):
            if not plr.is_fake:
                cmodes.append(("-v", plr.nick))
        for user, modes in channels.Main.old_modes.items():
            for mode in modes:
                cmodes.append(("+" + mode, user))
        channels.Main.old_modes.clear()
        if config.Main.get("gameplay.quiet_dead_players"):
            ircd = get_ircd()
            if ircd.supports_quiet():
                from src.status.dying import DEAD
                for deadguy in DEAD:
                    if not deadguy.is_fake:
                        cmodes.append((f"-{ircd.quiet_mode}", f"{ircd.quiet_prefix}{deadguy.nick}!*@*"))
        channels.Main.mode("-m", *cmodes)

    evt = Event("reset", {})
    evt.dispatch(var)

    if var:
        var.teardown()

    channels.Main.game_state = None

@event_listener("transition_night_begin")
def on_transition_night_begin(evt: Event, var: GameState):
    NIGHT_IDLE_EXEMPT.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    global DAY_ID, DAY_TIMEDELTA, DAY_START_TIME, NIGHT_ID, NIGHT_TIMEDELTA, NIGHT_START_TIME
    DAY_ID = 0
    DAY_TIMEDELTA = timedelta(0)
    DAY_START_TIME = None
    NIGHT_ID = 0
    NIGHT_TIMEDELTA = timedelta(0)
    NIGHT_START_TIME = None
    NIGHT_IDLE_EXEMPT.clear()
    ORIGINAL_ACCOUNTS.clear()
