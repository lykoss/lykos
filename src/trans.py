from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import TYPE_CHECKING
import threading
import time

from src.decorators import command, handle_error
from src.warnings import add_warning, expire_tempbans
from src.functions import get_players, get_main_role, get_reveal_role
from src.messages import messages
from src.status import is_silent, is_dying, try_protection, add_dying, kill_players, get_absent
from src.events import Event, event_listener
from src.votes import chk_decision
from src.cats import Wolfteam, Hidden, Village, Wolf_Objective, Village_Objective, role_order
from src import channels, users, locks, db

if TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.gamestate import GameState

@handle_error
def hurry_up(gameid, change, *, admin_forced=False):
    if var.PHASE != "day":
        return
    if gameid and gameid != var.DAY_ID:
        return

    if not change:
        event = Event("daylight_warning", {"message": "daylight_warning"})
        event.dispatch(var)
        channels.Main.send(messages[event.data["message"]])
        return

    var.DAY_ID = 0
    chk_decision(var, timeout=True, admin_forced=admin_forced)

@command("fnight", flag="N")
def fnight(wrapper: MessageDispatcher, message: str):
    """Force the day to end and night to begin."""
    if wrapper.game_state.PHASE != "day":
        wrapper.pm(messages["not_daytime"])
    else:
        hurry_up(0, True, admin_forced=True)

@command("fday", flag="N")
def fday(wrapper: MessageDispatcher, message: str):
    """Force the night to end and the next day to begin."""
    if wrapper.game_state.PHASE != "night":
        wrapper.pm(messages["not_nighttime"])
    else:
        transition_day()

def begin_day(var: GameState): # FIXME: Fix call sites
    # Reset nighttime variables
    var.GAMEPHASE = "day"
    var.STARTED_DAY_PLAYERS = len(get_players(var))
    var.LAST_GOAT.clear()
    msg = messages["villagers_lynch"].format(len(get_players(var)) // 2 + 1)
    channels.Main.send(msg)

    var.DAY_ID = time.time()
    if var.DAY_TIME_WARN > 0:
        if var.STARTED_DAY_PLAYERS <= var.SHORT_DAY_PLAYERS:
            t1 = threading.Timer(var.SHORT_DAY_WARN, hurry_up, [var.DAY_ID, False])
            l = var.SHORT_DAY_WARN
        else:
            t1 = threading.Timer(var.DAY_TIME_WARN, hurry_up, [var.DAY_ID, False])
            l = var.DAY_TIME_WARN
        var.TIMERS["day_warn"] = (t1, var.DAY_ID, l)
        t1.daemon = True
        t1.start()

    if var.DAY_TIME_LIMIT > 0:  # Time limit enabled
        if var.STARTED_DAY_PLAYERS <= var.SHORT_DAY_PLAYERS:
            t2 = threading.Timer(var.SHORT_DAY_LIMIT, hurry_up, [var.DAY_ID, True])
            l = var.SHORT_DAY_LIMIT
        else:
            t2 = threading.Timer(var.DAY_TIME_LIMIT, hurry_up, [var.DAY_ID, True])
            l = var.DAY_TIME_LIMIT
        var.TIMERS["day"] = (t2, var.DAY_ID, l)
        t2.daemon = True
        t2.start()

    if var.DEVOICE_DURING_NIGHT:
        modes = []
        for player in get_players(var):
            if not player.is_fake:
                modes.append(("+v", player.nick))
        channels.Main.mode(*modes)

    event = Event("begin_day", {})
    event.dispatch(var)
    # induce a lynch if we need to (due to lots of pacifism/impatience totems or whatever)
    chk_decision(var)

@handle_error
def night_warn(gameid):
    if gameid != var.NIGHT_ID or var.PHASE != "night":
        return

    channels.Main.send(messages["twilight_warning"])

    # determine who hasn't acted yet and remind them to act
    event = Event("chk_nightdone", {"acted": [], "nightroles": [], "transition_day": transition_day})
    event.dispatch(var)

    # remove all instances of them if they are silenced (makes implementing the event easier)
    nightroles = [p for p in event.data["nightroles"] if not is_silent(var, p)]
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
def night_timeout(gameid):
    if gameid != var.NIGHT_ID or var.PHASE != "night":
        return

    # determine which roles idled out night and give them warnings
    event = Event("chk_nightdone", {"acted": [], "nightroles": [], "transition_day": transition_day})
    event.dispatch(var)

    # if night idle warnings are disabled, head straight to day
    if not var.NIGHT_IDLE_PENALTY:
        event.data["transition_day"](gameid)
        return

    # remove all instances of them if they are silenced (makes implementing the event easier)
    nightroles = [p for p in event.data["nightroles"] if not is_silent(var, p)]
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
            var.NIGHT_IDLED.add(player)

    event.data["transition_day"](gameid)

@event_listener("night_idled")
def on_night_idled(evt, var, player):
    if player in var.NIGHT_IDLE_EXEMPT:
        evt.prevent_default = True

@handle_error
def transition_day(var, gameid=0): # FIXME: Fix call sites
    if gameid:
        if gameid != var.NIGHT_ID:
            return
    var.NIGHT_ID = 0

    if var.PHASE not in ("night", "join"):
        return

    var.PHASE = "day"
    var.DAY_COUNT += 1
    var.FIRST_DAY = (var.DAY_COUNT == 1)
    var.DAY_START_TIME = datetime.now()

    event_begin = Event("transition_day_begin", {})
    event_begin.dispatch(var)

    if var.START_WITH_DAY and var.FIRST_DAY:
        # TODO: need to message everyone their roles and give a short thing saying "it's daytime"
        # but this is good enough for now to prevent it from crashing
        begin_day()
        return

    td = var.DAY_START_TIME - var.NIGHT_START_TIME
    var.NIGHT_START_TIME = None
    var.NIGHT_TIMEDELTA += td
    minimum, sec = td.seconds // 60, td.seconds % 60

    # built-in logic runs at the following priorities:
    # 1 = wolf kills
    # 2 = non-wolf kills
    # 3 = fixing killers dict to have correct priority (wolf-side VG kills -> non-wolf kills -> wolf kills)
    # 4 = protections/fallen angel
    #     4.1 = shaman, 4.2 = bodyguard/GA, 4.3 = blessed villager
    # 5 = alpha wolf bite, other custom events that trigger after all protection stuff is resolved
    # 6 = rearranging victim list (ensure bodyguard/harlot messages plays),
    #     fixing killers dict priority again (in case step 4 or 5 added to it)
    # 7 = read-only operations
    # Actually killing off the victims happens in transition_day_resolve
    # We set the variables here first; listeners should mutate, not replace
    # We don't need to use User containers here, as these don't persist long enough
    # This removes the burden of having to clear them at the end or should an error happen
    victims = []
    killers = defaultdict(list)

    evt = Event("transition_day", {
        "victims": victims,
        "killers": killers,
        })
    evt.dispatch(var)

    # remove duplicates
    victims_set = set(victims)
    vappend = []
    victims.clear()
    # Ensures that special events play for bodyguard and harlot-visiting-victim so that kill can
    # be correctly attributed to wolves (for vengeful ghost lover), and that any gunner events
    # can play. Harlot visiting wolf doesn't play special events if they die via other means since
    # that assumes they die en route to the wolves (and thus don't shoot/give out gun/etc.)
    # TODO: this needs to be split off into bodyguard.py and harlot.py
    from src.roles import bodyguard, harlot
    for v in victims_set:
        if is_dying(var, v):
            victims.append(v)
        elif v in var.ROLES["bodyguard"] and v in bodyguard.GUARDED and bodyguard.GUARDED[v] in victims_set:
            vappend.append(v)
        elif harlot.VISITED.get(v) in victims_set:
            vappend.append(v)
        else:
            victims.append(v)
    prevlen = var.MAX_PLAYERS + 10
    while len(vappend) > 0:
        if len(vappend) == prevlen:
            # have a circular dependency, try to break it by appending the next value
            v = vappend[0]
            vappend.remove(v)
            victims.append(v)
            continue

        prevlen = len(vappend)
        for v in vappend[:]:
            if v in var.ROLES["bodyguard"] and bodyguard.GUARDED.get(v) not in vappend:
                vappend.remove(v)
                victims.append(v)
            elif harlot.VISITED.get(v) not in vappend:
                vappend.remove(v)
                victims.append(v)

    message = defaultdict(list)
    message["*"].append(messages["sunrise"].format(minimum, sec))

    dead = []
    vlist = victims[:]
    revt = Event("transition_day_resolve", {
        "message": message,
        "novictmsg": True,
        "dead": dead,
        "killers": killers,
        })
    # transition_day_resolve priorities:
    # 1: target not home
    # 2: protection
    # 6: riders on default logic
    # In general, an event listener < 6 should both stop propagation and prevent default
    # Priority 6 listeners add additional stuff to the default action and should not prevent default
    for victim in vlist:
        if not revt.dispatch(var, victim):
            continue
        if victim not in revt.data["dead"]: # not already dead via some other means
            for killer in list(killers[victim]):
                if killer == "@wolves":
                    attacker = None
                    role = "wolf"
                else:
                    attacker = killer
                    role = get_main_role(var, killer)
                protected = try_protection(var, victim, attacker, role, reason="night_death")
                if protected is not None:
                    revt.data["message"][victim].extend(protected)
                    killers[victim].remove(killer)
                    revt.data["novictmsg"] = False

            if not killers[victim]:
                continue

            to_send = "death_no_reveal"
            if var.ROLE_REVEAL in ("on", "team"):
                to_send = "death"
            revt.data["message"][victim].append(messages[to_send].format(victim, get_reveal_role(var, victim)))
            revt.data["dead"].append(victim)

    # Priorities:
    # 1 = harlot/succubus visiting victim (things that kill the role itself)
    # 2 = howl/novictmsg processing, alpha wolf bite/lycan turning (roleswaps)
    # 3 = harlot visiting wolf, bodyguard/GA guarding wolf (things that kill the role itself -- should move to pri 1)
    # 4 = gunner shooting wolf, retribution totem (things that kill the victim's killers)
    # 5 = wolves killing diseased, wolves stealing gun (all deaths must be finalized before pri 5)
    # Note that changing the "novictmsg" data item only makes sense for priority 2 events,
    # as after that point the message was already added (at priority 2.9).
    revt2 = Event("transition_day_resolve_end", {
        "message": message,
        "novictmsg": revt.data["novictmsg"],
        "howl": 0,
        "dead": dead,
        "killers": killers,
        })
    revt2.dispatch(var, victims)

    # flatten message, * goes first then everyone else
    to_send = message["*"]
    del message["*"]
    for msg in message.values():
        to_send.extend(msg)

    channels.Main.send(*to_send, sep="\n")

    # chilling howl message was played, give roles the opportunity to update !stats
    # to account for this
    event = Event("reconfigure_stats", {"new": []})
    for i in range(revt2.data["howl"]):
        newstats = set()
        for rs in var.ROLE_STATS:
            d = Counter(dict(rs))
            event.data["new"] = [d]
            event.dispatch(var, d, "howl")
            for v in event.data["new"]:
                if min(v.values()) >= 0:
                    newstats.add(frozenset(v.items()))
        var.ROLE_STATS = newstats

    killer_role = {}
    for deadperson in dead:
        if is_dying(var, deadperson):
            continue

        if killers.get(deadperson):
            killer = killers[deadperson][0]
            if killer == "@wolves":
                killer_role[deadperson] = "wolf"
            else:
                killer_role[deadperson] = get_main_role(var, killer)
        else:
            # no killers, so assume suicide
            killer_role[deadperson] = get_main_role(var, deadperson)

        add_dying(var, deadperson, killer_role[deadperson], "night_kill")

    kill_players(var, end_game=False) # temporary hack; end_game=False also prevents kill_players from attempting phase transitions

    event_end = Event("transition_day_end", {"begin_day": begin_day})
    event_end.dispatch(var)

    # make sure that we process ALL of the transition_day events before checking for game end
    if chk_win(): # game ending
        return

    event_end.data["begin_day"]()

@event_listener("transition_day_resolve_end", priority=2.9)
def on_transition_day_resolve_end(evt, var, victims):
    if evt.data["novictmsg"] and len(evt.data["dead"]) == 0:
        evt.data["message"]["*"].append(messages["no_victims"] + messages["no_victims_append"])
    for i in range(evt.data["howl"]):
        evt.data["message"]["*"].append(messages["new_wolf"])

def chk_nightdone():
    if var.PHASE != "night":
        return

    event = Event("chk_nightdone", {"acted": [], "nightroles": [], "transition_day": transition_day})
    event.dispatch(var)
    actedcount = len(event.data["acted"])

    # remove all instances of them if they are silenced (makes implementing the event easier)
    nightroles = [p for p in event.data["nightroles"] if not is_silent(var, p)]

    if var.PHASE == "night" and actedcount >= len(nightroles):
        for x, t in var.TIMERS.items():
            t[0].cancel()

        var.TIMERS = {}
        if var.PHASE == "night":  # Double check
            event.data["transition_day"]()

def stop_game(var, winner="", abort=False, additional_winners=None, log=True):
    if abort:
        channels.Main.send(messages["role_attribution_failed"])
    elif not var.ORIGINAL_ROLES: # game already ended
        return
    if var.DAY_START_TIME:
        now = datetime.now()
        td = now - var.DAY_START_TIME
        var.DAY_TIMEDELTA += td
    if var.NIGHT_START_TIME:
        now = datetime.now()
        td = now - var.NIGHT_START_TIME
        var.NIGHT_TIMEDELTA += td

    daymin, daysec = var.DAY_TIMEDELTA.seconds // 60, var.DAY_TIMEDELTA.seconds % 60
    nitemin, nitesec = var.NIGHT_TIMEDELTA.seconds // 60, var.NIGHT_TIMEDELTA.seconds % 60
    total = var.DAY_TIMEDELTA + var.NIGHT_TIMEDELTA
    tmin, tsec = total.seconds // 60, total.seconds % 60
    gameend_msg = messages["endgame_stats"].format(tmin, tsec, daymin, daysec, nitemin, nitesec)

    if not abort:
        channels.Main.send(gameend_msg)

        roles_msg = []

        # squirrel away a copy of our original roleset for stats recording, as the following code
        # modifies var.ORIGINAL_ROLES and var.ORIGINAL_MAIN_ROLES.
        rolecounts = {role: len(players) for role, players in var.ORIGINAL_ROLES.items()}

        # save some typing
        rolemap = var.ORIGINAL_ROLES
        mainroles = var.ORIGINAL_MAIN_ROLES
        orig_main = {} # if get_final_role changes mainroles, we want to stash original main role

        for player, role in mainroles.items():
            evt = Event("get_final_role", {"role": var.FINAL_ROLES.get(player, role)})
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
                evt.dispatch(var, player, role, is_mainrole=mainroles[player] == role)
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

        if winner != "" or log:
            if additional_winners is not None:
                winners.update(additional_winners)

            team_wins = set()
            for player, role in mainroles.items():
                if player in var.DCED_LOSERS or winner == "":
                    continue
                won = False
                # determine default team win for wolves/village
                if role in Wolfteam or (var.HIDDEN_ROLE == "cultist" and role in Hidden):
                    if winner == "wolves":
                        won = True
                elif role in Village or (var.HIDDEN_ROLE == "villager" and role in Hidden):
                    if winner == "villagers":
                        won = True
                # Let events modify this as necessary.
                # Neutral roles will need to listen in on this to determine team wins
                event = Event("team_win", {"team_win": won})
                event.dispatch(var, player, role, allroles[player], winner)
                if event.data["team_win"]:
                    team_wins.add(player)

            # Once *all* team wins are settled, we can determine individual wins and get the final list of winners
            team_wins = frozenset(team_wins)
            for player, role in mainroles.items():
                entry = {"version": 3,
                         "account": player.account,
                         "main_role": role,
                         "all_roles": list(allroles[player]),
                         "special": [],
                         "team_win": player in team_wins,
                         "individual_win": False,
                         "dced": player in var.DCED_LOSERS
                         }
                # player.account could be None if they disconnected during the game. Use original tracked account name
                if entry["account"] is None and player in var.ORIGINAL_ACCS:
                    entry["account"] = var.ORIGINAL_ACCS[player]

                survived = player in get_players()
                if not entry["dced"] and winner != "":
                    # by default, get an individual win if the team won and they survived
                    won = entry["team_win"] and survived

                    # let events modify this default and also add special tags/pseudo-roles to the stats
                    event = Event("player_win", {"individual_win": won, "special": []},
                                  team_wins=team_wins)
                    event.dispatch(var, player, role, allroles[player], winner, entry["team_win"], survived)
                    won = event.data["individual_win"]
                    # ensure that it is a) a list, and b) a copy (so it can't be mutated out from under us later)
                    entry["special"] = list(event.data["special"])

                    # special-case everyone for after the event
                    if winner == "everyone":
                        won = True

                    entry["individual_win"] = won

                if entry["team_win"] or entry["individual_win"]:
                    winners.add(player)

                if not player.is_fake:
                    # don't record fakes to the database
                    player_list.append(entry)

        if log:
            game_options = {"role reveal": var.ROLE_REVEAL,
                            "stats": var.STATS_TYPE,
                            "abstain": "on" if var.ABSTAIN_ENABLED and not var.LIMIT_ABSTAIN else "restricted" if var.ABSTAIN_ENABLED else "off",
                            "roles": {}}
            for role, pl in var.ORIGINAL_ROLES.items():
                if len(pl) > 0:
                    game_options["roles"][role] = len(pl)

            db.add_game(var.CURRENT_GAMEMODE.name,
                        len(get_players(var)) + len(var.DEAD),
                        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(var.GAME_ID)),
                        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                        winner,
                        player_list,
                        game_options)

            # spit out the list of winners
            if winners:
                winners = sorted(winners, key=lambda u: u.nick)
                channels.Main.send(messages["winners"].format(winners))
            else:
                channels.Main.send(messages["no_winners"])

    # Message players in deadchat letting them know that the game has ended
    if var.DEADCHAT_PLAYERS:
        for user in var.DEADCHAT_PLAYERS:
            user.queue_message(messages["endgame_deadchat"].format(channels.Main))

        user.send_messages()

    # Add warnings for people that idled out night
    if var.IDLE_PENALTY:
        for player in var.NIGHT_IDLED:
            if player.is_fake:
                continue
            add_warning(player, var.NIGHT_IDLE_PENALTY, users.Bot, messages["night_idle_warning"], expires=var.NIGHT_IDLE_EXPIRY)

    reset_modes_timers(var)
    reset()
    expire_tempbans()

    # This must be after reset()
    if var.AFTER_FLASTGAME is not None:
        var.AFTER_FLASTGAME()
        var.AFTER_FLASTGAME = None
    if var.ADMIN_TO_PING is not None:  # It was an flastgame
        channels.Main.send(messages["fstop_ping"].format([var.ADMIN_TO_PING]))
        var.ADMIN_TO_PING = None

def chk_win(*, end_game=True, winner=None):
    """ Returns True if someone won """
    lpl = len(get_players(var))

    if var.PHASE == "join":
        if lpl == 0:
            reset_modes_timers(var)

            reset()

            # This must be after reset()
            if var.AFTER_FLASTGAME is not None:
                var.AFTER_FLASTGAME()
                var.AFTER_FLASTGAME = None
            if var.ADMIN_TO_PING is not None:  # It was an flastgame
                channels.Main.send(messages["fstop_ping"].format([var.ADMIN_TO_PING]))
                var.ADMIN_TO_PING = None

            return True
        return False
    if var.PHASE not in var.GAME_PHASES:
        return False #some other thread already ended game probably

    return chk_win_conditions(var.ROLES, var.MAIN_ROLES, end_game, winner)

def chk_win_conditions(rolemap, mainroles, end_game=True, winner=None):
    """Internal handler for the chk_win function."""
    with locks.reaper:
        if var.PHASE == "day":
            pl = set(get_players(var)) - get_absent(var)
            lpl = len(pl)
        else:
            pl = set(get_players(var, mainroles=mainroles))
            lpl = len(pl)

        wolves = set(get_players(var, Wolf_Objective, mainroles=mainroles))
        lwolves = len(wolves & pl)
        lrealwolves = len(get_players(var, Village_Objective, mainroles=mainroles))

        message = ""
        if lpl < 1:
            message = messages["no_win"]
            # still want people like jesters, dullahans, etc. to get wins if they fulfilled their win conds
            winner = "no_team_wins"

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
        if not event.dispatch(var, rolemap, mainroles, lpl, lwolves, lrealwolves):
            return chk_win_conditions(rolemap, mainroles, end_game, winner)
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
    if var.PHASE != "join":
        stop_game(var, log=False)
    else:
        pl = [p for p in get_players(var) if not p.is_fake]
        reset_modes_timers(var)
        reset()
        if pl:
            wrapper.send(messages["fstop_ping"].format(pl))

def reset_settings(): # burn the cities. salt the earth so that nothing may ever grow again
    var.CURRENT_GAMEMODE.teardown()
    var.CURRENT_GAMEMODE = var.GAME_MODES["default"][0]()
    for attr in list(var.ORIGINAL_SETTINGS.keys()):
        setattr(var, attr, var.ORIGINAL_SETTINGS[attr])
    var.ORIGINAL_SETTINGS.clear()

def reset_modes_timers(var):
    # Reset game timers
    with locks.join_timer: # make sure it isn't being used by the ping join handler
        for x, timr in var.TIMERS.items():
            timr[0].cancel()
        var.TIMERS = {}

    # Reset modes
    cmodes = []
    for plr in get_players(var):
        if not plr.is_fake:
            cmodes.append(("-v", plr.nick))
    for user, modes in channels.Main.old_modes.items():
        for mode in modes:
            cmodes.append(("+" + mode, user))
    channels.Main.old_modes.clear()
    if var.QUIET_DEAD_PLAYERS:
        for deadguy in var.DEAD:
            if not deadguy.is_fake:
                cmodes.append(("-{0}".format(var.QUIET_MODE), var.QUIET_PREFIX + deadguy.nick + "!*@*"))
    channels.Main.mode("-m", *cmodes)

def reset():
    var.PHASE = "none" # "join", "day", or "night"
    var.GAME_ID = 0
    var.ALL_PLAYERS.clear()
    var.RESTART_TRIES = 0
    var.DEAD.clear()
    var.ORIGINAL_ACCS.clear()
    var.PINGED_ALREADY = set()
    var.PINGED_ALREADY_ACCS = set()
    var.FGAMED = False
    var.GAMEMODE_VOTES.clear()

    reset_settings()

    var.LAST_GOAT.clear()
    var.LAST_SAID_TIME.clear()
    var.DISCONNECTED.clear()
    var.DCED_LOSERS.clear()
    var.SPECTATING_WOLFCHAT.clear()
    var.SPECTATING_DEADCHAT.clear()

    var.IDLE_WARNED.clear()
    var.IDLE_WARNED_PM.clear()
    var.NIGHT_IDLED.clear()
    var.NIGHT_IDLE_EXEMPT.clear()

    var.ROLES.clear()
    var.ORIGINAL_ROLES.clear()
    var.FINAL_ROLES.clear()
    var.ROLES["person"] = UserSet()
    var.MAIN_ROLES.clear()
    var.ORIGINAL_MAIN_ROLES.clear()
    var.FORCE_ROLES.clear()

    evt = Event("reset", {})
    evt.dispatch(var)
