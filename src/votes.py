from collections import Counter
from datetime import datetime, timedelta
import copy
import math

from src.containers import UserDict, UserList, UserSet
from src.decorators import command, event_listener
from src.functions import get_players, get_target, get_reveal_role
from src.messages import messages
from src.status import try_absent, get_absent
from src import channels

VOTES = UserDict() # type: UserDict[users.User, UserList[users.User]]
ABSTAINS = UserSet() # type: UserSet[users.User]
ABSTAINED = False
LAST_VOTES = None

@command("nolynch", "nl", "novote", "nv", "abstain", "abs", playing=True, phases=("day",))
def no_lynch(var, wrapper, message):
    """Allow you to abstain from voting for the day."""
    if not var.ABSTAIN_ENABLED:
        wrapper.pm(messages["command_disabled"])
        return
    elif var.LIMIT_ABSTAIN and ABSTAINED:
        wrapper.pm(messages["exhausted_abstain"])
        return
    elif var.LIMIT_ABSTAIN and var.FIRST_DAY:
        wrapper.pm(messages["no_abstain_day_one"])
        return
    elif try_absent(var, wrapper.source):
        return
    for voter in list(VOTES):
        if wrapper.source in VOTES[voter]:
            VOTES[voter].remove(wrapper.source)
            if not VOTES[voter]:
                del VOTES[voter]
    ABSTAINS.add(wrapper.source)
    channels.Main.send(messages["player_abstain"].format(wrapper.source))

    chk_decision(var)

@command("lynch", playing=True, pm=True, phases=("day",))
def lynch(var, wrapper, message):
    """Use this to vote for a candidate to be lynched."""
    if not message:
        show_votes.func(var, wrapper, message)
        return
    if wrapper.private:
        return
    msg = re.split(" +", message)[0].strip()

    can_vote_bot = False
    if var.VILLAGERGAME_CHANCE:
        # Handle villagergame here - TODO: Maybe not do that?
        vilgame = var.GAME_MODES.get("villagergame")
        if vilgame is not None:
            if var.CURRENT_GAMEMODE.name in ("default", "villagergame") and vilgame[1] <= len(get_players()) <= vilgame[2]:
                can_vote_bot = True

    voted = get_target(var, wrapper, msg, allow_self=var.SELF_LYNCH_ALLOWED, allow_bot=can_vote_bot, not_self_message="no_self_lynch")
    if not voted:
        return

    if try_absent(var, wrapper.source):
        return

    ABSTAINS.discard(wrapper.source)

    for votee in list(VOTES):  # remove previous vote
        if votee is voted and wrapper.source in VOTES[votee]:
            break
        if wrapper.source in VOTES[votee]:
            VOTES[votee].remove(wrapper.source)
            if not VOTES.get(votee) and votee is not voted:
                del VOTES[votee]
            break

    if voted not in VOTES:
        VOTES[voted] = UserList()
    if wrapper.source not in VOTES[voted]:
        VOTES[voted].append(wrapper.source)
        channels.Main.send(messages["player_vote"].format(wrapper.source, voted))

    global LAST_VOTES
    LAST_VOTES = None # reset

    chk_decision(var)

@command("retract", "r", phases=("day", "join"))
def retract(var, wrapper, message):
    """Takes back your vote during the day (for whom to lynch)."""
    if wrapper.source not in get_players() or wrapper.source in var.DISCONNECTED or var.PHASE != "day":
        return

    global LAST_VOTES

    if wrapper.source in ABSTAINS:
        ABSTAINS.remove(wrapper.source)
        wrapper.send(messages["retracted_vote"].format(wrapper.source))
        LAST_VOTES = None # reset
        return

    for votee in list(VOTES):
        if wrapper.source in VOTES[votee]:
            VOTES[votee].remove(wrapper.source)
            if not VOTES[votee]:
                del VOTES[votee]
            wrapper.send(messages["retracted_vote"].format(wrapper.source))
            LAST_VOTES = None # reset
            break
    else:
        wrapper.pm(messages["pending_vote"])

@command("votes", pm=True, phases=("join", "day", "night"))
def show_votes(var, wrapper, message):
    """Show the current votes."""
    pl = get_players()
    if var.PHASE == "join":
        # get gamemode votes in a dict of {mode: number of votes}
        gm_votes = list(Counter(var.GAMEMODE_VOTES.values()).items())
        gm_votes.sort(key=lambda x: x[1], reverse=True) # sort from highest to lowest

        votelist = []
        majority = False
        for gamemode, num_votes in gm_votes:
            # We bold the game mode if:
            # - The number of players is within the bounds of the game mode
            # - This game mode has a majority of votes
            # - It can be randomly picked
            # - No other game mode has a majority
            if (var.GAME_MODES[gamemode][1] <= len(pl) <= var.GAME_MODES[gamemode][2] and
                (not majority or num_votes >= len(pl) / 2) and (var.GAME_MODES[gamemode][3] > 0 or num_votes >= len(pl) / 2)):
                votelist.append("\u0002{0}\u0002: {1}".format(gamemode, num_votes))
                if num_votes >= len(pl) / 2:
                    majority = True
            else:
                votelist.append("{0}: {1}".format(gamemode, num_votes))

        msg = ", ".join(votelist)
        if len(pl) >= var.MIN_PLAYERS:
            msg += messages["majority_votes"].format("; " if votelist else "", math.ceil(len(pl) / 2))

        with var.WARNING_LOCK:
            if var.START_VOTES:
                msg += messages["start_votes"].format(len(var.START_VOTES), ", ".join(p.nick for p in var.START_VOTES))

        wrapper.send(msg)
        return

    if var.PHASE == "night":
        wrapper.pm(messages["voting_daytime_only"])
        return

    global LAST_VOTES

    if (wrapper.public and LAST_VOTES and var.VOTES_RATE_LIMIT and
            LAST_VOTES + timedelta(seconds=var.VOTES_RATE_LIMIT) > datetime.now()):
        wrapper.pm(messages["command_ratelimited"])
        return

    if wrapper.public and wrapper.source in pl:
        LAST_VOTES = datetime.now()

    if not VOTES:
        msg = messages["no_votes"]
        if wrapper.source in pl:
            LAST_VOTES = None # reset

    else:
        votelist = []
        for votee, voters in VOTES.items():
            votelist.append("{0}: {1} ({2})".format(votee, len(voters), ", ".join(p.nick for p in voters)))
        msg = ", ".join(votelist)

    wrapper.reply(msg, prefix_nick=True)

    avail = len(pl) - len(get_absent(var))
    votesneeded = avail // 2 + 1
    abstaining = len(ABSTAINS)
    if abstaining == 1: # *i18n* hardcoded English
        plural = " has"
    else:
        plural = "s have"

    to_send = messages["vote_stats"].format(len(pl), votesneeded, avail)
    if var.ABSTAIN_ENABLED:
        to_send += messages["vote_stats_abstain"].format(abstaining, plural)

    wrapper.reply(to_send, prefix_nick=True)

@command("vote", "v", pm=True, phases=("join", "day"))
def vote(var, wrapper, message):
    """Vote for a game mode if no game is running, or for a player to be lynched."""
    if message:
        if var.PHASE == "join" and wrapper.public:
            from src.wolfgame import game
            return game.caller(wrapper.client, wrapper.source.nick, wrapper.target.name, message)
        return lynch.caller(wrapper.client, wrapper.source.nick, wrapper.target.name, message)
    return show_votes.caller(wrapper.client, wrapper.source.nick, wrapper.target.name, message)

# Specify timeout=True to force a lynch even if there is no majority
def chk_decision(var, *, timeout=False):
    with var.GRAVEYARD_LOCK:
        if var.PHASE != "day":
            return
        do_night_transition = timeout

        pl = set(get_players()) - get_absent(var)









    with var.GRAVEYARD_LOCK:
        if var.PHASE != "day":
            return
        do_night_transition = timeout
        pl = set(get_players()) - get_absent(var)
        not_lynching = set(var.NO_LYNCH)

        avail = len(pl)
        votesneeded = avail // 2 + 1

        with copy.deepcopy(var.VOTES) as votelist:
            event = Event("chk_decision", {
                "not_lynching": not_lynching,
                "votelist": votelist,
                "numvotes": {}, # filled as part of a priority 1 event
                "weights": {}, # filled as part of a priority 1 event
                "transition_night": transition_night,
                "force": timeout, # can be a bool or an iterable of users
                "lynch_multiple": False # whether or not we can lynch more than 1 person
                }, voters=pl, timeout=timeout)
            if not event.dispatch(var):
                return

            force = set()
            numvotes = event.data["numvotes"]
            if event.data["force"] is True:
                maxfound = 0
                for votee, voters in votelist.items():
                    if numvotes[votee] > maxfound:
                        maxfound = numvotes[votee]
                        force = set(votee)
                    elif numvotes[votee] == maxfound[0]:
                        force.add(votee)
            elif event.data["force"] is not False:
                force = event.data["force"]

            if not event.data["lynch_multiple"] and len(force) > 1:
                force = set()

            if timeout:
                if force:
                    channels.Main.send(messages["sunset_lynch"])
                else:
                    channels.Main.send(messages["sunset"])

            # we only need 50%+ to not lynch, instead of an actual majority, because a tie would time out day anyway
            # don't check for ABSTAIN_ENABLED here since we may have a case where the majority of people have pacifism totems or something
            if not force and len(not_lynching) >= math.ceil(avail / 2):
                abs_evt = Event("chk_decision_abstain", {}, votelist=votelist, numvotes=numvotes)
                abs_evt.dispatch(var, not_lynching)
                channels.Main.send(messages["village_abstain"])
                global ABSTAINED
                ABSTAINED = True
                do_night_transition = True
            for votee, voters in votelist.items():
                if numvotes[votee] >= votesneeded or votee in force:
                    # priorities:
                    # 1 = displaying impatience totem messages
                    # 3 = mayor/revealing totem
                    # 4 = fool
                    # 5 = desperation totem, other things that happen on generic lynch
                    vote_evt = Event("chk_decision_lynch", {"votee": votee},
                        original_votee=votee,
                        force=(votee in force),
                        votelist=votelist,
                        not_lynching=not_lynching)
                    if vote_evt.dispatch(var, voters):
                        votee = vote_evt.data["votee"]

                        if var.ROLE_REVEAL in ("on", "team"):
                            rrole = get_reveal_role(votee)
                            an = "n" if rrole.startswith(("a", "e", "i", "o", "u")) else ""
                            lmsg = random.choice(messages["lynch_reveal"]).format(votee, an, rrole)
                        else:
                            lmsg = random.choice(messages["lynch_no_reveal"]).format(votee)
                        channels.Main.send(lmsg)
                        add_dying(var, votee, "villager", "lynch")
                        do_night_transition = True
            if do_night_transition:
                kill_players(var, end_game=False) # temporary hack; end_game=True calls chk_decision and we don't want that
                if chk_win():
                    return
                event.data["transition_night"]()

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    if var.PHASE == "day":
        if player in VOTES:
            del VOTES[player] # Delete other people's votes on the player
        for k in list(VOTES):
            if player in VOTES[k]:
                VOTES[k].remove(player)
                if not VOTES[k]:  # no more votes on that person
                    del VOTES[k]
                break # can only vote once

        ABSTAINS.discard(player)

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    ABSTAINS.clear()
    VOTES.clear()

@event_listener("reset")
def on_reset(evt, var):
    global ABSTAINED
    ABSTAINED = False
    ABSTAINS.clear()
    VOTES.clear()
